# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Spyder Editor plugin.
"""

# Standard library imports
from typing import Union, List

# Third party imports
from qtpy.QtCore import Slot

# Local imports
from spyder.api.plugin_registration.decorators import (
    on_plugin_available, on_plugin_teardown)
from spyder.api.translations import get_translation
from spyder.api.plugins import SpyderDockablePlugin, Plugins
from spyder.plugins.outlineexplorer.main_widget import OutlineExplorerWidget
from spyder.plugins.editor.widgets.main_widget import EditorWidget

# Localization
_ = get_translation('spyder')


class Editor(SpyderDockablePlugin):
    NAME = 'editor'
    CONF_SECTION = 'editor'
    REQUIRES = []
    OPTIONAL = []

    CONF_FILE = False
    WIDGET_CLASS = EditorWidget

    # ---- SpyderDockablePlugin API
    # ------------------------------------------------------------------------
    @staticmethod
    def get_name() -> str:
        """Return widget title."""
        return _('Editor')

    def get_description(self) -> str:
        """Return the description of the editor widget."""
        return _("Write, edit and save text files")

    def get_icon(self):
        """Return the editor icon."""
        return self.create_icon('edit')

    def on_initialize(self):
        return super().on_initialize()

    def on_close(self, cancelable=False):
        return super().on_close(cancelable)

    def on_first_registration(self):
        return super().on_first_registration()

    def before_mainwindow_visible(self):
        return super().before_mainwindow_visible()

    def on_mainwindow_visible(self):
        return super().on_mainwindow_visible()

    def can_close(self) -> bool:
        return super().can_close()

    def update_font(self):
        return super().update_font()

    def update_style(self):
        return super().update_style()

    def after_container_creation(self):
        return super().after_container_creation()

    def after_configuration_update(self, options: List[Union[str, tuple]]):
        return super().after_configuration_update(options)
