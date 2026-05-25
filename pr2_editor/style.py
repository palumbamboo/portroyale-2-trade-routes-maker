"""Centralised palette + Qt stylesheet for the editor.

Light theme by default. The stylesheet only targets explicitly-named selectors
or objectNames; it does not blanket-restyle every widget so the application
still looks at home in the host OS.
"""
from __future__ import annotations

# Semantic colors
ACCENT = "#0e6cc4"
ACCENT_HOVER = "#0a559a"
ACCENT_PRESSED = "#084579"
ACCENT_FG = "white"

NEUTRAL_BG = "#f7f7f8"
NEUTRAL_BORDER = "#d8d8dc"
TEXT_PRIMARY = "#1f1f23"
TEXT_SECONDARY = "#6b6b73"

# Row tints for excluded states
TINT_ROUTE_EXCLUDED = "#fde2e2"   # light pink
TINT_STOP_EXCLUDED = "#eeeeee"    # light gray

# Indicator text colors (used in code, not in stylesheet)
COLOR_ROUTE_EXCLUDED_TEXT = "#b13838"
COLOR_STOP_EXCLUDED_TEXT = "#777777"
COLOR_PRODUCED_TEXT = "#15803d"


APP_STYLESHEET = f"""
/* Section header card on top of each goods section */
#sectionHeader {{
    background-color: {NEUTRAL_BG};
    border: 1px solid {NEUTRAL_BORDER};
    border-radius: 4px;
}}

/* Stop info card at the top of the right panel: noticeable contrast against the window background */
QFrame#stopInfoCard {{
    background-color: #e6edf8;
    border: 1px solid #b8c6dd;
    border-radius: 6px;
    padding: 6px 10px;
}}
QFrame#stopInfoCard QLabel {{
    background-color: transparent;
}}

/* Toolbar row that hosts filter + selection bulk controls */
QFrame#tableToolbar {{
    background-color: transparent;
    border: none;
}}

/* Inline bulk-action popover inside the toolbar */
QFrame#bulkInline {{
    background-color: #eef5ff;
    border: 1px solid #c7ddf5;
    border-radius: 4px;
}}

/* Accent (primary action) button: opt-in via setProperty('accent', True) */
QPushButton[accent="true"], QToolButton[accent="true"] {{
    background-color: {ACCENT};
    color: {ACCENT_FG};
    border: 1px solid {ACCENT_HOVER};
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover, QToolButton[accent="true"]:hover {{
    background-color: {ACCENT_HOVER};
}}
QPushButton[accent="true"]:pressed, QToolButton[accent="true"]:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QPushButton[accent="true"]:disabled, QToolButton[accent="true"]:disabled {{
    background-color: #b9c8d8;
    color: #f0f0f0;
    border-color: #a8b8c8;
}}

/* Secondary "ghost" button: opt-in via setProperty('ghost', True) */
QPushButton[ghost="true"], QToolButton[ghost="true"] {{
    background-color: transparent;
    color: {ACCENT};
    border: 1px solid {NEUTRAL_BORDER};
    border-radius: 4px;
    padding: 4px 10px;
}}
QPushButton[ghost="true"]:hover, QToolButton[ghost="true"]:hover {{
    background-color: #eef5ff;
    border-color: {ACCENT};
}}
"""


def apply_class_property(widget, **flags) -> None:
    """Set boolean properties used by the stylesheet selectors and refresh the style."""
    for key, value in flags.items():
        widget.setProperty(key, value)
    # Force Qt to re-evaluate the dynamic property in the stylesheet
    widget.style().unpolish(widget)
    widget.style().polish(widget)
