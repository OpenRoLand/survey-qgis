"""Shared pytest fixtures for survey-qgis core tests."""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from openroland_survey.database import create_engine, ensure_schema, utcnow
from openroland_survey.geopackage import encode_point_geom
from openroland_survey.models import SourceFile, SurveyPoint, SurveyPointSource
from openroland_survey.records import SourceFormat

from survey_qgis.core.db import open_engine
from survey_qgis.core.observations import materialize_observations
from survey_qgis.core.schema import ensure_plugin_schema


@pytest.fixture
def gpkg_path(tmp_path: Path) -> Path:
    """Return a temporary GeoPackage path."""
    return tmp_path / "survey.gpkg"


@pytest.fixture
def engine(gpkg_path: Path):
    """Create an empty survey GeoPackage engine with plugin tables."""
    engine = create_engine(gpkg_path)
    ensure_schema(engine)
    ensure_plugin_schema(engine)
    yield engine
    engine.dispose()


def _aware(year, month, day, hour=0, minute=0, second=0):
    return datetime.datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=datetime.timezone.utc,
    )


@pytest.fixture
def seeded_engine(engine):
    """Seed two source files and timed observations spanning gaps.

    Layout (gap threshold 30 minutes):

    - source 1: 10:00, 10:10, 10:20  -> interval A
                 11:00, 11:05        -> interval B (40 min gap)
    - source 2: 10:05, 10:15         -> overlaps source 1 in wall time
    """
    now = utcnow()
    with Session(engine) as session:
        source_a = SourceFile(
            path="/tmp/a.rw5",
            name="a.rw5",
            source_type=SourceFormat.RW5,
            sha256="a" * 64,
            size_bytes=10,
            mtime_ns=1,
            imported_at=now,
            point_count=0,
            issue_count=0,
        )
        source_b = SourceFile(
            path="/tmp/b.rw5",
            name="b.rw5",
            source_type=SourceFormat.RW5,
            sha256="b" * 64,
            size_bytes=10,
            mtime_ns=1,
            imported_at=now,
            point_count=0,
            issue_count=0,
        )
        session.add_all([source_a, source_b])
        session.flush()

        specs = [
            # east, north, height, source, observed_at
            (500001.0, 500001.0, 100.0, source_a, _aware(2024, 1, 1, 10, 0)),
            (500002.0, 500002.0, 100.0, source_a, _aware(2024, 1, 1, 10, 10)),
            (500003.0, 500003.0, 100.0, source_a, _aware(2024, 1, 1, 10, 20)),
            (500004.0, 500004.0, 100.0, source_a, _aware(2024, 1, 1, 11, 0)),
            (500005.0, 500005.0, 100.0, source_a, _aware(2024, 1, 1, 11, 5)),
            (500011.0, 500011.0, 100.0, source_b, _aware(2024, 1, 1, 10, 5)),
            (500012.0, 500012.0, 100.0, source_b, _aware(2024, 1, 1, 10, 15)),
            # Untimed observation (should be skipped by interval logic).
            (500099.0, 500099.0, 100.0, source_a, None),
        ]

        for index, (east, north, height, source, observed) in enumerate(
            specs
        ):
            north_mm = int(Decimal(str(north)) * 1000)
            east_mm = int(Decimal(str(east)) * 1000)
            height_mm = int(Decimal(str(height)) * 1000)
            point = SurveyPoint(
                north=Decimal(str(north)),
                east=Decimal(str(east)),
                height=Decimal(str(height)),
                north_mm=north_mm,
                east_mm=east_mm,
                height_mm=height_mm,
                name=f"P{index}",
                code="TEST",
                description=("Corner A" if index == 0 else None),
                observed_at_utc=observed,
                geom=encode_point_geom(east, north),
                created_at=now,
                updated_at=now,
            )
            session.add(point)
            session.flush()
            session.add(
                SurveyPointSource(
                    survey_point_id=point.id,
                    source_file_id=source.id,
                    occurrence_count=1,
                    observed_at=observed,
                )
            )

        session.commit()

    materialize_observations(engine)
    return engine


@pytest.fixture
def opened_seeded(seeded_engine, gpkg_path):
    """Re-open the seeded gpkg via the plugin open_engine helper."""
    engine = open_engine(gpkg_path)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def qgis_app():
    """Provide a QgsApplication for tests that need the QGIS API.

    Skips the entire dependent test when QGIS is not importable.
    """
    pytest.importorskip("qgis.core")
    from qgis.core import QgsApplication

    # Reuse an existing application when pytest is already inside QGIS.
    existing = QgsApplication.instance()
    if existing is not None:
        yield existing
        return

    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        yield app
    finally:
        # QGIS 4 currently segfaults during explicit shutdown in the test
        # container after all tests have passed. Process teardown performs the
        # same cleanup safely for both supported QGIS generations.
        pass
