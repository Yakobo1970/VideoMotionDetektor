import os
import sys

# Im Fenstermodus (PyInstaller, console=False) sind stdout/stderr None --
# Bibliotheken wie ultralytics/tqdm wuerden beim Schreiben abstuerzen.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.main_window import APP_DATA_DIR, DB_PATH, MainWindow
from gui.theme import apply_theme
from engine.db import Database
from paths import ASSETS_DIR

ICON_PATH = ASSETS_DIR / "icon.ico"


def selftest(video_path: str, out_path: str):
    """Diagnose fuer die gebaute .exe: analysiert ein Video und schreibt das
    Ergebnis in eine Datei (die Fenster-.exe hat keine Konsole)."""
    from pathlib import Path

    from engine.motion_analysis import (
        AnalysisConfig,
        _detector_cache,
        analyze_video,
        detector_available,
    )

    try:
        result = analyze_video(Path(video_path), AnalysisConfig())
        text = (
            f"detector={detector_available()} label={result.label} "
            f"score={result.score:.1f} objects={result.detected_objects} "
            f"details={result.details} detector_error={_detector_cache.get('last_error')}"
        )
    except Exception as exc:
        text = f"FEHLER: {exc!r}"
    Path(out_path).write_text(text, encoding="utf-8")


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2], sys.argv[3])
        return

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
