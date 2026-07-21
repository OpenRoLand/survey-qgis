"""Plugin-owned tables for survey observations and intervals.

Creates ``survey_observations`` (registered GeoPackage POINT feature
table), ``survey_intervals``, and ``survey_qgis_config`` on demand. Never
drops existing user data.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from siscadro_survey.geopackage import LAYER_SRS_ID

logger = logging.getLogger(__name__)

__all__ = [
    "OBSERVATIONS_TABLE",
    "INTERVALS_TABLE",
    "CONFIG_TABLE",
    "DEFAULT_GAP_SECONDS",
    "ensure_plugin_schema",
    "get_config",
    "set_config",
]

OBSERVATIONS_TABLE = "survey_observations"
INTERVALS_TABLE = "survey_intervals"
CONFIG_TABLE = "survey_qgis_config"
DEFAULT_GAP_SECONDS = 1800


def ensure_plugin_schema(engine: Engine) -> None:
    """Create plugin tables and register the observations feature layer.

    Idempotent: existing tables and catalog rows are left alone when
    compatible.

    Args:
        engine: Engine for the survey GeoPackage.
    """
    with engine.begin() as connection:
        _create_observations_table(connection)
        _create_intervals_table(connection)
        _create_config_table(connection)
        _register_observations_layer(connection)
    logger.debug("Plugin schema ensured on %s", engine.url)


def _create_observations_table(connection: Connection) -> None:
    """Create the materialized observations feature table."""
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {OBSERVATIONS_TABLE} ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  point_id INTEGER NOT NULL,"
            "  source_file_id INTEGER NOT NULL,"
            "  observed_at TEXT,"
            "  interval_id INTEGER,"
            "  seq INTEGER,"
            "  name TEXT,"
            "  code TEXT,"
            "  geom BLOB,"
            "  FOREIGN KEY (point_id) REFERENCES survey_points(id),"
            "  FOREIGN KEY (source_file_id) REFERENCES source_files(id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS "
            f"ix_{OBSERVATIONS_TABLE}_observed_at "
            f"ON {OBSERVATIONS_TABLE}(observed_at)"
        )
    )
    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS "
            f"ix_{OBSERVATIONS_TABLE}_interval_id "
            f"ON {OBSERVATIONS_TABLE}(interval_id)"
        )
    )
    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS "
            f"ix_{OBSERVATIONS_TABLE}_source_file_id "
            f"ON {OBSERVATIONS_TABLE}(source_file_id)"
        )
    )
    connection.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS "
            f"uq_{OBSERVATIONS_TABLE}_point_source "
            f"ON {OBSERVATIONS_TABLE}(point_id, source_file_id)"
        )
    )


def _create_intervals_table(connection: Connection) -> None:
    """Create the precomputed intervals table."""
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {INTERVALS_TABLE} ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  source_file_id INTEGER,"
            "  started_at TEXT NOT NULL,"
            "  ended_at TEXT NOT NULL,"
            "  observation_count INTEGER NOT NULL DEFAULT 0,"
            "  threshold_seconds INTEGER NOT NULL,"
            "  group_by_source INTEGER NOT NULL DEFAULT 0,"
            "  FOREIGN KEY (source_file_id) REFERENCES source_files(id)"
            ")"
        )
    )
    connection.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS "
            f"ix_{INTERVALS_TABLE}_started_at "
            f"ON {INTERVALS_TABLE}(started_at)"
        )
    )


def _create_config_table(connection: Connection) -> None:
    """Create the plugin key/value config table."""
    connection.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {CONFIG_TABLE} ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
    )


def _register_observations_layer(connection: Connection) -> None:
    """Register ``survey_observations`` in GeoPackage catalogs."""
    existing = connection.execute(
        text(
            "SELECT srs_id FROM gpkg_contents "
            "WHERE table_name = :table_name"
        ),
        {"table_name": OBSERVATIONS_TABLE},
    ).first()
    if existing is None:
        connection.execute(
            text(
                "INSERT INTO gpkg_contents ("
                "  table_name, data_type, identifier, description, srs_id"
                ") VALUES ("
                "  :table_name, 'features', :identifier, :description, "
                "  :srs_id"
                ")"
            ),
            {
                "table_name": OBSERVATIONS_TABLE,
                "identifier": OBSERVATIONS_TABLE,
                "description": (
                    "Survey observations (EPSG:3844) for QGIS temporal "
                    "filtering"
                ),
                "srs_id": LAYER_SRS_ID,
            },
        )
    elif int(existing[0]) != LAYER_SRS_ID:
        raise RuntimeError(
            "gpkg_contents row for %r uses srs_id %r; expected %r"
            % (OBSERVATIONS_TABLE, existing[0], LAYER_SRS_ID)
        )

    existing_geom = connection.execute(
        text(
            "SELECT srs_id, geometry_type_name, column_name "
            "FROM gpkg_geometry_columns "
            "WHERE table_name = :table_name"
        ),
        {"table_name": OBSERVATIONS_TABLE},
    ).first()
    if existing_geom is None:
        connection.execute(
            text(
                "INSERT INTO gpkg_geometry_columns ("
                "  table_name, column_name, geometry_type_name, "
                "  srs_id, z, m"
                ") VALUES ("
                "  :table_name, 'geom', 'POINT', :srs_id, 0, 0"
                ")"
            ),
            {
                "table_name": OBSERVATIONS_TABLE,
                "srs_id": LAYER_SRS_ID,
            },
        )
        return

    srs_id, geometry_type_name, column_name = existing_geom
    if (
        int(srs_id) != LAYER_SRS_ID
        or str(geometry_type_name).upper() != "POINT"
        or str(column_name) != "geom"
    ):
        raise RuntimeError(
            "gpkg_geometry_columns row for %r is incompatible "
            "(column=%r type=%r srs_id=%r)"
            % (
                OBSERVATIONS_TABLE,
                column_name,
                geometry_type_name,
                srs_id,
            )
        )


def get_config(
    engine: Engine,
    key: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """Read one config value from ``survey_qgis_config``.

    Args:
        engine: Survey GeoPackage engine.
        key: Config key.
        default: Value returned when the key is missing.

    Returns:
        The stored value, or ``default``.
    """
    with engine.connect() as connection:
        row = connection.execute(
            text(f"SELECT value FROM {CONFIG_TABLE} WHERE key = :key"),
            {"key": key},
        ).first()
    if row is None:
        return default
    return str(row[0])


def set_config(engine: Engine, key: str, value: str) -> None:
    """Upsert one config value into ``survey_qgis_config``.

    Args:
        engine: Survey GeoPackage engine.
        key: Config key.
        value: Config value stored as text.
    """
    with engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO {CONFIG_TABLE} (key, value) "
                f"VALUES (:key, :value) "
                f"ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            ),
            {"key": key, "value": value},
        )
