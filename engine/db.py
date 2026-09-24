import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    folder TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    analyzed_at REAL,
    score REAL,
    label TEXT NOT NULL DEFAULT 'unanalyzed',
    detected_objects TEXT NOT NULL DEFAULT '',
    thumbnail BLOB,
    marked INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_videos_folder ON videos(folder);
CREATE INDEX IF NOT EXISTS idx_videos_marked ON videos(marked);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()

    def _migrate(self):
        # Neue Spalten NIE direkt ins statische SCHEMA aufnehmen: bei einer
        # bereits bestehenden DB ist CREATE TABLE IF NOT EXISTS ein No-Op,
        # die Spalte muss per ALTER TABLE nachgeruestet werden.
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(videos)")}
        if "duration" not in cols:
            self.conn.execute("ALTER TABLE videos ADD COLUMN duration REAL")
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -- Settings -----------------------------------------------------

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    # -- Videos ---------------------------------------------------------

    def upsert_video_stub(self, path: Path, root_folder: Path, duration_probe=None) -> int:
        """Legt einen Eintrag fuer eine gefundene Videodatei an (falls noch
        nicht vorhanden) oder gibt die vorhandene ID zurueck. `root_folder`
        ist der vom Nutzer gewaehlte (oberste) Ordner -- nicht zwingend der
        direkte Elternordner der Datei, da Unterordner rekursiv einbezogen
        werden. Bei geaenderter Dateigroesse/mtime wird der Analysestatus
        zurueckgesetzt, damit veraenderte Dateien neu analysiert werden;
        die Ordner-Zuordnung wird immer aktualisiert, damit eine Datei nach
        Auswahl eines anderen (z.B. uebergeordneten) Ordners dort auftaucht.

        `duration_probe`, falls angegeben, wird NUR fuer neue/geaenderte
        Dateien aufgerufen (teurer als ein reiner Datei-Stat-Aufruf, da die
        Videodatei kurz geoeffnet werden muss) -- unveraenderte Dateien
        behalten ihre bereits bekannte Laufzeit. Fehlt sie noch (z.B. bei
        Eintraegen aus einer Datenbank von vor Einfuehrung dieser Spalte),
        wird sie beim naechsten Scan einmalig nachgetragen."""
        stat = path.stat()
        folder = str(root_folder)
        row = self.conn.execute(
            "SELECT id, mtime, size, duration FROM videos WHERE path = ?", (str(path),)
        ).fetchone()
        if row is None:
            duration = duration_probe(path) if duration_probe else None
            cur = self.conn.execute(
                "INSERT INTO videos(path, filename, folder, mtime, size, duration) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(path), path.name, folder, stat.st_mtime, stat.st_size, duration),
            )
            self.conn.commit()
            return cur.lastrowid
        if row["mtime"] != stat.st_mtime or row["size"] != stat.st_size:
            duration = duration_probe(path) if duration_probe else None
            self.conn.execute(
                "UPDATE videos SET folder = ?, mtime = ?, size = ?, duration = ?, "
                "analyzed_at = NULL, score = NULL, label = 'unanalyzed', "
                "detected_objects = '', thumbnail = NULL, marked = 0 WHERE id = ?",
                (folder, stat.st_mtime, stat.st_size, duration, row["id"]),
            )
        elif row["duration"] is None and duration_probe:
            duration = duration_probe(path)
            self.conn.execute(
                "UPDATE videos SET folder = ?, duration = ? WHERE id = ?",
                (folder, duration, row["id"]),
            )
        else:
            self.conn.execute(
                "UPDATE videos SET folder = ? WHERE id = ?", (folder, row["id"])
            )
        self.conn.commit()
        return row["id"]

    def remove_missing(self, folder: str, existing_paths: set):
        rows = self.conn.execute(
            "SELECT id, path FROM videos WHERE folder = ?", (folder,)
        ).fetchall()
        stale_ids = [r["id"] for r in rows if r["path"] not in existing_paths]
        if stale_ids:
            self.conn.executemany(
                "DELETE FROM videos WHERE id = ?", [(i,) for i in stale_ids]
            )
            self.conn.commit()

    def save_analysis(
        self,
        video_id: int,
        score: float,
        label: str,
        detected_objects: list,
        thumbnail: bytes | None,
        auto_mark: bool,
    ):
        self.conn.execute(
            "UPDATE videos SET analyzed_at = ?, score = ?, label = ?, "
            "detected_objects = ?, thumbnail = COALESCE(?, thumbnail), marked = ? "
            "WHERE id = ?",
            (
                time.time(),
                score,
                label,
                ",".join(detected_objects),
                thumbnail,
                1 if auto_mark else 0,
                video_id,
            ),
        )
        self.conn.commit()

    def set_marked(self, video_id: int, marked: bool):
        self.conn.execute(
            "UPDATE videos SET marked = ? WHERE id = ?", (1 if marked else 0, video_id)
        )
        self.conn.commit()

    def invert_marks(self, folder: str):
        self.conn.execute(
            "UPDATE videos SET marked = 1 - marked WHERE folder = ?", (folder,)
        )
        self.conn.commit()

    def mark_all(self, folder: str, marked: bool):
        self.conn.execute(
            "UPDATE videos SET marked = ? WHERE folder = ?", (1 if marked else 0, folder)
        )
        self.conn.commit()

    def videos_for_folder(self, folder: str):
        return self.conn.execute(
            "SELECT * FROM videos WHERE folder = ? ORDER BY filename", (folder,)
        ).fetchall()

    def delete_videos(self, video_ids: list):
        self.conn.executemany(
            "DELETE FROM videos WHERE id = ?", [(i,) for i in video_ids]
        )
        self.conn.commit()
