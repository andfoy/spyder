# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""Tests for merging the Editor's unsaved changes with changes on disk."""

# Local imports
from spyder.plugins.editor.utils.merge import (
    CONFLICT_END,
    CONFLICT_MIDDLE,
    CONFLICT_START,
    diff_lines,
    merge3,
    split_lines,
)

BASE = "import os\n\ndef f():\n    return 1\n\ndef g():\n    return 2\n"


def test_diff_lines():
    hunks = diff_lines(split_lines("a\nb\nc\n"), split_lines("a\nB\nc\nd\n"))
    assert [(h.start, h.end, h.lines) for h in hunks] == [
        (1, 2, ["B\n"]),
        (3, 3, ["d\n"]),
    ]


def test_changes_in_different_places_are_merged():
    ours = BASE.replace("return 1", "return 10")
    theirs = BASE.replace("return 2", "return 20")
    result = merge3(BASE, ours, theirs)
    assert result.conflicts == 0
    assert result.text == BASE.replace("return 1", "return 10").replace(
        "return 2", "return 20"
    )


def test_one_sided_changes():
    theirs = "import sys\n" + BASE
    assert merge3(BASE, BASE, theirs).text == theirs
    assert merge3(BASE, theirs, BASE).text == theirs

    # Both made the same change
    result = merge3(BASE, theirs, theirs)
    assert (result.text, result.conflicts) == (theirs, 0)


def test_conflicts():
    ours = BASE.replace("return 1", "return 'mine'")
    theirs = BASE.replace("return 1", "return 'disk'")
    result = merge3(BASE, ours, theirs)
    assert result.conflicts == 1

    # Without markers, the editor's version is kept
    assert result.text == ours

    marked = merge3(BASE, ours, theirs, with_markers=True).text
    assert marked == BASE.replace(
        "    return 1\n",
        CONFLICT_START
        + "    return 'mine'\n"
        + CONFLICT_MIDDLE
        + "    return 'disk'\n"
        + CONFLICT_END,
    )


def test_touching_changes_conflict():
    """Like in git, changes to adjacent lines are a conflict."""
    ours = BASE.replace("def f():", "def f(x):")
    theirs = BASE.replace("return 1", "return 2")
    assert merge3(BASE, ours, theirs).conflicts == 1


def test_last_line_without_newline():
    base = "a\nb"
    result = merge3(base, "a\nB", "A\nb", with_markers=True)
    assert result.conflicts == 1
    assert result.text.endswith(CONFLICT_END)
    assert "B\n" + CONFLICT_MIDDLE in result.text

    result = merge3("a\n\nb", "A\n\nb", "a\n\nB")
    assert (result.text, result.conflicts) == ("A\n\nB", 0)
