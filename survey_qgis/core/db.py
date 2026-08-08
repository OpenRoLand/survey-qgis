"""Database helpers for opening a openroland-survey-core GeoPackage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from openroland_survey.database import create_engine, ensure_schema

logger = logging.getLogger(__name__)

__all__ = [
    "open_engine",
    "session_factory",
]


def open_engine(database: Union[str, Path], *, echo: bool = False) -> Engine:
    """Open a survey GeoPackage and ensure the canonical schema exists.

    Args:
        database: Path to the survey GeoPackage (``.gpkg``).
        echo: Whether to echo SQLAlchemy SQL.

    Returns:
        A configured SQLAlchemy engine.
    """
    path = Path(database).expanduser().resolve()
    logger.debug("Opening survey GeoPackage at %s", path)
    engine = create_engine(path, echo=echo)
    ensure_schema(engine)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a session factory bound to ``engine``.

    Args:
        engine: Survey GeoPackage engine.

    Returns:
        A SQLAlchemy ``sessionmaker``.
    """
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)
