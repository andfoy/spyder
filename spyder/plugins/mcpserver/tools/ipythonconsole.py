# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""MCP tools for the IPython console plugin."""

# Standard library imports
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Third-party imports
from qtpy.QtCore import QObject, QTimer
from spyder_kernels.utils.nsview import REMOTE_SETTINGS

# Local imports
from spyder.plugins.mcpserver.api import (
    MCPTool,
    ToolCall,
    ToolError,
    image_content,
    text_content,
)
from spyder.plugins.mcpserver.tools.utils import (
    strip_ansi,
    svg_to_png,
    truncate,
)

if TYPE_CHECKING:
    from spyder.plugins.ipythonconsole.plugin import IPythonConsole
    from spyder.plugins.ipythonconsole.widgets import ShellWidget

logger = logging.getLogger(__name__)

# Default time to wait for code to finish running.
DEFAULT_EXECUTE_TIMEOUT = 60

# Maximum number of images returned by a single execution.
MAX_IMAGES = 8

# Maximum length of a variable's value preview.
MAX_VIEW_CHARS = 300

CONSOLE_ID_SCHEMA = {
    "type": "string",
    "description": (
        "Id of the console to use, as returned by list_consoles. Defaults "
        "to the console currently selected in Spyder."
    ),
}


# ---- Helpers
# -----------------------------------------------------------------------------
def get_console_id(client) -> str:
    return f"{client.id_['int_id']}/{client.id_['str_id']}"


def get_shellwidget(
    ipyconsole: IPythonConsole, console_id: str | None
) -> ShellWidget:
    """Get the shellwidget for ``console_id``, or the current one."""
    if console_id is None:
        client = ipyconsole.get_current_client()
        if client is None:
            raise ToolError("There are no IPython consoles open.")
    else:
        for client in ipyconsole.get_clients():
            if get_console_id(client) == console_id:
                break
        else:
            raise ToolError(
                f"No console with id {console_id!r}. Use list_consoles to "
                f"get the available ids."
            )

    shellwidget = client.shellwidget
    if not shellwidget.spyder_kernel_ready:
        raise ToolError("The console's kernel is not ready yet.")
    return shellwidget


def check_idle(shellwidget: ShellWidget) -> None:
    """Raise an error if the console can't run code right now."""
    if shellwidget.is_debugging():
        raise ToolError(
            "The console is in debugging mode. Wait for the user to finish "
            "debugging."
        )
    if shellwidget._executing:
        raise ToolError(
            "The console is busy running code. Wait for it to finish or use "
            "interrupt_console."
        )


# ---- Code execution
# -----------------------------------------------------------------------------
class ExecutionCollector(QObject):
    """
    Run code in a console and collect its outputs from the kernel messages.

    The code is executed through the console widget, so the user sees it
    and its output as if they had typed it.
    """

    # Keep a reference to running collectors so they're not garbage collected
    _running: set[ExecutionCollector] = set()

    def __init__(
        self, shellwidget: ShellWidget, call: ToolCall, timeout: float
    ) -> None:
        super().__init__(shellwidget)
        self.shellwidget = shellwidget
        self.call = call
        self.msg_id = None
        self.text: list[str] = []
        self.images: list[dict] = []
        self.is_error = False
        self.notes: list[str] = []

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(int(timeout * 1000))
        self._timer.timeout.connect(self._on_timeout)

    def run(self, code: str) -> None:
        kernel_client = self.shellwidget.kernel_client
        kernel_client.iopub_channel.message_received.connect(self._on_iopub)
        kernel_client.stdin_channel.message_received.connect(self._on_stdin)

        # The msg_id of the execute request is only stored by the widget, so
        # look for the new one after executing.
        requests = self.shellwidget._request_info["execute"]
        before = set(requests)
        self.shellwidget.execute(code)
        new = set(requests) - before

        if len(new) != 1:
            self._disconnect()
            self.call.error("The code could not be sent to the kernel.")
            return

        self.msg_id = new.pop()
        self._running.add(self)
        self._timer.start()

    # ---- Message handling
    def _on_iopub(self, msg: dict) -> None:
        if msg.get("parent_header", {}).get("msg_id") != self.msg_id:
            return

        msg_type = msg["header"]["msg_type"]
        content = msg["content"]

        if msg_type == "stream":
            self.text.append(content["text"])
        elif msg_type == "execute_result":
            data = content.get("data", {})
            if not self._add_image(data) and "text/plain" in data:
                self.text.append(
                    f"Out[{content.get('execution_count')}]: "
                    f"{data['text/plain']}\n"
                )
        elif msg_type == "display_data":
            data = content.get("data", {})
            if not self._add_image(data) and "text/plain" in data:
                self.text.append(data["text/plain"] + "\n")
        elif msg_type == "error":
            self.is_error = True
            self.text.append(strip_ansi("\n".join(content["traceback"])))
        elif (
            msg_type == "status"
            and content.get("execution_state") == "idle"
        ):
            self._finish()

    def _on_stdin(self, msg: dict) -> None:
        if msg.get("parent_header", {}).get("msg_id") != self.msg_id:
            return
        if msg["header"]["msg_type"] == "input_request":
            self.notes.append(
                "The code is waiting for user input in the console "
                f"(prompt: {msg['content'].get('prompt', '')!r}). Ask the "
                "user to answer it or use interrupt_console."
            )
            self._finish()

    def _add_image(self, data: dict) -> bool:
        if len(self.images) >= MAX_IMAGES:
            return False

        if "image/png" in data:
            self.images.append(image_content(data["image/png"], "image/png"))
        elif "image/jpeg" in data:
            self.images.append(image_content(data["image/jpeg"], "image/jpeg"))
        elif "image/svg+xml" in data:
            png = svg_to_png(data["image/svg+xml"])
            self.images.append(image_content(png))
        else:
            return False

        return True

    def _on_timeout(self) -> None:
        self.notes.append(
            f"The code is still running after "
            f"{self._timer.interval() // 1000} seconds. Its remaining output "
            f"will only be shown in the console. Use interrupt_console to "
            f"stop it."
        )
        self._finish()

    # ---- Finishing
    def _finish(self) -> None:
        self._timer.stop()
        self._disconnect()
        self._running.discard(self)

        output = truncate("".join(self.text))
        content = [text_content(output if output else "(no output)")]
        content.extend(self.images)
        if self.notes:
            content.append(text_content("\n".join(self.notes)))

        # Errors raised by the user code are reported as results, so the
        # agent can see the traceback and fix its code.
        if self.is_error:
            content.insert(0, text_content("The code raised an exception:"))
        self.call.reply(content)
        self.deleteLater()

    def _disconnect(self) -> None:
        kernel_client = self.shellwidget.kernel_client
        if kernel_client is None:
            return
        for channel, slot in [
            (kernel_client.iopub_channel, self._on_iopub),
            (kernel_client.stdin_channel, self._on_stdin),
        ]:
            try:
                channel.message_received.disconnect(slot)
            except (TypeError, RuntimeError):
                pass


# ---- Tools
# -----------------------------------------------------------------------------
def get_tools(ipyconsole: IPythonConsole) -> list[MCPTool]:

    def list_consoles(call: ToolCall):
        current = ipyconsole.get_current_client()
        consoles = []
        for client in ipyconsole.get_clients():
            shellwidget = client.shellwidget
            if not shellwidget.spyder_kernel_ready:
                state = "starting"
            elif shellwidget.is_debugging():
                state = "debugging"
            elif shellwidget._executing:
                state = "busy"
            else:
                state = "idle"

            consoles.append(
                f"- id: {get_console_id(client)} | name: {client.get_name()}"
                f" | state: {state}"
                + (" | current" if client is current else "")
            )

        if not consoles:
            return "There are no IPython consoles open."
        return "IPython consoles:\n" + "\n".join(consoles)

    def execute_code(call: ToolCall):
        shellwidget = get_shellwidget(
            ipyconsole, call.arguments.get("console_id")
        )
        check_idle(shellwidget)

        code = call.arguments["code"]
        timeout = call.arguments.get("timeout", DEFAULT_EXECUTE_TIMEOUT)
        ExecutionCollector(shellwidget, call, timeout).run(code)

    def interrupt_console(call: ToolCall):
        shellwidget = get_shellwidget(
            ipyconsole, call.arguments.get("console_id")
        )
        shellwidget.interrupt_kernel()
        return "Interrupt sent to the kernel."

    def list_variables(call: ToolCall):
        shellwidget = get_shellwidget(
            ipyconsole, call.arguments.get("console_id")
        )
        check_idle(shellwidget)

        # Fail if the kernel doesn't answer, instead of waiting forever
        timer = QTimer(shellwidget)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda: call.error("The kernel didn't answer in time.")
        )
        timer.start(15000)

        def on_namespace_view(view):
            timer.stop()
            timer.deleteLater()
            if call.finished:
                return
            if not view:
                call.reply("There are no variables in the namespace.")
                return

            lines = []
            for name, props in view.items():
                value = props.get("view", "")
                if len(value) > MAX_VIEW_CHARS:
                    value = value[:MAX_VIEW_CHARS] + "..."
                lines.append(
                    f"- {name} | type: {props.get('type')} | "
                    f"size: {props.get('size')} | value: {value}"
                )
            call.reply("\n".join(lines))

        # The kernel only computes the namespace view after the Variable
        # Explorer sends its settings, so send them if it hasn't (e.g. when
        # it's disabled).
        if "namespace_view_settings" not in shellwidget._kernel_configuration:
            shellwidget.set_kernel_configuration(
                "namespace_view_settings",
                {
                    name: shellwidget.get_conf(
                        name, section="variable_explorer"
                    )
                    for name in REMOTE_SETTINGS
                },
            )

        shellwidget.call_kernel(
            callback=on_namespace_view
        ).get_namespace_view()

    return [
        MCPTool(
            name="list_consoles",
            title="List IPython consoles",
            description=(
                "List the IPython consoles open in Spyder with their ids and "
                "state (idle, busy, debugging or starting)."
            ),
            handler=list_consoles,
            read_only=True,
        ),
        MCPTool(
            name="execute_code",
            title="Run code in an IPython console",
            description=(
                "Run Python code in one of Spyder's IPython consoles and "
                "return its output (stdout, stderr, results, tracebacks and "
                "figures as images). The code runs in the user's live "
                "kernel, so variables persist between calls and the user "
                "sees the code and its output in the console. IPython magics "
                "are supported. Figures also appear in Spyder's Plots pane."
            ),
            handler=execute_code,
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to run.",
                    },
                    "console_id": CONSOLE_ID_SCHEMA,
                    "timeout": {
                        "type": "number",
                        "description": (
                            "Seconds to wait for the code to finish before "
                            "returning the output collected so far. The code "
                            f"keeps running. Defaults to "
                            f"{DEFAULT_EXECUTE_TIMEOUT}."
                        ),
                    },
                },
                "required": ["code"],
            },
        ),
        MCPTool(
            name="interrupt_console",
            title="Interrupt an IPython console",
            description=(
                "Interrupt the code running in an IPython console, like "
                "pressing Ctrl+C."
            ),
            handler=interrupt_console,
            input_schema={
                "type": "object",
                "properties": {"console_id": CONSOLE_ID_SCHEMA},
            },
        ),
        MCPTool(
            name="list_variables",
            title="List console variables",
            description=(
                "List the variables defined in an IPython console, with "
                "their type, size and a short preview of their value, as "
                "shown in Spyder's Variable Explorer. Use execute_code to "
                "inspect a variable in more detail."
            ),
            handler=list_variables,
            input_schema={
                "type": "object",
                "properties": {"console_id": CONSOLE_ID_SCHEMA},
            },
            read_only=True,
        ),
    ]
