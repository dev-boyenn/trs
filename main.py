import json
import math
import os
import sys
from pathlib import Path

from PySide6 import QtCore, QtMultimedia, QtMultimediaWidgets, QtWidgets
from streamlink import Streamlink

TOKEN_ENV_VAR = "TWITCH_OAUTH_TOKEN"
SAVE_FILE = Path("save.json")


def configure_qt_plugins() -> None:
    # Ensure Qt can find multimedia plugins when running from a bundled Python.
    pyside_dir = Path(QtCore.__file__).resolve().parent
    plugin_dir = pyside_dir / "plugins"
    if plugin_dir.is_dir():
        QtCore.QCoreApplication.addLibraryPath(str(plugin_dir))
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_dir))
        # Keep DLL resolution happy for the FFmpeg backend shipped with PySide6.
        os.environ.setdefault("PATH", str(pyside_dir) + os.pathsep + os.environ.get("PATH", ""))
        # Windows needs explicit DLL search paths for plugin dependencies.
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(pyside_dir))
            os.add_dll_directory(str(plugin_dir))


def get_oauth_token() -> str:
    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    if not token:
        print(f"missing required auth token: set {TOKEN_ENV_VAR}")
        raise SystemExit(2)
    return token


def resolve_hls_url(channel: str, oauth_token: str) -> str:
    session = Streamlink()
    session.set_option("twitch-oauth-token", oauth_token)
    streams = session.streams(f"https://twitch.tv/{channel}")
    stream = streams.get("best")
    if stream is None:
        raise RuntimeError(f"streamlink could not resolve '{channel}'")
    return stream.to_url()


class PlayerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("TRS")
        self.resize(1280, 720)

        self._central = QtWidgets.QWidget(self)
        self.setCentralWidget(self._central)
        self._grid = QtWidgets.QGridLayout(self._central)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)

        self._players: list[QtMultimedia.QMediaPlayer] = []
        self._audio_outputs: list[QtMultimedia.QAudioOutput] = []
        self._video_widgets: list[QtMultimediaWidgets.QVideoWidget] = []
        self._placeholder: QtWidgets.QLabel | None = None

    def set_streams(self, channels: list[str], oauth_token: str) -> None:
        urls: list[str] = []
        for channel in channels:
            try:
                urls.append(resolve_hls_url(channel, oauth_token))
            except Exception as exc:
                print(f"stream resolve failed for '{channel}': {exc}")
        self._set_urls(urls)

    def _set_urls(self, urls: list[str]) -> None:
        self._clear_players()
        if not urls:
            self._placeholder = QtWidgets.QLabel("No streams configured.", self)
            self._placeholder.setAlignment(QtCore.Qt.AlignCenter)
            self._grid.addWidget(self._placeholder, 0, 0)
            return

        columns = max(1, math.ceil(math.sqrt(len(urls))))
        for index, url in enumerate(urls):
            row = index // columns
            col = index % columns
            video_widget = QtMultimediaWidgets.QVideoWidget(self)
            self._grid.addWidget(video_widget, row, col)

            player = QtMultimedia.QMediaPlayer(self)
            audio_output = QtMultimedia.QAudioOutput(self)
            if index != 0:
                audio_output.setVolume(0.0)
            player.setAudioOutput(audio_output)
            player.setVideoOutput(video_widget)
            player.errorOccurred.connect(self._on_error)
            player.setSource(QtCore.QUrl(url))
            player.play()

            self._video_widgets.append(video_widget)
            self._players.append(player)
            self._audio_outputs.append(audio_output)

    def _clear_players(self) -> None:
        for player in self._players:
            player.stop()
            player.deleteLater()
        for audio_output in self._audio_outputs:
            audio_output.deleteLater()
        for widget in self._video_widgets:
            self._grid.removeWidget(widget)
            widget.deleteLater()
        if self._placeholder is not None:
            self._grid.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None

        self._players.clear()
        self._audio_outputs.clear()
        self._video_widgets.clear()

    def _on_error(
        self, error: QtMultimedia.QMediaPlayer.Error, error_string: str
    ) -> None:
        if error == QtMultimedia.QMediaPlayer.NoError:
            return
        print(f"qt multimedia error: {error_string}")


class ControlPanelWindow(QtWidgets.QWidget):
    streams_changed = QtCore.Signal(list)

    def __init__(self, streams: list[str]) -> None:
        super().__init__()
        self.setWindowTitle("TRS Control Panel")
        self.resize(360, 480)
        self._streams = list(streams)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

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
        layout.addWidget(self._list, 1)
        self._refresh_list()

    def _add_stream(self) -> None:
        channel = self._input.text().strip()
        if not channel:
            return
        if channel in self._streams:
            self._input.clear()
            return
        self._streams.append(channel)
        self._input.clear()
        self._refresh_list()
        self.streams_changed.emit(list(self._streams))

    def _remove_stream(self, channel: str) -> None:
        if channel not in self._streams:
            return
        self._streams.remove(channel)
        self._refresh_list()
        self.streams_changed.emit(list(self._streams))

    def _refresh_list(self) -> None:
        self._list.clear()
        for channel in self._streams:
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


def load_saved_streams() -> list[str]:
    if not SAVE_FILE.exists():
        SAVE_FILE.write_text(json.dumps({"streams": []}, indent=2), encoding="utf-8")
        return []
    try:
        payload = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    streams = payload.get("streams", [])
    if not isinstance(streams, list):
        return []
    return [str(stream).strip() for stream in streams if str(stream).strip()]


def save_streams(streams: list[str]) -> None:
    SAVE_FILE.write_text(
        json.dumps({"streams": streams}, indent=2), encoding="utf-8"
    )


def main() -> int:
    oauth_token = get_oauth_token()
    streams = load_saved_streams()

    configure_qt_plugins()
    app = QtWidgets.QApplication(sys.argv)
    player_window = PlayerWindow()
    player_window.show()
    player_window.set_streams(streams, oauth_token)

    control_panel = ControlPanelWindow(streams)

    def on_streams_changed(updated: list[str]) -> None:
        save_streams(updated)
        player_window.set_streams(updated, oauth_token)

    control_panel.streams_changed.connect(on_streams_changed)
    control_panel.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
