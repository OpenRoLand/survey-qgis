"""Track managed survey layers and the currently controlled one."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from qgis.core import QgsMapLayer, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QObject, pyqtSignal

from survey_qgis.layers.managed_layer import is_managed_layer
from survey_qgis.layers.snake_layer import is_snake_layer

logger = logging.getLogger(__name__)

__all__ = ["ManagedLayerRegistry"]


class ManagedLayerRegistry(QObject):
    """Registry of managed survey layers in the current project.

    Attributes:
        controlled_changed: Emitted when the controlled layer changes.
        layers_changed: Emitted when the managed layer list changes.
    """

    controlled_changed = pyqtSignal(object)
    layers_changed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Create an empty registry.

        Args:
            parent: Optional Qt parent.
        """
        super().__init__(parent)
        self._layers: Dict[str, QgsVectorLayer] = {}
        self._snake_by_managed: Dict[str, str] = {}
        self._controlled_id: Optional[str] = None
        self._connected = False

    def connect_project(self, project: Optional[QgsProject] = None) -> None:
        """Connect to project layer add/remove signals.

        Args:
            project: Project to watch (defaults to the current instance).
        """
        project = project or QgsProject.instance()
        if self._connected:
            return
        project.layersAdded.connect(self._on_layers_added)
        project.layersWillBeRemoved.connect(self._on_layers_will_be_removed)
        self._connected = True
        self.resync(project)

    def disconnect_project(
        self, project: Optional[QgsProject] = None
    ) -> None:
        """Disconnect from project signals.

        Args:
            project: Project previously watched.
        """
        project = project or QgsProject.instance()
        if not self._connected:
            return
        try:
            project.layersAdded.disconnect(self._on_layers_added)
        except TypeError:
            logger.log(1, "layersAdded was not connected", exc_info=True)
        try:
            project.layersWillBeRemoved.disconnect(
                self._on_layers_will_be_removed
            )
        except TypeError:
            logger.log(
                1,
                "layersWillBeRemoved was not connected",
                exc_info=True,
            )
        self._connected = False

    def resync(self, project: Optional[QgsProject] = None) -> None:
        """Rebuild the registry from the current project layers.

        Args:
            project: Project to scan.
        """
        project = project or QgsProject.instance()
        self._layers.clear()
        snake_layers: Dict[str, QgsVectorLayer] = {}
        for layer in project.mapLayers().values():
            if is_managed_layer(layer):
                self._layers[layer.id()] = layer
            elif is_snake_layer(layer):
                snake_layers[layer.id()] = layer

        # Drop snake links whose managed layer is gone.
        self._snake_by_managed = {
            managed_id: snake_id
            for managed_id, snake_id in self._snake_by_managed.items()
            if managed_id in self._layers and snake_id in snake_layers
        }

        if self._controlled_id not in self._layers:
            self._controlled_id = next(iter(self._layers), None)
            self.controlled_changed.emit(self.controlled_layer())
        self.layers_changed.emit()

    def register(
        self,
        layer: QgsVectorLayer,
        *,
        snake_layer: Optional[QgsVectorLayer] = None,
        make_controlled: bool = True,
    ) -> None:
        """Register a managed layer and optional snake overlay.

        Args:
            layer: Managed observations layer.
            snake_layer: Optional associated snake layer.
            make_controlled: Whether to make this the controlled layer.
        """
        self._layers[layer.id()] = layer
        if snake_layer is not None:
            self._snake_by_managed[layer.id()] = snake_layer.id()
        if make_controlled or self._controlled_id is None:
            self._controlled_id = layer.id()
            self.controlled_changed.emit(layer)
        self.layers_changed.emit()

    def unregister(self, layer_id: str) -> None:
        """Remove a managed layer from the registry.

        Args:
            layer_id: Layer id that was removed.
        """
        self._layers.pop(layer_id, None)
        self._snake_by_managed.pop(layer_id, None)
        if self._controlled_id == layer_id:
            self._controlled_id = next(iter(self._layers), None)
            self.controlled_changed.emit(self.controlled_layer())
        self.layers_changed.emit()

    def managed_layers(self) -> List[QgsVectorLayer]:
        """Return managed layers in stable insertion order."""
        return list(self._layers.values())

    def controlled_layer(self) -> Optional[QgsVectorLayer]:
        """Return the currently controlled managed layer."""
        if self._controlled_id is None:
            return None
        return self._layers.get(self._controlled_id)

    def set_controlled(self, layer: Optional[QgsVectorLayer]) -> None:
        """Set which managed layer the dock panel controls.

        Args:
            layer: Managed layer, or None to clear.
        """
        if layer is None:
            self._controlled_id = None
            self.controlled_changed.emit(None)
            return
        if layer.id() not in self._layers:
            self._layers[layer.id()] = layer
        self._controlled_id = layer.id()
        self.controlled_changed.emit(layer)

    def snake_layer_id(self, managed_layer_id: str) -> Optional[str]:
        """Return the snake layer id linked to a managed layer."""
        return self._snake_by_managed.get(managed_layer_id)

    def snake_for(
        self, managed_layer: QgsVectorLayer
    ) -> Optional[QgsVectorLayer]:
        """Return the snake overlay for a managed layer, if present."""
        snake_id = self._snake_by_managed.get(managed_layer.id())
        if not snake_id:
            return None
        layer = QgsProject.instance().mapLayer(snake_id)
        if isinstance(layer, QgsVectorLayer):
            return layer
        return None

    def _on_layers_added(self, layers: List[QgsMapLayer]) -> None:
        """Handle newly added project layers."""
        changed = False
        for layer in layers:
            if is_managed_layer(layer) and layer.id() not in self._layers:
                self._layers[layer.id()] = layer
                changed = True
                if self._controlled_id is None:
                    self._controlled_id = layer.id()
                    self.controlled_changed.emit(layer)
        if changed:
            self.layers_changed.emit()

    def _on_layers_will_be_removed(self, layer_ids: List[str]) -> None:
        """Handle layers about to be removed from the project."""
        changed = False
        for layer_id in layer_ids:
            if layer_id in self._layers:
                self._layers.pop(layer_id, None)
                self._snake_by_managed.pop(layer_id, None)
                changed = True
                if self._controlled_id == layer_id:
                    self._controlled_id = next(iter(self._layers), None)
                    self.controlled_changed.emit(self.controlled_layer())
            # Also drop snake links that point at a removed snake layer.
            stale = [
                managed_id
                for managed_id, snake_id in self._snake_by_managed.items()
                if snake_id == layer_id
            ]
            for managed_id in stale:
                self._snake_by_managed.pop(managed_id, None)
                changed = True
        if changed:
            self.layers_changed.emit()
