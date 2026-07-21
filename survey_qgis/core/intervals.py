"""Observation-level survey interval computation."""

from __future__ import annotations

import datetime
import logging
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.engine import Engine

from survey_qgis.core.observations import ObservationRow, load_observations
from survey_qgis.core.schema import (
    DEFAULT_GAP_SECONDS,
    INTERVALS_TABLE,
    OBSERVATIONS_TABLE,
    ensure_plugin_schema,
    set_config,
)

logger = logging.getLogger(__name__)

__all__ = [
    "IntervalRecord",
    "compute_intervals",
    "list_intervals",
    "parse_observed_at",
]


class IntervalRecord(NamedTuple):
    """One continuous stretch of survey observations.

    Attributes:
        id: Interval id after persistence (None before insert).
        source_file_id: Source file when grouping by source, else None.
        started_at: First observation timestamp (ISO-8601 UTC).
        ended_at: Last observation timestamp (ISO-8601 UTC).
        observation_count: Number of observations in the interval.
        threshold_seconds: Gap threshold used to compute the interval.
        group_by_source: Whether intervals were grouped by source file.
        observation_ids: Observation row ids belonging to this interval.
    """

    id: Optional[int]
    source_file_id: Optional[int]
    started_at: str
    ended_at: str
    observation_count: int
    threshold_seconds: int
    group_by_source: bool
    observation_ids: Tuple[int, ...]


def parse_observed_at(value: str) -> datetime.datetime:
    """Parse an observation timestamp into an aware UTC datetime.

    Args:
        value: ISO-8601 timestamp string from the database.

    Returns:
        Timezone-aware UTC datetime.
    """
    text_value = str(value).strip()
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    parsed = datetime.datetime.fromisoformat(text_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _split_group(
    observations: Sequence[ObservationRow],
    *,
    threshold_seconds: int,
    group_by_source: bool,
    source_file_id: Optional[int],
) -> List[IntervalRecord]:
    """Split one ordered observation group into intervals by gap."""
    if not observations:
        return []

    threshold = datetime.timedelta(seconds=threshold_seconds)
    intervals: List[IntervalRecord] = []
    current_ids: List[int] = []
    current_start: Optional[str] = None
    current_end: Optional[str] = None
    previous_time: Optional[datetime.datetime] = None

    for obs in observations:
        if obs.id is None or obs.observed_at is None:
            continue
        observed = parse_observed_at(obs.observed_at)
        if previous_time is not None and (observed - previous_time) > threshold:
            intervals.append(
                IntervalRecord(
                    id=None,
                    source_file_id=source_file_id if group_by_source else None,
                    started_at=current_start or obs.observed_at,
                    ended_at=current_end or obs.observed_at,
                    observation_count=len(current_ids),
                    threshold_seconds=threshold_seconds,
                    group_by_source=group_by_source,
                    observation_ids=tuple(current_ids),
                )
            )
            current_ids = []
            current_start = None
            current_end = None

        if current_start is None:
            current_start = obs.observed_at
        current_end = obs.observed_at
        current_ids.append(obs.id)
        previous_time = observed

    if current_ids and current_start and current_end:
        intervals.append(
            IntervalRecord(
                id=None,
                source_file_id=source_file_id if group_by_source else None,
                started_at=current_start,
                ended_at=current_end,
                observation_count=len(current_ids),
                threshold_seconds=threshold_seconds,
                group_by_source=group_by_source,
                observation_ids=tuple(current_ids),
            )
        )
    return intervals


def build_interval_records(
    observations: Sequence[ObservationRow],
    *,
    threshold_seconds: int = DEFAULT_GAP_SECONDS,
    group_by_source: bool = False,
) -> List[IntervalRecord]:
    """Compute intervals from in-memory observations (pure, testable).

    Args:
        observations: Observations with non-null times preferred.
        threshold_seconds: Gap that starts a new interval.
        group_by_source: When True, split independently per source file.

    Returns:
        Interval records ordered by ``started_at``.
    """
    timed = [obs for obs in observations if obs.observed_at and obs.id]
    if not timed:
        return []

    groups: Dict[Optional[int], List[ObservationRow]] = defaultdict(list)
    if group_by_source:
        for obs in timed:
            groups[obs.source_file_id].append(obs)
    else:
        groups[None] = list(timed)

    result: List[IntervalRecord] = []
    for source_file_id, group in groups.items():
        ordered = sorted(
            group,
            key=lambda item: (
                parse_observed_at(item.observed_at or ""),
                item.id or 0,
            ),
        )
        result.extend(
            _split_group(
                ordered,
                threshold_seconds=threshold_seconds,
                group_by_source=group_by_source,
                source_file_id=source_file_id,
            )
        )

    result.sort(key=lambda item: parse_observed_at(item.started_at))
    return result


def compute_intervals(
    engine: Engine,
    *,
    threshold_seconds: int = DEFAULT_GAP_SECONDS,
    group_by_source: bool = False,
) -> List[IntervalRecord]:
    """Recompute and persist intervals for all timed observations.

    Regenerates ``survey_intervals`` and rewrites ``interval_id`` on
    ``survey_observations``.

    Args:
        engine: Survey GeoPackage engine.
        threshold_seconds: Gap threshold in seconds.
        group_by_source: Whether to group intervals by source file.

    Returns:
        Persisted interval records with ids.
    """
    ensure_plugin_schema(engine)
    observations = load_observations(engine, require_time=True)
    records = build_interval_records(
        observations,
        threshold_seconds=threshold_seconds,
        group_by_source=group_by_source,
    )

    persisted: List[IntervalRecord] = []
    with engine.begin() as connection:
        connection.execute(text(f"DELETE FROM {INTERVALS_TABLE}"))
        connection.execute(
            text(
                f"UPDATE {OBSERVATIONS_TABLE} SET interval_id = NULL"
            )
        )

        for record in records:
            result = connection.execute(
                text(
                    f"INSERT INTO {INTERVALS_TABLE} ("
                    "  source_file_id, started_at, ended_at, "
                    "  observation_count, threshold_seconds, "
                    "  group_by_source"
                    ") VALUES ("
                    "  :source_file_id, :started_at, :ended_at, "
                    "  :observation_count, :threshold_seconds, "
                    "  :group_by_source"
                    ")"
                ),
                {
                    "source_file_id": record.source_file_id,
                    "started_at": record.started_at,
                    "ended_at": record.ended_at,
                    "observation_count": record.observation_count,
                    "threshold_seconds": record.threshold_seconds,
                    "group_by_source": 1 if record.group_by_source else 0,
                },
            )
            interval_id = int(result.lastrowid)
            if record.observation_ids:
                # Update interval_id for each observation in this stretch.
                placeholders = ", ".join(
                    f":id_{index}"
                    for index, _ in enumerate(record.observation_ids)
                )
                params = {
                    f"id_{index}": obs_id
                    for index, obs_id in enumerate(record.observation_ids)
                }
                params["interval_id"] = interval_id
                connection.execute(
                    text(
                        f"UPDATE {OBSERVATIONS_TABLE} "
                        f"SET interval_id = :interval_id "
                        f"WHERE id IN ({placeholders})"
                    ),
                    params,
                )
            persisted.append(record._replace(id=interval_id))

    set_config(engine, "gap_seconds", str(threshold_seconds))
    set_config(
        engine,
        "group_by_source",
        "1" if group_by_source else "0",
    )
    logger.info(
        "Computed %d intervals (threshold=%ds, group_by_source=%s)",
        len(persisted),
        threshold_seconds,
        group_by_source,
    )
    return persisted


def list_intervals(
    engine: Engine,
    *,
    start: Optional[datetime.datetime] = None,
    end: Optional[datetime.datetime] = None,
) -> List[IntervalRecord]:
    """List persisted intervals, optionally filtered by date range.

    An interval is included when it overlaps ``[start, end]``. Filtering
    is done in Python after parsing timestamps so mixed SQLite datetime
    text formats remain comparable.

    Args:
        engine: Survey GeoPackage engine.
        start: Inclusive lower bound on ``ended_at``.
        end: Inclusive upper bound on ``started_at``.

    Returns:
        Interval records ordered by ``started_at``.
    """
    ensure_plugin_schema(engine)

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                f"SELECT "
                f"  id, source_file_id, started_at, ended_at, "
                f"  observation_count, threshold_seconds, group_by_source "
                f"FROM {INTERVALS_TABLE} "
                f"ORDER BY started_at, id"
            )
        ).fetchall()

        result: List[IntervalRecord] = []
        for row in rows:
            started_at = str(row[2])
            ended_at = str(row[3])
            started = parse_observed_at(started_at)
            ended = parse_observed_at(ended_at)
            if start is not None and ended < start.astimezone(
                datetime.timezone.utc
            ):
                continue
            if end is not None and started > end.astimezone(
                datetime.timezone.utc
            ):
                continue

            obs_ids = connection.execute(
                text(
                    f"SELECT id FROM {OBSERVATIONS_TABLE} "
                    f"WHERE interval_id = :interval_id "
                    f"ORDER BY seq, id"
                ),
                {"interval_id": int(row[0])},
            ).fetchall()
            result.append(
                IntervalRecord(
                    id=int(row[0]),
                    source_file_id=(
                        int(row[1]) if row[1] is not None else None
                    ),
                    started_at=started_at,
                    ended_at=ended_at,
                    observation_count=int(row[4]),
                    threshold_seconds=int(row[5]),
                    group_by_source=bool(row[6]),
                    observation_ids=tuple(int(item[0]) for item in obs_ids),
                )
            )
    return result
