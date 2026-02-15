import math
import time
from pathlib import Path
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtMultimedia, QtWidgets

from ..config import APP_TITLE
from ..perf_log import log_perf
from ..stream_resolver import StreamEntry


class _VideoSurface(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._image = QtGui.QImage()
        self._sink = QtMultimedia.QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

    def video_sink(self) -> QtMultimedia.QVideoSink:
        return self._sink

    def _on_frame(self, frame: QtMultimedia.QVideoFrame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._image = image
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.black)
        if self._image.isNull():
            return
        target = self._scaled_rect(self._image.size(), self.rect())
        painter.drawImage(target, self._image)

    @staticmethod
    def _scaled_rect(
        image_size: QtCore.QSize,
        target_rect: QtCore.QRect,
    ) -> QtCore.QRect:
        scaled = image_size.scaled(
            target_rect.size(),
            QtCore.Qt.KeepAspectRatio,
        )
        x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
        y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
        return QtCore.QRect(
            x,
            y,
            scaled.width(),
            scaled.height(),
        )


class _ClickableOverlay(QtWidgets.QFrame):
    clicked = QtCore.Signal()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _StreamContainer(QtWidgets.QWidget):
    def __init__(
        self,
        video_widget: _VideoSurface,
        overlay_frame: QtWidgets.QFrame,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(video_widget)
        overlay_frame.setParent(self)
        overlay_frame.raise_()
        overlay_frame.move(16, 16)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        for child in self.findChildren(QtWidgets.QFrame):
            if child.objectName() == "streamOverlay":
                child.move(16, 16)
                break


class PlayerWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 720)

        self._central = QtWidgets.QWidget(self)
        self.setCentralWidget(self._central)
        self._grid = QtWidgets.QGridLayout(self._central)
        self._normal_margins = (8, 8, 8, 8)
        self._grid.setContentsMargins(*self._normal_margins)
        self._grid.setSpacing(8)

        self._entries: dict[str, "_PlayerEntry"] = {}
        self._placeholder: QtWidgets.QLabel | None = None
        self._last_streams: list[StreamEntry] = []
        self._last_focused = False
        self._last_manual_mode = False
        self._last_manual_grid_columns = 0
        self._last_manual_grid_rows = 0
        self._last_grid_rows = 0
        self._last_grid_cols = 0
        self._manual_grid_columns = 0
        self._manual_grid_rows = 0
        self._overlay_info: dict[str, dict[str, str | None]] = {}
        self._overlay_enabled = True
        self._icon_cache: dict[str, QtGui.QPixmap] = {}
        self._channel_muted: dict[str, bool] = {}
        self._icon_dir = (
            Path(__file__).resolve().parent.parent
            / "assets"
            / "paceman-icons"
        )

    def set_fullscreen(self, enabled: bool) -> None:
        if enabled == self.isFullScreen():
            return
        if enabled:
            self._grid.setContentsMargins(0, 0, 0, 0)
            self.showFullScreen()
        else:
            self.showNormal()
            self._grid.setContentsMargins(*self._normal_margins)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key_F11:
            self.set_fullscreen(not self.isFullScreen())
            event.accept()
            return
        if event.key() == QtCore.Qt.Key_Escape and self.isFullScreen():
            self.set_fullscreen(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def set_manual_grid_limits(self, columns: int, rows: int) -> None:
        self._manual_grid_columns = max(0, int(columns))
        self._manual_grid_rows = max(0, int(rows))

    def set_streams(
        self,
        streams: list[StreamEntry],
        focused: bool = False,
        manual_mode: bool = False,
    ) -> None:
        start = time.perf_counter()
        effective_streams = list(streams)
        if (
            manual_mode
            and not focused
            and self._manual_grid_columns > 0
            and self._manual_grid_rows > 0
        ):
            effective_streams = effective_streams[
                : self._manual_grid_columns * self._manual_grid_rows
            ]
        if (
            effective_streams == self._last_streams
            and focused == self._last_focused
            and manual_mode == self._last_manual_mode
            and self._manual_grid_columns == self._last_manual_grid_columns
            and self._manual_grid_rows == self._last_manual_grid_rows
        ):
            return
        self._last_streams = list(effective_streams)
        self._last_focused = focused
        self._last_manual_mode = manual_mode
        self._last_manual_grid_columns = self._manual_grid_columns
        self._last_manual_grid_rows = self._manual_grid_rows
        if not effective_streams:
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
        active_channels: set[str] = set()
        created = 0
        reused = 0
        for index, stream in enumerate(effective_streams):
            active_channels.add(stream.channel)
            if stream.channel not in self._channel_muted:
                self._channel_muted[stream.channel] = index != 0
            entry = old_entries.pop(stream.channel, None)
            if entry is None or entry.url != stream.url:
                if entry is not None:
                    self._release_entry(entry)
                entry = self._create_entry(stream.channel, stream.url)
                created += 1
            else:
                reused += 1
            self._entries[stream.channel] = entry
            ordered_entries.append(entry)

        released = len(old_entries)
        for entry in old_entries.values():
            self._release_entry(entry)
        for channel in list(self._channel_muted):
            if channel not in active_channels:
                self._channel_muted.pop(channel, None)

        self._clear_layout(ordered_entries)
        use_focused_layout = (
            focused
            and len(ordered_entries) > 1
        )
        if use_focused_layout:
            rows, cols = self._layout_focused(ordered_entries)
        else:
            columns = self._compute_grid_columns(
                len(ordered_entries),
                manual_mode=manual_mode,
            )
            for index, entry in enumerate(ordered_entries):
                row = index // columns
                col = index % columns
                self._add_player_widget(row, col, entry)
            rows = math.ceil(len(ordered_entries) / columns)
            cols = columns
        self._apply_grid_stretch(rows, cols, focused)
        self._apply_audio_levels(ordered_entries)
        for entry in ordered_entries:
            self._update_entry_overlay(entry)
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_perf(
            "player_window.set_streams.internal",
            duration_ms=duration_ms,
            streams=len(effective_streams),
            focused=focused,
            created=created,
            reused=reused,
            released=released,
        )

    def set_overlay_info(
        self,
        info: dict[str, dict[str, str | None]],
        enabled: bool,
    ) -> None:
        self._overlay_info = dict(info)
        self._overlay_enabled = enabled
        for entry in self._entries.values():
            self._update_entry_overlay(entry)

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
        self._grid.addWidget(entry.container, row, col, 1, col_span)

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
            self._grid.removeWidget(entry.container)

    def _apply_audio_levels(self, entries: list["_PlayerEntry"]) -> None:
        for entry in entries:
            is_muted = self._channel_muted.get(entry.channel, True)
            entry.audio_output.setVolume(0.0 if is_muted else 1.0)

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

    def _compute_grid_columns(self, count: int, manual_mode: bool) -> int:
        if count <= 0:
            return 1
        if manual_mode and self._manual_grid_columns > 0:
            return self._manual_grid_columns
        if manual_mode and self._manual_grid_rows > 0:
            return max(1, math.ceil(count / self._manual_grid_rows))
        return max(1, math.ceil(math.sqrt(count)))


    def _create_entry(self, channel: str, url: str) -> "_PlayerEntry":
        video_widget = _VideoSurface(self)
        player = QtMultimedia.QMediaPlayer(self)
        audio_output = QtMultimedia.QAudioOutput(self)
        player.setAudioOutput(audio_output)
        player.setVideoOutput(video_widget.video_sink())
        player.errorOccurred.connect(self._on_error)
        player.setSource(QtCore.QUrl(url))
        player.play()
        overlay_frame = _ClickableOverlay(self)
        overlay_frame.setObjectName("streamOverlay")
        overlay_frame.setStyleSheet(
            "QFrame#streamOverlay { background: rgba(0, 0, 0, 150);"
            " border-radius: 8px; }"
            " QFrame#streamOverlay QLabel { color: #f5f5f5; font-size: 18px; }"
        )
        overlay_frame.clicked.connect(
            lambda c=channel: self._toggle_channel_mute(c)
        )
        overlay_layout = QtWidgets.QVBoxLayout(overlay_frame)
        overlay_layout.setContentsMargins(10, 6, 10, 6)
        overlay_layout.setSpacing(2)
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        icon_label = QtWidgets.QLabel(overlay_frame)
        icon_label.setFixedSize(22, 22)
        icon_label.setScaledContents(True)
        icon_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        time_label = QtWidgets.QLabel("", overlay_frame)
        time_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        top_row.addWidget(icon_label)
        top_row.addWidget(time_label)
        top_row.addStretch(1)
        overlay_layout.addLayout(top_row)
        name_label = QtWidgets.QLabel("", overlay_frame)
        font = name_label.font()
        font.setBold(True)
        name_label.setFont(font)
        name_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        overlay_layout.addWidget(name_label)
        container = _StreamContainer(video_widget, overlay_frame, self)
        overlay_frame.setVisible(False)
        return _PlayerEntry(
            channel=channel,
            url=url,
            player=player,
            audio_output=audio_output,
            video_widget=video_widget,
            container=container,
            overlay_frame=overlay_frame,
            overlay_icon=icon_label,
            overlay_time=time_label,
            overlay_name=name_label,
        )

    def _release_entry(self, entry: "_PlayerEntry") -> None:
        entry.player.stop()
        entry.player.setVideoOutput(None)
        entry.player.setAudioOutput(None)
        entry.player.setSource(QtCore.QUrl())
        entry.player.deleteLater()
        entry.audio_output.deleteLater()
        self._grid.removeWidget(entry.container)
        entry.container.deleteLater()

    def _update_entry_overlay(self, entry: "_PlayerEntry") -> None:
        is_muted = self._channel_muted.get(entry.channel, True)
        if not self._overlay_enabled:
            entry.overlay_frame.setVisible(False)
            return
        info = self._overlay_info.get(entry.channel) or {}
        name = info.get("runner") or entry.channel
        split_time = info.get("split_time") or ""
        pb_time = info.get("pb_time") or ""
        name_label = (
            f"{name} (PB: {pb_time})" if pb_time else name
        )
        entry.overlay_name.setText(name_label)
        mute_state = "Muted" if is_muted else "Live"
        if split_time:
            entry.overlay_time.setText(f"{split_time} • {mute_state}")
        else:
            entry.overlay_time.setText(mute_state)
        icon_name = info.get("icon_name")
        pixmap = self._pixmap_for_icon(icon_name)
        entry.overlay_icon.setPixmap(pixmap or QtGui.QPixmap())
        visible = True
        if visible:
            entry.overlay_frame.adjustSize()
            entry.overlay_frame.raise_()
        entry.overlay_frame.setVisible(visible)

    def _toggle_channel_mute(self, channel: str) -> None:
        if not channel:
            return
        current = self._channel_muted.get(channel, True)
        self._channel_muted[channel] = not current
        entry = self._entries.get(channel)
        if entry is None:
            return
        entry.audio_output.setVolume(0.0 if self._channel_muted[channel] else 1.0)
        self._update_entry_overlay(entry)

    def _pixmap_for_icon(self, icon_name: str | None) -> QtGui.QPixmap | None:
        if not icon_name:
            return None
        cached = self._icon_cache.get(icon_name)
        if cached is not None:
            return cached
        icon_path = self._icon_dir / icon_name
        if not icon_path.exists():
            return None
        pixmap = QtGui.QPixmap(str(icon_path))
        if pixmap.isNull():
            return None
        self._icon_cache[icon_name] = pixmap
        return pixmap


@dataclass(frozen=True)
class _PlayerEntry:
    channel: str
    url: str
    player: QtMultimedia.QMediaPlayer
    audio_output: QtMultimedia.QAudioOutput
    video_widget: _VideoSurface
    container: QtWidgets.QWidget
    overlay_frame: QtWidgets.QFrame
    overlay_icon: QtWidgets.QLabel
    overlay_time: QtWidgets.QLabel
    overlay_name: QtWidgets.QLabel
