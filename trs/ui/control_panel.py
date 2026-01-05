from PySide6 import QtCore, QtWidgets

from ..config import CONTROL_PANEL_TITLE


class ControlPanelWindow(QtWidgets.QWidget):
    streams_changed = QtCore.Signal(list)

    def __init__(self, streams: list[str]) -> None:
        super().__init__()
        self.setWindowTitle(CONTROL_PANEL_TITLE)
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
