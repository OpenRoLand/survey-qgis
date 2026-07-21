"""Optional QGIS smoke tests (skipped when qgis is unavailable)."""

from __future__ import annotations

import pytest

from survey_qgis.core.intervals import compute_intervals
from survey_qgis.core.schema import OBSERVATIONS_TABLE

qgis = pytest.importorskip("qgis.core")


class TestQgisObservationsLayer:
    """Smoke-test opening survey_observations as a QgsVectorLayer."""

    def test_subset_string_filters_intervals(
        self, seeded_engine, gpkg_path, qgis_app
    ):
        """A subset string on interval_id reduces the feature count."""
        from qgis.core import QgsVectorLayer

        intervals = compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        assert len(intervals) >= 1
        uri = f"{gpkg_path.as_posix()}|layername={OBSERVATIONS_TABLE}"
        layer = QgsVectorLayer(uri, "obs", "ogr")
        assert layer.isValid()

        total = layer.featureCount()
        assert total >= 7

        first_id = intervals[0].id
        layer.setSubsetString(f"interval_id = {first_id}")
        filtered = layer.featureCount()
        assert 0 < filtered < total
