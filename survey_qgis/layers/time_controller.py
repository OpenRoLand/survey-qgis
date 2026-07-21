"""Wire the canvas Temporal Controller to a sliding observation window."""

from __future__ import annotations

import logging
from typing import Optional

from qgis.core import QgsDateTimeRange, QgsInterval, QgsProject
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QDateTime, Qt

logger = logging.getLogger(__name__)

__all__ = ["TimeWindowController"]


class TimeWindowController:
    """Configure and drive the map canvas temporal controller.

    Attributes:
        iface: QGIS interface used to reach the map canvas.
        window_seconds: Sliding window duration in seconds.
    """

    def __init__(
        self,
        iface: QgisInterface,
        *,
        window_seconds: int = 300,
    ) -> None:
        """Create a controller bound to ``iface``.

        Args:
            iface: QGIS interface.
            window_seconds: Initial window size.
        """
        self.iface = iface
        self.window_seconds = max(1, int(window_seconds))

    def temporal_controller(self):
        """Return the map canvas temporal controller."""
        canvas = self.iface.mapCanvas()
        return canvas.temporalController()

    def set_window_seconds(self, seconds: int) -> None:
        """Update the sliding window size and refresh the frame duration.

        Args:
            seconds: Window size in seconds.
        """
        self.window_seconds = max(1, int(seconds))
        controller = self.temporal_controller()
        if controller is None:
            return
        # Frame duration equals the sliding window length.
        controller.setFrameDuration(
            QgsInterval(float(self.window_seconds))
        )

    def configure_range(
        self,
        start: QDateTime,
        end: QDateTime,
    ) -> None:
        """Set the overall animation range and enable temporal navigation.

        Args:
            start: Animation start.
            end: Animation end.
        """
        controller = self.temporal_controller()
        if controller is None:
            logger.warning("No temporal controller available on the canvas")
            return

        # Enable temporal navigation on the canvas.
        if hasattr(controller, "setNavigationMode"):
            from qgis.core import QgsTemporalNavigationObject

            controller.setNavigationMode(
                QgsTemporalNavigationObject.NavigationMode.Animated
            )

        total = QgsDateTimeRange(start, end)
        if hasattr(controller, "setTemporalExtents"):
            controller.setTemporalExtents(total)
        controller.setFrameDuration(
            QgsInterval(float(self.window_seconds))
        )
        if hasattr(controller, "setFramesPerSecond"):
            controller.setFramesPerSecond(1.0)

        # Enable temporal filtering on the project time settings.
        time_settings = QgsProject.instance().timeSettings()
        if hasattr(time_settings, "setIsTemporalRangeEnabled"):
            time_settings.setIsTemporalRangeEnabled(True)

        logger.debug(
            "Configured temporal range %s .. %s (window=%ds)",
            start.toString(Qt.DateFormat.ISODate),
            end.toString(Qt.DateFormat.ISODate),
            self.window_seconds,
        )

    def enable_filtering(self) -> None:
        """Enable canvas temporal navigation and project time filtering."""
        controller = self.temporal_controller()
        if controller is None:
            logger.warning("No temporal controller available on the canvas")
            return

        # Switch the canvas to animated temporal navigation.
        if hasattr(controller, "setNavigationMode"):
            from qgis.core import QgsTemporalNavigationObject

            controller.setNavigationMode(
                QgsTemporalNavigationObject.NavigationMode.Animated
            )

        # Turn on project-level temporal range filtering.
        time_settings = QgsProject.instance().timeSettings()
        if hasattr(time_settings, "setIsTemporalRangeEnabled"):
            time_settings.setIsTemporalRangeEnabled(True)

        logger.debug("Enabled temporal window filtering")

    def disable_filtering(self) -> None:
        """Pause playback and disable canvas temporal filtering."""
        self.pause()

        controller = self.temporal_controller()
        if controller is not None and hasattr(controller, "setNavigationMode"):
            from qgis.core import QgsTemporalNavigationObject

            controller.setNavigationMode(
                QgsTemporalNavigationObject.NavigationMode.Disabled
            )

        # Turn off project-level temporal range filtering.
        time_settings = QgsProject.instance().timeSettings()
        if hasattr(time_settings, "setIsTemporalRangeEnabled"):
            time_settings.setIsTemporalRangeEnabled(False)

        logger.debug("Disabled temporal window filtering")

    def play(self) -> None:
        """Start autoadvance playback."""
        controller = self.temporal_controller()
        if controller is None:
            return
        if hasattr(controller, "playForward"):
            controller.playForward()
        elif hasattr(controller, "play"):
            controller.play()

    def pause(self) -> None:
        """Pause autoadvance playback."""
        controller = self.temporal_controller()
        if controller is None:
            return
        if hasattr(controller, "pause"):
            controller.pause()

    def step_forward(self) -> None:
        """Advance one frame (one window step)."""
        controller = self.temporal_controller()
        if controller is None:
            return
        if hasattr(controller, "next"):
            controller.next()
        elif hasattr(controller, "skipToNextFrame"):
            controller.skipToNextFrame()

    def step_backward(self) -> None:
        """Step one frame backward."""
        controller = self.temporal_controller()
        if controller is None:
            return
        if hasattr(controller, "previous"):
            controller.previous()
        elif hasattr(controller, "skipToPreviousFrame"):
            controller.skipToPreviousFrame()

    def set_current_time(self, when: QDateTime) -> None:
        """Jump the temporal cursor to ``when``.

        Args:
            when: Instant to show.
        """
        controller = self.temporal_controller()
        if controller is None:
            return
        end = when.addSecs(self.window_seconds)
        if hasattr(controller, "setTemporalRange"):
            controller.setTemporalRange(QgsDateTimeRange(when, end))
        elif hasattr(controller, "setCurrentTimestamp"):
            controller.setCurrentTimestamp(when)
