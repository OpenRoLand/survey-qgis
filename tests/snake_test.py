"""Tests for snake segment construction."""

from __future__ import annotations

from survey_qgis.core.intervals import compute_intervals
from survey_qgis.core.observations import ObservationRow, load_observations
from survey_qgis.core.snake import build_snake_segments


class TestBuildSnakeSegments:
    """Cover snake segment rules."""

    def test_no_cross_gap_segments(self, seeded_engine):
        """Segments never bridge distinct intervals."""
        compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        observations = load_observations(seeded_engine, require_time=True)
        segments = build_snake_segments(observations)
        interval_ids = {row.interval_id for row in observations}
        assert len(interval_ids) == 2

        # Within each interval, segments = count - 1.
        expected = 0
        for interval_id in interval_ids:
            count = sum(
                1 for row in observations if row.interval_id == interval_id
            )
            expected += max(0, count - 1)
        assert len(segments) == expected
        for segment in segments:
            assert segment.interval_id in interval_ids
            assert segment.seg_start <= segment.seg_end

    def test_filter_by_interval_ids(self, seeded_engine):
        """Only selected intervals contribute segments."""
        intervals = compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        observations = load_observations(seeded_engine, require_time=True)
        first_id = intervals[0].id
        segments = build_snake_segments(
            observations,
            interval_ids=[first_id],
        )
        assert segments
        assert all(item.interval_id == first_id for item in segments)

    def test_missing_coordinates_skipped(self):
        """Observations without east/north do not create segments."""
        observations = [
            ObservationRow(
                id=1,
                point_id=1,
                source_file_id=1,
                observed_at="2024-01-01T10:00:00+00:00",
                name=None,
                code=None,
                geom=None,
                east=None,
                north=None,
                interval_id=1,
                seq=1,
            ),
            ObservationRow(
                id=2,
                point_id=2,
                source_file_id=1,
                observed_at="2024-01-01T10:01:00+00:00",
                name=None,
                code=None,
                geom=None,
                east=1.0,
                north=1.0,
                interval_id=1,
                seq=2,
            ),
        ]
        assert build_snake_segments(observations) == []
