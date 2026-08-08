"""Managed survey observations QgsVectorLayer helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence, Union

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDateTimeRange,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsVectorLayerTemporalProperties,
)
from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.PyQt.QtGui import QColor, QFont

from survey_qgis.core.schema import OBSERVATIONS_TABLE

logger = logging.getLogger(__name__)

__all__ = [
    "MANAGED_LAYER_PROPERTY",
    "create_observations_layer",
    "is_managed_layer",
    "apply_interval_filter",
    "configure_temporal_properties",
    "configure_point_labels",
    "set_temporal_filtering_active",
    "layer_gpkg_path",
    "datetime_range_from_iso",
]

MANAGED_LAYER_PROPERTY = "openroland_survey_managed"
MANAGED_LAYER_VALUE = "1"
CUSTOM_GPKG_PROPERTY = "openroland_survey_gpkg"


def create_observations_layer(
    gpkg_path: Union[str, Path],
    *,
    name: Optional[str] = None,
) -> QgsVectorLayer:
    """Create a managed vector layer over ``survey_observations``.

    Args:
        gpkg_path: Path to the survey GeoPackage.
        name: Optional layer display name.

    Returns:
        A valid ``QgsVectorLayer`` configured for temporal filtering.

    Raises:
        RuntimeError: If the layer cannot be opened.
    """
    path = Path(gpkg_path).expanduser().resolve()
    uri = f"{path.as_posix()}|layername={OBSERVATIONS_TABLE}"
    layer_name = name or f"Survey observations ({path.stem})"
    layer = QgsVectorLayer(uri, layer_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(
            "Failed to open survey observations layer from %s: %s"
            % (path, layer.error().message())
        )

    layer.setCrs(QgsCoordinateReferenceSystem("EPSG:3844"))
    layer.setCustomProperty(MANAGED_LAYER_PROPERTY, MANAGED_LAYER_VALUE)
    layer.setCustomProperty(CUSTOM_GPKG_PROPERTY, str(path))
    configure_temporal_properties(layer)
    configure_point_labels(layer)
    logger.info("Created managed survey layer from %s", path)
    return layer


def is_managed_layer(layer) -> bool:
    """Return whether ``layer`` is a plugin-managed survey layer.

    Args:
        layer: A map layer instance (or None).
    """
    if layer is None:
        return False
    if not isinstance(layer, QgsVectorLayer):
        return False
    return (
        str(layer.customProperty(MANAGED_LAYER_PROPERTY, ""))
        == MANAGED_LAYER_VALUE
    )


def layer_gpkg_path(layer: QgsVectorLayer) -> Optional[Path]:
    """Return the GeoPackage path stored on a managed layer."""
    value = layer.customProperty(CUSTOM_GPKG_PROPERTY, "")
    if not value:
        # Fall back to parsing the data provider URI.
        source = layer.source()
        if "|layername=" in source:
            value = source.split("|layername=", 1)[0]
    if not value:
        return None
    return Path(str(value))


def apply_interval_filter(
    layer: QgsVectorLayer,
    interval_ids: Optional[Sequence[int]] = None,
) -> None:
    """Apply a subset string selecting the given interval ids.

    An empty or None selection clears the subset (shows all timed
    observations that have an interval).

    Args:
        layer: Managed observations layer.
        interval_ids: Interval ids to keep visible.
    """
    if not interval_ids:
        # Show all observations that belong to any computed interval.
        expression = "interval_id IS NOT NULL"
    else:
        ids = ", ".join(str(int(item)) for item in interval_ids)
        expression = f"interval_id IN ({ids})"
    layer.setSubsetString(expression)
    layer.triggerRepaint()
    logger.debug("Applied subset %s on layer %s", expression, layer.id())


def configure_point_labels(layer: QgsVectorLayer) -> None:
    """Label points with description when set, otherwise point name.

    Args:
        layer: Managed observations layer.
    """
    settings = QgsPalLayerSettings()
    # Prefer description; fall back to the survey point number/name.
    expression = (
        "coalesce("
        "nullif(trim(description), ''), "
        "nullif(trim(name), '')"
        ")"
    )
    if hasattr(settings, "setFieldName"):
        settings.setFieldName(expression)
        if hasattr(settings, "setIsExpression"):
            settings.setIsExpression(True)
    else:
        settings.fieldName = expression
        settings.isExpression = True

    # Keep labels readable over survey basemaps.
    text_format = QgsTextFormat()
    text_format.setSize(9)
    text_format.setColor(QColor(20, 20, 20))
    font = QFont()
    font.setPointSize(9)
    text_format.setFont(font)
    buffer_settings = text_format.buffer()
    if hasattr(buffer_settings, "setEnabled"):
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(0.8)
        buffer_settings.setColor(QColor(255, 255, 255))
        text_format.setBuffer(buffer_settings)
    if hasattr(settings, "setFormat"):
        settings.setFormat(text_format)
    else:
        settings.format = text_format

    if hasattr(settings, "setPlacement"):
        around_point = getattr(
            QgsPalLayerSettings,
            "AroundPoint",
            None,
        )
        if around_point is None:
            around_point = QgsPalLayerSettings.Placement.AroundPoint
        settings.setPlacement(around_point)
    else:
        settings.placement = QgsPalLayerSettings.AroundPoint

    labeling = QgsVectorLayerSimpleLabeling(settings)
    layer.setLabeling(labeling)
    layer.setLabelsEnabled(True)
    logger.debug("Configured point labels on %s", layer.id())


def configure_temporal_properties(
    layer: QgsVectorLayer,
    *,
    field_name: str = "observed_at",
) -> None:
    """Enable single-field temporal properties on the observations layer.

    Args:
        layer: Managed observations layer.
        field_name: Datetime field used for the sliding window.
    """
    props = layer.temporalProperties()
    # Inactive until the user enables the time-window filter.
    props.setIsActive(False)
    mode = getattr(
        QgsVectorLayerTemporalProperties,
        "ModeFeatureDateTimeInstantFromField",
        None,
    )
    if mode is None:
        mode = (
            QgsVectorLayerTemporalProperties.TemporalMode.ModeFeatureDateTimeInstantFromField
        )
    props.setMode(mode)
    props.setStartField(field_name)

    # Accumulate features inside the current temporal range window.
    if hasattr(props, "setAccumulateFeatures"):
        props.setAccumulateFeatures(False)

    # Limit units help the temporal controller interpret the field.
    if hasattr(props, "setDurationUnits"):
        units = getattr(QgsUnitTypes, "TemporalMilliseconds", None)
        if units is None:
            units = QgsUnitTypes.TemporalUnit.TemporalMilliseconds
        props.setDurationUnits(units)

    layer.setCustomProperty("temporal_field", field_name)
    logger.debug("Configured temporal properties on %s", layer.id())


def set_temporal_filtering_active(
    layer: QgsVectorLayer,
    active: bool,
) -> None:
    """Enable or disable temporal filtering on a vector layer.

    Args:
        layer: Layer whose temporal properties to toggle.
        active: True to filter by the canvas temporal range.
    """
    props = layer.temporalProperties()
    props.setIsActive(bool(active))
    layer.triggerRepaint()
    logger.debug(
        "Temporal filtering %s on layer %s",
        "enabled" if active else "disabled",
        layer.id(),
    )


def datetime_range_from_iso(
    start_iso: str,
    end_iso: str,
) -> QgsDateTimeRange:
    """Build a QgsDateTimeRange from ISO-8601 strings.

    Args:
        start_iso: Range start timestamp.
        end_iso: Range end timestamp.
    """
    start = QDateTime.fromString(start_iso, Qt.DateFormat.ISODate)
    end = QDateTime.fromString(end_iso, Qt.DateFormat.ISODate)
    if not start.isValid():
        start = QDateTime.fromString(
            start_iso.replace("Z", ""),
            "yyyy-MM-ddTHH:mm:ss",
        )
    if not end.isValid():
        end = QDateTime.fromString(
            end_iso.replace("Z", ""),
            "yyyy-MM-ddTHH:mm:ss",
        )
    return QgsDateTimeRange(start, end)
