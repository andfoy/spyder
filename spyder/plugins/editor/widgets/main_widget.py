# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Plots Main Widget.
"""

# Third party imports
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import QSpinBox

# Local imports
from spyder.api.config.decorators import on_conf_change
from spyder.api.translations import get_translation
from spyder.api.widgets.main_widget import PluginMainWidgetMenus, PluginMainWidget
from spyder.utils.misc import getcwd_or_home
from spyder.utils.palette import QStylePalette
from spyder.api.widgets.mixins import SpyderWidgetMixin

# Localization
_ = get_translation('spyder')


class EditorWidget(PluginMainWidget):
    """Editor plugin main widget."""

    CONF_SECTION = 'editor'

    def __init__(self, name, plugin, parent=None):
        super().__init__(name, plugin, parent)

    # ------------------- PluginMainWidget API --------------------------------
    def get_focus_widget(self):
        return super().get_focus_widget()

    def get_title(self):
        return _('Editor')

    def setup(self):
        pass

    def update_actions(self):
        return super().update_actions()

