from pathlib import Path

from PySide6.QtCore import QThread, Signal

from engine.db import Database
from engine.motion_analysis import (
    AnalysisConfig,
    analyze_video,
    detector_available,
    probe_duration_seconds,
)

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".h264", ".ts"}


def find_video_files(folder: Path, recursive: bool = True) -> list[Path]:
    it = folder.rglob("*") if recursive else folder.iterdir()
    return sorted(
        p for p in it if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def _scan_and_stub(db: Database, folder: Path) -> list[tuple[Path, int]]:
    """Findet alle Videodateien unterhalb von `folder` (inkl. Unterordner),
    entfernt DB-Eintraege zu inzwischen geloeschten Dateien und legt fuer
    neue/bereits bekannte Dateien einen DB-Eintrag an. Reine Datei-Metadaten-
    Operation (kein Video-Decoding) -- schnell genug fuer eine sofortige
    Anzeige direkt nach der Ordnerwahl, noch vor der eigentlichen Analyse."""
    files = find_video_files(folder, recursive=True)
    db.remove_missing(str(folder), {str(p) for p in files})
    return [
        (p, db.upsert_video_stub(p, folder, duration_probe=probe_duration_seconds))
        for p in files
    ]


class FolderScanWorker(QThread):
    """Scannt einen Ordner (inkl. Unterordner) auf Videodateien und legt
    DB-Eintraege an, damit die Liste sofort nach der Ordnerwahl erscheint --
    unabhaengig vom eigentlichen (deutlich langsameren) Analyse-Lauf."""

    finished_scan = Signal(int)  # Anzahl gefundener Dateien

    def __init__(self, db_path: Path, folder: Path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.folder = folder

    def run(self):
        db = Database(self.db_path)
        found = _scan_and_stub(db, self.folder)
        db.close()
        self.finished_scan.emit(len(found))


class AnalysisWorker(QThread):
    """Analysiert alle (neuen/geaenderten) Videos eines Ordners im Hintergrund,
    damit die GUI waehrend eines groesseren Batches nicht einfriert."""

    progress = Signal(int, int, str)  # erledigt, gesamt, aktueller Dateiname
    video_started = Signal(int)  # video_id, das gerade analysiert wird
    video_done = Signal(int)  # video_id, dessen Analyse-Ergebnis in der DB steht
    detector_status = Signal(bool)  # ob YOLO-Objekterkennung verfuegbar ist
    finished_all = Signal()

    def __init__(self, db_path: Path, folder: Path, config: AnalysisConfig, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.folder = folder
        self.config = config
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        if self.config.use_object_detector:
            self.detector_status.emit(detector_available())
        else:
            self.detector_status.emit(False)

        # Eigene DB-Verbindung, da SQLite-Connections nicht threaduebergreifend sind.
        db = Database(self.db_path)
        ids = _scan_and_stub(db, self.folder)
        to_analyze = []
        for p, vid in ids:
            row = db.conn.execute(
                "SELECT label FROM videos WHERE id = ?", (vid,)
            ).fetchone()
            if row["label"] == "unanalyzed":
                to_analyze.append((p, vid))

        total = len(to_analyze)
        for done, (path, video_id) in enumerate(to_analyze, start=1):
            if self._stop_requested:
                break
            self.progress.emit(done - 1, total, path.name)
            self.video_started.emit(video_id)
            try:
                result = analyze_video(path, self.config)
            except Exception as exc:
                result = None
                self.progress.emit(done, total, f"{path.name} (Fehler: {exc})")
            if result is not None:
                db.save_analysis(
                    video_id,
                    result.score,
                    result.label,
                    result.detected_objects,
                    result.thumbnail_jpeg,
                    auto_mark=result.auto_mark,
                )
            # Auch bei einem Fehler emittieren, damit die GUI die Zeile aus
            # dem "wird gerade analysiert"-Zustand wieder herausnimmt.
            self.video_done.emit(video_id)
            self.progress.emit(done, total, path.name)

        db.close()
        self.finished_all.emit()
