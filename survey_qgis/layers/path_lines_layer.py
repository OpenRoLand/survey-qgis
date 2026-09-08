"""On-demand in-memory path lines between consecutive observations."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsLineString,
    QgsPointXY,
    QgsProject,
    QgsSymbol,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerTemporalProperties,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QDateTime, Qt, QVariant
from qgis.PyQt.QtGui import QColor

from survey_qgis.core.intervals import parse_observed_at
from survey_qgis.core.snake import SnakeSegment

logger = logging.getLogger(__name__)

__all__ = [
    "PATH_LINES_LAYER_PROPERTY",
    "create_path_lines_layer",
    "is_path_lines_layer",
    "rebuild_path_lines_layer",
    "add_path_lines_layer",
    "apply_path_lines_color_scale",
]

PATH_LINES_LAYER_PROPERTY = "openroland_survey_path_lines"
PATH_LINES_LAYER_VALUE = "1"
PATH_LINES_CLASS_COUNT = 10
PATH_LINES_LINE_WIDTH = 1.8


def create_path_lines_layer(
    *,
    name: str = "Survey path lines",
) -> QgsVectorLayer:
    """Create an empty in-memory LineString path-lines layer.

    Args:
        name: Display name shown in the legend.

    Returns:
        A memory vector layer with temporal segment attributes.
    """
    layer = QgsVectorLayer(
        "LineString?crs=EPSG:3844",
        name,
        "memory",
    )
    provider = layer.dataProvider()
    fields = QgsFields()
    int_type = getattr(QVariant, "Int", None) or QVariant.Type.Int
    double_type = getattr(QVariant, "Double", None) or QVariant.Type.Double
    datetime_type = (
        getattr(QVariant, "DateTime", None) or QVariant.Type.DateTime
    )
    fields.append(QgsField("interval_id", int_type))
    fields.append(QgsField("seg_start", datetime_type))
    fields.append(QgsField("seg_end", datetime_type))
    fields.append(QgsField("t_epoch", double_type))
    fields.append(QgsField("obs_id_a", int_type))
    fields.append(QgsField("obs_id_b", int_type))
    provider.addAttributes(fields.toList())
    layer.updateFields()
    layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3844"))
    layer.setCustomProperty(
        PATH_LINES_LAYER_PROPERTY,
        PATH_LINES_LAYER_VALUE,
    )

    props = layer.temporalProperties()
    # Inactive until the user enables the time-window filter.
    props.setIsActive(False)
    mode = getattr(
        QgsVectorLayerTemporalProperties,
        "ModeFeatureDateTimeStartAndEndFromFields",
        None,
    )
    if mode is None:
        mode = (
            QgsVectorLayerTemporalProperties.TemporalMode
            .ModeFeatureDateTimeStartAndEndFromFields
        )
    props.setMode(mode)
    props.setStartField("seg_start")
    props.setEndField("seg_end")
    if hasattr(props, "setAccumulateFeatures"):
        props.setAccumulateFeatures(False)
    if hasattr(props, "setDurationUnits"):
        units = getattr(
            QgsUnitTypes,
            "TemporalMilliseconds",
            None,
        )
        if units is None:
            units = QgsUnitTypes.TemporalUnit.TemporalMilliseconds
        props.setDurationUnits(units)

    apply_path_lines_color_scale(layer, [])
    return layer


def is_path_lines_layer(layer) -> bool:
    """Return whether ``layer`` is a plugin path-lines overlay.

    Args:
        layer: Candidate map layer.

    Returns:
        True when the custom property marks a path-lines layer.
    """
    if layer is None or not isinstance(layer, QgsVectorLayer):
        return False
    return (
        str(layer.customProperty(PATH_LINES_LAYER_PROPERTY, ""))
        == PATH_LINES_LAYER_VALUE
    )


def _segment_qdatetime(iso_value: str) -> QDateTime:
    """Convert an ISO-8601 observation timestamp to ``QDateTime``."""
    parsed = parse_observed_at(iso_value)
    qt_value = QDateTime.fromString(
        parsed.isoformat(),
        Qt.DateFormat.ISODate,
    )
    if not qt_value.isValid():
        qt_value = QDateTime.fromSecsSinceEpoch(int(parsed.timestamp()))
    return qt_value


def _direction_color_ramp() -> QgsGradientColorRamp:
    """Return a cool-to-warm ramp for movement direction."""
    ramp = QgsGradientColorRamp(
        QColor(0, 70, 255),
        QColor(220, 20, 20),
    )
    ramp.setStops(
        [
            QgsGradientStop(0.33, QColor(0, 200, 220)),
            QgsGradientStop(0.66, QColor(255, 220, 0)),
        ]
    )
    return ramp


def _equal_interval_mode():
    """Return the EqualInterval graduated mode for Qt5/Qt6 QGIS."""
    mode_enum = getattr(QgsGraduatedSymbolRenderer, "Mode", None)
    if mode_enum is not None:
        return mode_enum.EqualInterval
    return QgsGraduatedSymbolRenderer.EqualInterval


def apply_path_lines_color_scale(
    layer: QgsVectorLayer,
    epochs: Sequence[float],
) -> None:
    """Apply a graduated cool-to-warm line renderer on ``t_epoch``.

    Args:
        layer: Path-lines memory layer.
        epochs: ``t_epoch`` values of the current segments.
    """
    from qgis.core import QgsSingleSymbolRenderer

    geom_type = layer.geometryType()
    symbol = QgsSymbol.defaultSymbol(geom_type)
    if symbol is None:
        symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.GeometryType.LineGeometry)
    if hasattr(symbol, "setWidth"):
        symbol.setWidth(PATH_LINES_LINE_WIDTH)

    values = [float(value) for value in epochs]
    if len(values) < 2:
        # Single class fallback when there is little or no data.
        color = QColor(0, 70, 255) if not values else QColor(220, 20, 20)
        symbol.setColor(color)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
        return

    minimum = min(values)
    maximum = max(values)
    class_count = min(PATH_LINES_CLASS_COUNT, max(2, len(set(values))))
    renderer = QgsGraduatedSymbolRenderer.createRenderer(
        layer,
        "t_epoch",
        class_count,
        _equal_interval_mode(),
        symbol,
        _direction_color_ramp(),
    )
    layer.setRenderer(renderer)
    logger.debug(
        "Path lines color scale applied (%d classes, %.0f..%.0f)",
        class_count,
        minimum,
        maximum,
    )
    layer.triggerRepaint()


def rebuild_path_lines_layer(
    layer: QgsVectorLayer,
    segments: Sequence[SnakeSegment],
) -> int:
    """Replace all features on the path-lines layer with ``segments``.

    Args:
        layer: Path-lines memory layer.
        segments: Segments to draw.

    Returns:
        Number of features written.
    """
    layer.startEditing()
    epochs: List[float] = []
    try:
        # Delete existing features.
        feature_ids = [feature.id() for feature in layer.getFeatures()]
        if feature_ids:
            layer.deleteFeatures(feature_ids)

        features: List[QgsFeature] = []
        for segment in segments:
            feature = QgsFeature(layer.fields())
            line = QgsLineString(
                [
                    QgsPointXY(segment.east_a, segment.north_a),
                    QgsPointXY(segment.east_b, segment.north_b),
                ]
            )
            start_qt = _segment_qdatetime(segment.seg_start)
            end_qt = _segment_qdatetime(segment.seg_end)
            epoch = float(parse_observed_at(segment.seg_start).timestamp())
            epochs.append(epoch)
            feature.setGeometry(QgsGeometry(line))
            feature.setAttribute("interval_id", segment.interval_id)
            feature.setAttribute("seg_start", start_qt)
            feature.setAttribute("seg_end", end_qt)
            feature.setAttribute("t_epoch", epoch)
            feature.setAttribute("obs_id_a", segment.obs_id_a)
            feature.setAttribute("obs_id_b", segment.obs_id_b)
            features.append(feature)
        layer.addFeatures(features)
        layer.commitChanges()
    except Exception:
        layer.rollBack()
        logger.exception("Failed to rebuild path lines layer")
        raise

    apply_path_lines_color_scale(layer, epochs)
    logger.debug("Path lines layer rebuilt with %d segments", len(segments))
    return len(segments)


def add_path_lines_layer(
    layer: QgsVectorLayer,
    project: Optional[QgsProject] = None,
    *,
    after_layer: Optional[QgsVectorLayer] = None,
) -> None:
    """Add the path-lines layer to the project legend.

    Args:
        layer: Path-lines memory layer.
        project: Project to add to (defaults to the current instance).
        after_layer: When provided, insert the layer just above this
            layer in the layer tree.
    """
    project = project or QgsProject.instance()
    project.addMapLayer(layer, addToLegend=True)

    # Place the path lines next to the observations layer when possible.
    if after_layer is None:
        return
    root = project.layerTreeRoot()
    path_node = root.findLayer(layer.id())
    after_node = root.findLayer(after_layer.id())
    if path_node is None or after_node is None:
        return
    parent = after_node.parent()
    if parent is None:
        return
    cloned = path_node.clone()
    index = parent.children().index(after_node)
    parent.insertChildNode(index, cloned)
    parent.removeChildNode(path_node)
