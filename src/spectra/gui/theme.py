"""Light theme for PySide6 — calm, light, sparse.

Sole styling authority for the app. Copy to <package>/ui/theme.py with the Inter
TTFs in <package>/ui/fonts/. Call apply_theme(app) once after QApplication.
Run `python theme.py` after any token change to verify contrast and grid.

Sibling theme: pyside6-dark. Both files share the engine below the Tokens class.
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from string import Template

from PySide6.QtCore import QByteArray, QEvent, QObject, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QFrame, QHBoxLayout, QLayout, QTableView, QWidget,
)


class Tokens:
    NAME = "light"
    DARK = False

    # Canvas and ink — every neutral is INK at an alpha over CANVAS
    CANVAS = "#FFFFFF"
    INK = (0, 0, 0)
    INK_PRIMARY = 1.00     # values, headings, body
    INK_SECONDARY = 0.64   # supporting text, inactive tabs
    INK_TERTIARY = 0.56    # units, captions, placeholders
    INK_GLYPH = 0.44       # icons, focus ring, indicator borders — never text
    INK_DISABLED = 0.38

    # Surfaces (ink alpha)
    WASH = 0.03
    HOVER = 0.05
    PRESSED = 0.09         # pressed, checked, selected — carries primary ink only
    BORDER = 0.10          # panels, cards, dividers
    BORDER_STRONG = 0.18   # control boundaries
    SCROLL_HANDLE = 0.18

    # Action: blue marks "on / in progress / the main action"
    ACTION = "#2563EB"
    ACTION_HOVER = "#1D4ED8"
    ACTION_PRESSED = "#1E40AF"
    ON_ACTION = "#FFFFFF"
    FOCUS_ON_ACTION = "#1E3A8A"
    LINK = "#1D4ED8"
    TEXT_SELECTION = "rgba(37, 99, 235, 0.180)"

    # Semantic — text-safe on canvas (≥ 4.5:1); always paired with a label or icon
    SUCCESS = "#15803D"
    WARNING = "#B45309"
    ERROR = "#DC2626"
    ERROR_FILL = "#DC2626"
    ERROR_PRESSED = "#B91C1C"
    ON_ERROR = "#FFFFFF"
    SUCCESS_BG = "rgba(21, 128, 61, 0.080)"
    WARNING_BG = "rgba(180, 83, 9, 0.080)"
    ERROR_BG = "rgba(220, 38, 38, 0.080)"

    # Data series (≥ 3:1 on canvas), in plotting order
    SERIES = ("#2563EB", "#059669", "#D97706", "#7C3AED", "#E11D48", "#0891B2")

    # Component surfaces
    SHELL = "#F7F7F7"              # solid(WASH) — sidebar shell; content sits on CANVAS
    SIDEBAR_BG = "transparent"
    SIDEBAR_RULE = ""
    INSET_BORDER = "none"
    BUTTON_BG = CANVAS
    INPUT_BG = CANVAS
    CARD_BG = "transparent"
    VIEW_BG = CANVAS
    POPUP_BG = CANVAS
    HEADER_BG = "transparent"
    SEGMENT_TRACK = "rgba(0, 0, 0, 0.050)"
    SEGMENT_ON = CANVAS
    NAV_INK = INK_SECONDARY
    TABLE_STYLE = "wash"           # alternating wash rows, no rules
    TAB_STYLE = "underline"

    # Typography — Inter, px
    FONT_FAMILY = "Inter"
    SIZE_METRIC = 24
    SIZE_TITLE = 22
    SIZE_HEADING = 16
    SIZE_BODY = 14
    SIZE_LABEL = 13
    SIZE_CAPTION = 12
    WEIGHT_TITLE = 600
    WEIGHT_METRIC = 500

    # Geometry — 8 px grid, 4 px steps allowed
    WINDOW_MARGIN = 20
    GROUP_MARGIN = 16
    ROW_SPACING = 8
    GROUP_SPACING = 20
    SECTION_SPACING = 32
    CONTROL_HEIGHT = 32
    COMPACT_HEIGHT = 28
    ROW_HEIGHT = 32
    ICON_SIZE = 16
    RADIUS_CONTROL = 6
    RADIUS_PANEL = 8
    RADIUS_INSET = 0
    SHELL_GAP = 0
    SIDEBAR_WIDTH = 224

    MIN_WINDOW = (480, 360)
    MIN_DIALOG_WIDTH = 360

    animate = True                 # bind to a user setting; check at every animation call site
    MOTION_MS = 160

# ═════════════════════════════════════════════════════════════════════════════
# Engine — identical in pyside6-light and pyside6-dark. Everything above this
# line is theme-specific; everything below reads only from Tokens. Change the two
# copies together.
# ═════════════════════════════════════════════════════════════════════════════

_HERE = Path(__file__).resolve().parent
# ui/fonts next to theme.py in a project; assets/fonts when run inside the skill folder
_FONT_DIR = next((d for d in (_HERE / "fonts", _HERE.parent / "assets" / "fonts") if d.is_dir()), _HERE / "fonts")
_ASSET_DIR: Path | None = None  # generated indicator SVGs, created once per process


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _mix(fg: tuple[int, int, int], bg: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    return tuple(round(f * alpha + b * (1 - alpha)) for f, b in zip(fg, bg))  # type: ignore[return-value]


def ink(alpha: float) -> str:
    """Ink at `alpha` as a QSS rgba() string. Composites over whatever surface is below."""
    r, g, b = Tokens.INK
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def solid(alpha: float, over: str | None = None) -> str:
    """Ink at `alpha` pre-composited over `over` (default CANVAS) as an opaque hex.

    Use for surfaces that stack (shell, popups, header rows) so that overlays do not
    compound, and anywhere a library needs an opaque colour (QPalette, Matplotlib).
    """
    return _hex(_mix(Tokens.INK, _rgb(over or Tokens.CANVAS), alpha))


def tint(hex_colour: str, alpha: float) -> str:
    r, g, b = _rgb(hex_colour)
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


Tokens.ink = staticmethod(ink)      # type: ignore[attr-defined]  # Tokens.ink(alpha), as documented
Tokens.solid = staticmethod(solid)  # type: ignore[attr-defined]


# ── Contrast maths (WCAG 2.x relative luminance) ────────────────────────────

def _lum(rgb: tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str) -> float:
    a, b = _lum(_rgb(fg)), _lum(_rgb(bg))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ── Assets ──────────────────────────────────────────────────────────────────

def _write_assets() -> Path:
    """Write the small SVGs QSS needs for indicators. QSS url() cannot take data URIs."""
    global _ASSET_DIR
    if _ASSET_DIR is not None:
        return _ASSET_DIR
    d = Path(tempfile.mkdtemp(prefix=f"{Tokens.NAME}-theme-"))
    on = Tokens.ON_ACTION
    chevron = solid(Tokens.INK_SECONDARY)
    svgs = {
        "check.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="{on}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "dot.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.5" fill="{on}"/></svg>',
        "chevron-down.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 6l4 4 4-4" fill="none" stroke="{chevron}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "chevron-up.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M4 10l4-4 4 4" fill="none" stroke="{chevron}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    for name, svg in svgs.items():
        (d / name).write_text(svg, encoding="utf-8")
    _ASSET_DIR = d
    return d


def _load_fonts() -> str:
    """Register bundled Inter TTFs (ui/fonts/*.ttf) and return the family to use."""
    if _FONT_DIR.is_dir():
        for ttf in sorted(_FONT_DIR.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(ttf))
    if Tokens.FONT_FAMILY in QFontDatabase.families():
        return Tokens.FONT_FAMILY
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


# ── Stylesheet ──────────────────────────────────────────────────────────────

_QSS = Template("""
QWidget { color: $ink1; font-size: ${body}px; }
QMainWindow, QDialog { background: $canvas; }
QMainWindow::separator { background: $border; width: 1px; height: 1px; }

/* Structure ------------------------------------------------------------ */
QFrame[role="shell"]   { background: $shell; }
QFrame[role="sidebar"] { background: $sidebar_bg; border: none; $sidebar_rule }
QFrame[role="inset"]   { background: $canvas; border: $inset_border; border-radius: ${r_inset}px; }
QFrame[role="card"]    { background: $card_bg; border: 1px solid $border; border-radius: ${r_panel}px; }
QFrame[role="divider"] { background: $border; border: none; min-height: 1px; max-height: 1px; }
QFrame[role="segmented"] { background: $track; border: none; border-radius: ${r_control}px; }

/* Text roles ----------------------------------------------------------- */
QLabel { background: transparent; color: $ink1; }
QLabel:disabled { color: $ink_disabled; }
QLabel[role="title"]      { font-size: ${title}px;   font-weight: $w_title; }
QLabel[role="metric"]     { font-size: ${metric}px;  font-weight: $w_metric; }
QLabel[role="heading"]    { font-size: ${heading}px; font-weight: 600; }
QLabel[role="supporting"] { color: $ink2; }
QLabel[role="caption"], QLabel[role="unit"] { font-size: ${caption}px; font-weight: 500; color: $ink3; }
QLabel[role="section"]    { font-size: ${caption}px; font-weight: 500; color: $ink3; padding: 0 8px; }
QLabel[role="badge"] {
    font-size: ${caption}px; font-weight: 500; color: $ink2;
    border: 1px solid $border_strong; border-radius: ${r_badge}px; padding: 2px 7px;
}
$tone_rules

/* Buttons -------------------------------------------------------------- */
QPushButton, QToolButton {
    background: $button_bg; color: $ink1;
    border: 1px solid $border_strong; border-radius: ${r_control}px;
    padding: 1px 12px; min-height: ${control_inner}px;
    font-size: ${label}px; font-weight: 500;
}
QToolButton { padding: 1px 8px; }
QPushButton:hover, QToolButton:hover { background: $hover; }
QPushButton:pressed, QToolButton:pressed,
QPushButton:checked, QToolButton:checked { background: $pressed; }
QPushButton:focus, QToolButton:focus { border: 2px solid $focus; padding: 0 11px; }
QToolButton:focus { padding: 0 7px; }
QPushButton:disabled, QToolButton:disabled { background: $wash; color: $ink_disabled; border-color: $border; }
QToolButton::menu-indicator { image: none; }

QPushButton[variant="primary"] { background: $action; color: $on_action; border-color: $action; }
QPushButton[variant="primary"]:hover   { background: $action_hover; border-color: $action_hover; }
QPushButton[variant="primary"]:pressed { background: $action_pressed; border-color: $action_pressed; }
QPushButton[variant="primary"]:focus   { border: 2px solid $focus_on_action; }
QPushButton[variant="primary"]:disabled { background: $wash; color: $ink_disabled; border-color: $border; }

QPushButton[variant="quiet"], QToolButton[variant="quiet"] { background: transparent; border-color: transparent; }
QPushButton[variant="quiet"]:hover, QToolButton[variant="quiet"]:hover { background: $hover; }
QPushButton[variant="quiet"]:pressed, QToolButton[variant="quiet"]:pressed,
QPushButton[variant="quiet"]:checked, QToolButton[variant="quiet"]:checked { background: $pressed; }
QPushButton[variant="quiet"]:focus, QToolButton[variant="quiet"]:focus { border: 2px solid $focus; }
QPushButton[variant="quiet"]:disabled { background: transparent; border-color: transparent; }

QPushButton[variant="danger"] { background: transparent; color: $error; border-color: $error; }
QPushButton[variant="danger"]:hover   { background: $error_fill; color: $on_error; border-color: $error_fill; }
QPushButton[variant="danger"]:pressed { background: $error_pressed; color: $on_error; border-color: $error_pressed; }
QPushButton[variant="danger"]:focus   { border: 2px solid $error_pressed; }
QPushButton[variant="danger"]:disabled { background: $wash; color: $ink_disabled; border-color: $border; }

/* Sidebar navigation: checkable buttons in an exclusive QButtonGroup */
QPushButton[role="nav"] {
    text-align: left; background: transparent; border: 1px solid transparent;
    color: $nav_ink; font-weight: 400; padding: 1px 8px;
}
QPushButton[role="nav"]:hover   { background: $hover; color: $ink1; }
QPushButton[role="nav"]:checked { background: $pressed; color: $ink1; font-weight: 500; }
QPushButton[role="nav"]:focus   { border: 2px solid $focus; padding: 0 7px; }

/* Segmented control: checkable buttons inside QFrame[role="segmented"] */
QFrame[role="segmented"] QPushButton {
    background: transparent; border: 1px solid transparent; color: $ink2;
    min-height: ${segment_inner}px; padding: 1px 12px;
}
QFrame[role="segmented"] QPushButton:hover   { color: $ink1; background: transparent; }
QFrame[role="segmented"] QPushButton:checked { background: $segment_on; color: $ink1; border-color: $border; }
QFrame[role="segmented"] QPushButton:focus   { border: 2px solid $focus; padding: 0 11px; }

/* Inputs --------------------------------------------------------------- */
QLineEdit, QComboBox, $spins {
    background: $input_bg; color: $ink1;
    border: 1px solid $border_strong; border-radius: ${r_control}px;
    selection-background-color: $text_selection; selection-color: $ink1;
}
QLineEdit, QComboBox { padding: 1px 8px; min-height: ${control_inner}px; }
QPlainTextEdit, QTextEdit {
    background: $input_bg; color: $ink1;
    border: 1px solid $border_strong; border-radius: ${r_control}px; padding: 4px;
    selection-background-color: $text_selection; selection-color: $ink1;
}
QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover { border-color: $border_hover; }
QLineEdit:focus, QComboBox:focus { border: 2px solid $focus; padding: 0 7px; }
QPlainTextEdit:focus, QTextEdit:focus { border: 2px solid $focus; padding: 3px; }
QLineEdit:disabled, QComboBox:disabled, QPlainTextEdit:disabled, QTextEdit:disabled
    { background: $wash; color: $ink_disabled; border-color: $border; }
QLineEdit[state="error"], QComboBox[state="error"], QPlainTextEdit[state="error"] { border-color: $error; }
QLineEdit[state="error"]:focus, QComboBox[state="error"]:focus { border: 2px solid $error; }

/* Spin boxes: Qt ignores left padding here; apply_theme sets the inner line edit's text margin */
$spin_sel { padding: 0 24px 0 0; min-height: ${control_inner}px; max-height: ${spin_max}px; }
$spin_hover { border-color: $border_hover; }
$spin_focus { border: 2px solid $focus; padding: 0 23px 0 0; max-height: ${spin_max_focus}px; }
$spin_disabled { background: $wash; color: $ink_disabled; border-color: $border; }
$spin_error { border-color: $error; }
QAbstractSpinBox QLineEdit, QComboBox QLineEdit,
QAbstractSpinBox QLineEdit:focus, QComboBox QLineEdit:focus {
    background: transparent; border: none; padding: 0; min-height: 0;
}
QAbstractSpinBox QLineEdit:disabled { background: transparent; }

QComboBox::drop-down { border: none; width: 24px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { image: url($assets/chevron-down.svg); width: 16px; height: 16px; }
QComboBox QAbstractItemView {
    background: $popup_bg; border: 1px solid $border_strong; border-radius: ${r_control}px;
    padding: 4px; outline: 0; selection-background-color: $pressed; selection-color: $ink1;
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    border: none; background: transparent; width: 20px; subcontrol-origin: border;
}
QAbstractSpinBox::up-button   { subcontrol-position: top right; margin: 2px 2px 0 0; }
QAbstractSpinBox::down-button { subcontrol-position: bottom right; margin: 0 2px 2px 0; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: $hover; border-radius: 4px; }
QAbstractSpinBox::up-arrow   { image: url($assets/chevron-up.svg);   width: 12px; height: 12px; }
QAbstractSpinBox::down-arrow { image: url($assets/chevron-down.svg); width: 12px; height: 12px; }

QCheckBox, QRadioButton { spacing: 8px; background: transparent; }
QCheckBox:disabled, QRadioButton:disabled { color: $ink_disabled; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px; height: 14px; background: $input_bg; border: 1px solid $indicator_border;
}
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $ink2; }
QCheckBox::indicator:focus, QRadioButton::indicator:focus { width: 12px; height: 12px; border: 2px solid $focus; }
QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate { background: $action; border-color: $action; image: url($assets/check.svg); }
QRadioButton::indicator:checked { background: $action; border-color: $action; image: url($assets/dot.svg); }
QCheckBox::indicator:checked:focus, QRadioButton::indicator:checked:focus { border: 2px solid $focus_on_action; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: $wash; border-color: $border; image: none; }

QSlider::groove:horizontal { height: 4px; background: $pressed; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $action; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -6px 0; border-radius: 8px;
    background: $canvas; border: 1px solid $indicator_border;
}
QSlider::handle:horizontal:hover, QSlider::handle:horizontal:focus { border: 2px solid $action; width: 12px; height: 12px; }
QSlider::handle:horizontal:disabled { border-color: $border; }

QProgressBar {
    background: $pressed; border: none; border-radius: 3px;
    min-height: 6px; max-height: 6px; color: transparent; text-align: center;
}
QProgressBar::chunk { background: $action; border-radius: 3px; }

/* Containers ----------------------------------------------------------- */
QGroupBox {
    background: transparent; border: 1px solid $border; border-radius: ${r_panel}px;
    margin-top: 12px; padding: ${group_margin}px ${group_margin}px ${group_margin}px ${group_margin}px;
    font-size: ${label}px; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 12px; padding: 0 4px; background: $canvas; color: $ink1;
}

$tab_rules

QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QScrollBar:vertical   { background: transparent; width: 10px;  margin: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:vertical   { background: $scroll_handle; min-height: 32px; border-radius: 3px; margin: 2px; }
QScrollBar::handle:horizontal { background: $scroll_handle; min-width: 32px;  border-radius: 3px; margin: 2px; }
QScrollBar::handle:hover { background: $glyph; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle:horizontal {
    width: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.428 transparent,
                stop:0.429 $border, stop:0.571 $border, stop:0.572 transparent, stop:1 transparent);
}
QSplitter::handle:vertical {
    height: 7px;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 transparent, stop:0.428 transparent,
                stop:0.429 $border, stop:0.571 $border, stop:0.572 transparent, stop:1 transparent);
}

/* Item views ----------------------------------------------------------- */
QAbstractItemView {
    background: $view_bg; border: 1px solid $border; border-radius: ${r_panel}px;
    alternate-background-color: $wash; gridline-color: $border; outline: 0;
    selection-background-color: $selection_solid; selection-color: $ink1;
}
QAbstractItemView::item { padding: 0 5px; $item_rule }  /* + Qt's 3 px text margin = 8 px */
QAbstractItemView::item:hover    { background: $hover; }
QAbstractItemView::item:selected { color: $ink1; }  /* opaque fill from selection-background-color: rgba here paints twice */
QListView::item { min-height: ${row_h}px; border-radius: $list_item_radius; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: $header_bg; color: $ink2; border: none; border-bottom: 1px solid $border;
    padding: 0 8px; min-height: ${row_h}px; font-size: ${label}px; font-weight: 500;
}
QHeaderView::section:first { border-top-left-radius: ${r_header}px; }
QHeaderView::section:last  { border-top-right-radius: ${r_header}px; }
QTableCornerButton::section { background: $header_bg; border: none; }

/* Menus, tooltips, bars -------------------------------------------------- */
QMenuBar { background: transparent; border-bottom: 1px solid $border; }
QMenuBar::item { background: transparent; padding: 4px 8px; border-radius: 4px; }
QMenuBar::item:selected { background: $hover; }
QMenu { background: $popup_bg; border: 1px solid $border_strong; border-radius: ${r_panel}px; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 8px; border-radius: 4px; font-size: ${label}px; }
QMenu::item:selected { background: $pressed; color: $ink1; }
QMenu::item:disabled { color: $ink_disabled; }
QMenu::separator { height: 1px; background: $border; margin: 4px 0; }
QToolTip { background: $popup_bg; color: $ink1; border: 1px solid $border_strong; border-radius: 4px; padding: 4px 8px; font-size: ${caption}px; }
QToolBar { background: transparent; border: none; border-bottom: 1px solid $border; spacing: 4px; padding: 4px; }
QStatusBar { background: transparent; color: $ink3; font-size: ${caption}px; border-top: 1px solid $border; }
QStatusBar QLabel { color: $ink3; font-size: ${caption}px; }
""")

_UNDERLINE_TABS = """
QTabWidget::pane { border: none; border-top: 1px solid $border; top: -1px; padding-top: ${group_spacing}px; }
QTabBar::tab {
    background: transparent; color: $ink2; border: none; border-bottom: 2px solid transparent;
    padding: 8px 12px; margin-right: 4px; font-size: ${label}px; font-weight: 500;
}
QTabBar::tab:hover    { color: $ink1; }
QTabBar::tab:selected { color: $ink1; border-bottom: 2px solid $ink1; }
QTabBar::tab:disabled { color: $ink_disabled; }
"""

_PILL_TABS = """
QTabWidget::pane { border: none; padding-top: ${group_spacing}px; }
QTabBar::tab {
    background: transparent; color: $ink2; border: 1px solid transparent; border-radius: ${r_control}px;
    padding: 6px 12px; margin-right: 4px; font-size: ${label}px; font-weight: 500;
}
QTabBar::tab:hover    { color: $ink1; background: $hover; }
QTabBar::tab:selected { color: $ink1; background: $pressed; border-color: $border; }
QTabBar::tab:disabled { color: $ink_disabled; }
"""


def _tone_rules() -> str:
    rules = []
    for tone, fg, bg in (
        ("success", Tokens.SUCCESS, Tokens.SUCCESS_BG),
        ("warning", Tokens.WARNING, Tokens.WARNING_BG),
        ("error", Tokens.ERROR, Tokens.ERROR_BG),
    ):
        rules.append(
            f'QLabel[role="caption"][tone="{tone}"] {{ color: {fg}; }}\n'
            f'QLabel[role="badge"][tone="{tone}"] {{ color: {fg}; border-color: {tint(fg, 0.40)}; background: {bg}; }}\n'
            f'QLabel[role="banner"][tone="{tone}"] {{ color: {fg}; background: {bg}; border: 1px solid {tint(fg, 0.30)}; '
            f"border-radius: {Tokens.RADIUS_CONTROL}px; padding: 8px 12px; }}"
        )
    return "\n".join(rules)


_SPINS = ("QSpinBox", "QDoubleSpinBox", "QDateEdit", "QTimeEdit", "QDateTimeEdit")


def build_qss() -> str:
    T = Tokens
    assets = _write_assets().as_posix()
    values = dict(
        canvas=T.CANVAS, shell=T.SHELL,
        ink1=ink(T.INK_PRIMARY), ink2=ink(T.INK_SECONDARY), ink3=ink(T.INK_TERTIARY),
        glyph=ink(T.INK_GLYPH), ink_disabled=ink(T.INK_DISABLED),
        wash=ink(T.WASH), hover=ink(T.HOVER), pressed=ink(T.PRESSED),
        border=ink(T.BORDER), border_strong=ink(T.BORDER_STRONG), border_hover=ink(T.INK_GLYPH),
        focus=ink(T.INK_GLYPH), focus_on_action=T.FOCUS_ON_ACTION,
        indicator_border=ink(T.INK_GLYPH), scroll_handle=ink(T.SCROLL_HANDLE),
        action=T.ACTION, action_hover=T.ACTION_HOVER, action_pressed=T.ACTION_PRESSED, on_action=T.ON_ACTION,
        error=T.ERROR, error_fill=T.ERROR_FILL, error_pressed=T.ERROR_PRESSED, on_error=T.ON_ERROR,
        text_selection=T.TEXT_SELECTION, selection_solid=solid(T.PRESSED),
        button_bg=T.BUTTON_BG, input_bg=T.INPUT_BG, card_bg=T.CARD_BG, view_bg=T.VIEW_BG,
        popup_bg=T.POPUP_BG, header_bg=T.HEADER_BG, track=T.SEGMENT_TRACK, segment_on=T.SEGMENT_ON,
        sidebar_bg=T.SIDEBAR_BG, sidebar_rule=T.SIDEBAR_RULE, nav_ink=ink(T.NAV_INK),
        inset_border=T.INSET_BORDER, r_inset=T.RADIUS_INSET,
        r_control=T.RADIUS_CONTROL, r_panel=T.RADIUS_PANEL, r_badge=T.RADIUS_CONTROL - 2,
        r_header=T.RADIUS_PANEL - 1 if T.HEADER_BG != "transparent" else 0,
        list_item_radius=f"{T.RADIUS_CONTROL - 2}px",
        title=T.SIZE_TITLE, metric=T.SIZE_METRIC, heading=T.SIZE_HEADING, body=T.SIZE_BODY,
        label=T.SIZE_LABEL, caption=T.SIZE_CAPTION, w_title=T.WEIGHT_TITLE, w_metric=T.WEIGHT_METRIC,
        control_inner=T.CONTROL_HEIGHT - 4, segment_inner=T.CONTROL_HEIGHT - 12,
        row_h=T.ROW_HEIGHT, group_margin=T.GROUP_MARGIN, group_spacing=T.GROUP_SPACING,
        spin_max=T.CONTROL_HEIGHT - 2, spin_max_focus=T.CONTROL_HEIGHT - 4,
        spins=", ".join(_SPINS),
        spin_sel=", ".join(_SPINS), spin_hover=", ".join(f"{c}:hover" for c in _SPINS),
        spin_focus=", ".join(f"{c}:focus" for c in _SPINS),
        spin_disabled=", ".join(f"{c}:disabled" for c in _SPINS),
        spin_error=", ".join(f'{c}[state="error"]' for c in _SPINS),
        item_rule=f"border-bottom: 1px solid {ink(T.BORDER)};" if T.TABLE_STYLE == "rule" else "",
        assets=assets,
    )
    tabs = Template(_PILL_TABS if T.TAB_STYLE == "pill" else _UNDERLINE_TABS).substitute(values)
    return _QSS.substitute(values, tone_rules=_tone_rules(), tab_rules=tabs)


def _palette() -> QPalette:
    T, p = Tokens, QPalette()
    c = lambda h: QColor(h)  # noqa: E731
    roles = {
        QPalette.ColorRole.Window: T.CANVAS, QPalette.ColorRole.Base: T.CANVAS,
        QPalette.ColorRole.AlternateBase: solid(T.WASH), QPalette.ColorRole.Button: T.CANVAS,
        QPalette.ColorRole.WindowText: solid(T.INK_PRIMARY), QPalette.ColorRole.Text: solid(T.INK_PRIMARY),
        QPalette.ColorRole.ButtonText: solid(T.INK_PRIMARY), QPalette.ColorRole.BrightText: T.ON_ERROR,
        QPalette.ColorRole.PlaceholderText: solid(T.INK_TERTIARY),
        QPalette.ColorRole.Highlight: solid(T.PRESSED), QPalette.ColorRole.HighlightedText: solid(T.INK_PRIMARY),
        QPalette.ColorRole.ToolTipBase: _opaque(T.POPUP_BG), QPalette.ColorRole.ToolTipText: solid(T.INK_PRIMARY),
        QPalette.ColorRole.Link: T.LINK, QPalette.ColorRole.LinkVisited: T.LINK,
        QPalette.ColorRole.Light: solid(T.WASH), QPalette.ColorRole.Midlight: solid(T.BORDER),
        QPalette.ColorRole.Mid: solid(T.BORDER_STRONG), QPalette.ColorRole.Dark: solid(T.INK_GLYPH),
        QPalette.ColorRole.Shadow: solid(T.INK_SECONDARY),
    }
    for role, hex_colour in roles.items():
        p.setColor(role, c(hex_colour))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(solid(T.INK_DISABLED)))
    return p


def _opaque(colour: str) -> str:
    """Popup and header surfaces are given as hex or 'transparent'; make them opaque for QPalette."""
    return colour if colour.startswith("#") else Tokens.CANVAS


class _Polisher(QObject):
    """Fixes what QSS cannot reach: the text inset of the line edit inside spin boxes."""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt name)
        if event.type() == QEvent.Type.Polish and isinstance(obj, QAbstractSpinBox):
            obj.lineEdit().setTextMargins(7, 0, 0, 0)
        return False


# ── Public API ──────────────────────────────────────────────────────────────

def apply_theme(app: QApplication) -> None:
    """Call once, immediately after constructing QApplication."""
    app.setStyle("Fusion")  # the only built-in style that honours QSS fully on every OS
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):  # Qt ≥ 6.8: native title bars and dialogs follow the theme
        hints.setColorScheme(Qt.ColorScheme.Dark if Tokens.DARK else Qt.ColorScheme.Light)
    family = _load_fonts()
    font = QFont(family)
    font.setPixelSize(Tokens.SIZE_BODY)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if hasattr(QFont, "Tag"):  # Qt ≥ 6.7: tabular figures so numbers align in columns
        font.setFeature(QFont.Tag("tnum"), 1)
    app.setFont(font)
    app.setPalette(_palette())
    app.setStyleSheet(build_qss())
    app.installEventFilter(_Polisher(app))  # parented to app, so it lives as long as the app


def restyle(widget: QWidget) -> None:
    """Re-evaluate QSS after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_role(widget: QWidget, role: str, **extra: str) -> QWidget:
    """Set a role (and optional extra properties such as tone=...) and restyle. Returns the widget."""
    widget.setProperty("role", role)
    for key, value in extra.items():
        widget.setProperty(key, value)
    restyle(widget)
    return widget


def set_variant(button: QWidget, variant: str) -> QWidget:
    button.setProperty("variant", variant)
    restyle(button)
    return button


def set_state(widget: QWidget, state: str | None) -> None:
    """state='error' marks an input invalid; None clears it. Pair with a caption explaining why."""
    widget.setProperty("state", state or "")
    restyle(widget)


def apply_layout(layout: QLayout, margins: int, spacing: int) -> QLayout:
    """Set both metrics explicitly; Qt's defaults (9/6 px) are off-grid."""
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(spacing)
    return layout


def build_shell(sidebar: QWidget, content: QWidget) -> QWidget:
    """Sidebar + content shell. Returns the central widget for QMainWindow.setCentralWidget."""
    shell = QFrame()
    set_role(shell, "shell")
    set_role(sidebar, "sidebar")
    sidebar.setFixedWidth(Tokens.SIDEBAR_WIDTH)  # width only; never a fixed height
    inset = QFrame()
    set_role(inset, "inset")
    inner = QHBoxLayout(inset)
    inner.setContentsMargins(0, 0, 0, 0)
    inner.addWidget(content)
    row = QHBoxLayout(shell)
    gap = Tokens.SHELL_GAP
    row.setContentsMargins(0, gap, gap, gap)
    row.setSpacing(gap)
    row.addWidget(sidebar)
    row.addWidget(inset, 1)
    return shell


def style_table(view: QAbstractItemView, *, row_height: int | None = None) -> None:
    """Apply the theme's table conventions that QSS cannot express."""
    view.setAlternatingRowColors(Tokens.TABLE_STYLE == "wash")
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setWordWrap(False)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    if isinstance(view, QTableView):
        view.setShowGrid(False)
        view.verticalHeader().setVisible(False)
        view.verticalHeader().setDefaultSectionSize(row_height or Tokens.ROW_HEIGHT)
        header = view.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setMinimumHeight(Tokens.ROW_HEIGHT)


def icon(svg: str | Path, *, size: int | None = None, stroke_px: float = 1.5, on_action: bool = False) -> QIcon:
    """Recolour a currentColor SVG icon (Lucide, Tabler, Phosphor outline) to the ink ladder.

    Normal → glyph, Active (focus/hover where Qt uses it) → secondary, Selected and
    checked (On) → primary, Disabled → disabled. Rendered at 1× and 2× for HiDPI.
    on_action=True colours the icon ON_ACTION at full strength, for primary buttons.
    """
    size = size or Tokens.ICON_SIZE
    text = Path(svg).read_text(encoding="utf-8") if Path(str(svg)).suffix == ".svg" else str(svg)
    view = re.search(r'viewBox="0 0 ([\d.]+)', text)
    if view:  # keep the visual stroke at stroke_px whatever the source grid
        width = stroke_px * float(view.group(1)) / size
        text = re.sub(r'stroke-width="[\d.]+"', f'stroke-width="{width:.3f}"', text)
    text = text.replace("currentColor", Tokens.ON_ACTION if on_action else _hex(Tokens.INK))
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    result = QIcon()
    states = (
        (QIcon.Mode.Normal, QIcon.State.Off, Tokens.INK_GLYPH),
        (QIcon.Mode.Active, QIcon.State.Off, Tokens.INK_SECONDARY),
        (QIcon.Mode.Selected, QIcon.State.Off, Tokens.INK_PRIMARY),
        (QIcon.Mode.Disabled, QIcon.State.Off, Tokens.INK_DISABLED),
        (QIcon.Mode.Normal, QIcon.State.On, Tokens.INK_PRIMARY),
        (QIcon.Mode.Active, QIcon.State.On, Tokens.INK_PRIMARY),
        (QIcon.Mode.Selected, QIcon.State.On, Tokens.INK_PRIMARY),
        (QIcon.Mode.Disabled, QIcon.State.On, Tokens.INK_DISABLED),
    )
    if on_action:
        states = tuple((m, st, 1.0 if a != Tokens.INK_DISABLED else Tokens.INK_DISABLED) for m, st, a in states)
    for mode, state, alpha in states:
        for scale in (1, 2):
            pm = QPixmap(size * scale, size * scale)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setOpacity(alpha)
            renderer.render(painter)
            painter.end()
            pm.setDevicePixelRatio(scale)
            result.addPixmap(pm, mode, state)
    return result


def apply_mpl_theme() -> None:
    """Matplotlib chrome to the ink ladder; data series keep colour. Call once at startup."""
    import matplotlib as mpl
    from cycler import cycler
    from matplotlib import font_manager

    if _FONT_DIR.is_dir():
        for ttf in _FONT_DIR.glob("*.ttf"):
            font_manager.fontManager.addfont(str(ttf))
    names = {f.name for f in font_manager.fontManager.ttflist}
    pt = 0.75  # 1 px = 0.75 pt at 96 dpi
    mpl.rcParams.update({
        "font.family": Tokens.FONT_FAMILY if Tokens.FONT_FAMILY in names else "sans-serif",
        "font.size": Tokens.SIZE_CAPTION * pt,
        "axes.titlesize": Tokens.SIZE_HEADING * pt, "axes.titleweight": 600,
        "axes.labelsize": Tokens.SIZE_CAPTION * pt,
        "figure.facecolor": Tokens.CANVAS, "axes.facecolor": Tokens.CANVAS, "savefig.facecolor": Tokens.CANVAS,
        "text.color": solid(Tokens.INK_PRIMARY), "axes.labelcolor": solid(Tokens.INK_SECONDARY),
        "axes.titlecolor": solid(Tokens.INK_PRIMARY),
        "xtick.color": solid(Tokens.BORDER_STRONG), "ytick.color": solid(Tokens.BORDER_STRONG),
        "xtick.labelcolor": solid(Tokens.INK_TERTIARY), "ytick.labelcolor": solid(Tokens.INK_TERTIARY),
        "axes.edgecolor": solid(Tokens.BORDER_STRONG), "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": solid(Tokens.BORDER), "grid.linewidth": 0.8,
        "axes.prop_cycle": cycler(color=list(Tokens.SERIES)),
        "lines.linewidth": 1.75, "legend.frameon": False,
        "legend.labelcolor": solid(Tokens.INK_SECONDARY),
    })


def apply_pg_theme() -> None:
    """pyqtgraph equivalent of apply_mpl_theme. Call before creating any plot widget."""
    import pyqtgraph as pg

    pg.setConfigOptions(background=Tokens.CANVAS, foreground=solid(Tokens.INK_SECONDARY), antialias=True)


# ── Self-check: `python theme.py` ──────────────────────────────────────────

def _self_check() -> int:
    T = Tokens
    # Opaque surfaces text can sit on at rest. Selected/pressed surfaces carry primary ink only.
    surfaces = {
        "canvas": T.CANVAS,
        "shell": T.SHELL,
        "wash": solid(T.WASH),
        "header": _opaque(T.HEADER_BG) if T.HEADER_BG.startswith("#") else T.CANVAS,
        "popup": _opaque(T.POPUP_BG),
    }
    rungs = [
        ("primary", T.INK_PRIMARY, 7.0), ("secondary", T.INK_SECONDARY, 4.5),
        ("tertiary", T.INK_TERTIARY, 4.5), ("glyph", T.INK_GLYPH, 3.0), ("disabled", T.INK_DISABLED, 0.0),
    ]
    failures = 0
    print(f"{T.NAME}: ink ladder (worst surface shown)")
    for name, alpha, need in rungs:
        worst = min(((contrast(solid(alpha, s), s), k) for k, s in surfaces.items()), key=lambda x: x[0])
        on_canvas = contrast(solid(alpha), T.CANVAS)
        ok = worst[0] >= need
        failures += not ok
        print(f"  {name:<10} α={alpha:.2f}  canvas {on_canvas:5.2f}:1  worst {worst[0]:5.2f}:1 on {worst[1]:<7}"
              f"  need {need:>4.1f}  {'ok' if ok else 'FAIL'}")
    pairs = [
        ("on action", T.ON_ACTION, T.ACTION, 4.5), ("on action hover", T.ON_ACTION, T.ACTION_HOVER, 4.5),
        ("on error fill", T.ON_ERROR, T.ERROR_FILL, 4.5),
        ("success text", T.SUCCESS, T.CANVAS, 4.5), ("warning text", T.WARNING, T.CANVAS, 4.5),
        ("error text", T.ERROR, T.CANVAS, 4.5), ("link", T.LINK, T.CANVAS, 4.5),
        ("focus ring", solid(T.INK_GLYPH), T.CANVAS, 3.0), ("action vs canvas", T.ACTION, T.CANVAS, 3.0),
    ] + [(f"series {i}", s, T.CANVAS, 3.0) for i, s in enumerate(T.SERIES)]
    print(f"{T.NAME}: pairs")
    for name, fg, bg, need in pairs:
        ratio = contrast(fg, bg)
        ok = ratio >= need
        failures += not ok
        print(f"  {name:<18} {fg} on {bg}  {ratio:5.2f}:1  need {need:.1f}  {'ok' if ok else 'FAIL'}")
    grid = [T.WINDOW_MARGIN, T.GROUP_MARGIN, T.ROW_SPACING, T.GROUP_SPACING, T.SECTION_SPACING,
            T.CONTROL_HEIGHT, T.COMPACT_HEIGHT, T.ROW_HEIGHT, T.SHELL_GAP, T.SIDEBAR_WIDTH]
    off = [v for v in grid if v % 4]
    failures += bool(off)
    print(f"{T.NAME}: grid {'ok' if not off else f'FAIL off-grid {off}'}")
    print("PASS" if not failures else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_self_check())
