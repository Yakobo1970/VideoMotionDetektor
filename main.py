import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.main_window import APP_DATA_DIR, DB_PATH, MainWindow
from gui.theme import apply_theme
from engine.db import Database
from paths import ASSETS_DIR

ICON_PATH = ASSETS_DIR / "icon.ico"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Video Motion Detektor")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    prefs_db = Database(DB_PATH)
    apply_theme(app, prefs_db.get_setting("theme", "dark"))
    prefs_db.close()

    window = MainWindow()
    if ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(ICON_PATH)))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
