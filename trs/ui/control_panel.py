from pathlib import Path

from PySide6 import QtCore, QtGui, QtMultimedia, QtWidgets

from ..config import CONTROL_PANEL_TITLE, PACE_AUTOFOCUS_THRESHOLD
from ..paceman import PacemanRun, fetch_live_runs, set_pace_config

_ICON_NAME_BY_EVENT = {
    "rsg.enter_end": "end.webp",
    "rsg.enter_stronghold": "stronghold.webp",
    "rsg.first_portal": "first_portal.webp",
    "rsg.enter_fortress": "fortress.webp",
    "rsg.enter_bastion": "bastion.webp",
    "rsg.enter_nether": "nether.webp",
}


class _PacemanWorkerSignals(QtCore.QObject):
    finished = QtCore.Signal(list)
    error = QtCore.Signal(str)


class _PacemanWorker(QtCore.QRunnable):
    def __init__(self) -> None:
        super().__init__()
        self.signals = _PacemanWorkerSignals()

    def run(self) -> None:
        try:
            runs = fetch_live_runs()
        except Exception as exc:
            self.signals.error.emit(str(exc))
            return
        self.signals.finished.emit(runs)


class _FlowLayout(QtWidgets.QLayout):
    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        margin: int = 0,
        h_spacing: int = 6,
        v_spacing: int = 6,
    ) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientations:
        return QtCore.Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(),
                             margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(
                    QtCore.QRect(
                        QtCore.QPoint(x, y),
                        item.sizeHint(),
                    )
                )
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()


class ControlPanelWindow(QtWidgets.QWidget):
    manual_streams_changed = QtCore.Signal(list)
    active_streams_changed = QtCore.Signal(list, bool)
    settings_changed = QtCore.Signal(dict)

    def __init__(
        self,
        streams: list[str],
        settings: dict[str, object] | None = None,
    ) -> None:
        super().__init__()
        settings = settings or {}
        self.setWindowTitle(CONTROL_PANEL_TITLE)
        self.resize(420, 560)
        self._manual_streams = list(streams)
        self._paceman_runs: list[PacemanRun] = []
        self._paceman_mode = False
        self._paceman_loading = False
        self._include_hidden = False
        self._paceman_fallback = False
        self._hide_offline = False
        self._pace_sort_enabled = True
        self._pace_autofocus_enabled = True
        self._pace_autofocus_threshold = PACE_AUTOFOCUS_THRESHOLD
        self._pace_good_splits: dict[str, float] = {}
        self._pace_progression_bonus: dict[str, float] = {}
        self._focused_channel: str | None = None
        self._auto_focus_active = False
        self._current_worker: _PacemanWorker | None = None
        self._thread_pool = QtCore.QThreadPool.globalInstance()
        self._bell_effect = QtMultimedia.QSoundEffect(self)
        bell_path = (
            Path(__file__).resolve().parent.parent
            / "mixkit-achievement-bell-600.wav"
        )
        if bell_path.exists():
            self._bell_effect.setSource(
                QtCore.QUrl.fromLocalFile(str(bell_path))
            )
        self._bell_effect.setVolume(0.35)
        self._icon_cache: dict[str, QtGui.QPixmap] = {}
        self._icon_dir = (
            Path(__file__).resolve().parent.parent
            / "assets"
            / "paceman-icons"
        )
        self._paceman_timer = QtCore.QTimer(self)
        self._paceman_timer.setInterval(10_000)
        self._paceman_timer.timeout.connect(self._start_paceman_refresh)
        self._last_active_streams: list[str] = []
        self._last_active_focused = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        options_flow = _FlowLayout()
        self._paceman_toggle = QtWidgets.QCheckBox("Paceman mode", self)
        self._paceman_toggle.toggled.connect(self._toggle_paceman_mode)
        self._show_hidden_toggle = QtWidgets.QCheckBox("Show hidden/cheated", self)
        self._show_hidden_toggle.toggled.connect(self._toggle_show_hidden)
        self._show_hidden_toggle.setEnabled(False)
        self._hide_offline_toggle = QtWidgets.QCheckBox("Hide offline", self)
        self._hide_offline_toggle.toggled.connect(self._toggle_hide_offline)
        self._hide_offline_toggle.setEnabled(False)
        self._paceman_fallback_toggle = QtWidgets.QCheckBox(
            "Fallback to manual if none live",
            self,
        )
        self._paceman_fallback_toggle.toggled.connect(
            self._toggle_paceman_fallback
        )
        self._paceman_fallback_toggle.setEnabled(False)
        self._refresh_button = QtWidgets.QPushButton("Refresh", self)
        self._refresh_button.clicked.connect(self._start_paceman_refresh)
        self._refresh_button.setEnabled(False)
        self._clear_focus_button = QtWidgets.QPushButton("Clear focus", self)
        self._clear_focus_button.clicked.connect(self._clear_focus)
        self._clear_focus_button.setEnabled(False)
        options_flow.addWidget(self._paceman_toggle)
        options_flow.addWidget(self._show_hidden_toggle)
        options_flow.addWidget(self._hide_offline_toggle)
        options_flow.addWidget(self._paceman_fallback_toggle)
        options_flow.addWidget(self._refresh_button)
        options_flow.addWidget(self._clear_focus_button)
        layout.addLayout(options_flow)

        self._status_label = QtWidgets.QLabel("", self)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)
        self._focus_label = QtWidgets.QLabel("", self)
        self._focus_label.setWordWrap(True)
        self._focus_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self._focus_label)

        form_row = QtWidgets.QHBoxLayout()
        self._tabs = QtWidgets.QTabWidget(self)
        self._manual_tab = QtWidgets.QWidget(self._tabs)
        self._paceman_tab = QtWidgets.QWidget(self._tabs)
        self._tabs.addTab(self._paceman_tab, "Paceman")
        self._tabs.addTab(self._manual_tab, "Manual")
        layout.addWidget(self._tabs, 1)
        self._tabs.setCurrentWidget(self._manual_tab)
        self._tabs.setTabEnabled(
            self._tabs.indexOf(self._paceman_tab), self._paceman_mode
        )

        manual_layout = QtWidgets.QVBoxLayout(self._manual_tab)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        manual_layout.setSpacing(8)
        self._input = QtWidgets.QLineEdit(self._manual_tab)
        self._input.setPlaceholderText("twitch channel name")
        self._add_button = QtWidgets.QPushButton("Add Stream", self._manual_tab)
        self._add_button.clicked.connect(self._add_stream)
        self._input.returnPressed.connect(self._add_stream)
        form_row.addWidget(self._input)
        form_row.addWidget(self._add_button)
        manual_layout.addLayout(form_row)

        self._manual_list = QtWidgets.QListWidget(self._manual_tab)
        manual_layout.addWidget(self._manual_list, 1)

        paceman_layout = QtWidgets.QVBoxLayout(self._paceman_tab)
        paceman_layout.setContentsMargins(0, 0, 0, 0)
        paceman_layout.setSpacing(8)
        pace_controls = QtWidgets.QHBoxLayout()
        self._pace_sort_toggle = QtWidgets.QCheckBox("Sort by pace", self)
        self._pace_sort_toggle.toggled.connect(
            self._toggle_pace_sort
        )
        self._pace_autofocus_toggle = QtWidgets.QCheckBox(
            "Auto-focus pace ≤", self
        )
        self._pace_autofocus_toggle.toggled.connect(
            self._toggle_pace_autofocus
        )
        self._pace_threshold_input = QtWidgets.QDoubleSpinBox(self)
        self._pace_threshold_input.setDecimals(2)
        self._pace_threshold_input.setSingleStep(0.05)
        self._pace_threshold_input.setRange(-1.0, 10.0)
        self._pace_threshold_input.valueChanged.connect(
            self._update_pace_threshold
        )
        pace_controls.addWidget(self._pace_sort_toggle)
        pace_controls.addWidget(self._pace_autofocus_toggle)
        pace_controls.addWidget(self._pace_threshold_input)
        pace_controls.addStretch(1)
        paceman_layout.addLayout(pace_controls)
        self._paceman_table = QtWidgets.QTableWidget(self._paceman_tab)
        self._paceman_table.setColumnCount(8)
        self._paceman_table.setHorizontalHeaderLabels(
            ["", "Name", "Split", "Time", "Est", "PB", "Pace", ""]
        )
        self._paceman_table.verticalHeader().setVisible(False)
        self._paceman_table.setSelectionMode(
            QtWidgets.QAbstractItemView.NoSelection
        )
        self._paceman_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
        )
        self._paceman_table.setShowGrid(False)
        header = self._paceman_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(12)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(6, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(7, QtWidgets.QHeaderView.Interactive)
        self._paceman_table.setColumnWidth(0, 18)
        self._paceman_table.setColumnWidth(1, 140)
        self._paceman_table.setColumnWidth(2, 58)
        self._paceman_table.setColumnWidth(3, 52)
        self._paceman_table.setColumnWidth(4, 52)
        self._paceman_table.setColumnWidth(5, 52)
        self._paceman_table.setColumnWidth(6, 62)
        self._paceman_table.setColumnWidth(7, 52)
        self._paceman_table.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.AdjustIgnored
        )
        paceman_layout.addWidget(self._paceman_table, 1)
        self._apply_settings(settings)
        self._refresh_list()

    def _toggle_paceman_mode(self, enabled: bool) -> None:
        self._paceman_mode = enabled
        self._tabs.setTabEnabled(
            self._tabs.indexOf(self._paceman_tab), enabled
        )
        self._tabs.setCurrentWidget(
            self._paceman_tab if enabled else self._manual_tab
        )
        self._show_hidden_toggle.setEnabled(enabled)
        self._hide_offline_toggle.setEnabled(enabled)
        self._paceman_fallback_toggle.setEnabled(enabled)
        self._refresh_button.setEnabled(enabled and not self._paceman_loading)
        self._clear_focus_button.setEnabled(self._focused_channel is not None)
        self._pace_sort_toggle.setEnabled(enabled)
        self._pace_autofocus_toggle.setEnabled(enabled)
        self._pace_threshold_input.setEnabled(
            enabled and self._pace_autofocus_enabled
        )
        self._emit_settings()
        if enabled:
            self._status_label.setText("Fetching live runs...")
            self._start_paceman_refresh()
            self._paceman_timer.start()
        else:
            self._status_label.setText("")
            self._paceman_timer.stop()
            if self._focused_channel not in self._manual_streams:
                self._focused_channel = None
            self._clear_focus_button.setEnabled(self._focused_channel is not None)
            self._update_focus_label()
            self._refresh_list()
            self.active_streams_changed.emit(list(self._manual_streams), False)
            self._last_active_streams = list(self._manual_streams)
            self._last_active_focused = False

    def _toggle_show_hidden(self, enabled: bool) -> None:
        self._include_hidden = enabled
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _toggle_hide_offline(self, enabled: bool) -> None:
        self._hide_offline = enabled
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _toggle_paceman_fallback(self, enabled: bool) -> None:
        self._paceman_fallback = enabled
        self._emit_settings()
        if self._paceman_mode:
            self._emit_active_streams()

    def _toggle_pace_sort(self, enabled: bool) -> None:
        self._pace_sort_enabled = enabled
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _toggle_pace_autofocus(self, enabled: bool) -> None:
        self._pace_autofocus_enabled = enabled
        self._pace_threshold_input.setEnabled(
            self._paceman_mode and enabled
        )
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _update_pace_threshold(self, value: float) -> None:
        self._pace_autofocus_threshold = float(value)
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _start_paceman_refresh(self) -> None:
        if self._paceman_loading:
            return
        self._paceman_loading = True
        self._refresh_button.setEnabled(False)
        self._status_label.setText("Fetching live runs...")
        worker = _PacemanWorker()
        worker.signals.finished.connect(self._on_paceman_runs)
        worker.signals.error.connect(self._on_paceman_error)
        self._current_worker = worker
        self._thread_pool.start(worker)

    def _on_paceman_runs(self, runs: list[PacemanRun]) -> None:
        self._paceman_loading = False
        self._current_worker = None
        self._refresh_button.setEnabled(self._paceman_mode)
        self._paceman_runs = runs
        if self._paceman_mode:
            self._status_label.setText(f"Loaded {len(runs)} live runs.")
            self._refresh_list()
            self._emit_active_streams()

    def _on_paceman_error(self, message: str) -> None:
        self._paceman_loading = False
        self._current_worker = None
        self._refresh_button.setEnabled(self._paceman_mode)
        if self._paceman_mode:
            self._status_label.setText(f"Paceman refresh failed: {message}")

    def _add_stream(self) -> None:
        channel = self._input.text().strip()
        if not channel:
            return
        if channel in self._manual_streams:
            self._input.clear()
            return
        self._manual_streams.append(channel)
        self._input.clear()
        self._refresh_list()
        self.manual_streams_changed.emit(list(self._manual_streams))
        self._emit_active_streams()

    def _remove_stream(self, channel: str) -> None:
        if channel not in self._manual_streams:
            return
        self._manual_streams.remove(channel)
        if self._focused_channel == channel:
            self._focused_channel = None
            self._clear_focus_button.setEnabled(False)
        self._refresh_list()
        self.manual_streams_changed.emit(list(self._manual_streams))
        self._emit_active_streams()

    def _refresh_list(self) -> None:
        self._manual_list.clear()
        self._paceman_table.setRowCount(0)
        self._refresh_paceman_list()
        self._refresh_manual_list()
        self._update_focus_label()

    def _refresh_manual_list(self) -> None:
        for channel in self._manual_streams:
            item = QtWidgets.QListWidgetItem(self._manual_list)
            row_widget = QtWidgets.QWidget(self._manual_list)
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 4, 6, 4)
            label = QtWidgets.QLabel(channel, row_widget)
            if channel == self._focused_channel:
                label.setStyleSheet("font-weight: 600;")
            focus_button = QtWidgets.QPushButton("Focus", row_widget)
            focus_button.clicked.connect(
                lambda _, c=channel: self._set_focus(c)
            )
            delete_button = QtWidgets.QPushButton("Delete", row_widget)
            delete_button.clicked.connect(
                lambda _, c=channel: self._remove_stream(c)
            )
            row_layout.addWidget(label)
            row_layout.addStretch(1)
            row_layout.addWidget(focus_button)
            row_layout.addWidget(delete_button)
            item.setSizeHint(row_widget.sizeHint())
            self._manual_list.addItem(item)
            self._manual_list.setItemWidget(item, row_widget)

    def _refresh_paceman_list(self) -> None:
        visible_runs = self._sorted_paceman_runs()
        self._maybe_auto_focus(visible_runs)
        self._paceman_table.clearSpans()
        if not visible_runs:
            self._paceman_table.setRowCount(1)
            self._paceman_table.setSpan(0, 0, 1, 8)
            empty_item = QtWidgets.QTableWidgetItem(
                "No runs available."
            )
            empty_item.setFlags(empty_item.flags() & ~QtCore.Qt.ItemIsEnabled)
            self._paceman_table.setItem(0, 0, empty_item)
            return
        self._clear_focus_button.setEnabled(self._focused_channel is not None)
        self._paceman_table.setRowCount(len(visible_runs))
        for row, run in enumerate(visible_runs):
            icon_item = QtWidgets.QTableWidgetItem()
            pixmap = self._icon_for_run(run)
            if pixmap is not None:
                icon_item.setIcon(QtGui.QIcon(pixmap))
            icon_item.setFlags(icon_item.flags() & ~QtCore.Qt.ItemIsEditable)
            name_item = QtWidgets.QTableWidgetItem(
                run.nickname or "unknown runner"
            )
            if run.channel:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            split_item = QtWidgets.QTableWidgetItem(
                run.last_event_label or ""
            )
            time_item = QtWidgets.QTableWidgetItem(
                self._format_event_time(run)
            )
            pb_item = QtWidgets.QTableWidgetItem(
                self._format_pb_time(run)
            )
            est_item = QtWidgets.QTableWidgetItem(
                self._format_estimated_time(run)
            )
            pace_item = QtWidgets.QTableWidgetItem(
                self._format_pace(run)
            )
            focus_button = QtWidgets.QPushButton("Focus", self._paceman_table)
            focus_button.setFixedWidth(58)
            focus_button.setEnabled(bool(run.channel))
            focus_button.clicked.connect(
                lambda _, c=run.channel: self._set_focus(c)
            )
            self._paceman_table.setItem(row, 0, icon_item)
            self._paceman_table.setItem(row, 1, name_item)
            self._paceman_table.setItem(row, 2, split_item)
            self._paceman_table.setItem(row, 3, time_item)
            self._paceman_table.setItem(row, 4, est_item)
            self._paceman_table.setItem(row, 5, pb_item)
            self._paceman_table.setItem(row, 6, pace_item)
            self._paceman_table.setCellWidget(row, 7, focus_button)

    def _filtered_paceman_runs(self) -> list[PacemanRun]:
        if self._include_hidden:
            visible = list(self._paceman_runs)
        else:
            visible = [
                run
                for run in self._paceman_runs
                if not run.is_hidden and not run.is_cheated
            ]
        if self._hide_offline:
            visible = [run for run in visible if run.channel]
        return visible

    def _sorted_paceman_runs(self) -> list[PacemanRun]:
        visible_runs = self._filtered_paceman_runs()
        if not self._pace_sort_enabled:
            return visible_runs

        def pace_key(run: PacemanRun) -> tuple[bool, float, str]:
            score = run.pace_score
            return (
                score is None,
                score if score is not None else float("inf"),
                run.nickname,
            )

        return sorted(visible_runs, key=pace_key)

    def _maybe_auto_focus(self, visible_runs: list[PacemanRun]) -> None:
        if not self._paceman_mode or not self._pace_autofocus_enabled:
            return
        if self._focused_channel is not None and not self._auto_focus_active:
            return
        candidates = [
            run
            for run in visible_runs
            if run.channel
            and run.pace_score is not None
            and run.pace_score <= self._pace_autofocus_threshold
        ]
        if not candidates:
            if self._auto_focus_active and self._focused_channel is not None:
                self._focused_channel = None
                self._auto_focus_active = False
                self._clear_focus_button.setEnabled(False)
            return
        best_run = min(candidates, key=lambda run: run.pace_score)
        if not best_run.channel:
            return
        if best_run.channel == self._focused_channel:
            return
        self._focused_channel = best_run.channel
        self._auto_focus_active = True
        self._clear_focus_button.setEnabled(True)
        self._bell_effect.play()

    def _emit_active_streams(self) -> None:
        if not self._paceman_mode:
            channels = list(self._manual_streams)
            if self._focused_channel in channels:
                channels.remove(self._focused_channel)
                channels.insert(0, self._focused_channel)
                focused = True
            else:
                focused = False
        else:
            visible_runs = self._sorted_paceman_runs()
            channels = [run.channel for run in visible_runs if run.channel]
            if not channels and self._paceman_fallback:
                channels = list(self._manual_streams)
                focused = False
            elif self._focused_channel in channels:
                channels.remove(self._focused_channel)
                channels.insert(0, self._focused_channel)
                focused = True
            else:
                focused = False
        if (
            channels == self._last_active_streams
            and focused == self._last_active_focused
        ):
            return
        self._last_active_streams = list(channels)
        self._last_active_focused = focused
        self.active_streams_changed.emit(channels, focused)

    def _emit_settings(self) -> None:
        self.settings_changed.emit(
            {
                "paceman_mode": self._paceman_mode,
                "include_hidden": self._include_hidden,
                "paceman_fallback": self._paceman_fallback,
                "paceman_hide_offline": self._hide_offline,
                "pace_sort_enabled": self._pace_sort_enabled,
                "pace_autofocus_enabled": self._pace_autofocus_enabled,
                "pace_autofocus_threshold": self._pace_autofocus_threshold,
                "pace_good_splits": dict(self._pace_good_splits),
                "pace_progression_bonus": dict(self._pace_progression_bonus),
            }
        )

    def _set_focus(self, channel: str | None, *, auto: bool = False) -> None:
        if not channel:
            return
        if not auto and channel == self._focused_channel:
            self._focused_channel = None
            self._auto_focus_active = False
        else:
            self._focused_channel = channel
            self._auto_focus_active = auto
        self._clear_focus_button.setEnabled(self._focused_channel is not None)
        self._refresh_list()
        self._emit_active_streams()

    def _clear_focus(self) -> None:
        if self._focused_channel is None:
            return
        self._focused_channel = None
        self._auto_focus_active = False
        self._clear_focus_button.setEnabled(False)
        self._refresh_list()
        self._emit_active_streams()

    def _apply_settings(self, settings: dict[str, object]) -> None:
        self._paceman_toggle.setChecked(
            bool(settings.get("paceman_mode", False))
        )
        self._show_hidden_toggle.setChecked(
            bool(settings.get("include_hidden", False))
        )
        self._paceman_fallback_toggle.setChecked(
            bool(settings.get("paceman_fallback", False))
        )
        self._hide_offline = bool(
            settings.get("paceman_hide_offline", False)
        )
        self._hide_offline_toggle.setChecked(self._hide_offline)
        self._pace_sort_enabled = bool(settings.get("pace_sort_enabled", True))
        self._pace_sort_toggle.setChecked(self._pace_sort_enabled)
        self._pace_autofocus_enabled = bool(
            settings.get("pace_autofocus_enabled", True)
        )
        self._pace_autofocus_toggle.setChecked(self._pace_autofocus_enabled)
        self._pace_autofocus_threshold = float(
            settings.get(
                "pace_autofocus_threshold", PACE_AUTOFOCUS_THRESHOLD
            )
        )
        self._pace_threshold_input.setValue(self._pace_autofocus_threshold)
        self._pace_threshold_input.setEnabled(
            self._paceman_mode and self._pace_autofocus_enabled
        )
        good_splits = settings.get("pace_good_splits")
        if isinstance(good_splits, dict):
            self._pace_good_splits = {
                str(key): float(value)
                for key, value in good_splits.items()
                if value is not None
            }
        progression_bonus = settings.get("pace_progression_bonus")
        if isinstance(progression_bonus, dict):
            self._pace_progression_bonus = {
                str(key): float(value)
                for key, value in progression_bonus.items()
                if value is not None
            }
        if self._pace_good_splits or self._pace_progression_bonus:
            set_pace_config(
                good_splits_sec=self._pace_good_splits,
                progression_bonus=self._pace_progression_bonus,
            )

    def shutdown(self) -> None:
        self._paceman_timer.stop()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(500)

    def _update_focus_label(self) -> None:
        if self._focused_channel:
            self._focus_label.setText(f"Focused: {self._focused_channel}")
        else:
            self._focus_label.setText("Focused: none")

    def _icon_for_run(self, run: PacemanRun) -> QtGui.QPixmap | None:
        event_id = getattr(run, "last_event_id", None)
        if not isinstance(event_id, str):
            return None
        icon_name = _ICON_NAME_BY_EVENT.get(event_id)
        if not icon_name:
            return None
        cached = self._icon_cache.get(icon_name)
        if cached is not None:
            return cached
        icon_path = self._ensure_icon(icon_name)
        if not icon_path:
            return None
        pixmap = QtGui.QPixmap(str(icon_path))
        if pixmap.isNull():
            return None
        self._icon_cache[icon_name] = pixmap
        return pixmap

    def _ensure_icon(self, icon_name: str) -> Path | None:
        icon_path = self._icon_dir / icon_name
        if icon_path.exists():
            return icon_path
        return None

    @staticmethod
    def _format_paceman_event(run: PacemanRun) -> str:
        if not run.last_event_label:
            return ""
        if run.last_event_time_ms is None:
            return run.last_event_label
        total_seconds = max(0, run.last_event_time_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{run.last_event_label} {minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_event_time(run: PacemanRun) -> str:
        if run.last_event_time_ms is None:
            return ""
        total_seconds = max(0, run.last_event_time_ms // 1000)
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_pb_time(run: PacemanRun) -> str:
        if run.pb_time_sec is None:
            return ""
        minutes = int(run.pb_time_sec) // 60
        seconds = int(run.pb_time_sec) % 60
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_estimated_time(run: PacemanRun) -> str:
        if run.pace_estimated_time_sec is None:
            return ""
        total_seconds = max(0, int(run.pace_estimated_time_sec))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _format_pace(run: PacemanRun) -> str:
        if run.pace_score is None:
            return ""
        pace_label = f"{run.pace_score:.2f}"
        if run.pace_split:
            pace_label = f"{pace_label} ({run.pace_split})"
        return pace_label
