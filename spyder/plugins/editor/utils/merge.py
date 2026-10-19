# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Line-based diffs and three-way merges, to bring changes made to a file on
disk (e.g. by an agent, a formatter or git) into the Editor without losing
the user's unsaved changes.
"""

# Standard library imports
from __future__ import annotations

from dataclasses import dataclass
import difflib

CONFLICT_START = "<<<<<<< Editor (unsaved changes)\n"
CONFLICT_MIDDLE = "=======\n"
CONFLICT_END = ">>>>>>> Disk\n"


@dataclass
class Hunk:
    """Lines ``start:end`` of the original text replaced by ``lines``."""

    start: int
    end: int
    lines: list[str]


def split_lines(text: str) -> list[str]:
    """Split text into lines, keeping their line endings."""
    return text.splitlines(keepends=True)


def diff_lines(old: list[str], new: list[str]) -> list[Hunk]:
    """Hunks that turn ``old`` into ``new``."""
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return [
        Hunk(i1, i2, new[j1:j2])
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


@dataclass
class MergeResult:
    text: str
    """
    Merged text. Conflicting regions are marked like in git if
    ``with_markers`` was given, or else they keep the editor's version.
    """

    conflicts: int
    """Number of regions changed differently in both versions."""


def _apply(base: list[str], hunks: list[Hunk], start: int, end: int):
    """Lines ``start:end`` of ``base`` after applying ``hunks`` to them."""
    lines = []
    position = start
    for hunk in hunks:
        lines += base[position:hunk.start] + hunk.lines
        position = hunk.end
    return lines + base[position:end]


def merge3(
    base: str, ours: str, theirs: str, with_markers: bool = False
) -> MergeResult:
    """
    Merge two versions of a text that come from ``base``: ``ours`` (the
    Editor's, with unsaved changes) and ``theirs`` (the file on disk).

    Regions changed in only one version take that change. Regions changed in
    both (overlapping or touching, like in git) are conflicts unless both
    made the same change.
    """
    base_lines = split_lines(base)
    hunks = [
        (hunk, side)
        for side, text in [("ours", ours), ("theirs", theirs)]
        for hunk in diff_lines(base_lines, split_lines(text))
    ]
    hunks.sort(key=lambda item: (item[0].start, item[0].end))

    # Group hunks whose base regions overlap or touch
    groups = []
    for hunk, side in hunks:
        if groups and hunk.start <= groups[-1]["end"]:
            group = groups[-1]
            group["end"] = max(group["end"], hunk.end)
        else:
            group = {"start": hunk.start, "end": hunk.end, "ours": [],
                     "theirs": []}
            groups.append(group)
        group[side].append(hunk)

    merged = []
    conflicts = 0
    position = 0
    for group in groups:
        start, end = group["start"], group["end"]
        merged += base_lines[position:start]
        position = end

        ours_region = _apply(base_lines, group["ours"], start, end)
        theirs_region = _apply(base_lines, group["theirs"], start, end)
        if not group["theirs"] or ours_region == theirs_region:
            merged += ours_region
        elif not group["ours"]:
            merged += theirs_region
        else:
            conflicts += 1
            if with_markers:
                merged += (
                    [CONFLICT_START]
                    + _ensure_newline(ours_region)
                    + [CONFLICT_MIDDLE]
                    + _ensure_newline(theirs_region)
                    + [CONFLICT_END]
                )
            else:
                merged += ours_region

    merged += base_lines[position:]
    return MergeResult("".join(merged), conflicts)


def _ensure_newline(lines: list[str]) -> list[str]:
    """Make sure a region ends with a newline before a conflict marker."""
    if lines and not lines[-1].endswith(("\n", "\r")):
        return lines[:-1] + [lines[-1] + "\n"]
    return lines
