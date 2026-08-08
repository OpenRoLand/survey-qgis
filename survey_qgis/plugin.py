"""Main QGIS plugin class for Siscadro Survey Time Filter."""

from __future__ import annotations

import logging
import os
from typing import Optional

from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from survey_qgis.gui.dock import SurveyDockWidget
from survey_qgis.layers.registry import ManagedLayerRegistry
from survey_qgis.layers.time_controller import TimeWindowController
from survey_qgis.log_setup import configure_logging
from survey_qgis import settings as plugin_settings

logger = logging.getLogger(__name__)

PLUGIN_MENU = "&Siscadro Survey Time Filter"


class SurveySnakePlugin:
    """QGIS plugin entry that owns the dock and layer registry.

    Attributes:
        iface: QGIS interface instance.
        plugin_dir: Absolute path to the plugin package root.
        assets_dir: Absolute path to the assets directory.
    """

    def __init__(self, iface: QgisInterface) -> None:
        """Create the plugin (GUI is built in ``initGui``).

        Args:
            iface: QGIS interface.
        """
        self.iface = iface
        self.plugin_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        self.assets_dir = os.path.join(self.plugin_dir, "assets")
        self.dock: Optional[SurveyDockWidget] = None
        self.registry = ManagedLayerRegistry()
        self.time_controller = TimeWindowController(
            iface,
            window_seconds=plugin_settings.get_window_seconds(),
        )
        self.action_toggle: Optional[QAction] = None
        configure_logging()

    def get_icon(self, key: str = "icon") -> QIcon:
        """Return an icon from the assets directory.

        Args:
            key: Asset basename without extension.
        """
        path = os.path.join(self.assets_dir, f"{key}.png")
        return QIcon(path)

    def initGui(self) -> None:
        """Create actions, dock widget, and connect project signals."""
        self.registry.connect_project()

        self.dock = SurveyDockWidget(
            self.iface,
            self.registry,
            self.time_controller,
            parent=self.iface.mainWindow(),
        )
        self.iface.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.dock,
        )
        self.dock.hide()
        self.dock.status_message.connect(self._show_status)

        self.action_toggle = QAction(
            self.get_icon(),
            "Survey Time Filter",
            self.iface.mainWindow(),
        )
        self.action_toggle.setObjectName(
            "SiscadroSurveyTimeFilter_ToggleDock"
        )
        self.action_toggle.setCheckable(True)
        self.action_toggle.toggled.connect(self._toggle_dock)
        self.iface.addPluginToMenu(PLUGIN_MENU, self.action_toggle)
        self.iface.addToolBarIcon(self.action_toggle)
        self.dock.visibilityChanged.connect(self.action_toggle.setChecked)
        logger.info("Siscadro Survey Time Filter initialized")

    def unload(self) -> None:
        """Remove UI and disconnect project signals."""
        if self.dock is not None:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.action_toggle is not None:
            self.iface.removePluginMenu(PLUGIN_MENU, self.action_toggle)
            self.iface.removeToolBarIcon(self.action_toggle)
            self.action_toggle = None
        self.registry.disconnect_project()
        logger.info("Siscadro Survey Time Filter unloaded")

    def _toggle_dock(self, checked: bool) -> None:
        """Show or hide the dock from the toolbar action."""
        if self.dock is None:
            return
        self.dock.setVisible(bool(checked))

    def _show_status(self, message: str) -> None:
        """Show a short status bar message."""
        self.iface.mainWindow().statusBar().showMessage(message, 5000)
