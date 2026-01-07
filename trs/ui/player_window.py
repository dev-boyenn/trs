import math
from dataclasses import dataclass

from PySide6 import QtCore, QtMultimedia, QtMultimediaWidgets, QtWidgets

from ..config import APP_TITLE


class PlayerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 720)

        self._central = QtWidgets.QWidget(self)
        self.setCentralWidget(self._central)
        self._grid = QtWidgets.QGridLayout(self._central)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)

        self._entries: dict[str, "_PlayerEntry"] = {}
        self._placeholder: QtWidgets.QLabel | None = None
        self._last_urls: list[str] = []
        self._last_focused = False
        self._last_grid_rows = 0
        self._last_grid_cols = 0

    def set_urls(self, urls: list[str], focused: bool = False) -> None:
        if urls == self._last_urls and focused == self._last_focused:
            return
        self._last_urls = list(urls)
        self._last_focused = focused
        if not urls:
            self._clear_players()
            self._placeholder = QtWidgets.QLabel("No streams configured.", self)
            self._placeholder.setAlignment(QtCore.Qt.AlignCenter)
            self._grid.addWidget(self._placeholder, 0, 0)
            return
        if self._placeholder is not None:
            self._grid.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None

        old_entries = self._entries
        self._entries = {}
        ordered_entries: list["_PlayerEntry"] = []
        for url in urls:
            entry = old_entries.pop(url, None)
            if entry is None:
                entry = self._create_entry(url)
            self._entries[url] = entry
            ordered_entries.append(entry)

        for entry in old_entries.values():
            self._release_entry(entry)

        self._clear_layout(ordered_entries)
        if focused and len(ordered_entries) > 1:
            rows, cols = self._layout_focused(ordered_entries)
        else:
            columns = max(1, math.ceil(math.sqrt(len(ordered_entries))))
            for index, entry in enumerate(ordered_entries):
                row = index // columns
                col = index % columns
                self._add_player_widget(row, col, entry)
            rows = math.ceil(len(ordered_entries) / columns)
            cols = columns
        self._apply_grid_stretch(rows, cols, focused)
        self._apply_audio_focus(ordered_entries)

    def _layout_focused(self, entries: list["_PlayerEntry"]) -> tuple[int, int]:
        top_entry = entries[0]
        bottom_entries = entries[1:]
        columns = max(1, len(bottom_entries))
        self._add_player_widget(0, 0, top_entry, col_span=columns)
        for index, entry in enumerate(bottom_entries):
            self._add_player_widget(1, index, entry)
        return 2, columns

    def _add_player_widget(
        self, row: int, col: int, entry: "_PlayerEntry", col_span: int = 1
    ) -> None:
        self._grid.addWidget(entry.video_widget, row, col, 1, col_span)

    def _clear_players(self) -> None:
        for entry in self._entries.values():
            self._release_entry(entry)
        if self._placeholder is not None:
            self._grid.removeWidget(self._placeholder)
            self._placeholder.deleteLater()
            self._placeholder = None

        self._entries.clear()
        self._apply_grid_stretch(0, 0, False)

    def shutdown(self) -> None:
        self._clear_players()

    def _on_error(
        self, error: QtMultimedia.QMediaPlayer.Error, error_string: str
    ) -> None:
        if error == QtMultimedia.QMediaPlayer.NoError:
            return
        print(f"qt multimedia error: {error_string}")

    def _clear_layout(self, entries: list["_PlayerEntry"]) -> None:
        for entry in entries:
            self._grid.removeWidget(entry.video_widget)

    def _apply_audio_focus(self, entries: list["_PlayerEntry"]) -> None:
        for index, entry in enumerate(entries):
            entry.audio_output.setVolume(1.0 if index == 0 else 0.0)

    def _apply_grid_stretch(self, rows: int, cols: int, focused: bool) -> None:
        for row in range(rows, self._last_grid_rows):
            self._grid.setRowStretch(row, 0)
        for col in range(cols, self._last_grid_cols):
            self._grid.setColumnStretch(col, 0)
        if focused and rows >= 2:
            self._grid.setRowStretch(0, 7)
            self._grid.setRowStretch(1, 3)
            for row in range(2, rows):
                self._grid.setRowStretch(row, 1)
        else:
            for row in range(rows):
                self._grid.setRowStretch(row, 1)
        for col in range(cols):
            self._grid.setColumnStretch(col, 1)
        self._last_grid_rows = rows
        self._last_grid_cols = cols


    def _create_entry(self, url: str) -> "_PlayerEntry":
        video_widget = QtMultimediaWidgets.QVideoWidget(self)
        player = QtMultimedia.QMediaPlayer(self)
        audio_output = QtMultimedia.QAudioOutput(self)
        player.setAudioOutput(audio_output)
        player.setVideoOutput(video_widget)
        player.errorOccurred.connect(self._on_error)
        player.setSource(QtCore.QUrl(url))
        player.play()
        return _PlayerEntry(url, player, audio_output, video_widget)

    def _release_entry(self, entry: "_PlayerEntry") -> None:
        entry.player.stop()
        entry.player.deleteLater()
        entry.audio_output.deleteLater()
        self._grid.removeWidget(entry.video_widget)
        entry.video_widget.deleteLater()


@dataclass(frozen=True)
class _PlayerEntry:
    url: str
    player: QtMultimedia.QMediaPlayer
    audio_output: QtMultimedia.QAudioOutput
    video_widget: QtMultimediaWidgets.QVideoWidget
