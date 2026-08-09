"""Canvas snake overlay drawn with colored QgsRubberBand segments."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsLineString,
    QgsPointXY,
    QgsProject,
    QgsWkbTypes,
)
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtGui import QColor

from survey_qgis.core.intervals import parse_observed_at
from survey_qgis.core.snake import SnakeSegment, snake_segment_rgb

logger = logging.getLogger(__name__)

__all__ = [
    "SnakeOverlay",
    "snake_segment_color",
]

SNAKE_SOURCE_CRS = "EPSG:3844"
SNAKE_LINE_WIDTH = 2.0


def _line_geometry_type():
    """Return the Line geometry type enum for Qt5/Qt6 QGIS."""
    geom = getattr(QgsWkbTypes, "GeometryType", None)
    if geom is not None:
        return geom.LineGeometry
    return QgsWkbTypes.LineGeometry


def snake_segment_color(index: int, count: int) -> QColor:
    """Return blue→red color for segment ``index`` in a visible set.

    Args:
        index: Zero-based position among visible segments (oldest
            first).
        count: Number of visible segments.

    Returns:
        Interpolated ``QColor``.
    """
    return QColor(*snake_segment_rgb(index, count))


def _qdatetime_is_valid(value) -> bool:
    """Return whether a Qt datetime value is usable."""
    if value is None:
        return False
    if hasattr(value, "isValid"):
        return bool(value.isValid())
    return True


class SnakeOverlay:
    """Ephemeral snake drawn on the map canvas with a blue→red ramp.

    Each visible segment gets its own rubber band so colors can vary.
    Colors are recomputed from the currently visible set on every
    redraw (oldest blue, newest red).

    Attributes:
        canvas: Map canvas that owns the rubber bands.
    """

    def __init__(self, canvas: QgsMapCanvas) -> None:
        """Create an empty overlay bound to ``canvas``.

        Args:
            canvas: QGIS map canvas.
        """
        self.canvas = canvas
        self._rubbers: List[QgsRubberBand] = []
        self._rubber_colors: List[QColor] = []
        self._segments: List[SnakeSegment] = []
        self._enabled = False
        self._filter_by_time = False
        self._window_start = None
        self._window_end = None

    def set_enabled(self, enabled: bool) -> None:
        """Show or hide the overlay.

        Args:
            enabled: Whether the snake should be drawn.
        """
        self._enabled = bool(enabled)
        self._redraw()

    def is_enabled(self) -> bool:
        """Return whether the overlay is enabled."""
        return self._enabled

    def set_time_filter(
        self,
        active: bool,
        *,
        start=None,
        end=None,
    ) -> None:
        """Configure optional temporal filtering of segments.

        Args:
            active: When True, only segments overlapping the window.
            start: Window start as ``QDateTime`` or aware datetime.
            end: Window end as ``QDateTime`` or aware datetime.
        """
        self._filter_by_time = bool(active)
        self._window_start = start
        self._window_end = end
        self._redraw()

    def set_segments(self, segments: Sequence[SnakeSegment]) -> None:
        """Replace the cached segments and redraw.

        Args:
            segments: Full segment list for the selected intervals.
        """
        self._segments = list(segments)
        self._redraw()

    def rubber_band_count(self) -> int:
        """Return how many rubber bands are currently drawn."""
        return len(self._rubbers)

    def rubber_band_colors(self) -> List[QColor]:
        """Return the colors assigned to the currently drawn bands."""
        return list(self._rubber_colors)

    def clear(self) -> None:
        """Clear cached segments and hide all rubber bands."""
        self._segments = []
        self._clear_rubbers()

    def destroy(self) -> None:
        """Remove all rubber bands from the canvas scene."""
        self._segments = []
        self._clear_rubbers()

    def _clear_rubbers(self) -> None:
        """Reset and remove every rubber band item."""
        scene = self.canvas.scene()
        for rubber in self._rubbers:
            rubber.reset(_line_geometry_type())
            rubber.setVisible(False)
            if scene is not None:
                scene.removeItem(rubber)
        self._rubbers = []
        self._rubber_colors = []

    def _visible_segments(self) -> List[SnakeSegment]:
        """Return segments that should be drawn right now."""
        if not self._enabled:
            return []
        if not self._filter_by_time:
            return list(self._segments)
        if (
            not _qdatetime_is_valid(self._window_start)
            or not _qdatetime_is_valid(self._window_end)
        ):
            return list(self._segments)

        window_start = self._to_epoch(self._window_start)
        window_end = self._to_epoch(self._window_end)
        if window_start is None or window_end is None:
            return list(self._segments)

        visible: List[SnakeSegment] = []
        for segment in self._segments:
            seg_start = parse_observed_at(segment.seg_start).timestamp()
            seg_end = parse_observed_at(segment.seg_end).timestamp()
            # Overlap: segment intersects the sliding window.
            if seg_end >= window_start and seg_start <= window_end:
                visible.append(segment)
        return visible

    @staticmethod
    def _to_epoch(value) -> Optional[float]:
        """Convert a Qt or Python datetime to a Unix epoch."""
        if value is None:
            return None
        if hasattr(value, "toSecsSinceEpoch"):
            if hasattr(value, "isValid") and not value.isValid():
                return None
            return float(value.toSecsSinceEpoch())
        if hasattr(value, "timestamp"):
            return float(value.timestamp())
        return None

    def _transform(self) -> Optional[QgsCoordinateTransform]:
        """Build a transform from survey CRS to the canvas CRS."""
        source = QgsCoordinateReferenceSystem(SNAKE_SOURCE_CRS)
        destination = self.canvas.mapSettings().destinationCrs()
        if not destination.isValid():
            return None
        return QgsCoordinateTransform(
            source,
            destination,
            QgsProject.instance(),
        )

    def _segment_geometry(
        self,
        segment: SnakeSegment,
        transform: Optional[QgsCoordinateTransform],
    ) -> Optional[QgsGeometry]:
        """Build a canvas-CRS geometry for one segment."""
        line = QgsLineString(
            [
                QgsPointXY(segment.east_a, segment.north_a),
                QgsPointXY(segment.east_b, segment.north_b),
            ]
        )
        geometry = QgsGeometry(line)
        if transform is None:
            return geometry
        try:
            geometry.transform(transform)
        except Exception:
            logger.log(
                1,
                "Failed to transform snake segment",
                exc_info=True,
            )
            return None
        return geometry

    def _redraw(self) -> None:
        """Rebuild rubber bands from the visible segments."""
        self._clear_rubbers()
        visible = self._visible_segments()
        if not visible:
            return

        # Oldest → newest so colors map blue → red within this step.
        ordered = sorted(
            visible,
            key=lambda item: parse_observed_at(item.seg_start),
        )
        transform = self._transform()
        count = len(ordered)
        for index, segment in enumerate(ordered):
            geometry = self._segment_geometry(segment, transform)
            if geometry is None:
                continue
            rubber = QgsRubberBand(self.canvas, _line_geometry_type())
            rubber.setWidth(SNAKE_LINE_WIDTH)
            color = snake_segment_color(index, count)
            rubber.setColor(color)
            rubber.setToGeometry(geometry, None)
            rubber.setVisible(True)
            rubber.updatePosition()
            self._rubbers.append(rubber)
            self._rubber_colors.append(color)

        logger.log(
            1,
            "Snake overlay drew %d colored segments",
            len(self._rubbers),
        )
