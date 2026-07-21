"""Tests for interval computation."""

from __future__ import annotations

import datetime

from survey_qgis.core.intervals import (
    build_interval_records,
    compute_intervals,
    list_intervals,
)
from survey_qgis.core.observations import ObservationRow, load_observations


class TestBuildIntervalRecords:
    """Pure in-memory interval splitting."""

    def _obs(self, obs_id, source, when, east=1.0, north=1.0):
        return ObservationRow(
            id=obs_id,
            point_id=obs_id,
            source_file_id=source,
            observed_at=when,
            name=None,
            code=None,
            geom=None,
            east=east,
            north=north,
        )

    def test_gap_splits_interval(self):
        """A gap larger than the threshold starts a new interval."""
        observations = [
            self._obs(1, 1, "2024-01-01T10:00:00+00:00"),
            self._obs(2, 1, "2024-01-01T10:10:00+00:00"),
            self._obs(3, 1, "2024-01-01T11:00:00+00:00"),
        ]
        intervals = build_interval_records(
            observations,
            threshold_seconds=1800,
            group_by_source=False,
        )
        assert len(intervals) == 2
        assert intervals[0].observation_count == 2
        assert intervals[1].observation_count == 1

    def test_threshold_boundary_inclusive(self):
        """A gap equal to the threshold does not start a new interval."""
        observations = [
            self._obs(1, 1, "2024-01-01T10:00:00+00:00"),
            self._obs(2, 1, "2024-01-01T10:30:00+00:00"),
        ]
        intervals = build_interval_records(
            observations,
            threshold_seconds=1800,
            group_by_source=False,
        )
        assert len(intervals) == 1
        assert intervals[0].observation_count == 2

    def test_group_by_source_splits_same_wall_time(self):
        """Per-source grouping yields separate intervals for each file."""
        observations = [
            self._obs(1, 1, "2024-01-01T10:00:00+00:00"),
            self._obs(2, 2, "2024-01-01T10:05:00+00:00"),
            self._obs(3, 1, "2024-01-01T10:10:00+00:00"),
            self._obs(4, 2, "2024-01-01T10:15:00+00:00"),
        ]
        intervals = build_interval_records(
            observations,
            threshold_seconds=1800,
            group_by_source=True,
        )
        assert len(intervals) == 2
        sources = {item.source_file_id for item in intervals}
        assert sources == {1, 2}

    def test_null_times_skipped(self):
        """Observations without a timestamp are ignored."""
        observations = [
            self._obs(1, 1, None),
            self._obs(2, 1, "2024-01-01T10:00:00+00:00"),
        ]
        intervals = build_interval_records(
            observations,
            threshold_seconds=1800,
        )
        assert len(intervals) == 1
        assert intervals[0].observation_ids == (2,)


class TestComputeIntervals:
    """Persisted interval computation against a seeded GeoPackage."""

    def test_global_intervals(self, seeded_engine):
        """Without grouping, wall-clock gaps produce two intervals."""
        intervals = compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        # Timed points: 10:00,10:05,10:10,10:15,10:20 then 11:00,11:05.
        assert len(intervals) == 2
        assert intervals[0].observation_count == 5
        assert intervals[1].observation_count == 2

        loaded = load_observations(seeded_engine, require_time=True)
        assigned = [row.interval_id for row in loaded]
        assert None not in assigned

    def test_group_by_source_intervals(self, seeded_engine):
        """Grouping by source yields three intervals for the seeded data."""
        intervals = compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=True,
        )
        # source A: 10:00-10:20 and 11:00-11:05; source B: 10:05-10:15.
        assert len(intervals) == 3
        assert all(item.source_file_id is not None for item in intervals)

    def test_list_intervals_date_filter(self, seeded_engine):
        """Date filter keeps only overlapping intervals."""
        compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        start = datetime.datetime(
            2024, 1, 1, 10, 50, tzinfo=datetime.timezone.utc
        )
        end = datetime.datetime(
            2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc
        )
        filtered = list_intervals(seeded_engine, start=start, end=end)
        assert len(filtered) == 1
        assert filtered[0].observation_count == 2
