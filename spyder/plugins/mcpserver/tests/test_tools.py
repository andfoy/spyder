# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Tests for the MCP tools of the IPython console."""

# Standard library imports
import base64

# Third-party imports
import pytest

# Local imports
from spyder.plugins.ipythonconsole.tests.conftest import SHELL_TIMEOUT
from spyder.plugins.mcpserver.api import ToolCall
from spyder.plugins.mcpserver.tools import ipythonconsole

# A 1x1 PNG image
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChw"
    "GA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def tools(ipyconsole):
    return {
        tool.name: tool for tool in ipythonconsole.get_tools(ipyconsole)
    }


def call_tool(qtbot, tool, **arguments):
    """Call ``tool`` and wait for its result."""
    results = []
    tool.call(
        ToolCall(
            arguments,
            lambda content, is_error: results.append((content, is_error)),
        )
    )
    qtbot.waitUntil(lambda: len(results) > 0, timeout=SHELL_TIMEOUT)
    return results[0]


def wait_idle(qtbot, ipyconsole):
    shell = ipyconsole.get_current_shellwidget()
    qtbot.waitUntil(lambda: not shell._executing, timeout=SHELL_TIMEOUT)


def test_list_consoles(ipyconsole, tools, qtbot):
    content, is_error = call_tool(qtbot, tools["list_consoles"])
    assert not is_error
    assert "id: 1/A" in content[0]["text"]
    assert "state: idle | current" in content[0]["text"]


def test_execute_code_output(ipyconsole, tools, qtbot):
    """Test that stdout and results are captured."""
    content, is_error = call_tool(
        qtbot, tools["execute_code"], code="print('hello')\n40 + 2"
    )
    assert not is_error
    assert content[0]["text"] == "hello\nOut[1]: 42\n"

    # The code and its output are shown in the console
    control = ipyconsole.get_current_shellwidget()._control
    assert "print('hello')" in control.toPlainText()


def test_execute_code_error(ipyconsole, tools, qtbot):
    """Test that tracebacks are returned without color codes."""
    content, is_error = call_tool(qtbot, tools["execute_code"], code="1/0")

    # User code errors are results the agent can act on, not tool errors
    assert not is_error
    assert content[0]["text"] == "The code raised an exception:"
    assert "ZeroDivisionError" in content[1]["text"]
    assert "\x1b[" not in content[1]["text"]


def test_execute_code_images(ipyconsole, tools, qtbot):
    """Test that displayed images are returned as image content."""
    code = (
        "import base64\n"
        "from IPython.display import Image, display\n"
        f"display(Image(data=base64.b64decode({base64.b64encode(PNG)!r})))"
    )
    content, is_error = call_tool(qtbot, tools["execute_code"], code=code)
    assert not is_error
    images = [item for item in content if item["type"] == "image"]
    assert len(images) == 1
    assert images[0]["mimeType"] == "image/png"
    assert base64.b64decode(images[0]["data"]) == PNG


def test_execute_code_timeout(ipyconsole, tools, qtbot):
    """Test long running code, busy consoles and interrupting them."""
    content, is_error = call_tool(
        qtbot,
        tools["execute_code"],
        code="import time\nprint('start')\ntime.sleep(30)",
        timeout=1,
    )
    assert not is_error
    assert content[0]["text"] == "start\n"
    assert "still running" in content[-1]["text"]

    # The console can't run more code while busy
    content, is_error = call_tool(qtbot, tools["execute_code"], code="1")
    assert is_error
    assert "busy" in content[0]["text"]

    content, is_error = call_tool(qtbot, tools["interrupt_console"])
    assert not is_error
    wait_idle(qtbot, ipyconsole)

    content, is_error = call_tool(qtbot, tools["execute_code"], code="1")
    assert not is_error


def test_execute_code_input(ipyconsole, tools, qtbot):
    """Test that waiting for user input is reported."""
    content, is_error = call_tool(
        qtbot, tools["execute_code"], code="name = input('Name: ')"
    )
    assert not is_error
    assert "waiting for user input" in content[-1]["text"]

    # Answer the prompt like the user would
    shell = ipyconsole.get_current_shellwidget()
    qtbot.waitUntil(lambda: shell._reading, timeout=SHELL_TIMEOUT)
    shell._control.insertPlainText("Spyder")
    qtbot.keyClick(shell._control, "\r")
    wait_idle(qtbot, ipyconsole)
    assert shell.get_value("name") == "Spyder"


def test_list_variables(ipyconsole, tools, qtbot):
    call_tool(qtbot, tools["execute_code"], code="answer = 42")

    content, is_error = call_tool(qtbot, tools["list_variables"])
    assert not is_error
    assert "- answer | type: int | size: 1 | value: 42" in content[0]["text"]


def test_unknown_console(ipyconsole, tools, qtbot):
    content, is_error = call_tool(
        qtbot, tools["execute_code"], code="1", console_id="9/Z"
    )
    assert is_error
    assert "No console with id '9/Z'" in content[0]["text"]
