"""Dark theme (QSS) from the logo's colours: near-black, gold, orange and a violet secondary.

Only the logo and Qt-drawn shapes are used (no art, no game assets, no downloads). Widgets pick a style with
dynamic properties: `role="nav"` (sidebar button), `role="segment"` (segmented choice), `role="primary"` (main
action), `role="title"` / `"subtitle"` / `"muted"` (labels) and `QFrame#card` (a rounded panel).
"""

# Sampled from assets/logo.png: gold (216, 168, 24), orange (192, 96, 0), cream (240, 240, 216), violet (128, 80, 160).
BG = "#0d0b0e"
SIDEBAR = "#120f14"
CARD = "#1a161e"
CARD_HOVER = "#221d28"
BORDER = "#2e2735"
TEXT = "#eeeadb"
MUTED = "#a199ab"
GOLD = "#d8a818"
GOLD_HOVER = "#e8bb30"
ORANGE = "#c06000"
VIOLET = "#8a5fb0"
VIOLET_DARK = "#4a3560"
DISABLED = "#5a5460"
DANGER = "#d9534f"

RADIUS = 10


def stylesheet() -> str:
    return f"""
* {{ font-family: "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; }}
QWidget {{ background: transparent; color: {TEXT}; }}
QMainWindow, QStackedWidget, QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QWidget#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QWidget#page {{ background: {BG}; }}
QToolTip {{ background: {CARD_HOVER}; color: {TEXT}; border: 1px solid {VIOLET}; padding: 6px; }}

QLabel[role="title"] {{ font-size: 18pt; font-weight: 600; color: {GOLD}; }}
QLabel[role="subtitle"] {{ font-size: 12pt; font-weight: 600; color: {TEXT}; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel:disabled {{ color: {DISABLED}; }}

QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}
QFrame#card:hover {{ border-color: {VIOLET_DARK}; }}

QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 16px; }}
QPushButton:hover {{ background: {CARD_HOVER}; border-color: {VIOLET}; }}
QPushButton:pressed {{ background: {VIOLET_DARK}; }}
QPushButton:focus {{ border: 2px solid {GOLD}; padding: 6px 15px; }}
QPushButton:disabled {{ color: {DISABLED}; border-color: {BORDER}; background: {SIDEBAR}; }}
QPushButton[role="primary"] {{ background: {GOLD}; color: #1a1200; border: 1px solid {GOLD}; font-weight: 600; }}
QPushButton[role="primary"]:hover {{ background: {GOLD_HOVER}; }}
QPushButton[role="primary"]:pressed {{ background: {ORANGE}; color: {TEXT}; }}
QPushButton[role="primary"]:disabled {{ background: {CARD}; color: {DISABLED}; border-color: {BORDER}; }}

QPushButton[role="nav"] {{ text-align: left; border: none; border-left: 3px solid transparent; border-radius: 0;
    padding: 11px 18px; background: transparent; font-size: 11.5pt; }}
QPushButton[role="nav"]:hover {{ background: {CARD}; }}
QPushButton[role="nav"]:checked {{ background: {CARD_HOVER}; border-left: 3px solid {GOLD}; color: {GOLD}; }}

QPushButton[role="segment"] {{ border-radius: 0; padding: 6px 14px; margin: 0; border: 1px solid {BORDER}; }}
QPushButton[role="segment"][pos="first"] {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QPushButton[role="segment"][pos="last"] {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QPushButton[role="segment"][pos="only"] {{ border-radius: 8px; }}
QPushButton[role="segment"]:checked {{ background: {VIOLET_DARK}; border-color: {VIOLET}; color: {TEXT}; }}
QPushButton[role="segment"]:checked:hover {{ background: {VIOLET}; }}
QPushButton[role="segment"]:disabled {{ color: {DISABLED}; }}
QPushButton[role="segment"]:checked:disabled {{ background: {CARD_HOVER}; border-color: {BORDER}; }}

QComboBox, QSpinBox, QLineEdit {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 5px 10px; min-height: 22px; selection-background-color: {VIOLET}; }}
QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {VIOLET}; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border: 2px solid {GOLD}; padding: 4px 9px; }}
QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {{ color: {DISABLED}; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {VIOLET};
    selection-background-color: {VIOLET_DARK};
    outline: none; }}

QTabBar::tab {{ background: transparent; padding: 9px 16px; border: none; border-bottom: 2px solid transparent;
    color: {MUTED}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {GOLD}; border-bottom: 2px solid {GOLD}; }}
QTabWidget::pane {{ border: none; }}

QProgressBar {{ background: {SIDEBAR}; border: 1px solid {BORDER}; border-radius: 8px;
    height: 16px; text-align: center; }}
QProgressBar::chunk {{ border-radius: 7px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 {ORANGE}, stop:1 {GOLD}); }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {VIOLET}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {VIOLET}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; }}
"""


def apply_theme(app) -> None:
    from PySide6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    palette = QPalette()
    roles = QPalette.ColorRole
    for role, colour in ((roles.Window, BG), (roles.Base, SIDEBAR), (roles.Button, CARD),
                         (roles.WindowText, TEXT), (roles.Text, TEXT),
                         (roles.ButtonText, TEXT), (roles.Highlight, VIOLET)):
        palette.setColor(role, QColor(colour))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())

