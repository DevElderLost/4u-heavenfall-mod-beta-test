"""The main window: a sidebar (logo, pages, language, platform) and pages built the first time they are shown. The
title, the pages and the platforms are the edition's (game/data/curated/edition.json).

Speed rules: this module imports neither the pipeline, the fix mode nor the knowledge base; pages are
factories run on first show; a language change re-runs registered setters (no rebuild); heavy work goes in workers.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

from PySide6.QtCore import QEvent, QLocale, QObject, QPointF, QPropertyAnimation, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea, QAbstractSpinBox, QApplication, QButtonGroup, QComboBox, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QSlider, QStackedWidget, QTabBar, QVBoxLayout, QWidget,
)

from core.app.edition import edition
from core.gui.i18n import LANGUAGE_NAMES, T, language_for_locales
from core.gui.qt import theme
from core.gui.qt.page import Page, PlaceholderPage
from core.gui.qt.resources import resource_path
from core.gui.qt.state import AppState
from core.gui.qt.translate import translator

WINDOW_TITLE = T(edition().window_title, edition().window_title)
PAGE_INSTALL = T("Instalar", "Install")
PAGE_OPTIONS = T("Opciones", "Options")
PAGE_RANDOMIZER = T("Randomizer", "Randomizer")
PLATFORM_EMULATOR = T("Emulador", "Emulator")
PLATFORM_3DS = T("3DS", "3DS")

APP_USER_MODEL_ID = edition().app_user_model_id   # Windows groups the taskbar button by it, with our icon

PageFactory = Callable[[], Page]
PageSpec = tuple[str, T, PageFactory]


def system_language(locale: QLocale | None = None) -> str:
    """The language of the system's interface (`locale`: Qt's, default the system's) when the player has not chosen
    one: Spanish for a Spanish system, else English (i18n.language_for_locales)."""
    locale = locale or QLocale.system()
    return language_for_locales([*locale.uiLanguages(), locale.name()])

# key -> (module of this package, Page class, nav title); each class takes the window's AppState
ALL_PAGES = {
    "install": ("install_page", "InstallPage", PAGE_INSTALL),
    "options": ("options_page", "OptionsPage", PAGE_OPTIONS),
    "randomizer": ("randomizer_page", "RandomizerPage", PAGE_RANDOMIZER),
}
PAGES = {key: ALL_PAGES[key] for key in edition().pages}    # the edition's, in its order


def _page_factory(module: str, name: str, title: T, state: AppState) -> PageFactory:
    """Import the page's module only when the page is first shown; a page not written yet is a placeholder."""
    def build() -> Page:
        try:
            page_module = importlib.import_module(f"{__package__}.{module}")
        except ModuleNotFoundError as error:
            if error.name != f"{__package__}.{module}":
                raise
            return PlaceholderPage(title)
        return getattr(page_module, name)(state)
    return build


class WheelGuard(QObject):
    """Options never change with the mouse wheel: over a combo, a number, a slider or a tab bar the wheel goes to the
    nearest scroll area around it, so scrolling a page of options never changes one by accident."""
    WIDGETS = (QComboBox, QAbstractSpinBox, QSlider, QTabBar)

    def eventFilter(self, obj, event) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(obj, self.WIDGETS):
            return False
        area = obj.parentWidget()
        while area is not None and not isinstance(area, QAbstractScrollArea):
            area = area.parentWidget()
        if area is not None:
            viewport = area.viewport()
            position = QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
            QApplication.sendEvent(viewport, QWheelEvent(
                position, event.globalPosition(), event.pixelDelta(), event.angleDelta(), event.buttons(),
                event.modifiers(), event.phase(), event.inverted()))
        event.accept()   # handled: Qt must not also pass it up to the parents (the page would scroll twice)
        return True


def install_wheel_guard(app: QApplication) -> None:
    """Install the `WheelGuard` on the whole application (once)."""
    if getattr(app, "_wheel_guard", None) is None:
        app._wheel_guard = WheelGuard(app)
        app.installEventFilter(app._wheel_guard)


def app_icon() -> QIcon:
    """The logo as the window and taskbar icon, centred on a transparent square (a wide image would be squashed)."""
    logo = QPixmap(str(resource_path("logo.png")))
    if logo.isNull():
        return QIcon()
    side = max(logo.width(), logo.height())
    square = QPixmap(side, side)
    square.fill(Qt.GlobalColor.transparent)
    painter = QPainter(square)
    painter.drawPixmap((side - logo.width()) // 2, (side - logo.height()) // 2, logo)
    painter.end()
    return QIcon(square)


def default_pages(state: AppState) -> list[PageSpec]:
    """(key, nav title, factory) of the real pages."""
    return [(key, title, _page_factory(module, name, title, state)) for key, (module, name, title) in PAGES.items()]


class MainWindow(QMainWindow):
    def __init__(self, pages: list[PageSpec] | None = None, state: AppState | None = None):
        super().__init__()
        self.state = state if state is not None else AppState()
        self.preferences = self.state.preferences
        pages = pages or default_pages(self.state)
        translator.language = self.preferences.language if self.preferences.language in LANGUAGE_NAMES \
            else system_language()
        self.console = self.state.console and "console" in edition().platforms
        self._factories = {key: factory for key, _, factory in pages}
        self.page_keys = [key for key, _, _ in pages]
        self._titles = {key: title for key, title, _ in pages}
        self._pages: dict[str, Page] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.resize(1100, 740)
        self.setMinimumSize(820, 560)
        translator.bind(self, self.setWindowTitle, WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        app = QApplication.instance()
        if app is not None:
            install_wheel_guard(app)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.show_page(self.page_keys[0], animate=False)

    # -- sidebar
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(230)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 18, 0, 16)
        layout.setSpacing(2)
        pixmap = QPixmap(str(resource_path("logo.png")))
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaledToWidth(190, Qt.TransformationMode.SmoothTransformation))
        else:   # an edition without a logo (none in gui/qt/assets): its name
            logo.setText(edition().name)
            logo.setProperty("role", "title")
        layout.addWidget(logo)
        layout.addSpacing(14)
        group = QButtonGroup(self)
        for key in self.page_keys:
            button = QPushButton()
            button.setProperty("role", "nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            translator.bind(button, button.setText, self._titles[key])
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(button)
            layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addStretch(1)
        self.language_buttons = self._segmented(
            layout, {code: T(name, name) for code, name in LANGUAGE_NAMES.items()}, translator.language,
            self.set_language)
        self.platform_buttons: dict[str, QPushButton] = {}
        if len(edition().platforms) > 1:    # an emulator-only edition shows no switch
            layout.addSpacing(8)
            self.platform_buttons = self._segmented(
                layout, {"emulator": PLATFORM_EMULATOR, "console": PLATFORM_3DS},
                "console" if self.console else "emulator", lambda key: self.set_platform(key == "console"))
        return side

    @staticmethod
    def _segmented(parent_layout, items: dict[str, T], current: str, on_pick) -> dict[str, QPushButton]:
        row = QWidget()
        box = QHBoxLayout(row)
        box.setContentsMargins(18, 0, 18, 0)
        box.setSpacing(0)
        group, buttons = QButtonGroup(row), {}
        for i, (key, text) in enumerate(items.items()):
            button = QPushButton()
            button.setCheckable(True)
            button.setProperty("role", "segment")
            pos = "only" if len(items) == 1 else "first" if i == 0 else "last" if i == len(items) - 1 else "mid"
            button.setProperty("pos", pos)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            translator.bind(button, button.setText, text)
            button.setChecked(key == current)
            button.clicked.connect(lambda _=False, k=key: on_pick(k))
            group.addButton(button)
            box.addWidget(button, 1)
            buttons[key] = button
        parent_layout.addWidget(row)
        return buttons

    # -- pages
    def built_pages(self) -> list[str]:
        return [key for key in self.page_keys if key in self._pages]

    def page(self, key: str) -> Page:
        """The page for `key`, built now if it was not yet."""
        if key not in self._pages:
            page = self._factories[key]()
            page.set_platform(self.console)
            self._pages[key] = page
            self.stack.addWidget(page)
        return self._pages[key]

    def show_page(self, key: str, animate: bool = True) -> None:
        page = self.page(key)
        self.nav_buttons[key].setChecked(True)
        if self.stack.currentWidget() is page:
            return
        self.stack.setCurrentWidget(page)
        if animate:
            self._fade_in(page)
        page.on_shown()

    @staticmethod
    def _fade_in(page: QWidget) -> None:
        """A short fade (the effect is removed afterwards: graphics effects slow painting)."""
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(140)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def closeEvent(self, event) -> None:
        """Keep everything the player set, not only what a run saved: the pages' own values, then the options with
        the defaults filled in."""
        for page in self._pages.values():
            page.on_close()
        self.preferences.install_options = self.state.personal
        self.preferences.save()
        super().closeEvent(event)

    # -- language and platform
    def set_language(self, code: str) -> None:
        translator.set_language(code)
        for key, button in self.language_buttons.items():
            button.setChecked(key == code)
        for page in self._pages.values():
            page.retranslate()
        self.preferences.language = code
        self.preferences.save()

    def set_platform(self, console: bool) -> None:
        self.console = console
        for key, button in self.platform_buttons.items():
            button.setChecked((key == "console") == console)
        for page in self._pages.values():
            page.set_platform(console)
        self.state.console = console


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setWindowIcon(app_icon())
    theme.apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()
