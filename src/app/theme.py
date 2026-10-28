"""Colours and the style sheet of the converter window (dark, in the style of RunSpriteRun)."""
BG = "#1e1e22"
PANEL = "#2a2a30"
LINE = "#3a3c46"
TEXT = "#e6e6eb"
DIM = "#9096a8"
ACCENT = "#508cdc"
BUTTON = "#424652"
VIEW = "#15151a"
ORANGE = "#ffa03c"

STYLE = f"""
QMainWindow, QWidget#root {{ background: {BG}; color: {TEXT}; }}
QWidget {{ color: {TEXT}; font-size: 12px; }}
QMenuBar {{ background: #26262c; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {ACCENT}; }}
QMenu {{ background: #26262c; border: 1px solid {LINE}; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 6px; }}
QLabel {{ background: transparent; }}
QFrame#selbox {{ background: #2f3445; border: 1px solid {ACCENT}; border-radius: 8px; }}
QLabel#folder {{ background: #1b1c21; border: 1px solid #5a5f72; border-radius: 3px; padding: 3px 6px; }}
QLabel#head {{ font-size: 13px; font-weight: 600; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#section {{ color: {DIM}; font-size: 10px; letter-spacing: 1px; padding-top: 6px; }}
QLabel#orange {{ color: {ORANGE}; }}
QPushButton {{ background: {BUTTON}; border: 1px solid #7a8094; border-radius: 4px; padding: 3px 10px; }}
QPushButton:hover {{ border-color: #b4bdd6; }}
QPushButton:checked {{ background: #b4bdd6; color: #14151a; border-color: #ffffff; }}
QPushButton:disabled {{ color: #6a6e7c; border-color: #4a4e5c; }}
QPushButton#primary {{ background: {ACCENT}; border-color: #9cc2f5; color: white; font-size: 13px; padding: 7px 18px; }}
QSpinBox, QComboBox {{ background: #1b1c21; border: 1px solid #5a5f72; border-radius: 3px; padding: 2px 5px; }}
QComboBox QAbstractItemView {{ background: #26262c; selection-background-color: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #3d4050; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; margin: -6px 0; background: #aab2c8; border-radius: 3px; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QScrollArea {{ background: {VIEW}; border: 1px solid {LINE}; }}
QTabBar::tab {{ background: #33343d; color: {DIM}; border: 1px solid {LINE}; border-bottom: none;
    border-radius: 5px 5px 0 0; padding: 5px 12px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #3d4a66; color: white; border-color: {ACCENT}; }}
QTabBar QToolButton {{ background: {BUTTON}; border: 1px solid #7a8094; }}
QToolTip {{ background: #26262c; color: {TEXT}; border: 1px solid {LINE}; }}
QMessageBox, QDialog {{ background: {PANEL}; color: {TEXT}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
QMessageBox QPushButton {{ min-width: 72px; padding: 4px 12px; }}
"""
