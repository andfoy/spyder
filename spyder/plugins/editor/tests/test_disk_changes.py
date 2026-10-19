# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Tests for following the changes made on disk to open files (e.g. by an
agent, a formatter or git).
"""

# Standard library imports
import os

# Third-party imports
from qtpy.QtCore import QFileInfo
from qtpy.QtGui import QTextCursor

# Local imports
from spyder.plugins.editor.utils.merge import CONFLICT_START

TEXT = (
    "# 😀 emoji take two positions in Qt\n"
    "def f():\n"
    "    return 1\n"
    "\n"
    "\n"
    "def g():\n"
    "    return 2\n"
)


def write(filename, text, atomic=False):
    """Write a file in place, or by replacing it like many tools do."""
    if atomic:
        tmp = filename + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, filename)
    else:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)


def test_follow_disk_changes(editor_plugin, qtbot, tmp_path):
    filename = str(tmp_path / "module.py")
    write(filename, TEXT)
    editor_plugin.load(filename)
    widget = editor_plugin.get_widget()
    editor = editor_plugin.get_current_editor()
    document = editor.document()
    qtbot.waitUntil(lambda: filename in widget._disk_watcher.get_files())

    # The cursor is in g
    cursor = document.find("return 2")
    cursor.setPosition(cursor.selectionStart())
    editor.setTextCursor(cursor)

    # A change on disk shows up without the Editor getting focus, and the
    # cursor stays on the same code
    changed = TEXT.replace("def f():", "def f(x):\n    '''Doc.'''")
    write(filename, changed)
    qtbot.waitUntil(lambda: editor.toPlainText() == changed)
    assert not document.isModified()
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
    assert cursor.selectedText() == "return 2"

    # It's a single undoable step
    editor.undo()
    assert editor.toPlainText() == TEXT
    assert document.isModified()
    editor.redo()
    assert editor.toPlainText() == changed

    # Files replaced by renaming another one over them are followed too
    replaced = changed.replace("return 2", "return 20")
    write(filename, replaced, atomic=True)
    qtbot.waitUntil(lambda: editor.toPlainText() == replaced)
    replaced_again = replaced.replace("return 20", "return 200")
    write(filename, replaced_again, atomic=True)
    qtbot.waitUntil(lambda: editor.toPlainText() == replaced_again)

    # The Editor won't ask to reload it when it gets focus
    finfo = widget._get_finfo(filename)
    assert finfo.lastmodified == QFileInfo(filename).lastModified()


def test_merge_with_unsaved_changes(editor_plugin, qtbot, tmp_path):
    filename = str(tmp_path / "module.py")
    write(filename, TEXT)
    editor_plugin.load(filename)
    widget = editor_plugin.get_widget()
    editor = editor_plugin.get_current_editor()
    document = editor.document()
    bar = widget.disk_conflict_bar
    qtbot.waitUntil(lambda: filename in widget._disk_watcher.get_files())

    # The user changes f without saving
    cursor = document.find("1")
    cursor.insertText("'mine'")
    assert document.isModified()

    # A change to g on disk is merged, keeping the unsaved change
    write(filename, TEXT.replace("return 2", "return 'disk'"))
    expected = TEXT.replace("return 1", "return 'mine'").replace(
        "return 2", "return 'disk'"
    )
    qtbot.waitUntil(lambda: editor.toPlainText() == expected)
    assert document.isModified()
    assert not bar.isVisible()

    # A change to f conflicts, so the Editor's text stays as it is and the
    # user is asked without a dialog
    disk = TEXT.replace("return 1", "return 'other'").replace(
        "return 2", "return 'disk'"
    )
    write(filename, disk)
    qtbot.waitUntil(bar.isVisible)
    assert bar.get_filename() == filename
    assert editor.toPlainText() == expected

    bar.markers_button.click()
    assert not bar.isVisible()
    text = editor.toPlainText()
    assert CONFLICT_START in text
    assert "    return 'mine'\n=======\n    return 'other'\n" in text
    assert document.isModified()

    # Taking the disk's version of a later conflict
    editor.undo()
    write(filename, disk.replace("return 'other'", "return 'other 2'"))
    qtbot.waitUntil(bar.isVisible)
    bar.take_button.click()
    assert editor.toPlainText() == disk.replace(
        "return 'other'", "return 'other 2'"
    )
    assert not document.isModified()

    # Saving in Spyder doesn't change anything
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    cursor.insertText("# saved\n")
    saved = editor.toPlainText()
    editor_plugin.save()
    qtbot.wait(500)
    assert editor.toPlainText() == saved
    assert not document.isModified()
    assert not bar.isVisible()


def test_closed_files_arent_watched(editor_plugin, qtbot, tmp_path):
    filename = str(tmp_path / "module.py")
    write(filename, TEXT)
    editor_plugin.load(filename)
    widget = editor_plugin.get_widget()
    qtbot.waitUntil(lambda: filename in widget._disk_watcher.get_files())

    editor_plugin.close_file()
    assert filename not in widget._disk_watcher.get_files()
