# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Follow changes made on disk to the files open in the Editor (e.g. by agents,
formatters or git) as they happen.

Only the open files are watched, through the operating system's
notifications, so this costs nothing while files don't change.
"""

# Standard library imports
from __future__ import annotations

import logging
import os.path as osp

# Third-party imports
from qtpy.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from qtpy.QtGui import QTextCursor

# Local imports
from spyder.plugins.editor.utils.merge import diff_lines, split_lines
from spyder.utils import encoding

logger = logging.getLogger(__name__)

# Wait this long after the last change to a file before handling it, so
# files written in several steps are handled once (in milliseconds).
DEBOUNCE = 200

# Times to look for a file that disappeared, e.g. while it's replaced.
REAPPEAR_RETRIES = 5


def normalize_newlines(text: str) -> str:
    """Use ``\\n`` for line endings, like the Editor's documents."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_file(filename: str) -> str:
    """Read a file like the Editor does, with normalized line endings."""
    text, _encoding = encoding.read(filename)
    return normalize_newlines(text)


def utf16_length(text: str) -> int:
    """Length of ``text`` in Qt's text positions (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def replace_text(editor, new_text: str) -> None:
    """
    Change the text of ``editor`` to ``new_text`` with the smallest line
    edits, as a single undoable step that keeps the cursor and scroll
    position where possible.
    """
    old_lines = split_lines(editor.toPlainText())
    hunks = diff_lines(old_lines, split_lines(new_text))
    if not hunks:
        return

    # Start of each line, in Qt positions
    offsets = [0]
    for line in old_lines:
        offsets.append(offsets[-1] + utf16_length(line))

    scrollbar = editor.verticalScrollBar()
    scroll = scrollbar.value()

    cursor = QTextCursor(editor.document())
    cursor.beginEditBlock()
    try:
        # From the end, so earlier positions stay valid
        for hunk in reversed(hunks):
            cursor.setPosition(offsets[hunk.start])
            cursor.setPosition(offsets[hunk.end], QTextCursor.KeepAnchor)
            cursor.insertText("".join(hunk.lines))
    finally:
        cursor.endEditBlock()

    scrollbar.setValue(scroll)


class OpenFilesWatcher(QObject):
    """
    Watch the files open in the Editor and report when they change on disk.

    It also keeps the last text seen on disk for each file (the base for
    merging the user's unsaved changes with the new contents).
    """

    sig_file_changed = Signal(str)
    """
    A watched file changed on disk.

    Parameters
    ----------
    filename: str
        Path of the file, as given to :meth:`set_files`.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_file_changed)
        self._files: set[str] = set()
        self._bases: dict[str, str] = {}
        self._timers: dict[str, QTimer] = {}
        self._retries: dict[str, int] = {}

    # ---- Public API
    def set_files(self, filenames: list[str]) -> None:
        """Watch ``filenames`` (and stop watching other files)."""
        new = {
            filename for filename in filenames if osp.isfile(filename)
        }
        for filename in self._files - new:
            self._unwatch(filename)
        for filename in new - self._files:
            self._watch(filename)

    def get_files(self) -> list[str]:
        return sorted(self._files)

    def get_base(self, filename: str) -> str | None:
        """Last text of ``filename`` seen on disk."""
        return self._bases.get(filename)

    def set_base(self, filename: str, text: str) -> None:
        """
        Set the last text of ``filename`` seen on disk, e.g. after saving
        it.
        """
        if filename in self._files:
            self._bases[filename] = normalize_newlines(text)

    def stop(self) -> None:
        for filename in list(self._files):
            self._unwatch(filename)

    # ---- Private API
    def _watch(self, filename: str) -> None:
        self._files.add(filename)
        try:
            self._bases[filename] = read_file(filename)
        except Exception:
            logger.debug("Could not read %s", filename, exc_info=True)
        if not self._watcher.addPath(filename):
            logger.debug("Could not watch %s", filename)

    def _unwatch(self, filename: str) -> None:
        self._files.discard(filename)
        self._bases.pop(filename, None)
        self._retries.pop(filename, None)
        timer = self._timers.pop(filename, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if filename in self._watcher.files():
            self._watcher.removePath(filename)

    def _on_file_changed(self, filename: str) -> None:
        if filename not in self._files:
            return

        timer = self._timers.get(filename)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(DEBOUNCE)
            timer.timeout.connect(lambda: self._handle(filename))
            self._timers[filename] = timer
        timer.start()

    def _handle(self, filename: str) -> None:
        if filename not in self._files:
            return

        if not osp.isfile(filename):
            # Files replaced by renaming another one over them (as many
            # tools save) disappear for a moment; deleted files are handled
            # by the Editor when it gets focus
            retries = self._retries.get(filename, 0)
            if retries < REAPPEAR_RETRIES:
                self._retries[filename] = retries + 1
                self._timers[filename].start()
            return

        self._retries.pop(filename, None)

        # Replacing a file drops its watch
        if filename not in self._watcher.files():
            self._watcher.addPath(filename)

        self.sig_file_changed.emit(filename)
