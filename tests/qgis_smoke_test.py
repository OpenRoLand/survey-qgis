"""Optional QGIS smoke tests (skipped when qgis is unavailable)."""

from __future__ import annotations

import pytest

from survey_qgis.core.intervals import compute_intervals
from survey_qgis.core.observations import load_observations
from survey_qgis.core.schema import OBSERVATIONS_TABLE
from survey_qgis.core.snake import build_snake_segments

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
        layer.reload()
        filtered = layer.featureCount()
        assert 0 < filtered <= total
        assert all(
            feature["interval_id"] == first_id
            for feature in layer.getFeatures()
        )

    def test_managed_layer_labels_prefer_description(
        self, seeded_engine, gpkg_path, qgis_app
    ):
        """Managed layer labels use description, else point name."""
        from survey_qgis.layers.managed_layer import create_observations_layer

        layer = create_observations_layer(gpkg_path)
        assert layer.labelsEnabled()
        labeling = layer.labeling()
        assert labeling is not None
        settings = labeling.settings()
        field_name = (
            settings.fieldName()
            if hasattr(settings, "fieldName")
            and callable(settings.fieldName)
            else settings.fieldName
        )
        assert "description" in field_name
        assert "name" in field_name


class TestQgisPathLinesLayer:
    """Smoke-test path-lines layer visibility, fields, and color scale."""

    def test_path_lines_added_to_legend_with_graduated_style(
        self, seeded_engine, gpkg_path, qgis_app
    ):
        """Path lines are in the layer tree with datetime fields and a ramp."""
        from qgis.core import (
            QgsGraduatedSymbolRenderer,
            QgsProject,
            QgsSingleSymbolRenderer,
        )

        from survey_qgis.layers.managed_layer import create_observations_layer
        from survey_qgis.layers.path_lines_layer import (
            add_path_lines_layer,
            create_path_lines_layer,
            rebuild_path_lines_layer,
        )

        # Materialize intervals so observations have interval_id values.
        compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        observations = load_observations(seeded_engine, require_time=True)
        segments = build_snake_segments(observations)
        assert len(segments) >= 2

        project = QgsProject.instance()
        project.removeAllMapLayers()

        obs_layer = create_observations_layer(gpkg_path)
        project.addMapLayer(obs_layer)

        path_layer = create_path_lines_layer(name="Path lines test")
        add_path_lines_layer(path_layer, after_layer=obs_layer)
        count = rebuild_path_lines_layer(path_layer, segments)
        assert count == len(segments)

        # Layer must be in the project and the legend tree to render.
        assert project.mapLayer(path_layer.id()) is not None
        assert (
            project.layerTreeRoot().findLayer(path_layer.id()) is not None
        )

        # Datetime and epoch attributes are populated.
        feature = next(path_layer.getFeatures())
        start_value = feature.attribute("seg_start")
        epoch_value = feature.attribute("t_epoch")
        assert start_value is not None
        assert epoch_value is not None

        renderer = path_layer.renderer()
        assert isinstance(
            renderer,
            (QgsGraduatedSymbolRenderer, QgsSingleSymbolRenderer),
        )
        if isinstance(renderer, QgsGraduatedSymbolRenderer):
            assert renderer.classAttribute() == "t_epoch"
            assert len(renderer.ranges()) >= 2


class TestQgisSnakeOverlay:
    """Smoke-test the canvas rubber-band snake overlay."""

    def test_overlay_draws_colored_segments(
        self, seeded_engine, qgis_app
    ):
        """One rubber band per visible segment; newest is red."""
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtCore import QDateTime
        from qgis.PyQt.QtGui import QColor

        from survey_qgis.core.snake import SNAKE_COLOR_NEWEST
        from survey_qgis.layers.snake_overlay import SnakeOverlay

        compute_intervals(
            seeded_engine,
            threshold_seconds=1800,
            group_by_source=False,
        )
        observations = load_observations(seeded_engine, require_time=True)
        segments = build_snake_segments(observations)
        assert len(segments) >= 2

        canvas = QgsMapCanvas()
        overlay = SnakeOverlay(canvas)
        try:
            overlay.set_enabled(True)
            overlay.set_segments(segments)
            assert overlay.rubber_band_count() == len(segments)

            # Newest rubber band uses the red tip color.
            assert overlay.rubber_band_colors()[-1] == QColor(*SNAKE_COLOR_NEWEST)

            # Restricting the window remaps colors for the visible set.
            start = QDateTime.fromString(
                segments[0].seg_start,
                "yyyy-MM-ddTHH:mm:ss",
            )
            if not start.isValid():
                start = QDateTime.fromString(
                    segments[0].seg_start[:19],
                    "yyyy-MM-ddTHH:mm:ss",
                )
            end = QDateTime.fromString(
                segments[0].seg_end,
                "yyyy-MM-ddTHH:mm:ss",
            )
            if not end.isValid():
                end = QDateTime.fromString(
                    segments[0].seg_end[:19],
                    "yyyy-MM-ddTHH:mm:ss",
                )
            overlay.set_time_filter(True, start=start, end=end)
            assert overlay.rubber_band_count() >= 1
            assert overlay.rubber_band_colors()[-1] == QColor(
                *SNAKE_COLOR_NEWEST
            )

            overlay.clear()
            assert overlay.rubber_band_count() == 0
        finally:
            overlay.destroy()
            canvas.deleteLater()
