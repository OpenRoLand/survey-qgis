"""Core algorithms and GeoPackage helpers for the survey QGIS plugin."""

from survey_qgis.core.db import open_engine, session_factory
from survey_qgis.core.intervals import IntervalRecord, compute_intervals
from survey_qgis.core.observations import (
    ObservationRow,
    load_observations,
    materialize_observations,
)
from survey_qgis.core.schema import ensure_plugin_schema
from survey_qgis.core.snake import SnakeSegment, build_snake_segments

__all__ = [
    "IntervalRecord",
    "ObservationRow",
    "SnakeSegment",
    "build_snake_segments",
    "compute_intervals",
    "ensure_plugin_schema",
    "load_observations",
    "materialize_observations",
    "open_engine",
    "session_factory",
]
