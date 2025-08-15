"""
Basic widgets for UI.
"""

import csv
import platform
from enum import Enum
from typing import cast, Any, Callable, Union
from copy import copy

from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtCore import QStringListModel, QTimer, Qt, QPropertyAnimation, QRect, Property, QDate, QTime, QDateTime
from PySide6.QtWidgets import QCompleter, QLineEdit, QWidget, QCheckBox, QLabel, QFormLayout, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QFontComboBox, QHBoxLayout, \
    QPushButton, QVBoxLayout, QDateTimeEdit, QDateEdit, QTimeEdit
from tzlocal import get_localzone_name
from datetime import datetime, date, time
from importlib import metadata

from .qt import QtCore, QtGui, QtWidgets, Qt
from ..constant import Direction, Exchange, Offset, OrderType
from ..engine import MainEngine, Event, EventEngine
from ..event import (
    EVENT_QUOTE,
    EVENT_TICK,
    EVENT_TRADE,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG, EVENT_TICK_UNSUB
)
from ..object import (
    OrderRequest,
    SubscribeRequest,
    CancelRequest,
    ContractData,
    PositionData,
    OrderData,
    QuoteData,
    TickData
)
from ..utility import load_json, save_json, get_digits, ZoneInfo
from ..setting import SETTING_FILENAME, SETTINGS
from ..locale import _


COLOR_LONG = QtGui.QColor("red")
COLOR_SHORT = QtGui.QColor("green")
COLOR_BID = QtGui.QColor(255, 174, 201)
COLOR_ASK = QtGui.QColor(160, 255, 160)
COLOR_BLACK = QtGui.QColor("black")


class QSwitch(QCheckBox):
    def __init__(
        self,
        text_on="启用",
        text_off="关闭",
        width=48,
        height=24,
        checked_color="#4CAF50",
        bg_color="#CCCCCC",
        circle_color="#FFFFFF",
        parent=None
    ):
        super().__init__(parent)

        self._circle_pos = 3
        self._width = width
        self._height = height
        self._radius = height // 2
        self._circle_diameter = height - 6
        self._bg_color = QColor(bg_color)
        self._checked_color = QColor(checked_color)
        self._circle_color = QColor(circle_color)
        self._text_on = text_on
        self._text_off = text_off

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(width + 60, height)

        # Label
        self._label = QLabel(self._text_off, self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._label.move(width + 8, 0)
        self._label.setFixedHeight(height)
        self._label.mousePressEvent = self._label_click

        # 动画
        self._anim = QPropertyAnimation(self, b"circlePosition")  # noqa
        self._anim.setTargetObject(self)
        self._anim.setDuration(200)

        self.stateChanged.connect(self.start_animation)
        self.stateChanged.connect(self.update_label)

    def _label_click(self, event):
        self.toggle()

    def update_label(self):
        self._label.setText(self._text_on if self.isChecked() else self._text_off)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        bg_rect = QRect(0, 0, self._width, self._height)
        painter.setBrush(QBrush(self._checked_color if self.isChecked() else self._bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, self._radius, self._radius)

        # 圆圈
        circle_rect = QRect(int(self._circle_pos), 3, self._circle_diameter, self._circle_diameter)
        painter.setBrush(QBrush(self._circle_color))
        painter.drawEllipse(circle_rect)

    def mousePressEvent(self, event):
        if event.pos().x() <= self.width():
            self.toggle()

    def start_animation(self):
        end = self._width - self._circle_diameter - 3 if self.isChecked() else 3
        self._anim.stop()
        self._anim.setStartValue(self._circle_pos)
        self._anim.setEndValue(end)
        self._anim.start()

    def get_circle_pos(self):
        return self._circle_pos

    def set_circle_pos(self, pos):
        self._circle_pos = pos
        self.update()

    circlePosition = Property(float, get_circle_pos, set_circle_pos)  # noqa


class FormWidget(QWidget):
    def __init__(self, title: str, ui_fields: dict, parent = None):
        super().__init__(parent=parent)
        self.title = title
        self.ui_fields: dict = ui_fields

        self.form_layout = QFormLayout()
        self.form_fields: dict[str, Union[QLineEdit, QComboBox, QCheckBox, QTextEdit, QSpinBox, QDoubleSpinBox, QFontComboBox, QDateTimeEdit]] = {}
        self.init_ui()
        self.setLayout(self.form_layout)

    def init_ui(self):
        """
        :param config: dict 配置原始数据
        :param ui_fields: dict 配置 UI 渲染描述
            {
                "username": {"label": "用户名", "type": "str"},
                "password": {"label": "密码", "type": "password"},
                "timeout": {"label": "超时时间", "type": "int", "min": 0, "max": 100},
                "note": {"label": "备注", "type": "text"},
                "env": {"label": "环境", "type": "select", "options": ["dev", "test", "prod"]},
                "sex": {"label": "性别", "type": "select", "options": {"男": "M", "女": "F"}},
            }
        """
        for key, field in self.ui_fields.items():
            if isinstance(field, dict):
                label = field.get("label", key)
                value = field.get("value", None)
                field_type = field.get("type", "str") if "type" in field \
                            else type(value).__name__ if value is not None and type(value) in [str, int, float, bool, date, time, datetime] \
                            else "str"
            else:
                field_type = type(field).__name__ if field is not None and type(field) in [str, int, float, bool, date, time, datetime] else "str"
                label = f"{key}({field_type})"
                value = field

            if field_type == "bool":
                widget = QSwitch()
                if value is not None:
                    widget.setChecked(bool(value))

            elif field_type == "text":
                widget = QTextEdit()
                widget.setPlaceholderText(field.get("placeholder", "请输入%s" % label))
                if value is not None:
                    widget.setText(str(value))

            elif field_type == "int":
                widget = QSpinBox()
                widget.setMinimum(field.get("min", -999999))
                widget.setMaximum(field.get("max", 999999))
                widget.setSingleStep(field.get("step", 1))
                if value is not None:
                    widget.setValue(int(value))

            elif field_type == "float":
                widget = QDoubleSpinBox()
                widget.setDecimals(field.get("decimals", 1))
                widget.setMinimum(field.get("min", -999999.0))
                widget.setMaximum(field.get("max", 999999.0))
                widget.setSingleStep(field.get("step", 0.1))
                if value is not None:
                    widget.setValue(float(value))

            elif field_type == "date":
                widget = QDateEdit()
                if value is not None:
                    widget.setDate(QDate.fromString(value, "yyyy-MM-dd"))
            elif field_type == "time":
                widget = QTimeEdit()
                if value is not None:
                    widget.setTime(QTime.fromString(value, "HH:mm:ss"))
            elif field_type == "datetime":
                widget = QDateTimeEdit()
                if value is not None:
                    widget.setDateTime(QDateTime.fromString(value, "yyyy-MM-dd HH:mm:ss"))

            elif field_type == "select":
                widget = QComboBox()
                options = field.get("options", None)
                if options:
                    _options = options() if isinstance(options, Callable) else options
                    if isinstance(_options, list):
                        for item in _options:
                            widget.addItem(item, item)
                    elif isinstance(_options, dict):
                        for text, item in _options.items():
                            widget.addItem(text, item)

                index = widget.findData(value) if value is not None else -1
                if index >= 0:
                    widget.setCurrentIndex(index)

                widget.setPlaceholderText(field.get("placeholder", "请选择%s" % label))

            elif field_type == "font" or ("font" in key.lower() and "family" in key.lower()):
                widget = QFontComboBox()
                widget.setPlaceholderText(field.get("placeholder", "请选择%s" % label))

                index = widget.findData(value) if value is not None else -1
                if index >= 0:
                    widget.setCurrentIndex(index)

            else:
                widget = QLineEdit()
                widget.setPlaceholderText(field.get("placeholder", "请输入%s" % label))

                if field_type == "password" or "password" in key.lower() or "token" in key.lower() or "secret" in key.lower():
                    widget.setEchoMode(QLineEdit.EchoMode.Password)

                if value is not None:
                    widget.setText(str(value))

            widget.setDisabled(field.get("disabled", False))
            tips = field.get("tips", "")
            if tips:
                widget.setToolTip(tips)

            self.form_layout.addRow(label, widget)
            self.form_fields[key] = widget

    def refresh_config(self, config: dict):
        for key, widget in self.form_fields.items():
            if isinstance(widget, QLineEdit):
                widget.setText(config.get(key, ""))
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(config.get(key, ""))
            elif isinstance(widget, QComboBox):
                index = widget.findData(config.get(key))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(config.get(key, "0")))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(config.get(key, "0.0")))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(config.get(key, False))
            elif isinstance(widget, QFontComboBox):
                widget.setCurrentFont(config.get(key, ""))
            elif isinstance(widget, QDateEdit):
                widget.setDate(QDate.fromString(config.get(key, ""), "yyyy-MM-dd"))
            elif isinstance(widget, QTimeEdit):
                widget.setTime(QTime.fromString(config.get(key, ""), "HH:mm:ss"))
            elif isinstance(widget, QDateTimeEdit):
                widget.setDateTime(QDateTime.fromString(config.get(key, ""), "yyyy-MM-dd HH:mm:ss"))

    def get_config(self) -> dict:
        config = {}
        for key, widget in self.form_fields.items():
            if isinstance(widget, QLineEdit):
                config[key] = widget.text()
            elif isinstance(widget, QTextEdit):
                config[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                config[key] = widget.currentData()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                config[key] = widget.value()
            elif isinstance(widget, QCheckBox):
                config[key] = widget.isChecked()
            elif isinstance(widget, QFontComboBox):
                config[key] = widget.currentFont().family()
            elif isinstance(widget, QDateEdit):
                config[key] = widget.date().toString("yyyy-MM-dd")
            elif isinstance(widget, QTimeEdit):
                config[key] = widget.time().toString("HH:mm:ss")
            elif isinstance(widget, QDateTimeEdit):
                config[key] = widget.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        return config


class CustomCompleter(QCompleter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterMode(Qt.MatchFlag.MatchContains)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

    def pathFromIndex(self, index):
        # 控制实际插入的内容 —— 只返回 symbol 部分
        text = self.model().data(index, Qt.ItemDataRole.DisplayRole)
        # 只返回 symbol

        return text.rsplit(" ", 1)[0].strip()


class SymbolCompleter:
    def __init__(self, line_edit: QLineEdit, get_all_contracts: Callable[[], list], on_symbol_selected: Callable[[ContractData], None] = None, vt_mode: bool = False, parent: QWidget = None):
        self.line_edit = line_edit
        self.get_all_contracts = get_all_contracts
        self.on_symbol_selected = on_symbol_selected
        self.vt_mode = vt_mode

        self.model = QStringListModel()
        self.completer = CustomCompleter(parent)
        self.completer.setModel(self.model)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self.line_edit.setCompleter(self.completer)
        self.line_edit.textEdited.connect(self.on_text_edited)
        self.completer.activated.connect(self.on_activated)

        self.filter_contracts: dict[str, ContractData] = {}

        # 绑定焦点事件
        self.install_focus_hooks()

    def install_focus_hooks(self):
        """给 QLineEdit 动态绑定焦点事件"""
        old_focus_in = self.line_edit.focusInEvent
        old_focus_out = self.line_edit.focusOutEvent

        def focus_in(event):
            if self.vt_mode:
                text = self.line_edit.text()
                if "." in text:
                    self.line_edit.setText(text.split(".")[0])  # 去掉 .exchange
                # 强制展开下拉提示
                self.on_text_edited(self.line_edit.text())
                self.completer.complete()
            old_focus_in(event)

        def focus_out(event):
            if self.vt_mode:
                text = self.line_edit.text()
                # 如果能匹配到合约，自动补全 .exchange
                for c in self.get_all_contracts():
                    if text.lower() == c.symbol.lower():
                        self.line_edit.setText(f"{c.symbol}.{c.exchange.value}")
                        break
            old_focus_out(event)

        self.line_edit.focusInEvent = focus_in
        self.line_edit.focusOutEvent = focus_out

    def on_text_edited(self, text: str):
        text = text.strip().lower()
        if not text:
            self.model.setStringList([])
            return

        all_contracts = self.get_all_contracts()
        matches = []
        self.filter_contracts.clear()

        for c in all_contracts:
            symbol_keywords = [c.symbol.lower(), f"{c.symbol.lower()}.{c.exchange.value.lower()}", c.name.lower()]
            if any(text in keyword for keyword in symbol_keywords):
                key = f"{c.symbol}.{c.exchange.value}" if self.vt_mode else c.symbol
                key = f"{key} {c.name}" if c.symbol != c.name else key
                matches.append(key)
                self.filter_contracts[key] = c
                self.filter_contracts[c.symbol] = c  # 允许用户只选 symbol

        self.model.setStringList(matches)

    def on_activated(self, selected: str):
        contract = self.filter_contracts.get(selected)
        if contract:
            QTimer.singleShot(0, lambda: self.line_edit.setText(contract.vt_symbol if self.vt_mode else contract.symbol))
            if self.on_symbol_selected:
                QTimer.singleShot(0, lambda: self.on_symbol_selected(contract))


class FormDialog(QtWidgets.QDialog):
    """
    Base class for all dialogs.
    """
    def __init__(self, title: str, ui_fields: dict, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.form_widget: FormWidget = FormWidget(title, ui_fields, self)
        self.get_config = self.form_widget.get_config
        self.refresh_config = self.form_widget.refresh_config

        # 按钮区域
        self.button_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.setMinimumWidth(120)
        self.save_btn.clicked.connect(self.accept)
        self.close_btn = QPushButton("关闭")
        self.close_btn.setMinimumWidth(120)
        self.close_btn.clicked.connect(self.reject)

        self.button_layout.addStretch()
        self.button_layout.addWidget(self.save_btn)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.close_btn)

        # 总布局
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.form_widget)
        main_layout.addLayout(self.button_layout)
        self.setLayout(main_layout)


class BaseCell(QtWidgets.QTableWidgetItem):
    """
    General cell used in tablewidgets.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__()

        self._text: str = ""
        self._data: Any = None

        self.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.set_content(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Set text content.
        """
        self._text = str(content)
        self._data = data

        self.setText(self._text)

    def get_data(self) -> Any:
        """
        Get data object.
        """
        return self._data

    def __lt__(self, other: "BaseCell") -> bool:        # type: ignore
        """
        Sort by text content.
        """
        result: bool = self._text < other._text
        return result


class EnumCell(BaseCell):
    """
    Cell used for showing enum data.
    """

    def __init__(self, content: Enum, data: Any) -> None:
        """"""
        super().__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Set text using enum.constant.value.
        """
        if content:
            super().set_content(content.value, data)


class DirectionCell(EnumCell):
    """
    Cell used for showing direction data.
    """

    def __init__(self, content: Enum, data: Any) -> None:
        """"""
        super().__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Cell color is set according to direction.
        """
        super().set_content(content, data)

        if content is Direction.SHORT:
            self.setForeground(COLOR_SHORT)
        else:
            self.setForeground(COLOR_LONG)


class BidCell(BaseCell):
    """
    Cell used for showing bid price and volume.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__(content, data)

        self.setForeground(COLOR_BID)


class AskCell(BaseCell):
    """
    Cell used for showing ask price and volume.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__(content, data)

        self.setForeground(COLOR_ASK)


class PnlCell(BaseCell):
    """
    Cell used for showing pnl data.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Cell color is set based on whether pnl is
        positive or negative.
        """
        super().set_content(content, data)

        if str(content).startswith("-"):
            self.setForeground(COLOR_SHORT)
        else:
            self.setForeground(COLOR_LONG)


class TimeCell(BaseCell):
    """
    Cell used for showing time string from datetime object.
    """

    local_tz = ZoneInfo(get_localzone_name())

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__(content, data)

    def set_content(self, content: datetime | None, data: Any) -> None:
        """"""
        if content is None:
            return

        content = content.astimezone(self.local_tz)
        timestamp: str = content.strftime("%H:%M:%S")

        millisecond: int = int(content.microsecond / 1000)
        if millisecond:
            timestamp = f"{timestamp}.{millisecond}"
        else:
            timestamp = f"{timestamp}.000"

        self.setText(timestamp)
        self._data = data


class DateCell(BaseCell):
    """
    Cell used for showing date string from datetime object.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super().__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """"""
        if content is None:
            return

        self.setText(content.strftime("%Y-%m-%d"))
        self._data = data


class MsgCell(BaseCell):
    """
    Cell used for showing msg data.
    """

    def __init__(self, content: str, data: Any) -> None:
        """"""
        super().__init__(content, data)
        self.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)


class BaseMonitor(QtWidgets.QTableWidget):
    """
    Monitor data update.
    """

    event_type: str = ""
    data_key: str = ""
    sorting: bool = False
    headers: dict = {}

    signal: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.cells: dict[str, dict] = {}

        self._context_menu_data = None
        self._context_menu_item = None

        self.init_ui()
        self.load_setting()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.init_table()
        self.init_menu()

    def init_table(self) -> None:
        """
        Initialize table.
        """
        self.setColumnCount(len(self.headers))

        labels: list = [d["display"] for d in self.headers.values()]
        self.setHorizontalHeaderLabels(labels)

        self.verticalHeader().setVisible(False)
        self.setEditTriggers(self.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(self.sorting)

    def init_menu(self) -> None:
        """
        Create right click menu.
        """
        self.menu: QtWidgets.QMenu = QtWidgets.QMenu(self)

        resize_action: QtGui.QAction = QtGui.QAction(_("调整列宽"), self)
        resize_action.triggered.connect(self.resize_columns)
        self.menu.addAction(resize_action)

        save_action: QtGui.QAction = QtGui.QAction(_("保存数据"), self)
        save_action.triggered.connect(self.save_csv)
        self.menu.addAction(save_action)

        if isinstance(self, TickMonitor):
            subscribe_action: QtGui.QAction = QtGui.QAction(_("取消订阅行情"), self)
            subscribe_action.triggered.connect(self.unsubscribe)
            self.menu.addAction(subscribe_action)
        elif isinstance(self, (TradeMonitor, OrderMonitor, PositionMonitor)):
            subscribe_action: QtGui.QAction = QtGui.QAction(_("订阅行情"), self)
            subscribe_action.triggered.connect(self.subscribe)
            self.menu.addAction(subscribe_action)


    def subscribe(self) -> None:
        if self._context_menu_data:
            req: SubscribeRequest = SubscribeRequest(
                symbol=self._context_menu_data.symbol, exchange=Exchange(self._context_menu_data.exchange)
            )
            self.main_engine.subscribe(req, self._context_menu_data.gateway_name)


    def unsubscribe(self) -> None:
        if self._context_menu_data:
            req: SubscribeRequest = SubscribeRequest(
                symbol=self._context_menu_data.symbol, exchange=Exchange(self._context_menu_data.exchange)
            )
            self.main_engine.unsubscribe(req, self._context_menu_data.gateway_name)

    def register_event(self) -> None:
        """
        Register event handler into event engine.
        """
        if self.event_type:
            self.signal.connect(self.process_event)
            self.event_engine.register(self.event_type, self.signal.emit)

    def process_event(self, event: Event) -> None:
        """
        Process new data from event and update into table.
        """
        # Disable sorting to prevent unwanted error.
        if self.sorting:
            self.setSortingEnabled(False)

        # Update data into table.
        data = event.data

        if not self.data_key:
            self.insert_new_row(data)
        else:
            key: str = data.__getattribute__(self.data_key)

            if key in self.cells:
                self.update_old_row(data)
            else:
                self.insert_new_row(data)

        # Enable sorting
        if self.sorting:
            self.setSortingEnabled(True)

    def insert_new_row(self, data: Any) -> None:
        """
        Insert a new row at the top of table.
        """
        self.insertRow(0)

        row_cells: dict = {}
        for column, header in enumerate(self.headers.keys()):
            setting: dict = self.headers[header]

            content = data.__getattribute__(header)
            cell: QtWidgets.QTableWidgetItem = setting["cell"](content, data)
            self.setItem(0, column, cell)

            if setting["update"]:
                row_cells[header] = cell

        if self.data_key:
            key: str = data.__getattribute__(self.data_key)
            self.cells[key] = row_cells

    def update_old_row(self, data: Any) -> None:
        """
        Update an old row in table.
        """
        key: str = data.__getattribute__(self.data_key)
        row_cells = self.cells[key]

        for header, cell in row_cells.items():
            content = data.__getattribute__(header)
            cell.set_content(content, data)

    def resize_columns(self) -> None:
        """
        Resize all columns according to contents.
        """
        self.horizontalHeader().resizeSections(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)

    def save_csv(self) -> None:
        """
        Save table data into a csv file
        """
        path, __ = QtWidgets.QFileDialog.getSaveFileName(
            self, _("保存数据"), "", "CSV(*.csv)")

        if not path:
            return

        with open(path, "w") as f:
            writer = csv.writer(f, lineterminator="\n")

            headers: list = [d["display"] for d in self.headers.values()]
            writer.writerow(headers)

            for row in range(self.rowCount()):
                if self.isRowHidden(row):
                    continue

                row_data: list = []
                for column in range(self.columnCount()):
                    item: QtWidgets.QTableWidgetItem | None = self.item(row, column)
                    if item:
                        row_data.append(str(item.text()))
                    else:
                        row_data.append("")
                writer.writerow(row_data)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """
        Show menu with right click.
        """
        item = self.itemAt(event.pos())
        self._context_menu_item = item
        if item and isinstance(item, BaseCell):
            self._context_menu_data = item.get_data()

        self.menu.popup(QtGui.QCursor.pos())

    def save_setting(self) -> None:
        """"""
        settings: QtCore.QSettings = QtCore.QSettings(self.__class__.__name__, "custom")
        settings.setValue("column_state", self.horizontalHeader().saveState())

    def load_setting(self) -> None:
        """"""
        settings: QtCore.QSettings = QtCore.QSettings(self.__class__.__name__, "custom")
        column_state = settings.value("column_state")

        if isinstance(column_state, QtCore.QByteArray):
            self.horizontalHeader().restoreState(column_state)
            self.horizontalHeader().setSortIndicator(-1, QtCore.Qt.SortOrder.AscendingOrder)


class TickMonitor(BaseMonitor):
    """
    Monitor for tick data.
    """

    event_type: str = EVENT_TICK
    data_key: str = "vt_symbol"
    sorting: bool = True

    headers: dict = {
        "symbol": {"display": _("代码"), "cell": BaseCell, "update": False},
        "exchange": {"display": _("交易所"), "cell": EnumCell, "update": False},
        "name": {"display": _("名称"), "cell": BaseCell, "update": True},
        "last_price": {"display": _("最新价"), "cell": BaseCell, "update": True},
        "volume": {"display": _("成交量"), "cell": BaseCell, "update": True},
        "open_price": {"display": _("开盘价"), "cell": BaseCell, "update": True},
        "high_price": {"display": _("最高价"), "cell": BaseCell, "update": True},
        "low_price": {"display": _("最低价"), "cell": BaseCell, "update": True},
        "bid_price_1": {"display": _("买1价"), "cell": BidCell, "update": True},
        "bid_volume_1": {"display": _("买1量"), "cell": BidCell, "update": True},
        "ask_price_1": {"display": _("卖1价"), "cell": AskCell, "update": True},
        "ask_volume_1": {"display": _("卖1量"), "cell": AskCell, "update": True},
        "datetime": {"display": _("时间"), "cell": TimeCell, "update": True},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }

    def unsubscribe(self) -> None:
        """
        Cancel subscribe on a specific instrument.
        """
        super().unsubscribe()
        if self._context_menu_item:
            key: str = self._context_menu_data.__getattribute__(self.data_key)
            if key in self.cells:
                self.cells.pop(key)
            row_index = self.row(self._context_menu_item)
            self.removeRow(row_index)


class LogMonitor(BaseMonitor):
    """
    Monitor for log data.
    """

    event_type: str = EVENT_LOG
    data_key: str = ""
    sorting: bool = False

    headers: dict = {
        "time": {"display": _("时间"), "cell": TimeCell, "update": False},
        "msg": {"display": _("信息"), "cell": MsgCell, "update": False},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }


class TradeMonitor(BaseMonitor):
    """
    Monitor for trade data.
    """

    event_type: str = EVENT_TRADE
    data_key: str = ""
    sorting: bool = True

    headers: dict = {
        "tradeid": {"display": _("成交号"), "cell": BaseCell, "update": False},
        "orderid": {"display": _("委托号"), "cell": BaseCell, "update": False},
        "symbol": {"display": _("代码"), "cell": BaseCell, "update": False},
        "exchange": {"display": _("交易所"), "cell": EnumCell, "update": False},
        "direction": {"display": _("方向"), "cell": DirectionCell, "update": False},
        "offset": {"display": _("开平"), "cell": EnumCell, "update": False},
        "price": {"display": _("价格"), "cell": BaseCell, "update": False},
        "volume": {"display": _("数量"), "cell": BaseCell, "update": False},
        "datetime": {"display": _("时间"), "cell": TimeCell, "update": False},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }


class OrderMonitor(BaseMonitor):
    """
    Monitor for order data.
    """

    event_type: str = EVENT_ORDER
    data_key: str = "vt_orderid"
    sorting: bool = True

    headers: dict = {
        "orderid": {"display": _("委托号"), "cell": BaseCell, "update": False},
        "reference": {"display": _("来源"), "cell": BaseCell, "update": False},
        "symbol": {"display": _("代码"), "cell": BaseCell, "update": False},
        "exchange": {"display": _("交易所"), "cell": EnumCell, "update": False},
        "type": {"display": _("类型"), "cell": EnumCell, "update": False},
        "direction": {"display": _("方向"), "cell": DirectionCell, "update": False},
        "offset": {"display": _("开平"), "cell": EnumCell, "update": False},
        "price": {"display": _("价格"), "cell": BaseCell, "update": False},
        "volume": {"display": _("总数量"), "cell": BaseCell, "update": True},
        "traded": {"display": _("已成交"), "cell": BaseCell, "update": True},
        "status": {"display": _("状态"), "cell": EnumCell, "update": True},
        "datetime": {"display": _("时间"), "cell": TimeCell, "update": True},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }

    def init_ui(self) -> None:
        """
        Connect signal.
        """
        super().init_ui()

        self.setToolTip(_("双击单元格撤单"))
        self.itemDoubleClicked.connect(self.cancel_order)

    def cancel_order(self, cell: BaseCell) -> None:
        """
        Cancel order if cell double clicked.
        """
        order: OrderData = cell.get_data()
        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)


class PositionMonitor(BaseMonitor):
    """
    Monitor for position data.
    """

    event_type: str = EVENT_POSITION
    data_key: str = "vt_positionid"
    sorting: bool = True

    headers: dict = {
        "symbol": {"display": _("代码"), "cell": BaseCell, "update": False},
        "exchange": {"display": _("交易所"), "cell": EnumCell, "update": False},
        "direction": {"display": _("方向"), "cell": DirectionCell, "update": False},
        "volume": {"display": _("数量"), "cell": BaseCell, "update": True},
        "yd_volume": {"display": _("昨仓"), "cell": BaseCell, "update": True},
        "frozen": {"display": _("冻结"), "cell": BaseCell, "update": True},
        "price": {"display": _("均价"), "cell": BaseCell, "update": True},
        "pnl": {"display": _("盈亏"), "cell": PnlCell, "update": True},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }


class AccountMonitor(BaseMonitor):
    """
    Monitor for account data.
    """

    event_type: str = EVENT_ACCOUNT
    data_key: str = "vt_accountid"
    sorting: bool = True

    headers: dict = {
        "accountid": {"display": _("账号"), "cell": BaseCell, "update": False},
        "balance": {"display": _("余额"), "cell": BaseCell, "update": True},
        "frozen": {"display": _("冻结"), "cell": BaseCell, "update": True},
        "available": {"display": _("可用"), "cell": BaseCell, "update": True},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }


class QuoteMonitor(BaseMonitor):
    """
    Monitor for quote data.
    """

    event_type: str = EVENT_QUOTE
    data_key: str = "vt_quoteid"
    sorting: bool = True

    headers: dict = {
        "quoteid": {"display": _("报价号"), "cell": BaseCell, "update": False},
        "reference": {"display": _("来源"), "cell": BaseCell, "update": False},
        "symbol": {"display": _("代码"), "cell": BaseCell, "update": False},
        "exchange": {"display": _("交易所"), "cell": EnumCell, "update": False},
        "bid_offset": {"display": _("买开平"), "cell": EnumCell, "update": False},
        "bid_volume": {"display": _("买量"), "cell": BidCell, "update": False},
        "bid_price": {"display": _("买价"), "cell": BidCell, "update": False},
        "ask_price": {"display": _("卖价"), "cell": AskCell, "update": False},
        "ask_volume": {"display": _("卖量"), "cell": AskCell, "update": False},
        "ask_offset": {"display": _("卖开平"), "cell": EnumCell, "update": False},
        "status": {"display": _("状态"), "cell": EnumCell, "update": True},
        "datetime": {"display": _("时间"), "cell": TimeCell, "update": True},
        "gateway_name": {"display": _("接口"), "cell": BaseCell, "update": False},
    }

    def init_ui(self) -> None:
        """
        Connect signal.
        """
        super().init_ui()

        self.setToolTip(_("双击单元格撤销报价"))
        self.itemDoubleClicked.connect(self.cancel_quote)

    def cancel_quote(self, cell: BaseCell) -> None:
        """
        Cancel quote if cell double clicked.
        """
        quote: QuoteData = cell.get_data()
        req: CancelRequest = quote.create_cancel_request()
        self.main_engine.cancel_quote(req, quote.gateway_name)


class ConnectDialog(QtWidgets.QDialog):
    """
    Start connection of a certain gateway.
    """

    def __init__(self, main_engine: MainEngine, gateway_name: str) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.gateway_name: str = gateway_name
        self.filename: str = f"connect_{gateway_name.lower()}.json"

        self.widgets: dict[str, tuple[QtWidgets.QWidget, type]] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(_("连接{}").format(self.gateway_name))

        # Default setting provides field name, field data type and field default value.
        default_setting: dict | None = self.main_engine.get_default_setting(self.gateway_name)

        # Saved setting provides field data used last time.
        loaded_setting: dict = load_json(self.filename)

        # Initialize line edits and form layout based on setting.
        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        if default_setting:
            for field_name, field_value in default_setting.items():
                field_type: type = type(field_value)

                if field_type is list:
                    combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
                    combo.addItems(field_value)

                    if field_name in loaded_setting:
                        saved_value = loaded_setting[field_name]
                        ix: int = combo.findText(saved_value)
                        combo.setCurrentIndex(ix)

                    form.addRow(f"{field_name} <{field_type.__name__}>", combo)
                    self.widgets[field_name] = (combo, field_type)
                else:
                    line: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(field_value))

                    if field_name in loaded_setting:
                        saved_value = loaded_setting[field_name]
                        line.setText(str(saved_value))

                    if _("密码") in field_name:
                        line.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

                    if field_type is int:
                        validator: QtGui.QIntValidator = QtGui.QIntValidator()
                        line.setValidator(validator)

                    form.addRow(f"{field_name} <{field_type.__name__}>", line)
                    self.widgets[field_name] = (line, field_type)

        button: QtWidgets.QPushButton = QtWidgets.QPushButton(_("连接"))
        button.clicked.connect(self.connect_gateway)
        form.addRow(button)

        self.setLayout(form)
        self.setMinimumSize(400, 300)
        self.adjustSize()

    def connect_gateway(self) -> None:
        """
        Get setting value from line edits and connect the gateway.
        """
        setting: dict = {}

        for field_name, tp in self.widgets.items():
            widget, field_type = tp
            if field_type is list:
                combo: QtWidgets.QComboBox = cast(QtWidgets.QComboBox, widget)
                field_value = str(combo.currentText())
            else:
                line: QtWidgets.QLineEdit = cast(QtWidgets.QLineEdit, widget)
                try:
                    field_value = field_type(line.text())
                except ValueError:
                    field_value = field_type()
            setting[field_name] = field_value

        save_json(self.filename, setting)

        self.main_engine.connect(setting, self.gateway_name)
        self.accept()


class TradingWidget(QtWidgets.QWidget):
    """
    General manual trading widget.
    """

    signal_tick: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.vt_symbol: str = ""
        self.price_digits: int = 0

        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.setFixedWidth(300)

        # Trading function area
        exchanges: list[Exchange] = self.main_engine.get_all_exchanges()
        self.exchange_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.exchange_combo.addItems([exchange.value for exchange in exchanges])

        self.symbol_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.symbol_line.returnPressed.connect(self.set_vt_symbol)
        self.symbol_line._completer = SymbolCompleter(line_edit=self.symbol_line,
                                                      get_all_contracts=self.main_engine.get_all_contracts,
                                                      on_symbol_selected=self.on_symbol_selected,
                                                      parent=self)

        self.name_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.name_line.setReadOnly(True)

        self.direction_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.direction_combo.addItems(
            [Direction.LONG.value, Direction.SHORT.value])

        self.offset_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.offset_combo.addItems([offset.value for offset in Offset])

        self.order_type_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.order_type_combo.addItems(
            [order_type.value for order_type in OrderType])

        double_validator: QtGui.QDoubleValidator = QtGui.QDoubleValidator()
        double_validator.setBottom(0)

        self.price_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.price_line.setValidator(double_validator)

        self.volume_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.volume_line.setValidator(double_validator)

        self.gateway_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.gateway_combo.addItems(self.main_engine.get_all_gateway_names())

        self.price_check: QtWidgets.QCheckBox = QtWidgets.QCheckBox()
        self.price_check.setToolTip(_("设置价格随行情更新"))

        send_button: QtWidgets.QPushButton = QtWidgets.QPushButton(_("委托"))
        send_button.clicked.connect(self.send_order)

        cancel_button: QtWidgets.QPushButton = QtWidgets.QPushButton(_("全撤"))
        cancel_button.clicked.connect(self.cancel_all)

        grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel(_("交易所")), 0, 0)
        grid.addWidget(QtWidgets.QLabel(_("代码")), 1, 0)
        grid.addWidget(QtWidgets.QLabel(_("名称")), 2, 0)
        grid.addWidget(QtWidgets.QLabel(_("方向")), 3, 0)
        grid.addWidget(QtWidgets.QLabel(_("开平")), 4, 0)
        grid.addWidget(QtWidgets.QLabel(_("类型")), 5, 0)
        grid.addWidget(QtWidgets.QLabel(_("价格")), 6, 0)
        grid.addWidget(QtWidgets.QLabel(_("数量")), 7, 0)
        grid.addWidget(QtWidgets.QLabel(_("接口")), 8, 0)
        grid.addWidget(self.exchange_combo, 0, 1, 1, 2)
        grid.addWidget(self.symbol_line, 1, 1, 1, 2)
        grid.addWidget(self.name_line, 2, 1, 1, 2)
        grid.addWidget(self.direction_combo, 3, 1, 1, 2)
        grid.addWidget(self.offset_combo, 4, 1, 1, 2)
        grid.addWidget(self.order_type_combo, 5, 1, 1, 2)
        grid.addWidget(self.price_line, 6, 1, 1, 1)
        grid.addWidget(self.price_check, 6, 2, 1, 1)
        grid.addWidget(self.volume_line, 7, 1, 1, 2)
        grid.addWidget(self.gateway_combo, 8, 1, 1, 2)
        grid.addWidget(send_button, 9, 0, 1, 3)
        grid.addWidget(cancel_button, 10, 0, 1, 3)

        # Market depth display area
        bid_color: str = "rgb(255,174,201)"
        ask_color: str = "rgb(160,255,160)"

        self.bp1_label: QtWidgets.QLabel = self.create_label(bid_color)
        self.bp2_label: QtWidgets.QLabel = self.create_label(bid_color)
        self.bp3_label: QtWidgets.QLabel = self.create_label(bid_color)
        self.bp4_label: QtWidgets.QLabel = self.create_label(bid_color)
        self.bp5_label: QtWidgets.QLabel = self.create_label(bid_color)

        self.bv1_label: QtWidgets.QLabel = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.bv2_label: QtWidgets.QLabel = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.bv3_label: QtWidgets.QLabel = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.bv4_label: QtWidgets.QLabel = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.bv5_label: QtWidgets.QLabel = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        self.ap1_label: QtWidgets.QLabel = self.create_label(ask_color)
        self.ap2_label: QtWidgets.QLabel = self.create_label(ask_color)
        self.ap3_label: QtWidgets.QLabel = self.create_label(ask_color)
        self.ap4_label: QtWidgets.QLabel = self.create_label(ask_color)
        self.ap5_label: QtWidgets.QLabel = self.create_label(ask_color)

        self.av1_label: QtWidgets.QLabel = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.av2_label: QtWidgets.QLabel = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.av3_label: QtWidgets.QLabel = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.av4_label: QtWidgets.QLabel = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        self.av5_label: QtWidgets.QLabel = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        self.lp_label: QtWidgets.QLabel = self.create_label()
        self.return_label: QtWidgets.QLabel = self.create_label(alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()
        form.addRow(self.ap5_label, self.av5_label)
        form.addRow(self.ap4_label, self.av4_label)
        form.addRow(self.ap3_label, self.av3_label)
        form.addRow(self.ap2_label, self.av2_label)
        form.addRow(self.ap1_label, self.av1_label)
        form.addRow(self.lp_label, self.return_label)
        form.addRow(self.bp1_label, self.bv1_label)
        form.addRow(self.bp2_label, self.bv2_label)
        form.addRow(self.bp3_label, self.bv3_label)
        form.addRow(self.bp4_label, self.bv4_label)
        form.addRow(self.bp5_label, self.bv5_label)

        # Overall layout
        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addLayout(form)
        self.setLayout(vbox)

    def on_symbol_selected(self, contract: ContractData):
        if contract:
            QTimer.singleShot(0, lambda: self.name_line.setText(contract.name))
            QTimer.singleShot(0, lambda: self.exchange_combo.setCurrentText(contract.exchange.value))
            QTimer.singleShot(10, lambda: self.set_vt_symbol())

    def create_label(
        self,
        color: str = "",
        alignment: int = QtCore.Qt.AlignmentFlag.AlignLeft
    ) -> QtWidgets.QLabel:
        """
        Create label with certain font color.
        """
        label: QtWidgets.QLabel = QtWidgets.QLabel()
        if color:
            label.setStyleSheet(f"color:{color}")
        label.setAlignment(Qt.AlignmentFlag(alignment))
        return label

    def register_event(self) -> None:
        """"""
        self.signal_tick.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal_tick.emit)
        self.event_engine.register(EVENT_TICK_UNSUB, self.signal_tick.emit)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        if tick.vt_symbol != self.vt_symbol:
            return

        if event.type == EVENT_TICK_UNSUB:
            self.clear_label_text()
            return

        price_digits: int = self.price_digits

        self.lp_label.setText(f"{tick.last_price:.{price_digits}f}")
        self.bp1_label.setText(f"{tick.bid_price_1:.{price_digits}f}")
        self.bv1_label.setText(str(tick.bid_volume_1))
        self.ap1_label.setText(f"{tick.ask_price_1:.{price_digits}f}")
        self.av1_label.setText(str(tick.ask_volume_1))

        if tick.pre_close:
            r: float = (tick.last_price / tick.pre_close - 1) * 100
            self.return_label.setText(f"{r:.2f}%")

        if tick.bid_price_2:
            self.bp2_label.setText(f"{tick.bid_price_2:.{price_digits}f}")
            self.bv2_label.setText(str(tick.bid_volume_2))
            self.ap2_label.setText(f"{tick.ask_price_2:.{price_digits}f}")
            self.av2_label.setText(str(tick.ask_volume_2))

            self.bp3_label.setText(f"{tick.bid_price_3:.{price_digits}f}")
            self.bv3_label.setText(str(tick.bid_volume_3))
            self.ap3_label.setText(f"{tick.ask_price_3:.{price_digits}f}")
            self.av3_label.setText(str(tick.ask_volume_3))

            self.bp4_label.setText(f"{tick.bid_price_4:.{price_digits}f}")
            self.bv4_label.setText(str(tick.bid_volume_4))
            self.ap4_label.setText(f"{tick.ask_price_4:.{price_digits}f}")
            self.av4_label.setText(str(tick.ask_volume_4))

            self.bp5_label.setText(f"{tick.bid_price_5:.{price_digits}f}")
            self.bv5_label.setText(str(tick.bid_volume_5))
            self.ap5_label.setText(f"{tick.ask_price_5:.{price_digits}f}")
            self.av5_label.setText(str(tick.ask_volume_5))

        if self.price_check.isChecked():
            self.price_line.setText(f"{tick.last_price:.{price_digits}f}")

    def set_vt_symbol(self) -> None:
        """
        Set the tick depth data to monitor by vt_symbol.
        """
        symbol: str = str(self.symbol_line.text())
        if not symbol:
            return

        # Generate vt_symbol from symbol and exchange
        exchange_value: str = str(self.exchange_combo.currentText())
        vt_symbol: str = f"{symbol}.{exchange_value}"

        if vt_symbol == self.vt_symbol:
            return
        self.vt_symbol = vt_symbol

        # Update name line widget and clear all labels
        contract: ContractData | None = self.main_engine.get_contract(vt_symbol)
        if not contract:
            self.name_line.setText("")
            gateway_name: str = self.gateway_combo.currentText()
        else:
            self.name_line.setText(contract.name)
            gateway_name = contract.gateway_name

            # Update gateway combo box.
            ix: int = self.gateway_combo.findText(gateway_name)
            self.gateway_combo.setCurrentIndex(ix)

            # Update price digits
            self.price_digits = get_digits(contract.pricetick)

        self.clear_label_text()
        self.volume_line.setText("")
        self.price_line.setText("")

        # Subscribe tick data
        req: SubscribeRequest = SubscribeRequest(
            symbol=symbol, exchange=Exchange(exchange_value)
        )

        self.main_engine.subscribe(req, gateway_name)

    def clear_label_text(self) -> None:
        """
        Clear text on all labels.
        """
        self.lp_label.setText("")
        self.return_label.setText("")

        self.bv1_label.setText("")
        self.bv2_label.setText("")
        self.bv3_label.setText("")
        self.bv4_label.setText("")
        self.bv5_label.setText("")

        self.av1_label.setText("")
        self.av2_label.setText("")
        self.av3_label.setText("")
        self.av4_label.setText("")
        self.av5_label.setText("")

        self.bp1_label.setText("")
        self.bp2_label.setText("")
        self.bp3_label.setText("")
        self.bp4_label.setText("")
        self.bp5_label.setText("")

        self.ap1_label.setText("")
        self.ap2_label.setText("")
        self.ap3_label.setText("")
        self.ap4_label.setText("")
        self.ap5_label.setText("")

    def send_order(self) -> None:
        """
        Send new order manually.
        """
        symbol: str = str(self.symbol_line.text())
        if not symbol:
            QtWidgets.QMessageBox.critical(self, _("委托失败"), _("请输入合约代码"))
            return

        volume_text: str = str(self.volume_line.text())
        if not volume_text:
            QtWidgets.QMessageBox.critical(self, _("委托失败"), _("请输入委托数量"))
            return
        volume: float = float(volume_text)

        price_text: str = str(self.price_line.text())
        if not price_text:
            price: float = 0
        else:
            price = float(price_text)

        req: OrderRequest = OrderRequest(
            symbol=symbol,
            exchange=Exchange(str(self.exchange_combo.currentText())),
            direction=Direction(str(self.direction_combo.currentText())),
            type=OrderType(str(self.order_type_combo.currentText())),
            volume=volume,
            price=price,
            offset=Offset(str(self.offset_combo.currentText())),
            reference="ManualTrading"
        )

        gateway_name: str = str(self.gateway_combo.currentText())

        self.main_engine.send_order(req, gateway_name)

    def cancel_all(self) -> None:
        """
        Cancel all active orders.
        """
        order_list: list[OrderData] = self.main_engine.get_all_active_orders()
        for order in order_list:
            req: CancelRequest = order.create_cancel_request()
            self.main_engine.cancel_order(req, order.gateway_name)

    def update_with_cell(self, cell: BaseCell) -> None:
        """"""
        data = cell.get_data()

        self.symbol_line.setText(data.symbol)
        self.exchange_combo.setCurrentIndex(
            self.exchange_combo.findText(data.exchange.value)
        )

        self.set_vt_symbol()

        if isinstance(data, PositionData):
            if data.direction == Direction.SHORT:
                direction: Direction = Direction.LONG
            elif data.direction == Direction.LONG:
                direction = Direction.SHORT
            else:       # Net position mode
                if data.volume > 0:
                    direction = Direction.SHORT
                else:
                    direction = Direction.LONG

            self.direction_combo.setCurrentIndex(
                self.direction_combo.findText(direction.value)
            )
            self.offset_combo.setCurrentIndex(
                self.offset_combo.findText(Offset.CLOSE.value)
            )
            self.volume_line.setText(str(abs(data.volume)))


class ActiveOrderMonitor(OrderMonitor):
    """
    Monitor which shows active order only.
    """

    def process_event(self, event: Event) -> None:
        """
        Hides the row if order is not active.
        """
        super().process_event(event)

        order: OrderData = event.data
        row_cells: dict = self.cells[order.vt_orderid]
        row: int = self.row(row_cells["volume"])

        if order.is_active():
            self.showRow(row)
        else:
            self.hideRow(row)


class ContractManager(QtWidgets.QWidget):
    """
    Query contract data available to trade in system.
    """

    headers: dict[str, str] = {
        "vt_symbol": _("本地代码"),
        "symbol": _("代码"),
        "exchange": _("交易所"),
        "name": _("名称"),
        "product": _("合约分类"),
        "size": _("合约乘数"),
        "pricetick": _("价格跳动"),
        "min_volume": _("最小委托量"),
        "option_portfolio": _("期权产品"),
        "option_expiry": _("期权到期日"),
        "option_strike": _("期权行权价"),
        "option_type": _("期权类型"),
        "gateway_name": _("交易接口"),
    }

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(_("合约查询"))
        self.resize(1000, 650)

        self.filter_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.filter_line.setPlaceholderText(_("输入合约代码或者交易所，留空则查询所有合约"))

        self.button_show: QtWidgets.QPushButton = QtWidgets.QPushButton(_("查询"))
        self.button_show.clicked.connect(self.show_contracts)

        labels: list = []
        for name, display in self.headers.items():
            label: str = f"{display}\n{name}"
            labels.append(label)

        self.contract_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.contract_table.setColumnCount(len(self.headers))
        self.contract_table.setHorizontalHeaderLabels(labels)
        self.contract_table.verticalHeader().setVisible(False)
        self.contract_table.setEditTriggers(self.contract_table.EditTrigger.NoEditTriggers)
        self.contract_table.setAlternatingRowColors(True)

        hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.filter_line)
        hbox.addWidget(self.button_show)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.contract_table)

        self.setLayout(vbox)

        self.setToolTip(_("双击订阅合约"))
        self.contract_table.itemDoubleClicked.connect(self.subscribe)

    def subscribe(self, cell: BaseCell) -> None:
        """
        Cancel order if cell double clicked.
        """
        contract: ContractData = cell.get_data()
        req: SubscribeRequest = SubscribeRequest(
            symbol=contract.symbol, exchange=Exchange(contract.exchange)
        )
        self.main_engine.subscribe(req, contract.gateway_name)

    def show_contracts(self) -> None:
        """
        Show contracts by symbol
        """
        flt: str = str(self.filter_line.text())

        all_contracts: list[ContractData] = self.main_engine.get_all_contracts()
        if flt:
            contracts: list[ContractData] = [
                contract for contract in all_contracts if flt in contract.vt_symbol
            ]
        else:
            contracts = all_contracts

        self.contract_table.clearContents()
        self.contract_table.setRowCount(len(contracts))

        for row, contract in enumerate(contracts):
            for column, name in enumerate(self.headers.keys()):
                value: Any = getattr(contract, name)

                if value in {None, 0}:
                    value = ""

                cell: BaseCell
                if isinstance(value, Enum):
                    cell = EnumCell(value, contract)
                elif isinstance(value, datetime):
                    cell = DateCell(value, contract)
                else:
                    cell = BaseCell(value, contract)
                self.contract_table.setItem(row, column, cell)

        self.contract_table.resizeColumnsToContents()


class AboutDialog(QtWidgets.QDialog):
    """
    Information about the trading platform.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(_("关于VeighNa Trader"))

        from ... import __version__ as vnpy_version

        text: str = f"""
            By Traders, For Traders.

            Created by VeighNa Technology


            License：MIT
            Website：www.vnpy.com
            Github：www.github.com/vnpy/vnpy


            VeighNa - {vnpy_version}
            Python - {platform.python_version()}
            PySide6 - {metadata.version("pyside6")}
            NumPy - {metadata.version("numpy")}
            pandas - {metadata.version("pandas")}
            """

        label: QtWidgets.QLabel = QtWidgets.QLabel()
        label.setText(text)
        label.setMinimumWidth(500)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(label)
        self.setLayout(vbox)


class GlobalDialog(QtWidgets.QDialog):
    """
    Start connection of a certain gateway.
    """

    def __init__(self) -> None:
        """"""
        super().__init__()

        self.widgets: dict[str, tuple[QtWidgets.QLineEdit, type]] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(_("全局配置"))
        self.setMinimumWidth(800)

        settings: dict = copy(SETTINGS)
        settings.update(load_json(SETTING_FILENAME))

        # Initialize line edits and form layout based on setting.
        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        for field_name, field_value in settings.items():
            field_type: type = type(field_value)
            widget: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(field_value))

            form.addRow(f"{field_name} <{field_type.__name__}>", widget)
            self.widgets[field_name] = (widget, field_type)

        button: QtWidgets.QPushButton = QtWidgets.QPushButton(_("确定"))
        button.clicked.connect(self.update_setting)
        form.addRow(button)

        scroll_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        scroll_widget.setLayout(form)

        scroll_area: QtWidgets.QScrollArea = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(scroll_area)
        self.setLayout(vbox)

    def update_setting(self) -> None:
        """
        Get setting value from line edits and update global setting file.
        """
        settings: dict = {}
        for field_name, tp in self.widgets.items():
            widget, field_type = tp
            value_text: str = widget.text()

            if field_type is bool:
                if value_text == "True":
                    field_value: bool = True
                else:
                    field_value = False
            else:
                field_value = field_type(value_text)

            settings[field_name] = field_value

        QtWidgets.QMessageBox.information(
            self,
            _("注意"),
            _("全局配置的修改需要重启后才会生效！"),
            QtWidgets.QMessageBox.StandardButton.Ok
        )

        save_json(SETTING_FILENAME, settings)
        self.accept()
