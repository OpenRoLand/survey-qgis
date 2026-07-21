"""Snake line segments between consecutive-in-time observations."""

from __future__ import annotations

import logging
from typing import Iterable, List, NamedTuple, Optional, Sequence, Set

from survey_qgis.core.intervals import parse_observed_at
from survey_qgis.core.observations import ObservationRow

logger = logging.getLogger(__name__)

__all__ = [
    "SnakeSegment",
    "build_snake_segments",
]


class SnakeSegment(NamedTuple):
    """One line segment between consecutive observations in an interval.

    Attributes:
        interval_id: Interval that owns both endpoints.
        east_a: Easting of the earlier observation.
        north_a: Northing of the earlier observation.
        east_b: Easting of the later observation.
        north_b: Northing of the later observation.
        seg_start: Timestamp of the earlier observation (ISO-8601).
        seg_end: Timestamp of the later observation (ISO-8601).
        obs_id_a: Observation id of the earlier endpoint.
        obs_id_b: Observation id of the later endpoint.
    """

    interval_id: int
    east_a: float
    north_a: float
    east_b: float
    north_b: float
    seg_start: str
    seg_end: str
    obs_id_a: int
    obs_id_b: int


def build_snake_segments(
    observations: Sequence[ObservationRow],
    *,
    interval_ids: Optional[Iterable[int]] = None,
) -> List[SnakeSegment]:
    """Build snake segments within each interval (never across gaps).

    Args:
        observations: Observations that already have ``interval_id`` and
            coordinates.
        interval_ids: When provided, only include these intervals.

    Returns:
        Segments ordered by ``seg_start``.
    """
    allowed: Optional[Set[int]] = None
    if interval_ids is not None:
        allowed = {int(item) for item in interval_ids}

    by_interval: dict[int, List[ObservationRow]] = {}
    for obs in observations:
        if obs.interval_id is None:
            continue
        if allowed is not None and obs.interval_id not in allowed:
            continue
        if (
            obs.east is None
            or obs.north is None
            or obs.observed_at is None
            or obs.id is None
        ):
            continue
        by_interval.setdefault(obs.interval_id, []).append(obs)

    segments: List[SnakeSegment] = []
    for interval_id, group in by_interval.items():
        ordered = sorted(
            group,
            key=lambda item: (
                parse_observed_at(item.observed_at or ""),
                item.id or 0,
            ),
        )
        for index in range(len(ordered) - 1):
            left = ordered[index]
            right = ordered[index + 1]
            segments.append(
                SnakeSegment(
                    interval_id=interval_id,
                    east_a=float(left.east),
                    north_a=float(left.north),
                    east_b=float(right.east),
                    north_b=float(right.north),
                    seg_start=str(left.observed_at),
                    seg_end=str(right.observed_at),
                    obs_id_a=int(left.id),
                    obs_id_b=int(right.id),
                )
            )

    segments.sort(key=lambda item: parse_observed_at(item.seg_start))
    logger.log(1, "Built %d snake segments", len(segments))
    return segments
