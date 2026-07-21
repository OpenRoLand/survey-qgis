"""Tests for observation materialization."""

from __future__ import annotations

from sqlalchemy import text

from survey_qgis.core.observations import load_observations, materialize_observations
from survey_qgis.core.schema import OBSERVATIONS_TABLE, ensure_plugin_schema


class TestMaterializeObservations:
    """Cover materialize_observations and load_observations."""

    def test_materialize_copies_geom_and_times(self, seeded_engine):
        """Observations get geom and prefer association timestamps."""
        rows = load_observations(seeded_engine)
        assert len(rows) == 8
        timed = [row for row in rows if row.observed_at is not None]
        assert len(timed) == 7
        for row in timed:
            assert row.geom is not None
            assert row.east is not None
            assert row.north is not None
            assert row.seq is not None

    def test_seq_orders_by_time(self, seeded_engine):
        """Global seq follows observation time."""
        timed = load_observations(seeded_engine, require_time=True)
        times = [row.observed_at for row in timed]
        assert times == sorted(times)
        seqs = [row.seq for row in timed]
        assert seqs == sorted(seqs)

    def test_rematerialize_replaces_rows(self, seeded_engine):
        """A second materialize clears and rewrites observations."""
        first = materialize_observations(seeded_engine)
        second = materialize_observations(seeded_engine)
        assert first == second
        with seeded_engine.connect() as connection:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM {OBSERVATIONS_TABLE}")
            ).scalar()
        assert int(count) == first

    def test_ensure_plugin_schema_idempotent(self, engine):
        """Calling ensure_plugin_schema twice does not fail."""
        ensure_plugin_schema(engine)
        ensure_plugin_schema(engine)
