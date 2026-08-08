"""Materialize survey_observations from points and source associations."""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from survey_qgis.core.schema import OBSERVATIONS_TABLE, ensure_plugin_schema

logger = logging.getLogger(__name__)

__all__ = [
    "ObservationRow",
    "materialize_observations",
    "load_observations",
]


class ObservationRow(NamedTuple):
    """One observation used for intervals and snake construction.

    Attributes:
        id: Row id in ``survey_observations`` (None before insert).
        point_id: Canonical survey point id.
        source_file_id: Source file version id.
        observed_at: ISO-8601 UTC timestamp string, or None.
        name: Point name when available.
        code: Point code when available.
        geom: GeoPackageBinary POINT blob.
        east: Easting in metres (decoded), when available.
        north: Northing in metres (decoded), when available.
        interval_id: Assigned interval id, when computed.
        seq: Global time-order sequence, when assigned.
    """

    id: Optional[int]
    point_id: int
    source_file_id: int
    observed_at: Optional[str]
    name: Optional[str]
    code: Optional[str]
    geom: Optional[bytes]
    east: Optional[float]
    north: Optional[float]
    interval_id: Optional[int] = None
    seq: Optional[int] = None


def materialize_observations(engine: Engine) -> int:
    """Refresh ``survey_observations`` from points and associations.

    Existing interval assignments are cleared; call
    :func:`~survey_qgis.core.intervals.compute_intervals` afterwards.
    Geometry is copied from the parent ``survey_points`` row. Observation
    time prefers ``survey_point_sources.observed_at`` and falls back to
    ``survey_points.observed_at_utc``.

    Args:
        engine: Survey GeoPackage engine.

    Returns:
        Number of observation rows written.
    """
    ensure_plugin_schema(engine)

    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {OBSERVATIONS_TABLE}"))
        result = connection.execute(
            text(
                f"INSERT INTO {OBSERVATIONS_TABLE} ("
                "  point_id, source_file_id, observed_at, interval_id, "
                "  seq, name, code, description, geom"
                ") "
                "SELECT "
                "  sps.survey_point_id, "
                "  sps.source_file_id, "
                "  COALESCE(sps.observed_at, sp.observed_at_utc), "
                "  NULL, "
                "  NULL, "
                "  sp.name, "
                "  sp.code, "
                "  sp.description, "
                "  sp.geom "
                "FROM survey_point_sources AS sps "
                "JOIN survey_points AS sp "
                "  ON sp.id = sps.survey_point_id"
            )
        )
        count = int(result.rowcount or 0)

        # Assign a stable global sequence ordered by observation time.
        connection.execute(
            text(
                f"WITH ordered AS ("
                f"  SELECT id, "
                f"    ROW_NUMBER() OVER ("
                f"      ORDER BY observed_at IS NULL, observed_at, id"
                f"    ) AS rn "
                f"  FROM {OBSERVATIONS_TABLE}"
                f") "
                f"UPDATE {OBSERVATIONS_TABLE} "
                f"SET seq = ("
                f"  SELECT rn FROM ordered WHERE ordered.id = "
                f"  {OBSERVATIONS_TABLE}.id"
                f")"
            )
        )

    logger.info("Materialized %d survey observations", count)
    return count


def load_observations(
    engine: Engine,
    *,
    require_time: bool = False,
) -> List[ObservationRow]:
    """Load observation rows for interval/snake algorithms.

    Args:
        engine: Survey GeoPackage engine.
        require_time: When True, skip rows with a null ``observed_at``.

    Returns:
        Observation rows ordered by ``seq`` then ``id``.
    """
    ensure_plugin_schema(engine)
    where = "WHERE observed_at IS NOT NULL" if require_time else ""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                f"SELECT "
                f"  o.id, o.point_id, o.source_file_id, o.observed_at, "
                f"  o.name, o.code, o.geom, "
                f"  CAST(sp.east AS REAL), CAST(sp.north AS REAL), "
                f"  o.interval_id, o.seq "
                f"FROM {OBSERVATIONS_TABLE} AS o "
                f"JOIN survey_points AS sp ON sp.id = o.point_id "
                f"{where} "
                f"ORDER BY o.seq IS NULL, o.seq, o.id"
            )
        ).fetchall()

    return [
        ObservationRow(
            id=int(row[0]),
            point_id=int(row[1]),
            source_file_id=int(row[2]),
            observed_at=row[3],
            name=row[4],
            code=row[5],
            geom=row[6],
            east=float(row[7]) if row[7] is not None else None,
            north=float(row[8]) if row[8] is not None else None,
            interval_id=int(row[9]) if row[9] is not None else None,
            seq=int(row[10]) if row[10] is not None else None,
        )
        for row in rows
    ]
