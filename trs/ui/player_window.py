import math

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

        self._players: list[QtMultimedia.QMediaPlayer] = []
        self._audio_outputs: list[QtMultimedia.QAudioOutput] = []
        self._video_widgets: list[QtMultimediaWidgets.QVideoWidget] = []
        self._placeholder: QtWidgets.QLabel | None = None

    def set_urls(self, urls: list[str]) -> None:
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
