# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Utilities shared by MCP tools."""

# Standard library imports
from __future__ import annotations

import re

# Third-party imports
from qtconsole.svg import svg_to_image
from qtpy.QtCore import QBuffer, QByteArray, QIODevice

# Maximum number of characters of text output returned to agents.
MAX_OUTPUT_CHARS = 20000

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Remove ANSI color codes, e.g. from tracebacks."""
    return ANSI_ESCAPE.sub("", text)


def truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Keep the start and end of ``text`` if it's too long."""
    if len(text) <= max_chars:
        return text

    half = max_chars // 2
    skipped = len(text) - 2 * half
    return (
        f"{text[:half]}\n\n[... {skipped} characters omitted ...]\n\n"
        f"{text[-half:]}"
    )


def svg_to_png(svg: str | bytes) -> bytes:
    """
    Render an SVG image to PNG.

    Agents can't read SVG images, so this is used to send them figures.
    """
    image = svg_to_image(svg)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)
