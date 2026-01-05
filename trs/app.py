import sys

from PySide6 import QtWidgets

from .auth import get_oauth_token
from .qt_utils import configure_qt_plugins
from .storage import load_saved_streams, save_streams
from .stream_resolver import resolve_channel_urls
from .ui.control_panel import ControlPanelWindow
from .ui.player_window import PlayerWindow


def main() -> int:
    oauth_token = get_oauth_token()
    streams = load_saved_streams()

    configure_qt_plugins()
    app = QtWidgets.QApplication(sys.argv)
    player_window = PlayerWindow()
    player_window.show()
    player_window.set_urls(resolve_channel_urls(streams, oauth_token))

    control_panel = ControlPanelWindow(streams)

    def on_streams_changed(updated: list[str]) -> None:
        save_streams(updated)
        player_window.set_urls(resolve_channel_urls(updated, oauth_token))

    control_panel.streams_changed.connect(on_streams_changed)
    control_panel.show()
    return app.exec()
