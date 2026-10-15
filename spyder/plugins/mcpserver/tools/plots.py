# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""MCP tools for the Plots plugin."""

# Standard library imports
from __future__ import annotations

from typing import TYPE_CHECKING

# Local imports
from spyder.plugins.mcpserver.api import (
    MCPTool,
    ToolCall,
    ToolError,
    image_content,
)
from spyder.plugins.mcpserver.tools.ipythonconsole import (
    CONSOLE_ID_SCHEMA,
    get_shellwidget,
)
from spyder.plugins.mcpserver.tools.utils import svg_to_png

if TYPE_CHECKING:
    from spyder.plugins.ipythonconsole.plugin import IPythonConsole
    from spyder.plugins.plots.plugin import Plots


def get_tools(plots: Plots, ipyconsole: IPythonConsole) -> list[MCPTool]:

    def get_thumbnails(console_id: str | None) -> list:
        shellwidget = get_shellwidget(ipyconsole, console_id)
        figure_browser = plots.get_widget().get_widget_for_shellwidget(
            shellwidget
        )
        if figure_browser is None:
            raise ToolError("The Plots pane has no figures for this console.")
        return figure_browser.thumbnails_sb._thumbnails

    def list_figures(call: ToolCall):
        thumbnails = get_thumbnails(call.arguments.get("console_id"))
        if not thumbnails:
            return "There are no figures in the Plots pane for this console."

        lines = []
        for index, thumbnail in enumerate(thumbnails):
            canvas = thumbnail.canvas
            size = canvas._qpix_orig.size()
            lines.append(
                f"- index: {index} | format: {canvas.fmt} | "
                f"size: {size.width()}x{size.height()} px"
            )
        return "Figures (oldest first):\n" + "\n".join(lines)

    def get_figure(call: ToolCall):
        thumbnails = get_thumbnails(call.arguments.get("console_id"))
        index = call.arguments.get("index", -1)
        try:
            canvas = thumbnails[index].canvas
        except IndexError:
            raise ToolError(
                f"There's no figure with index {index}. There are "
                f"{len(thumbnails)} figures."
            ) from None

        if canvas.fmt == "image/svg+xml":
            return image_content(svg_to_png(canvas.fig))
        return image_content(canvas.fig, canvas.fmt)

    return [
        MCPTool(
            name="list_figures",
            title="List figures in the Plots pane",
            description=(
                "List the figures shown in Spyder's Plots pane for a console."
            ),
            handler=list_figures,
            input_schema={
                "type": "object",
                "properties": {"console_id": CONSOLE_ID_SCHEMA},
            },
            read_only=True,
        ),
        MCPTool(
            name="get_figure",
            title="Get a figure from the Plots pane",
            description=(
                "Get a figure from Spyder's Plots pane as an image, to look "
                "at plots generated in a console."
            ),
            handler=get_figure,
            input_schema={
                "type": "object",
                "properties": {
                    "index": {
                        "type": "integer",
                        "description": (
                            "Index of the figure as given by list_figures. "
                            "Negative values count from the end. Defaults "
                            "to -1, the most recent figure."
                        ),
                    },
                    "console_id": CONSOLE_ID_SCHEMA,
                },
            },
            read_only=True,
        ),
    ]
