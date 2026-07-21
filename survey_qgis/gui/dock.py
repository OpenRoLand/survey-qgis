"""Docked panel with Source, Intervals, and Time pages."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import List, Optional, Sequence

from qgis.core import QgsProject, QgsVectorLayer
from qgis.gui import QgisInterface, QgsDockWidget
from qgis.PyQt.QtCore import QDate, QDateTime, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from survey_qgis.core.db import open_engine
from survey_qgis.core.intervals import (
    compute_intervals,
    list_intervals,
    parse_observed_at,
)
from survey_qgis.core.observations import (
    load_observations,
    materialize_observations,
)
from survey_qgis.core.snake import build_snake_segments
from survey_qgis.layers.managed_layer import (
    apply_interval_filter,
    create_observations_layer,
    layer_gpkg_path,
    set_temporal_filtering_active,
)
from survey_qgis.layers.registry import ManagedLayerRegistry
from survey_qgis.layers.snake_layer import (
    add_snake_layer,
    create_snake_layer,
    rebuild_snake_layer,
)
from survey_qgis.layers.time_controller import TimeWindowController
from survey_qgis import settings as plugin_settings

logger = logging.getLogger(__name__)


class SurveyDockWidget(QgsDockWidget):
    """Dock panel that drives managed survey layers.

    Attributes:
        iface: QGIS interface.
        registry: Managed layer registry.
        time_controller: Temporal sliding-window helper.
    """

    status_message = pyqtSignal(str)

    def __init__(
        self,
        iface: QgisInterface,
        registry: ManagedLayerRegistry,
        time_controller: TimeWindowController,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Build the dock UI.

        Args:
            iface: QGIS interface.
            registry: Shared managed-layer registry.
            time_controller: Temporal controller helper.
            parent: Optional parent widget.
        """
        super().__init__("Siscadro Survey Time Filter", parent)
        self.iface = iface
        self.registry = registry
        self.time_controller = time_controller
        self._snake_enabled = True
        self._building_list = False
        self._range_start: Optional[QDateTime] = None
        self._range_end: Optional[QDateTime] = None

        self.setObjectName("SiscadroSurveyTimeFilterDock")
        self._build_ui()
        self.registry.layers_changed.connect(self._refresh_layer_combo)
        self.registry.controlled_changed.connect(self._on_controlled_changed)
        self._refresh_layer_combo()
        # Match layer temporal state to the persisted switch.
        self._apply_time_window_enabled(
            plugin_settings.get_time_window_enabled(),
            announce_missing_range=False,
            emit_status=False,
        )

    def _build_ui(self) -> None:
        """Create tab pages and controls."""
        container = QWidget(self)
        root = QVBoxLayout(container)
        self.tabs = QTabWidget(container)
        root.addWidget(self.tabs)
        self.setWidget(container)

        self._build_source_page()
        self._build_intervals_page()
        self._build_time_page()

    def _build_source_page(self) -> None:
        """Build the Source tab."""
        page = QWidget(self.tabs)
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.gpkg_label = QLabel(plugin_settings.get_last_gpkg() or "(none)")
        self.gpkg_label.setWordWrap(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_gpkg)
        path_row = QHBoxLayout()
        path_row.addWidget(self.gpkg_label, stretch=1)
        path_row.addWidget(browse)
        form.addRow("GeoPackage", path_row)

        self.layer_combo = QComboBox()
        self.layer_combo.currentIndexChanged.connect(self._layer_combo_changed)
        form.addRow("Controlled layer", self.layer_combo)
        layout.addLayout(form)

        add_btn = QPushButton("Add survey layer")
        add_btn.clicked.connect(self._add_survey_layer)
        layout.addWidget(add_btn)
        layout.addStretch(1)
        self.tabs.addTab(page, "Source")

    def _build_intervals_page(self) -> None:
        """Build the Intervals tab."""
        page = QWidget(self.tabs)
        layout = QVBoxLayout(page)

        filter_box = QGroupBox("Date filter")
        filter_form = QFormLayout(filter_box)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setDate(QDate.currentDate().addYears(-1))
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setDate(QDate.currentDate())
        filter_form.addRow("Start", self.start_date)
        filter_form.addRow("End", self.end_date)
        apply_dates = QPushButton("Apply date filter")
        apply_dates.clicked.connect(self.refresh_intervals)
        filter_form.addRow(apply_dates)
        layout.addWidget(filter_box)

        self.interval_list = QListWidget()
        self.interval_list.itemChanged.connect(self._interval_selection_changed)
        layout.addWidget(self.interval_list, stretch=1)

        select_row = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_all.clicked.connect(self._select_all_intervals)
        select_none = QPushButton("Select none")
        select_none.clicked.connect(self._select_no_intervals)
        select_row.addWidget(select_all)
        select_row.addWidget(select_none)
        layout.addLayout(select_row)

        recompute_box = QGroupBox("Recompute")
        recompute_form = QFormLayout(recompute_box)
        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(60, 86400 * 7)
        self.gap_spin.setSingleStep(60)
        self.gap_spin.setValue(plugin_settings.get_gap_seconds())
        self.gap_spin.setSuffix(" s")
        self.group_by_source = QCheckBox("Group by source file")
        self.group_by_source.setChecked(plugin_settings.get_group_by_source())
        recompute_form.addRow("Gap threshold", self.gap_spin)
        recompute_form.addRow(self.group_by_source)
        recompute_btn = QPushButton("Recompute intervals")
        recompute_btn.clicked.connect(self._recompute_intervals)
        recompute_form.addRow(recompute_btn)
        layout.addWidget(recompute_box)

        self.tabs.addTab(page, "Intervals")

    def _build_time_page(self) -> None:
        """Build the Time tab."""
        page = QWidget(self.tabs)
        layout = QVBoxLayout(page)

        self.time_window_check = QCheckBox("Filter by time window")
        self.time_window_check.setChecked(
            plugin_settings.get_time_window_enabled()
        )
        self.time_window_check.toggled.connect(self._time_window_toggled)
        layout.addWidget(self.time_window_check)

        form = QFormLayout()
        self.window_spin = QSpinBox()
        self.window_spin.setRange(1, 86400)
        self.window_spin.setValue(plugin_settings.get_window_seconds())
        self.window_spin.setSuffix(" s")
        self.window_spin.valueChanged.connect(self._window_changed)
        form.addRow("Window size", self.window_spin)
        layout.addLayout(form)

        transport = QHBoxLayout()
        play_btn = QPushButton("Play")
        play_btn.clicked.connect(self.time_controller.play)
        pause_btn = QPushButton("Pause")
        pause_btn.clicked.connect(self.time_controller.pause)
        prev_btn = QPushButton("Step −")
        prev_btn.clicked.connect(self.time_controller.step_backward)
        next_btn = QPushButton("Step +")
        next_btn.clicked.connect(self.time_controller.step_forward)
        transport.addWidget(prev_btn)
        transport.addWidget(play_btn)
        transport.addWidget(pause_btn)
        transport.addWidget(next_btn)
        layout.addLayout(transport)

        configure_btn = QPushButton("Apply range from selected intervals")
        configure_btn.clicked.connect(self._configure_temporal_range)
        layout.addWidget(configure_btn)

        self.snake_check = QCheckBox("Show snake overlay")
        self.snake_check.setChecked(True)
        self.snake_check.toggled.connect(self._snake_toggled)
        layout.addWidget(self.snake_check)
        layout.addStretch(1)
        self.tabs.addTab(page, "Time")

    def _browse_gpkg(self) -> None:
        """Let the user pick a survey GeoPackage."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open survey GeoPackage",
            plugin_settings.get_last_gpkg() or "",
            "GeoPackage (*.gpkg);;All files (*.*)",
        )
        if not path:
            return
        self.gpkg_label.setText(path)
        plugin_settings.set_last_gpkg(path)

    def _add_survey_layer(self) -> None:
        """Materialize observations, compute intervals, and add layers."""
        path_text = self.gpkg_label.text().strip()
        if not path_text or path_text == "(none)":
            QMessageBox.warning(
                self,
                "Siscadro Survey",
                "Choose a survey GeoPackage first.",
            )
            return
        path = Path(path_text)
        if not path.is_file():
            QMessageBox.warning(
                self,
                "Siscadro Survey",
                "File not found:\n%s" % path,
            )
            return

        try:
            engine = open_engine(path)
            count = materialize_observations(engine)
            gap = int(self.gap_spin.value())
            group = bool(self.group_by_source.isChecked())
            intervals = compute_intervals(
                engine,
                threshold_seconds=gap,
                group_by_source=group,
            )
            plugin_settings.set_last_gpkg(str(path))
            plugin_settings.set_gap_seconds(gap)
            plugin_settings.set_group_by_source(group)
        except Exception as exc:
            logger.exception("Failed to prepare survey GeoPackage")
            QMessageBox.critical(
                self,
                "Siscadro Survey",
                "Failed to prepare GeoPackage:\n%s" % exc,
            )
            return

        layer = create_observations_layer(path)
        QgsProject.instance().addMapLayer(layer)

        snake = create_snake_layer(name=f"Snake ({path.stem})")
        add_snake_layer(snake, after_layer=layer)
        observations = load_observations(engine, require_time=True)
        segments = build_snake_segments(observations)
        rebuild_snake_layer(snake, segments)

        self.registry.register(layer, snake_layer=snake, make_controlled=True)
        apply_interval_filter(layer, [item.id for item in intervals if item.id])
        # Honour the current time-window switch for the new layers.
        self._set_layers_temporal_active(
            bool(self.time_window_check.isChecked())
        )
        self.refresh_intervals()
        self.status_message.emit(
            "Loaded %d observations in %d intervals" % (count, len(intervals))
        )

    def _refresh_layer_combo(self) -> None:
        """Refresh the controlled-layer combo from the registry."""
        current = self.registry.controlled_layer()
        self.layer_combo.blockSignals(True)
        self.layer_combo.clear()
        for layer in self.registry.managed_layers():
            self.layer_combo.addItem(layer.name(), layer.id())
        if current is not None:
            index = self.layer_combo.findData(current.id())
            if index >= 0:
                self.layer_combo.setCurrentIndex(index)
        self.layer_combo.blockSignals(False)

    def _layer_combo_changed(self, index: int) -> None:
        """Handle controlled-layer combo changes."""
        if index < 0:
            return
        layer_id = self.layer_combo.itemData(index)
        for layer in self.registry.managed_layers():
            if layer.id() == layer_id:
                self.registry.set_controlled(layer)
                self.refresh_intervals()
                return

    def _on_controlled_changed(self, layer: Optional[QgsVectorLayer]) -> None:
        """React when the registry changes the controlled layer."""
        self._refresh_layer_combo()
        if layer is not None:
            self.refresh_intervals()

    def refresh_intervals(self) -> None:
        """Reload the interval list for the controlled layer."""
        layer = self.registry.controlled_layer()
        self._building_list = True
        self.interval_list.clear()
        if layer is None:
            self._building_list = False
            return
        path = layer_gpkg_path(layer)
        if path is None or not path.is_file():
            self._building_list = False
            return

        start = datetime.datetime(
            self.start_date.date().year(),
            self.start_date.date().month(),
            self.start_date.date().day(),
            tzinfo=datetime.timezone.utc,
        )
        end = datetime.datetime(
            self.end_date.date().year(),
            self.end_date.date().month(),
            self.end_date.date().day(),
            23,
            59,
            59,
            tzinfo=datetime.timezone.utc,
        )
        try:
            engine = open_engine(path)
            intervals = list_intervals(engine, start=start, end=end)
        except Exception as exc:
            logger.exception("Failed to list intervals")
            self.status_message.emit("Failed to list intervals: %s" % exc)
            self._building_list = False
            return

        for interval in intervals:
            started = parse_observed_at(interval.started_at)
            ended = parse_observed_at(interval.ended_at)
            duration = ended - started
            source = (
                f"src={interval.source_file_id}"
                if interval.source_file_id is not None
                else "all sources"
            )
            label = (
                "%s → %s (%s, %d pts, %s)"
                % (
                    started.strftime("%Y-%m-%d %H:%M"),
                    ended.strftime("%Y-%m-%d %H:%M"),
                    duration,
                    interval.observation_count,
                    source,
                )
            )
            item = QListWidgetItem(label)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, interval.id)
            self.interval_list.addItem(item)

        self._building_list = False
        self._interval_selection_changed()

    def _selected_interval_ids(self) -> List[int]:
        """Return checked interval ids from the list."""
        ids: List[int] = []
        for index in range(self.interval_list.count()):
            item = self.interval_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                value = item.data(Qt.ItemDataRole.UserRole)
                if value is not None:
                    ids.append(int(value))
        return ids

    def _interval_selection_changed(self, *_args) -> None:
        """Apply interval selection to the controlled layer and snake."""
        if self._building_list:
            return
        layer = self.registry.controlled_layer()
        if layer is None:
            return
        interval_ids = self._selected_interval_ids()
        apply_interval_filter(layer, interval_ids)
        self._rebuild_snake(interval_ids)

    def _select_all_intervals(self) -> None:
        """Check every interval in the list."""
        self._building_list = True
        for index in range(self.interval_list.count()):
            self.interval_list.item(index).setCheckState(
                Qt.CheckState.Checked
            )
        self._building_list = False
        self._interval_selection_changed()

    def _select_no_intervals(self) -> None:
        """Uncheck every interval in the list."""
        self._building_list = True
        for index in range(self.interval_list.count()):
            self.interval_list.item(index).setCheckState(
                Qt.CheckState.Unchecked
            )
        self._building_list = False
        self._interval_selection_changed()

    def _recompute_intervals(self) -> None:
        """Recompute intervals for the controlled layer's GeoPackage."""
        layer = self.registry.controlled_layer()
        if layer is None:
            QMessageBox.information(
                self,
                "Siscadro Survey",
                "No controlled survey layer.",
            )
            return
        path = layer_gpkg_path(layer)
        if path is None:
            return
        gap = int(self.gap_spin.value())
        group = bool(self.group_by_source.isChecked())
        try:
            engine = open_engine(path)
            materialize_observations(engine)
            compute_intervals(
                engine,
                threshold_seconds=gap,
                group_by_source=group,
            )
            plugin_settings.set_gap_seconds(gap)
            plugin_settings.set_group_by_source(group)
            layer.dataProvider().reloadData()
            layer.triggerRepaint()
        except Exception as exc:
            logger.exception("Failed to recompute intervals")
            QMessageBox.critical(
                self,
                "Siscadro Survey",
                "Recompute failed:\n%s" % exc,
            )
            return
        self.refresh_intervals()
        self.status_message.emit("Intervals recomputed")

    def _rebuild_snake(self, interval_ids: Sequence[int]) -> None:
        """Rebuild the snake overlay for the selected intervals."""
        layer = self.registry.controlled_layer()
        if layer is None:
            return
        snake = self.registry.snake_for(layer)
        if snake is None:
            return
        if not self._snake_enabled:
            rebuild_snake_layer(snake, [])
            return
        path = layer_gpkg_path(layer)
        if path is None:
            return
        engine = open_engine(path)
        observations = load_observations(engine, require_time=True)
        segments = build_snake_segments(
            observations,
            interval_ids=interval_ids,
        )
        rebuild_snake_layer(snake, segments)

    def _window_changed(self, value: int) -> None:
        """Persist and apply the sliding window size."""
        plugin_settings.set_window_seconds(int(value))
        self.time_controller.set_window_seconds(int(value))

    def _snake_toggled(self, checked: bool) -> None:
        """Enable or disable the snake overlay."""
        self._snake_enabled = bool(checked)
        self._rebuild_snake(self._selected_interval_ids())

    def _time_window_toggled(self, checked: bool) -> None:
        """Enable or disable sliding-window point filtering."""
        plugin_settings.set_time_window_enabled(bool(checked))
        self._apply_time_window_enabled(
            bool(checked),
            announce_missing_range=True,
        )

    def _set_layers_temporal_active(self, active: bool) -> None:
        """Toggle temporal filtering on the controlled layer and snake."""
        layer = self.registry.controlled_layer()
        if layer is None:
            return
        set_temporal_filtering_active(layer, active)
        snake = self.registry.snake_for(layer)
        if snake is not None:
            set_temporal_filtering_active(snake, active)

    def _apply_time_window_enabled(
        self,
        enabled: bool,
        *,
        announce_missing_range: bool,
        emit_status: bool = True,
    ) -> None:
        """Apply the time-window switch to layers and the canvas.

        Args:
            enabled: Whether only the sliding window should be shown.
            announce_missing_range: When enabling without a configured
                range, emit a status hint for the user.
            emit_status: Whether to emit status_message updates.
        """
        if not enabled:
            self.time_controller.disable_filtering()
            self._set_layers_temporal_active(False)
            if emit_status:
                self.status_message.emit(
                    "Time window filter disabled (showing all points)"
                )
            return

        self._set_layers_temporal_active(True)
        if self._range_start is None or self._range_end is None:
            self.time_controller.enable_filtering()
            if announce_missing_range and emit_status:
                self.status_message.emit(
                    "Time window enabled — click "
                    "'Apply range from selected intervals'"
                )
            return

        self.time_controller.set_window_seconds(int(self.window_spin.value()))
        self.time_controller.configure_range(
            self._range_start,
            self._range_end,
        )
        self.time_controller.set_current_time(self._range_start)
        if emit_status:
            self.status_message.emit("Time window filter enabled")

    def _configure_temporal_range(self) -> None:
        """Set the temporal controller range from selected intervals."""
        layer = self.registry.controlled_layer()
        if layer is None:
            return
        path = layer_gpkg_path(layer)
        if path is None:
            return
        interval_ids = set(self._selected_interval_ids())
        engine = open_engine(path)
        intervals = list_intervals(engine)
        selected = [
            item for item in intervals if item.id in interval_ids
        ]
        if not selected:
            QMessageBox.information(
                self,
                "Siscadro Survey",
                "Select at least one interval.",
            )
            return
        start = min(parse_observed_at(item.started_at) for item in selected)
        end = max(parse_observed_at(item.ended_at) for item in selected)
        start_qt = QDateTime.fromString(
            start.isoformat(),
            Qt.DateFormat.ISODate,
        )
        end_qt = QDateTime.fromString(
            end.isoformat(),
            Qt.DateFormat.ISODate,
        )
        self._range_start = start_qt
        self._range_end = end_qt
        self.time_controller.set_window_seconds(int(self.window_spin.value()))
        self.time_controller.configure_range(start_qt, end_qt)
        self.time_controller.set_current_time(start_qt)

        # Keep layer temporal state aligned with the checkbox.
        enabled = bool(self.time_window_check.isChecked())
        self._set_layers_temporal_active(enabled)
        if not enabled:
            self.time_controller.disable_filtering()

        self.status_message.emit(
            "Temporal range %s → %s"
            % (start.isoformat(), end.isoformat())
        )
