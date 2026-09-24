DARK_QSS = """
QWidget { background-color: #1e1e1e; color: #e8e8e8; }
QMainWindow, QDialog { background-color: #1e1e1e; }
QPushButton { background-color: #333; color: #e8e8e8; border: 1px solid #555; padding: 4px 10px; border-radius: 3px; }
QPushButton:hover { background-color: #444; }
QPushButton:disabled { color: #777; background-color: #2a2a2a; }
QListWidget, QLineEdit, QSpinBox, QComboBox, QTableWidget { background-color: #262626; color: #e8e8e8; border: 1px solid #444; }
QListWidget::item:selected, QTableWidget::item:selected { background-color: #3a5a8a; }
QHeaderView::section { background-color: #2a2a2a; color: #e8e8e8; border: 1px solid #444; padding: 4px; }
QMenuBar, QMenu { background-color: #262626; color: #e8e8e8; }
QMenu::item:selected { background-color: #3a5a8a; }
QStatusBar { background-color: #1e1e1e; color: #ccc; }
QProgressBar { background-color: #262626; color: #e8e8e8; border: 1px solid #444; text-align: center; }
QProgressBar::chunk { background-color: #4a7fd6; }
QScrollArea { background-color: #1e1e1e; }
QFrame { background-color: #232323; }
QLabel { color: #e8e8e8; }
QSlider::groove:horizontal { background: #444; height: 4px; }
QSlider::handle:horizontal { background: #4a7fd6; width: 12px; margin: -5px 0; border-radius: 6px; }
"""

LIGHT_QSS = """
QWidget { background-color: #f4f4f4; color: #202020; }
QMainWindow, QDialog { background-color: #f4f4f4; }
QPushButton { background-color: #e6e6e6; color: #202020; border: 1px solid #bbb; padding: 4px 10px; border-radius: 3px; }
QPushButton:hover { background-color: #dcdcdc; }
QPushButton:disabled { color: #999; background-color: #eee; }
QListWidget, QLineEdit, QSpinBox, QComboBox, QTableWidget { background-color: #ffffff; color: #202020; border: 1px solid #ccc; }
QListWidget::item:selected, QTableWidget::item:selected { background-color: #cfe0ff; }
QHeaderView::section { background-color: #eaeaea; color: #202020; border: 1px solid #ccc; padding: 4px; }
QMenuBar, QMenu { background-color: #ffffff; color: #202020; }
QMenu::item:selected { background-color: #cfe0ff; }
QStatusBar { background-color: #f4f4f4; color: #333; }
QProgressBar { background-color: #ffffff; color: #202020; border: 1px solid #ccc; text-align: center; }
QProgressBar::chunk { background-color: #4a7fd6; }
QScrollArea { background-color: #f4f4f4; }
QFrame { background-color: #ffffff; }
QLabel { color: #202020; }
QSlider::groove:horizontal { background: #ccc; height: 4px; }
QSlider::handle:horizontal { background: #4a7fd6; width: 12px; margin: -5px 0; border-radius: 6px; }
"""

THEMES = {"dark": DARK_QSS, "light": LIGHT_QSS}

# Zeilenfarben je nach Erkennungsergebnis -- bewusst UNABHAENGIG davon, ob
# eine Zeile zur Aktion markiert ist (das zeigt nur die Checkbox in Spalte
# "M"). Rot = sicher keine Bewegung, Gruen = Objekt (Person/Tier/Fahrzeug)
# erkannt. Der unsichere Mittelbereich (Bewegung, aber kein Objekt bestaetigt)
# bleibt bewusst ungefaerbt.
NO_MOTION_ROW_COLORS = {"dark": "#5c3333", "light": "#f7cccc"}
REAL_ROW_COLORS = {"dark": "#2f4a33", "light": "#dcf3df"}
# Zeile, die die Analyse gerade untersucht (nur waehrend eines laufenden Batches).
PROCESSING_ROW_COLORS = {"dark": "#5c4a1f", "light": "#fbe8b0"}


def apply_theme(app, theme_name: str):
    app.setStyleSheet(THEMES.get(theme_name, DARK_QSS))
