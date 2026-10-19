# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Bar shown when a file changes on disk in a way that conflicts with the
user's unsaved changes in the Editor.
"""

# Standard library imports
from __future__ import annotations

import os.path as osp

# Third-party imports
from qtpy.QtCore import Signal
from qtpy.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

# Local imports
from spyder.api.translations import _


class DiskConflictBar(QFrame):
    """
    Non-modal bar to resolve a conflict between the Editor and the disk.
    Unlike a dialog, it doesn't interrupt the user, who can keep editing
    and decide later.
    """

    sig_keep_mine = Signal(str)
    """Keep the Editor's text (saving it will overwrite the disk)."""

    sig_take_disk = Signal(str)
    """Replace the Editor's text with the file on disk."""

    sig_insert_markers = Signal(str)
    """Merge both, marking the conflicting regions to edit them by hand."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("editor-disk-conflict")
        self._filename: str | None = None

        self.label = QLabel(self)
        self.label.setWordWrap(True)

        self.keep_button = QPushButton(_("Keep mine"), self)
        self.keep_button.clicked.connect(
            lambda: self._resolve(self.sig_keep_mine)
        )
        self.take_button = QPushButton(_("Take disk version"), self)
        self.take_button.clicked.connect(
            lambda: self._resolve(self.sig_take_disk)
        )
        self.markers_button = QPushButton(_("Merge with markers"), self)
        self.markers_button.setToolTip(
            _(
                "Keep both versions of the conflicting lines, between "
                "<<<<<<< and >>>>>>> markers, to edit them by hand"
            )
        )
        self.markers_button.clicked.connect(
            lambda: self._resolve(self.sig_insert_markers)
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self.label, stretch=1)
        for button in [
            self.keep_button,
            self.take_button,
            self.markers_button,
        ]:
            layout.addWidget(button)

        self.hide()

    def show_conflict(self, filename: str, conflicts: int) -> None:
        self._filename = filename
        self.label.setText(
            _(
                "<b>{}</b> changed on disk and {} of its changes conflict "
                "with your unsaved changes."
            ).format(osp.basename(filename), conflicts)
        )
        self.show()

    def get_filename(self) -> str | None:
        return self._filename if self.isVisible() else None

    def dismiss(self) -> None:
        self._filename = None
        self.hide()

    def _resolve(self, signal) -> None:
        filename = self._filename
        self.dismiss()
        if filename is not None:
            signal.emit(filename)
