"""Base class of the app's pages (built on first show by `MainWindow`)."""

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..i18n import T
from .translate import translator


class Page(QWidget):
    """A page of the main window. Subclass it, set `title`, build widgets in `__init__` (bind every text with
    `translator.bind` so a language change needs no rebuild) and override the hooks you need."""

    title: T

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("page")
        self.console = False   # the 3DS platform is selected (False: emulator)

    def on_shown(self) -> None:
        """The page became the visible one (each time)."""

    def on_close(self) -> None:
        """The window is closing: write whatever the page keeps only in its widgets into the state's preferences."""

    def set_platform(self, console: bool) -> None:
        """The platform changed (also called once after construction). Override to hide emulator-only parts."""
        self.console = console

    def retranslate(self) -> None:
        """Called after a language change, for texts not bound with `translator.bind`."""


class PlaceholderPage(Page):
    def __init__(self, title: T, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        heading = QLabel()
        heading.setProperty("role", "title")
        translator.bind(heading, heading.setText, title)
        layout.addWidget(heading)
        layout.addStretch(1)
