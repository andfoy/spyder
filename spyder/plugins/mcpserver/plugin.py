# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
MCP server plugin.

Exposes tools contributed by Spyder plugins to AI agents (e.g. Claude Code)
through the Model Context Protocol. The HTTP server runs in a subprocess,
which forwards tool calls to this plugin.
"""

# Standard library imports
import logging
import secrets

# Third-party imports
from qtpy.QtWidgets import QApplication

# Local imports
from spyder.api.plugins import Plugins, SpyderPluginV2
from spyder.api.plugin_registration.decorators import (
    on_plugin_available,
    on_plugin_teardown,
)
from spyder.api.translations import _
from spyder.plugins.mainmenu.api import ApplicationMenus, ToolsMenuSections
from spyder.plugins.mcpserver.api import MCPTool
from spyder.plugins.mcpserver.client import MCPServerClient
from spyder.plugins.mcpserver.container import (
    MCPServerActions,
    MCPServerContainer,
)
from spyder.utils.misc import select_port

logger = logging.getLogger(__name__)


class MCPServer(SpyderPluginV2):
    """MCP server plugin."""

    NAME = "mcp_server"
    OPTIONAL = [
        Plugins.Editor,
        Plugins.IPythonConsole,
        Plugins.MainMenu,
        Plugins.Plots,
    ]
    CONTAINER_CLASS = MCPServerContainer
    CONF_SECTION = NAME
    CONF_FILE = False

    # ---- SpyderPluginV2 API
    # -------------------------------------------------------------------------
    @staticmethod
    def get_name():
        return _("MCP server")

    @staticmethod
    def get_description():
        return _(
            "Let AI agents interact with Spyder through the Model Context "
            "Protocol."
        )

    @classmethod
    def get_icon(cls):
        return cls.create_icon("python")

    def on_initialize(self):
        self._tools: dict[str, MCPTool] = {}
        self._tools_by_plugin: dict[str, list[str]] = {}

        self._client = MCPServerClient(self, self._tools)
        self._client.sig_server_ready.connect(self._on_server_ready)
        self._client.sig_server_stopped.connect(self._on_server_stopped)

        container = self.get_container()
        container.sig_enabled_changed.connect(self._on_enabled_changed)
        container.sig_copy_command_requested.connect(self.copy_command)

    def on_mainwindow_visible(self):
        if self.get_conf("enabled"):
            self.start_server()

    def on_close(self, cancelable=False):
        self.stop_server()

    @on_plugin_available(plugin=Plugins.MainMenu)
    def on_main_menu_available(self):
        main_menu = self.get_plugin(Plugins.MainMenu)
        container = self.get_container()
        for action in [
            container.toggle_server_action,
            container.copy_command_action,
        ]:
            main_menu.add_item_to_application_menu(
                action,
                menu_id=ApplicationMenus.Tools,
                section=ToolsMenuSections.Managers,
                before_section=ToolsMenuSections.Preferences,
            )

    @on_plugin_teardown(plugin=Plugins.MainMenu)
    def on_main_menu_teardown(self):
        main_menu = self.get_plugin(Plugins.MainMenu)
        for action_id in [
            MCPServerActions.ToggleServer,
            MCPServerActions.CopyCommand,
        ]:
            main_menu.remove_item_from_application_menu(
                action_id, menu_id=ApplicationMenus.Tools
            )

    @on_plugin_available(plugin=Plugins.IPythonConsole)
    def on_ipython_console_available(self):
        from spyder.plugins.mcpserver.tools import ipythonconsole

        ipyconsole = self.get_plugin(Plugins.IPythonConsole)
        self._register_tools(
            Plugins.IPythonConsole, ipythonconsole.get_tools(ipyconsole)
        )
        self._register_plots_tools()

    @on_plugin_teardown(plugin=Plugins.IPythonConsole)
    def on_ipython_console_teardown(self):
        self._unregister_tools(Plugins.IPythonConsole)
        self._unregister_tools(Plugins.Plots)

    @on_plugin_available(plugin=Plugins.Plots)
    def on_plots_available(self):
        self._register_plots_tools()

    @on_plugin_teardown(plugin=Plugins.Plots)
    def on_plots_teardown(self):
        self._unregister_tools(Plugins.Plots)

    @on_plugin_available(plugin=Plugins.Editor)
    def on_editor_available(self):
        from spyder.plugins.mcpserver.tools import editor

        self._register_tools(
            Plugins.Editor, editor.get_tools(self.get_plugin(Plugins.Editor))
        )

    @on_plugin_teardown(plugin=Plugins.Editor)
    def on_editor_teardown(self):
        self._unregister_tools(Plugins.Editor)

    # ---- Public API
    # -------------------------------------------------------------------------
    def register_tool(self, tool: MCPTool) -> None:
        """
        Make ``tool`` available to AI agents.

        Parameters
        ----------
        tool: MCPTool
            Tool to register. Its name must be unique.
        """
        if tool.name in self._tools:
            raise ValueError(f"MCP tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> None:
        """Remove the tool called ``name``."""
        self._tools.pop(name, None)

    def get_tools(self) -> list[MCPTool]:
        """Return the registered tools."""
        return list(self._tools.values())

    def start_server(self) -> None:
        """Start the MCP server subprocess."""
        token = self.get_conf("token")
        if not token:
            token = secrets.token_urlsafe(32)
            self.set_conf("token", token)

        port = self.get_conf("port")
        free_port = select_port(default_port=port)
        if free_port != port:
            logger.warning(
                "Port %s is in use, starting the MCP server on port %s. "
                "Agents configured with the old port need to be updated.",
                port,
                free_port,
            )

        self._client.start(self.get_conf("host"), free_port, token)

    def stop_server(self) -> None:
        """Stop the MCP server subprocess."""
        self._client.stop()

    def get_url(self) -> str | None:
        """Return the URL of the MCP endpoint if the server is running."""
        return self._client.url

    def get_command(self) -> str | None:
        """Return the Claude Code command to add Spyder as an MCP server."""
        url = self.get_url()
        if url is None:
            return None
        return (
            f"claude mcp add --transport http spyder {url} "
            f"--header \"Authorization: Bearer {self.get_conf('token')}\""
        )

    def copy_command(self) -> None:
        """Copy the command to add Spyder to Claude Code to the clipboard."""
        command = self.get_command()
        if command is not None:
            QApplication.clipboard().setText(command)

    # ---- Private API
    # -------------------------------------------------------------------------
    def _register_tools(self, plugin_name: str, tools: list[MCPTool]) -> None:
        self._tools_by_plugin[plugin_name] = [tool.name for tool in tools]
        for tool in tools:
            self.register_tool(tool)

    def _unregister_tools(self, plugin_name: str) -> None:
        for name in self._tools_by_plugin.pop(plugin_name, []):
            self.unregister_tool(name)

    def _register_plots_tools(self) -> None:
        """Register the Plots tools, which also need the IPython console."""
        plots = self.get_plugin(Plugins.Plots, error=False)
        ipyconsole = self.get_plugin(Plugins.IPythonConsole, error=False)
        if (
            plots is None
            or ipyconsole is None
            or Plugins.Plots in self._tools_by_plugin
        ):
            return

        from spyder.plugins.mcpserver.tools import plots as plots_tools

        self._register_tools(
            Plugins.Plots, plots_tools.get_tools(plots, ipyconsole)
        )

    def _on_enabled_changed(self, enabled: bool) -> None:
        if enabled:
            self.start_server()
        else:
            self.stop_server()

    def _on_server_ready(self, url: str) -> None:
        self.get_container().set_server_running(True)

    def _on_server_stopped(self, returncode: int) -> None:
        self.get_container().set_server_running(False)
        if returncode not in (0, None) and self.get_conf("enabled"):
            logger.error(
                "The MCP server exited with code %s. Run Spyder with debug "
                "logging to see its output.",
                returncode,
            )
