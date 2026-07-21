"""Survey QGIS plugin settings helpers."""

from __future__ import annotations

from qgis.PyQt.QtCore import QSettings

SETTINGS_GROUP = "SiscadroSurveyQgis"
KEY_LAST_GPKG = "last_gpkg"
KEY_GAP_SECONDS = "gap_seconds"
KEY_GROUP_BY_SOURCE = "group_by_source"
KEY_WINDOW_SECONDS = "window_seconds"
KEY_TIME_WINDOW_ENABLED = "time_window_enabled"

DEFAULT_GAP_SECONDS = 1800
DEFAULT_WINDOW_SECONDS = 300
DEFAULT_TIME_WINDOW_ENABLED = False


def settings() -> QSettings:
    """Return the QSettings object scoped to this plugin."""
    return QSettings()


def get_last_gpkg() -> str:
    """Return the last GeoPackage path chosen by the user."""
    return str(
        settings().value(
            f"{SETTINGS_GROUP}/{KEY_LAST_GPKG}",
            "",
            type=str,
        )
    )


def set_last_gpkg(path: str) -> None:
    """Persist the last GeoPackage path.

    Args:
        path: Absolute path to the survey GeoPackage.
    """
    settings().setValue(f"{SETTINGS_GROUP}/{KEY_LAST_GPKG}", path)


def get_gap_seconds() -> int:
    """Return the interval gap threshold in seconds."""
    return int(
        settings().value(
            f"{SETTINGS_GROUP}/{KEY_GAP_SECONDS}",
            DEFAULT_GAP_SECONDS,
            type=int,
        )
    )


def set_gap_seconds(value: int) -> None:
    """Persist the interval gap threshold.

    Args:
        value: Gap threshold in seconds.
    """
    settings().setValue(f"{SETTINGS_GROUP}/{KEY_GAP_SECONDS}", int(value))


def get_group_by_source() -> bool:
    """Return whether intervals are grouped by source file."""
    return bool(
        settings().value(
            f"{SETTINGS_GROUP}/{KEY_GROUP_BY_SOURCE}",
            False,
            type=bool,
        )
    )


def set_group_by_source(value: bool) -> None:
    """Persist the group-by-source flag.

    Args:
        value: Whether to group intervals by source file.
    """
    settings().setValue(
        f"{SETTINGS_GROUP}/{KEY_GROUP_BY_SOURCE}",
        bool(value),
    )


def get_window_seconds() -> int:
    """Return the temporal sliding window size in seconds."""
    return int(
        settings().value(
            f"{SETTINGS_GROUP}/{KEY_WINDOW_SECONDS}",
            DEFAULT_WINDOW_SECONDS,
            type=int,
        )
    )


def set_window_seconds(value: int) -> None:
    """Persist the temporal sliding window size.

    Args:
        value: Window size in seconds.
    """
    settings().setValue(
        f"{SETTINGS_GROUP}/{KEY_WINDOW_SECONDS}",
        int(value),
    )


def get_time_window_enabled() -> bool:
    """Return whether sliding-window temporal filtering is enabled."""
    return bool(
        settings().value(
            f"{SETTINGS_GROUP}/{KEY_TIME_WINDOW_ENABLED}",
            DEFAULT_TIME_WINDOW_ENABLED,
            type=bool,
        )
    )


def set_time_window_enabled(value: bool) -> None:
    """Persist whether sliding-window temporal filtering is enabled.

    Args:
        value: True to filter points to the current time window.
    """
    settings().setValue(
        f"{SETTINGS_GROUP}/{KEY_TIME_WINDOW_ENABLED}",
        bool(value),
    )
