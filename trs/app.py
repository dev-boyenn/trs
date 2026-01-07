import signal
import sys

from PySide6 import QtCore, QtWidgets

from .auth import get_oauth_token
from .qt_utils import configure_qt_plugins
from .storage import load_saved_state, save_state
from .stream_resolver import resolve_channel_urls
from .ui.control_panel import ControlPanelWindow
from .ui.player_window import PlayerWindow


def main() -> int:
    oauth_token = get_oauth_token()
    streams, settings = load_saved_state()

    configure_qt_plugins()
    app = QtWidgets.QApplication(sys.argv)
    player_window = PlayerWindow()
    player_window.show()
    player_window.set_urls(resolve_channel_urls(streams, oauth_token))

    control_panel = ControlPanelWindow(streams, settings)
    current_streams = list(streams)
    current_settings = dict(settings)

    def on_manual_streams_changed(updated: list[str]) -> None:
        nonlocal current_streams
        current_streams = list(updated)
        save_state(current_streams, current_settings)

    def on_active_streams_changed(updated: list[str], focused: bool) -> None:
        player_window.set_urls(
            resolve_channel_urls(updated, oauth_token),
            focused=focused,
        )

    def on_settings_changed(updated: dict[str, object]) -> None:
        nonlocal current_settings
        current_settings = dict(updated)
        save_state(current_streams, current_settings)

    control_panel.manual_streams_changed.connect(on_manual_streams_changed)
    control_panel.active_streams_changed.connect(on_active_streams_changed)
    control_panel.settings_changed.connect(on_settings_changed)
    control_panel.show()

    def on_shutdown() -> None:
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
