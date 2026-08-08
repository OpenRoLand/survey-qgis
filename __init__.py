# -*- coding: utf-8 -*-
"""QGIS plugin entry point for Siscadro Survey Time Filter."""

from __future__ import annotations

import os
import sys


# QGIS puts ``.../python/plugins`` on ``sys.path`` and imports this folder as
# ``siscadro_survey``. The nested ``survey_qgis`` package is only importable
# when this plugin directory itself is on ``sys.path`` (same as Docker tests).
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load the plugin class from the package.

    Args:
        iface: A QGIS interface instance.

    Returns:
        The plugin instance.
    """
    from survey_qgis.plugin import SurveySnakePlugin

    return SurveySnakePlugin(iface)
