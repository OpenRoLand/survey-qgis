"""Logging setup for the survey QGIS plugin."""

from __future__ import annotations

import logging

from qgis.core import Qgis, QgsMessageLog

PLUGIN_LOG_TAG = "SiscadroSurveyQgis"


class QgsLogHandler(logging.Handler):
    """Forward Python log records to the QGIS message log."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit one log record into QgsMessageLog."""
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 - logging must not raise
            self.handleError(record)
            return

        # Map standard levels onto QGIS message levels.
        if record.levelno >= logging.ERROR:
            level = Qgis.MessageLevel.Critical
        elif record.levelno >= logging.WARNING:
            level = Qgis.MessageLevel.Warning
        else:
            level = Qgis.MessageLevel.Info
        QgsMessageLog.logMessage(message, PLUGIN_LOG_TAG, level)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure and return the plugin root logger.

    Args:
        level: Logging level for the plugin logger.

    Returns:
        The configured ``survey_qgis`` logger.
    """
    logger = logging.getLogger("survey_qgis")
    if not any(isinstance(h, QgsLogHandler) for h in logger.handlers):
        handler = QgsLogHandler()
        handler.setFormatter(
            logging.Formatter("%(name)s: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
