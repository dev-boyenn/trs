from PySide6 import QtCore, QtWidgets

from ..config import CONTROL_PANEL_TITLE
from ..paceman import PacemanRun, fetch_live_runs


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


class ControlPanelWindow(QtWidgets.QWidget):
    manual_streams_changed = QtCore.Signal(list)
    active_streams_changed = QtCore.Signal(list, bool)
    settings_changed = QtCore.Signal(dict)

    def __init__(
        self,
        streams: list[str],
        settings: dict[str, bool] | None = None,
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
        self._focused_channel: str | None = None
        self._current_worker: _PacemanWorker | None = None
        self._thread_pool = QtCore.QThreadPool.globalInstance()
        self._paceman_timer = QtCore.QTimer(self)
        self._paceman_timer.setInterval(10_000)
        self._paceman_timer.timeout.connect(self._start_paceman_refresh)
        self._last_active_streams: list[str] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        options_row = QtWidgets.QHBoxLayout()
        self._paceman_toggle = QtWidgets.QCheckBox("Paceman mode", self)
        self._paceman_toggle.toggled.connect(self._toggle_paceman_mode)
        self._show_hidden_toggle = QtWidgets.QCheckBox("Show hidden/cheated", self)
        self._show_hidden_toggle.toggled.connect(self._toggle_show_hidden)
        self._show_hidden_toggle.setEnabled(False)
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
        options_row.addWidget(self._paceman_toggle)
        options_row.addWidget(self._show_hidden_toggle)
        options_row.addWidget(self._paceman_fallback_toggle)
        options_row.addStretch(1)
        options_row.addWidget(self._refresh_button)
        options_row.addWidget(self._clear_focus_button)
        layout.addLayout(options_row)

        self._status_label = QtWidgets.QLabel("", self)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        form_row = QtWidgets.QHBoxLayout()
        self._input = QtWidgets.QLineEdit(self)
        self._input.setPlaceholderText("twitch channel name")
        self._add_button = QtWidgets.QPushButton("Add Stream", self)
        self._add_button.clicked.connect(self._add_stream)
        self._input.returnPressed.connect(self._add_stream)
        form_row.addWidget(self._input)
        form_row.addWidget(self._add_button)
        layout.addLayout(form_row)

        self._list = QtWidgets.QListWidget(self)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list, 1)
        self._apply_settings(settings)
        self._refresh_list()

    def _toggle_paceman_mode(self, enabled: bool) -> None:
        self._paceman_mode = enabled
        self._show_hidden_toggle.setEnabled(enabled)
        self._paceman_fallback_toggle.setEnabled(enabled)
        self._refresh_button.setEnabled(enabled and not self._paceman_loading)
        self._clear_focus_button.setEnabled(enabled and self._focused_channel is not None)
        self._input.setEnabled(not enabled)
        self._add_button.setEnabled(not enabled)
        self._emit_settings()
        if enabled:
            self._status_label.setText("Fetching live runs...")
            self._start_paceman_refresh()
            self._paceman_timer.start()
        else:
            self._status_label.setText("")
            self._paceman_timer.stop()
            self._focused_channel = None
            self._clear_focus_button.setEnabled(False)
            self._refresh_list()
            self.active_streams_changed.emit(list(self._manual_streams), False)
            self._last_active_streams = list(self._manual_streams)

    def _toggle_show_hidden(self, enabled: bool) -> None:
        self._include_hidden = enabled
        self._emit_settings()
        if self._paceman_mode:
            self._refresh_list()
            self._emit_active_streams()

    def _toggle_paceman_fallback(self, enabled: bool) -> None:
        self._paceman_fallback = enabled
        self._emit_settings()
        if self._paceman_mode:
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
        if self._paceman_mode:
            return
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
        self._refresh_list()
        self.manual_streams_changed.emit(list(self._manual_streams))
        self._emit_active_streams()

    def _refresh_list(self) -> None:
        self._list.clear()
        if self._paceman_mode:
            self._refresh_paceman_list()
        else:
            self._refresh_manual_list()

    def _refresh_manual_list(self) -> None:
        for channel in self._manual_streams:
            item = QtWidgets.QListWidgetItem(self._list)
            row_widget = QtWidgets.QWidget(self._list)
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 4, 6, 4)
            label = QtWidgets.QLabel(channel, row_widget)
            delete_button = QtWidgets.QPushButton("Delete", row_widget)
            delete_button.clicked.connect(
                lambda _, c=channel: self._remove_stream(c)
            )
            row_layout.addWidget(label)
            row_layout.addStretch(1)
            row_layout.addWidget(delete_button)
            item.setSizeHint(row_widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row_widget)

    def _refresh_paceman_list(self) -> None:
        visible_runs = self._filtered_paceman_runs()
        if not visible_runs:
            item = QtWidgets.QListWidgetItem(self._list)
            item.setText("No live runs available.")
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            return
        channels = [run.channel for run in visible_runs if run.channel]
        self._clear_focus_button.setEnabled(
            self._paceman_mode and self._focused_channel is not None
        )
        for run in visible_runs:
            item = QtWidgets.QListWidgetItem(self._list)
            item.setData(QtCore.Qt.UserRole, run.channel or "")
            row_widget = QtWidgets.QWidget(self._list)
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(6, 4, 6, 4)
            label = QtWidgets.QLabel(self._format_paceman_label(run), row_widget)
            if run.channel and run.channel == self._focused_channel:
                label.setStyleSheet("font-weight: 600;")
            focus_button = QtWidgets.QPushButton("Focus", row_widget)
            focus_button.setEnabled(bool(run.channel))
            focus_button.clicked.connect(
                lambda _, c=run.channel: self._set_focus(c)
            )
            row_layout.addWidget(label)
            row_layout.addStretch(1)
            row_layout.addWidget(focus_button)
            item.setSizeHint(row_widget.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row_widget)

    def _filtered_paceman_runs(self) -> list[PacemanRun]:
        if self._include_hidden:
            return list(self._paceman_runs)
        return [
            run
            for run in self._paceman_runs
            if not run.is_hidden and not run.is_cheated
        ]

    def _emit_active_streams(self) -> None:
        if not self._paceman_mode:
            channels = list(self._manual_streams)
            focused = False
        else:
            visible_runs = self._filtered_paceman_runs()
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
        if channels == self._last_active_streams:
            return
        self._last_active_streams = list(channels)
        self.active_streams_changed.emit(channels, focused)

    def _emit_settings(self) -> None:
        self.settings_changed.emit(
            {
                "paceman_mode": self._paceman_mode,
                "include_hidden": self._include_hidden,
                "paceman_fallback": self._paceman_fallback,
            }
        )

    def _set_focus(self, channel: str | None) -> None:
        if not channel:
            return
        if channel == self._focused_channel:
            self._focused_channel = None
        else:
            self._focused_channel = channel
        self._clear_focus_button.setEnabled(
            self._paceman_mode and self._focused_channel is not None
        )
        self._refresh_list()
        self._emit_active_streams()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if not self._paceman_mode:
            return
        channel = item.data(QtCore.Qt.UserRole)
        if channel:
            self._set_focus(str(channel))

    def _clear_focus(self) -> None:
        if not self._paceman_mode or self._focused_channel is None:
            return
        self._focused_channel = None
        self._clear_focus_button.setEnabled(False)
        self._refresh_list()
        self._emit_active_streams()

    def _apply_settings(self, settings: dict[str, bool]) -> None:
        self._paceman_toggle.setChecked(
            bool(settings.get("paceman_mode", False))
        )
        self._show_hidden_toggle.setChecked(
            bool(settings.get("include_hidden", False))
        )
        self._paceman_fallback_toggle.setChecked(
            bool(settings.get("paceman_fallback", False))
        )

    def shutdown(self) -> None:
        self._paceman_timer.stop()
        self._thread_pool.clear()
        self._thread_pool.waitForDone(500)

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
    def _format_paceman_label(run: PacemanRun) -> str:
        if run.channel:
            label = run.channel
            if run.nickname and run.nickname != run.channel:
                label = f"{label} ({run.nickname})"
        else:
            label = run.nickname or "unknown runner"
            label = f"{label} (no live account)"
        flags = []
        if run.is_hidden:
            flags.append("hidden")
        if run.is_cheated:
            flags.append("cheated")
        if flags:
            label = f"{label} [{' '.join(flags)}]"
        event_label = ControlPanelWindow._format_paceman_event(run)
        if event_label:
            label = f"{label} - {event_label}"
        return label
