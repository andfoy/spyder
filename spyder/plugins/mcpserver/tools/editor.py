# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""MCP tools for the Editor plugin."""

# Standard library imports
from __future__ import annotations

import os.path as osp
from typing import TYPE_CHECKING

# Local imports
from spyder.plugins.mcpserver.api import MCPTool, ToolCall, ToolError
from spyder.plugins.mcpserver.tools.utils import truncate

if TYPE_CHECKING:
    from spyder.plugins.editor.plugin import Editor

# Maximum number of characters returned when reading a file.
MAX_FILE_CHARS = 200000


def get_tools(editor: Editor) -> list[MCPTool]:

    def get_codeeditor(filename: str):
        codeeditor = editor.get_codeeditor_for_filename(
            osp.abspath(filename)
        )
        if codeeditor is None:
            raise ToolError(
                f"{filename} is not open in the Editor. Use open_file to "
                f"open it or read it from disk instead."
            )
        return codeeditor

    def get_editor_state(call: ToolCall):
        current = editor.get_current_filename()
        lines = [f"Current file: {current}"]

        codeeditor = editor.get_current_editor()
        if codeeditor is not None:
            line, column = codeeditor.get_cursor_line_column()
            lines.append(f"Cursor: line {line + 1}, column {column + 1}")

            selection = codeeditor.get_selected_text()
            if selection:
                lines.append(
                    f"Selected text:\n```\n{truncate(selection)}\n```"
                )

        lines.append("Open files:")
        for filename in editor.get_filenames():
            codeeditor = editor.get_codeeditor_for_filename(filename)
            modified = (
                codeeditor is not None and codeeditor.document().isModified()
            )
            lines.append(
                f"- {filename}" + (" (unsaved changes)" if modified else "")
            )

        return "\n".join(lines)

    def read_editor_file(call: ToolCall):
        filename = call.arguments.get("filename") or (
            editor.get_current_filename()
        )
        codeeditor = get_codeeditor(filename)
        return truncate(codeeditor.toPlainText(), MAX_FILE_CHARS)

    def open_file(call: ToolCall):
        filename = osp.abspath(call.arguments["filename"])
        if not osp.isfile(filename):
            raise ToolError(f"{filename} doesn't exist.")

        editor.load(filename, goto=call.arguments.get("line"))
        return f"Opened {filename} in the Editor."

    filename_schema = {
        "type": "string",
        "description": "Absolute path of the file.",
    }

    return [
        MCPTool(
            name="get_editor_state",
            title="Get the Editor state",
            description=(
                "Get the file the user is looking at in Spyder's Editor, the "
                "cursor position, the selected text and the list of open "
                "files, including which ones have unsaved changes. Use it to "
                "find out what the user refers to with 'this file', 'this "
                "function' or 'the selection'."
            ),
            handler=get_editor_state,
            read_only=True,
        ),
        MCPTool(
            name="read_editor_file",
            title="Read a file open in the Editor",
            description=(
                "Read the contents of a file open in Spyder's Editor, "
                "including unsaved changes that are not on disk yet."
            ),
            handler=read_editor_file,
            input_schema={
                "type": "object",
                "properties": {
                    "filename": {
                        **filename_schema,
                        "description": (
                            "Absolute path of the file. Defaults to the "
                            "current file."
                        ),
                    },
                },
            },
            read_only=True,
        ),
        MCPTool(
            name="open_file",
            title="Open a file in the Editor",
            description=(
                "Open a file in Spyder's Editor to show it to the user, "
                "optionally at a given line."
            ),
            handler=open_file,
            input_schema={
                "type": "object",
                "properties": {
                    "filename": filename_schema,
                    "line": {
                        "type": "integer",
                        "description": "Line to go to (1-based).",
                    },
                },
                "required": ["filename"],
            },
        ),
    ]
