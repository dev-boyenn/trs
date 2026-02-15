import signal
import sys

from PySide6 import QtCore, QtWidgets

from .auth import get_oauth_token
from .config import PERF_LOG_FILE
from .perf_log import perf_timer, setup_perf_logger
from .qt_utils import configure_qt_plugins
from .storage import load_saved_state, save_state
from .stream_resolver import resolve_channel_urls
from .ui.control_panel import ControlPanelWindow
from .ui.player_window import PlayerWindow


class _ResolveWorkerSignals(QtCore.QObject):
    finished = QtCore.Signal(list, bool, int)


class _ResolveWorker(QtCore.QRunnable):
    def __init__(
        self,
        channels: list[str],
        oauth_token: str,
        focused: bool,
        request_id: int,
        max_quality: int,
    ) -> None:
        super().__init__()
        self._channels = list(channels)
        self._oauth_token = oauth_token
        self._focused = focused
        self._request_id = request_id
        self._max_quality = max_quality
        self.signals = _ResolveWorkerSignals()

    def run(self) -> None:
        with perf_timer(
            "resolve_channel_urls",
            count=len(self._channels),
            focused=self._focused,
            request_id=self._request_id,
            max_quality=self._max_quality,
        ):
            resolved = resolve_channel_urls(
                self._channels,
                self._oauth_token,
                max_quality=self._max_quality,
            )
        self.signals.finished.emit(
            resolved,
            self._focused,
            self._request_id,
        )


def main() -> int:
    oauth_token = get_oauth_token()
    saved_streams, settings = load_saved_state()

    configure_qt_plugins()
    setup_perf_logger(PERF_LOG_FILE)
    app = QtWidgets.QApplication(sys.argv)
    player_window = PlayerWindow()
    player_window.show()
    initial_manual_columns = max(0, int(settings.get("manual_grid_columns", 0)))
    initial_manual_rows = max(0, int(settings.get("manual_grid_rows", 0)))
    player_window.set_manual_grid_limits(
        initial_manual_columns,
        initial_manual_rows,
    )
    manual_mode = not bool(settings.get("paceman_mode", False))
    initial_manual_layout = manual_mode or bool(
        settings.get("paceman_fallback", False)
    )
    initial_streams = list(saved_streams)
    initial_max_quality = int(settings.get("max_stream_quality", 720))
    player_window.set_streams(
        resolve_channel_urls(
            initial_streams,
            oauth_token,
            max_quality=initial_max_quality,
        ),
        manual_mode=initial_manual_layout,
    )

    control_panel = ControlPanelWindow(saved_streams, settings)
    current_streams = list(saved_streams)
    current_settings = dict(settings)
    thread_pool = QtCore.QThreadPool.globalInstance()
    latest_request_id = 0
    request_manual_layout: dict[int, bool] = {}
    pending_resolve_workers: dict[int, _ResolveWorker] = {}

    def on_manual_streams_changed(updated: list[str]) -> None:
        nonlocal current_streams
        current_streams = list(updated)
        save_state(current_streams, current_settings)

    def on_streams_resolved(
        resolved: list[object],
        focused: bool,
        request_id: int,
    ) -> None:
        pending_resolve_workers.pop(request_id, None)
        manual_mode = request_manual_layout.pop(
            request_id,
            control_panel.is_manual_source_active(),
        )
        if request_id != latest_request_id:
            return
        with perf_timer(
            "player_window.set_streams",
            count=len(resolved),
            focused=focused,
            request_id=request_id,
            manual_mode=manual_mode,
        ):
            player_window.set_streams(
                resolved,
                focused=focused,
                manual_mode=manual_mode,
            )

    def on_active_streams_changed(
        updated: list[str],
        focused: bool,
        manual_layout: bool,
    ) -> None:
        nonlocal latest_request_id
        latest_request_id += 1
        request_id = latest_request_id
        request_manual_layout[request_id] = manual_layout
        channels = list(updated)
        max_quality = int(current_settings.get("max_stream_quality", 720))
        worker = _ResolveWorker(
            channels,
            oauth_token,
            focused,
            request_id,
            max_quality,
        )
        worker.signals.finished.connect(on_streams_resolved)
        pending_resolve_workers[request_id] = worker
        thread_pool.start(worker)

    def on_settings_changed(updated: dict[str, object]) -> None:
        nonlocal current_settings
        previous_manual_columns = max(
            0, int(current_settings.get("manual_grid_columns", 0))
        )
        previous_manual_rows = max(
            0, int(current_settings.get("manual_grid_rows", 0))
        )
        current_settings = dict(updated)
        manual_columns = max(
            0, int(current_settings.get("manual_grid_columns", 0))
        )
        manual_rows = max(0, int(current_settings.get("manual_grid_rows", 0)))
        player_window.set_manual_grid_limits(manual_columns, manual_rows)
        save_state(current_streams, current_settings)
        if (
            manual_columns != previous_manual_columns
            or manual_rows != previous_manual_rows
        ):
            control_panel.force_refresh_active_streams()

    def on_overlay_info_changed(
        info: dict[str, dict[str, str | None]],
        enabled: bool,
    ) -> None:
        player_window.set_overlay_info(info, enabled)

    control_panel.manual_streams_changed.connect(on_manual_streams_changed)
    control_panel.active_streams_changed.connect(on_active_streams_changed)
    control_panel.settings_changed.connect(on_settings_changed)
    control_panel.overlay_info_changed.connect(on_overlay_info_changed)
    control_panel.fullscreen_toggled.connect(player_window.set_fullscreen)
    control_panel.show()

    def on_shutdown() -> None:
        pending_resolve_workers.clear()
        player_window.shutdown()
        control_panel.shutdown()

    app.aboutToQuit.connect(on_shutdown)

    def handle_sigint(_signum: int, _frame: object) -> None:
        QtCore.QCoreApplication.quit()

    signal.signal(signal.SIGINT, handle_sigint)
    sigint_timer = QtCore.QTimer()
    sigint_timer.setInterval(250)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()

    return app.exec()
