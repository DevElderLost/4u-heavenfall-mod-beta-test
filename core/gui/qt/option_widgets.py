"""Option widgets built from the toolkit-independent model in `gui/options.py`.

`SettingsForm(sections, defaults=..., master=...)` renders a tuple of `Section`s (tabs when there are several; each tab
is built the first time it is shown) with one widget per `Option`:

* bool: a toggle switch; enum: segmented buttons (a drop-down when `compact`); int: a spin box (two for `range_to`);
* `requires` / `also_with` / the form's master option enable or disable rows, refreshing only the rows that depend on
  the field that changed; `emulator_only` rows (and what requires them) are hidden on the 3DS platform;
* `values()` returns every field (enums as members) plus the `links` copies; `set_values()` loads fields without
  emitting `changed`; legacy choices exist only while the value is one.

A `requires` that points outside the form counts as on.
"""

from __future__ import annotations

import html
from enum import Enum
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from core.gui.i18n import EMPTY, T
from core.gui.qt import theme
from core.gui.qt.translate import translator

if TYPE_CHECKING:  # the model is only used through its attributes, so importing this module stays light
    from core.gui.options import Group, Hint, Option, Section


def tip_html(text: str) -> str:
    """A tooltip that wraps (Qt only wraps rich text)."""
    return f'<table width="380"><tr><td>{html.escape(text)}</td></tr></table>' if text else ""


class ToggleSwitch(QAbstractButton):
    """A drawn on/off switch with a short knob animation and a focus outline."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(110)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._slide)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(44, 24)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._animation.stop()
        self._offset = 1.0 if checked else 0.0
        self.update()

    def _slide(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        off, on = QColor(theme.BORDER), QColor(theme.GOLD if enabled else theme.DISABLED)
        track = QColor(
            round(off.red() + (on.red() - off.red()) * self._offset),
            round(off.green() + (on.green() - off.green()) * self._offset),
            round(off.blue() + (on.blue() - off.blue()) * self._offset))
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        d = rect.height() - 6
        x = rect.left() + 3 + (rect.width() - d - 6) * self._offset
        painter.setBrush(QColor(theme.TEXT if enabled else theme.MUTED))
        painter.drawEllipse(QRectF(x, rect.top() + 3, d, d))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme.VIOLET), 2))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 11, 11)


class _ClickLabel(QLabel):
    """A label that toggles its switch when clicked."""

    def __init__(self, target: QAbstractButton):
        super().__init__()
        self._target = target
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setWordWrap(True)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._target.isEnabled():
            self._target.toggle()
        super().mousePressEvent(event)


def _label(text: T, role: str | None = None) -> QLabel:
    label = QLabel()
    label.setWordWrap(True)
    if role:
        label.setProperty("role", role)
    translator.bind(label, label.setText, text)
    return label


def _tooltip(widget: QWidget, text: T) -> None:
    if text is not EMPTY and text.es:
        translator.bind(widget, lambda s: widget.setToolTip(tip_html(s)), text)


class _EnumControl(QWidget):
    """Segmented buttons or a drop-down over an option's choices; legacy choices exist only while selected."""

    picked = Signal(object)

    def __init__(self, option: Option):
        super().__init__()
        self.choices = list(option.choices)
        self._value: Enum = self.choices[0].value
        self._lock = False
        self._combo = option.compact
        self._long = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if self._combo:
            self.combo = QComboBox()
            self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.combo.activated.connect(lambda i: self._pick(self.combo.itemData(i)))
            layout.addWidget(self.combo)
            layout.addStretch(1)
            translator.bind(self.combo, lambda _: self._retext(), lambda _lang: "")
            self._rebuild_items()
        else:
            self._long = sum(max(len(c.label.es), len(c.label.en)) for c in self.choices) > 46
            self.group = QButtonGroup(self)
            self.buttons: list[QPushButton] = []
            if self._long:
                layout.setDirection(QHBoxLayout.Direction.TopToBottom)
                layout.setSpacing(4)
            for choice in self.choices:
                button = QPushButton()
                button.setCheckable(True)
                button.setProperty("role", "segment")
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                translator.bind(button, button.setText, choice.label)
                _tooltip(button, choice.tooltip)
                button.clicked.connect(lambda _=False, c=choice: self._pick(c.value))
                self.group.addButton(button)
                self.buttons.append(button)
                layout.addWidget(button)
            layout.addStretch(1)
            self.sync()

    def value(self) -> Enum:
        return self._value

    def set_value(self, value: Enum) -> None:
        self._value = value
        self.sync()

    def _pick(self, value: Enum) -> None:
        if self._lock or value is None:
            return
        self._value = value
        self.sync()
        self.picked.emit(value)

    def sync(self) -> None:
        self._lock = True
        try:
            if self._combo:
                self._rebuild_items()
            else:
                for button, choice in zip(self.buttons, self.choices):
                    button.setVisible(not choice.legacy or choice.value is self._value)
                    button.setChecked(choice.value is self._value)
                self._restyle()
        finally:
            self._lock = False

    def _rebuild_items(self) -> None:
        self.combo.clear()
        for choice in self.choices:
            if not choice.legacy or choice.value is self._value:
                self.combo.addItem(translator.text(choice.label), choice.value)
        self.combo.setCurrentIndex(max(0, self.combo.findData(self._value)))

    def _retext(self) -> None:
        by_value = {c.value: c for c in self.choices}
        for i in range(self.combo.count()):
            self.combo.setItemText(i, translator.text(by_value[self.combo.itemData(i)].label))

    def _restyle(self) -> None:
        shown = [b for b, c in zip(self.buttons, self.choices) if not c.legacy or c.value is self._value]
        for i, button in enumerate(shown):
            if self._long or len(shown) == 1:
                pos = "only"
            else:
                pos = "first" if i == 0 else "last" if i == len(shown) - 1 else "mid"
            if button.property("pos") != pos:
                button.setProperty("pos", pos)
                button.style().unpolish(button)
                button.style().polish(button)

    def labels(self) -> list[str]:
        if self._combo:
            return [self.combo.itemText(i) for i in range(self.combo.count())]
        return [b.text() for b, c in zip(self.buttons, self.choices) if not c.legacy or c.value is self._value]


class _Row:
    """One option: its container (shown / enabled as a unit), its input widget and, for pairs, the second spin box."""

    def __init__(self, option: Option, container: QWidget, widget: QWidget, set_value, high: QSpinBox | None = None):
        self.option = option
        self.container = container
        self.widget = widget
        self.set_value = set_value   # value -> None, without emitting
        self.high = high


class SettingsForm(QWidget):
    changed = Signal(str)

    def __init__(self, sections: tuple[Section, ...], defaults: dict | None = None, master: Option | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.sections = sections
        self.master = master
        self.console = False
        self.refresh_log: list[str] = []   # fields whose enabled state was re-evaluated (a test hook)
        self.rows: dict[str, _Row] = {}
        defaults = defaults or {}
        self._options: dict[str, Option] = {}
        self._section_of: dict[str, int] = {}
        self._pairs: dict[str, Option] = {}   # range_to field -> its option
        for i, section in enumerate(sections):
            for group in section.groups:
                for option in group.options:
                    self._options[option.field] = option
                    self._section_of[option.field] = i
                    if option.range_to:
                        self._pairs[option.range_to] = option
                        self._section_of[option.range_to] = i
        if master:
            self._options[master.field] = master
        self.store: dict[str, object] = {}
        for field, option in self._options.items():
            self.store[field] = self._start_value(option, defaults.get(field, self._default(option)))
        for field, option in self._pairs.items():
            self.store[field] = int(defaults.get(field, option.maximum))
        self._console_hidden = self._compute_console_hidden()
        self._dependents: dict[str, set[str]] = {}
        self._hints: dict[str, list] = {}
        for field, option in self._options.items():
            for trigger in self._triggers(option):
                self._dependents.setdefault(trigger, set()).add(field)
        self._groups: list[tuple[QWidget, list[Option]]] = []
        self._pages: list[QWidget | None] = [None] * len(sections)
        self._build_shell()
        self._ensure_built(0)

    # -- model helpers
    @staticmethod
    def _default(option: Option):
        if option.choices:
            return option.choices[0].value
        if option.range_to or option.maximum > option.minimum:
            return option.minimum
        return False

    def _start_value(self, option: Option, value):
        """`value` as the store holds it: an enum choice (the drop-down finds it by identity; a saved "common" would
        never match), an int or a bool. An unknown choice falls back to the option's default."""
        if option.choices:
            coerced = self._coerce(option, value)
            return self._default(option) if coerced is None else coerced
        if option.range_to or option.maximum > option.minimum:
            return int(value)
        return bool(value)

    def _triggers(self, option: Option) -> list[str]:
        out = []
        if self.master and option.field != self.master.field:
            out.append(self.master.field)
        out += [f for f in (option.requires, option.also_with) if f]
        return out

    def _compute_console_hidden(self) -> set[str]:
        hidden = {f for f, o in self._options.items() if o.emulator_only}
        grown = True
        while grown:
            more = {f for f, o in self._options.items() if o.requires in hidden}
            grown = not more <= hidden
            hidden |= more
        return hidden

    def is_on(self, field: str) -> bool:
        option = self._options.get(field)
        if option is None:
            return True
        value = self.store[field]
        if option.choices:
            return value is not option.choices[0].value
        return bool(value)

    def _enabled(self, option: Option) -> bool:
        must = [option.requires] if option.requires else []
        if self.master and option is not self.master:
            must.append(self.master.field)
        return all(self.is_on(f) for f in must) or bool(option.also_with and self.is_on(option.also_with))

    # -- shell and lazy sections
    def _build_shell(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        if self.master:
            holder = QFrame()
            holder.setObjectName("card")
            QVBoxLayout(holder).addWidget(self._make_row(self.master).container)
            outer.addWidget(holder)
        self.tabs: QTabWidget | None = None
        if len(self.sections) > 1:
            self.tabs = QTabWidget()
            self.tabs.setDocumentMode(True)
            for i, section in enumerate(self.sections):
                self.tabs.addTab(self._new_scroll(), "")
                translator.bind(self.tabs, lambda s, i=i: self.tabs.setTabText(i, s), section.title)
            self.tabs.currentChanged.connect(self._ensure_built)
            outer.addWidget(self.tabs, 1)
        else:
            self._single = self._new_scroll()
            outer.addWidget(self._single, 1)

    @staticmethod
    def _new_scroll() -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        return scroll

    def _scroll_of(self, index: int) -> QScrollArea:
        return self.tabs.widget(index) if self.tabs else self._single

    def _ensure_built(self, index: int) -> None:
        if index < 0 or self._pages[index] is not None:
            return
        content = QWidget()
        content.setObjectName("page")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 8, 8, 8)
        layout.setSpacing(12)
        for group in self.sections[index].groups:
            layout.addWidget(self._make_group(group))
        layout.addStretch(1)
        self._pages[index] = content
        self._scroll_of(index).setWidget(content)

    def built_sections(self) -> list[int]:
        return [i for i, page in enumerate(self._pages) if page is not None]

    def show_section(self, index: int) -> None:
        if self.tabs:
            self.tabs.setCurrentIndex(index)
        self._ensure_built(index)

    def show_all_sections(self) -> None:
        for i in range(len(self.sections)):
            self._ensure_built(i)

    # -- cards and rows
    def _make_group(self, group: Group) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(10)
        layout.addWidget(_label(group.title, "subtitle"))
        if group.description is not EMPTY and group.description.es:
            layout.addWidget(_label(group.description, "muted"))
        if group.hint:
            layout.addWidget(self._make_hint(group.hint))
        for option in group.options:
            layout.addWidget(self._make_row(option).container)
        options = list(group.options)
        self._groups.append((card, options))
        self._apply_group_visibility(card, options)
        return card

    def _make_hint(self, hint: Hint) -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.GOLD};")

        def text(lang: str) -> str:
            return (hint.on if all(self.is_on(f) for f in hint.fields) else hint.off)(lang)

        translator.bind(label, label.setText, text)
        for field in hint.fields:
            self._hints.setdefault(field, []).append((label, text))
        return label

    def _make_row(self, option: Option) -> _Row:
        field = option.field
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        high = None
        if option.choices:
            control = _EnumControl(option)
            control.set_value(self.store[field])
            control.picked.connect(lambda v, f=field: self._edit(f, v))
            widget, set_value = control, control.set_value
            if option.compact:
                layout.addWidget(_label(option.label))
                layout.addWidget(control, 1)
            else:
                layout.setDirection(QHBoxLayout.Direction.TopToBottom)
                layout.setSpacing(6)
                layout.addWidget(_label(option.label))
                layout.addWidget(control)
        elif option.range_to or option.maximum > option.minimum:
            widget = self._spin(option, field)
            set_value = self._silent(widget, widget.setValue)
            layout.addWidget(_label(option.label), 1)
            layout.addWidget(widget)
            if option.range_to:
                high = self._spin(option, option.range_to)
                layout.addWidget(QLabel("–"))
                layout.addWidget(high)
        else:
            widget = ToggleSwitch()
            widget.setChecked(bool(self.store[field]))
            widget.toggled.connect(lambda v, f=field: self._edit(f, bool(v)))
            label = _ClickLabel(widget)
            translator.bind(label, label.setText, option.label)
            _tooltip(label, option.tooltip)
            layout.addWidget(widget)
            layout.addWidget(label, 1)
            set_value = self._silent(widget, lambda v, w=widget: w.setChecked(bool(v)))
        _tooltip(box, option.tooltip)
        row = _Row(option, box, widget, set_value, high)
        self.rows[field] = row
        if option.range_to:
            self.rows[option.range_to] = row
        box.setEnabled(self._enabled(option))
        _set_shown(box, not (self.console and field in self._console_hidden))
        return row

    def _spin(self, option: Option, field: str) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(option.minimum, option.maximum)
        spin.setSingleStep(option.step)
        spin.setValue(int(self.store[field]))
        spin.valueChanged.connect(lambda v, f=field: self._edit(f, v))
        spin.setFixedWidth(84)
        return spin

    @staticmethod
    def _silent(widget: QWidget, setter):
        def apply(value) -> None:
            blocked = widget.blockSignals(True)
            try:
                setter(value)
            finally:
                widget.blockSignals(blocked)
        return apply

    # -- reading and editing
    def row_widget(self, field: str) -> QWidget:
        """The input widget of a field (building its section if needed): toggle, enum control or spin box."""
        self._ensure_built(self._section_of.get(field, 0))
        row = self.rows[field]
        return row.high if field in self._pairs else row.widget

    def _edit(self, field: str, value) -> None:
        self.store[field] = value
        option = self._options.get(field)
        if option and option.choices:
            self.rows[field].widget.sync()   # a legacy choice disappears once another is picked
        self._refresh(field)
        self.changed.emit(field)

    def _refresh(self, *fields: str) -> None:
        targets: set[str] = set()
        for field in fields:
            targets |= self._dependents.get(field, set())
            for label, text in self._hints.get(field, ()):
                label.setText(text(translator.language))
        for target in targets:
            self.refresh_log.append(target)
            row = self.rows.get(target)
            if row is not None:
                row.container.setEnabled(self._enabled(self._options[target]))

    def values(self) -> dict:
        out = dict(self.store)
        for option in self._options.values():
            for linked in option.links:
                out[linked] = out[option.field]
        return out

    def set_values(self, values: dict) -> None:
        """Load fields (unknown ones are ignored, missing ones stay); built widgets follow without `changed`."""
        touched = []
        for field, value in values.items():
            if field not in self.store:
                continue
            option = self._options.get(field)
            if option is None:
                value = int(value)     # a range_to field
            elif option.choices:
                value = self._coerce(option, value)
                if value is None:
                    continue
            elif option.range_to or option.maximum > option.minimum:
                value = int(value)
            else:
                value = bool(value)
            self.store[field] = value
            touched.append(field)
            row = self.rows.get(field)
            if row is not None:
                if option is None:
                    self._silent(row.high, row.high.setValue)(value)
                else:
                    row.set_value(value)
        self._refresh(*touched)

    @staticmethod
    def _coerce(option: Option, value):
        for choice in option.choices:
            if value is choice.value or value == choice.value:
                return choice.value
        for choice in option.choices:
            if not isinstance(value, bool) and value in (choice.value.value, choice.value.name):
                return choice.value
        return None

    def choice_labels(self, field: str) -> list[str]:
        """The texts of an enum field's visible choices (legacy ones only while set)."""
        return self.row_widget(field).labels()

    # -- platform
    def set_platform(self, console: bool) -> None:
        """On the 3DS (`console`) the emulator-only rows, and those that require them, are hidden."""
        self.console = console
        for field, row in self.rows.items():
            if field == row.option.field:
                _set_shown(row.container, not (console and field in self._console_hidden))
        for card, options in self._groups:
            self._apply_group_visibility(card, options)

    def _apply_group_visibility(self, card: QWidget, options: list[Option]) -> None:
        _set_shown(card, not (self.console and all(o.field in self._console_hidden for o in options)))


def _set_shown(widget: QWidget, shown: bool) -> None:
    """Show or hide a row or card. A widget without a parent yet is only ever hidden here: showing it would open it
    as a window of its own for a few frames (it becomes visible with its parent once it is added to a layout)."""
    if shown and widget.parentWidget() is None:
        if widget.isHidden() and widget.testAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide):
            widget.setAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide, False)
            widget.setAttribute(Qt.WidgetAttribute.WA_WState_Hidden, False)
        return
    widget.setVisible(shown)
