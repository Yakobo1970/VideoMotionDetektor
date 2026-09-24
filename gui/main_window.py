import shutil
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from engine.db import Database
from engine.motion_analysis import AnalysisConfig
from engine.scanner import AnalysisWorker, FolderScanWorker
from gui.theme import NO_MOTION_ROW_COLORS, PROCESSING_ROW_COLORS, REAL_ROW_COLORS
from gui.widgets.about_dialog import AboutDialog
from gui.widgets.preview_player import PreviewPlayer
from version import VERSION

APP_DATA_DIR = Path.home() / "AppData" / "Local" / "VideoMotionDetektor"
DB_PATH = APP_DATA_DIR / "videomotiondetektor.db"

COL_MARKED = 0
COL_THUMB = 1
COL_FILENAME = 2
COL_SIZE = 3
COL_DURATION = 4
COL_LABEL = 5
COL_SCORE = 6
COL_OBJECTS = 7
COLUMN_COUNT = 8

# Zusaetzliche Rolle, unter der wir den numerischen Sortierschluessel eines
# Zellinhalts ablegen -- getrennt von der angezeigten (formatierten) Zelle,
# siehe NumericItem weiter unten.
SORT_VALUE_ROLE = Qt.UserRole + 1
# Rolle, unter der die video_id einer Zeile am "Markiert"-Item haengt, damit
# eine Zeile auch nach dem Sortieren zuverlaessig ihrer DB-ID zugeordnet
# werden kann (der reine Zeilenindex ist nach einer Sortierung nicht mehr
# stabil).
VIDEO_ID_ROLE = Qt.UserRole + 2

LABEL_TEXT = {
    "unanalyzed": "Ungeprüft",
    "real": "Echte Bewegung",
    "false_alarm": "Fehlalarm-Verdacht",
    "no_motion": "Keine Bewegung",
}


class NumericItem(QTableWidgetItem):
    """QTableWidgetItem, das nach einem versteckten numerischen Wert
    (SORT_VALUE_ROLE) sortiert statt nach dem angezeigten, formatierten
    Text (z.B. "12,4 MB" oder "93")."""

    def __lt__(self, other):
        a = self.data(SORT_VALUE_ROLE)
        b = other.data(SORT_VALUE_ROLE) if isinstance(other, QTableWidgetItem) else None
        if a is None:
            a = float("-inf")
        if b is None:
            b = float("-inf")
        return a < b


def _format_size(num_bytes) -> str:
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}".replace(".", ",")
        size /= 1024
    return f"{size:.1f} GB".replace(".", ",")


def _format_duration(seconds) -> str:
    if seconds is None:
        return ""
    return str(int(round(seconds)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Video Motion Detektor {VERSION} — Bewegungsfilter für Überwachungsaufnahmen")
        self.resize(1300, 720)

        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = Database(DB_PATH)

        self.current_folder: Path | None = None
        self.worker: AnalysisWorker | None = None
        self.scan_worker: FolderScanWorker | None = None
        self._updating_table = False
        self._stopped_early = False
        self._current_preview_path: str | None = None

        self._build_ui()
        QApplication.instance().installEventFilter(self)

        last_folder = self.db.get_setting("last_folder", "")
        if last_folder and Path(last_folder).is_dir():
            self.folder_edit.setText(last_folder)
            self._load_folder(Path(last_folder))

    # -- UI-Aufbau -----------------------------------------------------

    def _build_ui(self):
        help_menu = self.menuBar().addMenu("Hilfe")
        about_action = help_menu.addAction("Über Video Motion Detektor…")
        about_action.triggered.connect(self._show_about_dialog)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(self)
        self.folder_edit.setPlaceholderText("Ordner mit Überwachungsaufnahmen wählen…")
        self.folder_edit.setReadOnly(True)
        choose_btn = QPushButton("Ordner wählen…", self)
        choose_btn.clicked.connect(self._choose_folder)
        self.analyze_btn = QPushButton("Analysieren", self)
        self.analyze_btn.clicked.connect(self._on_analyze_clicked)
        self.analyze_btn.setEnabled(False)
        self.stop_btn = QPushButton("Stop", self)
        self.stop_btn.clicked.connect(self._stop_analysis)
        self.stop_btn.setEnabled(False)
        folder_row.addWidget(QLabel("Ordner:"))
        folder_row.addWidget(self.folder_edit, stretch=1)
        folder_row.addWidget(choose_btn)
        folder_row.addWidget(self.analyze_btn)
        folder_row.addWidget(self.stop_btn)
        root.addLayout(folder_row)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        scroll_row = QHBoxLayout()
        self.auto_scroll_checkbox = QCheckBox("Automatisch mit Analyse scrollen", self)
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.setToolTip(
            "Bei aktivem Häkchen springt die Liste während der Analyse automatisch\n"
            "zur gerade untersuchten Zeile (gelb markiert). Deaktivieren, um währenddessen\n"
            "ungestört andere Clips anzusehen und zu markieren — die Analyse läuft weiter."
        )
        scroll_row.addWidget(self.auto_scroll_checkbox)
        scroll_row.addStretch(1)
        shortcuts_hint = QLabel(
            "Tastenkürzel: Leertaste = Markieren  ·  ↑/↓ = voriges/nächstes Video  ·  ←/→ = Tempo", self
        )
        shortcuts_hint.setStyleSheet("color: #888;")
        scroll_row.addWidget(shortcuts_hint)
        root.addLayout(scroll_row)

        splitter = QSplitter(Qt.Horizontal, self)
        root.addWidget(splitter, stretch=1)

        self.table = QTableWidget(0, COLUMN_COUNT, self)
        self.table.setHorizontalHeaderLabels(
            ["M", "Vorschau", "Datei", "Größe", "Sek.", "Klassifikation", "Konfidenz", "Erkannt"]
        )
        self.table.horizontalHeaderItem(COL_MARKED).setToolTip(
            "Markiert -- zur Aktion vorgemerkt (siehe Buttons unten:\n"
            "Verschieben/Kopieren/Löschen)."
        )
        self.table.horizontalHeaderItem(COL_LABEL).setToolTip(
            "Automatische Einschätzung. Zeilenfarbe zeigt nur DIESE Einschätzung an\n"
            "(grün = Objekt erkannt, rot = keine Bewegung gefunden) — unabhängig davon,\n"
            "ob die Zeile in Spalte „M“ markiert ist.\n\n"
            "„Echte Bewegung“ = ein Objekt (Person/Tier/Fahrzeug) wurde erkannt und bestätigt.\n"
            "„Fehlalarm-Verdacht“ = Bewegung erkannt, aber kein Objekt bestätigt — das reicht von\n"
            "  „vermutlich nur ein kurzer Reflex“ bis „echte Bewegung, aber vom Modell nicht\n"
            "  erkannt“, siehe Konfidenz. Nur der eindeutigste Fall (grossflächiger, diffuser\n"
            "  Helligkeitswechsel, Konfidenz 20) wird automatisch markiert — alles andere bleibt\n"
            "  zur manuellen Kontrolle unmarkiert, auch „Keine Bewegung“."
        )
        self.table.horizontalHeaderItem(COL_SCORE).setToolTip(
            "Kein Bewegungsanteil in %, sondern wie sicher die Software sich bei ihrer\n"
            "Einschätzung ist (0-100):\n"
            "  5 = gar keine Bewegung gefunden (evtl. aber nur ein sehr kurzes/schwaches\n"
            "      Ereignis verpasst, z.B. ein sehr schnelles Tier — deshalb nicht automatisch\n"
            "      markiert)\n"
            "  15 = nur 1-2 Frames Bewegung sichtbar (Reflex ODER sehr schnelles Tier —\n"
            "       beides nicht zuverlässig unterscheidbar, deshalb nicht automatisch markiert)\n"
            "  20 = grossflächiger, diffuser Helligkeitswechsel — einzige automatisch\n"
            "       markierte Kategorie\n"
            "  35-45 = länger anhaltende, kompakte Bewegung, aber kein Objekt erkannt/bestätigt\n"
            "  60-100 = Objekt erkannt und bestätigt (siehe Spalte „Erkannt“)"
        )
        self.table.horizontalHeaderItem(COL_OBJECTS).setToolTip(
            "Von der Objekterkennung (YOLOv8n) erkannte und bestätigte Klassen,\n"
            "z.B. person, cat, dog, car. Leer heisst: kein bekanntes Objekt gefunden\n"
            "(bedeutet nicht zwingend, dass es keine echte Bewegung war)."
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSortingEnabled(True)
        # Qt sortiert bei setSortingEnabled(True) sonst sofort (und bei jedem
        # spaeteren Wiedereinschalten) nach Spalte 0 aufsteigend, auch wenn
        # nie manuell sortiert wurde -- das wuerde jede Markierungs-Aenderung
        # (Spalte 0!) unbeabsichtigt zu einer Neusortierung samt Sprung der
        # aktuellen Auswahl fuehren. Erst explizit "keine Sortierung aktiv"
        # setzen, bevor ueberhaupt Zeilen eingefuegt werden.
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.horizontalHeader().setSectionResizeMode(COL_FILENAME, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemChanged.connect(self._on_table_item_changed)
        splitter.addWidget(self.table)

        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        self.preview = PreviewPlayer(right)
        self.preview.request_next.connect(lambda: self._select_relative_row(1))
        right_layout.addWidget(self.preview)

        self.info_label = QLabel("Kein Clip ausgewählt.", right)
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.info_label)

        self.mark_checkbox = QCheckBox("Diesen Clip markieren (für Verschieben/Kopieren/Löschen unten)", right)
        self.mark_checkbox.setToolTip(
            "Identisch mit dem Häkchen in der Tabellenspalte „M“ links —\n"
            "hier nur bequemer erreichbar, während der Clip in der Vorschau läuft.\n"
            "Die Buttons „Markierte verschieben/kopieren/löschen“ unten wirken auf\n"
            "alle so markierten Clips, nicht nur auf den aktuell ausgewählten."
        )
        self.mark_checkbox.stateChanged.connect(self._on_mark_checkbox_changed)
        self.mark_checkbox.setEnabled(False)
        right_layout.addWidget(self.mark_checkbox)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setSizes([860, 440])

        actions_row = QHBoxLayout()
        mark_all_btn = QPushButton("Alle Fehlalarm-Kandidaten markieren", self)
        mark_all_btn.clicked.connect(self._mark_all_false_alarms)
        mark_recognized_btn = QPushButton("Alle erkannten Kandidaten markieren", self)
        mark_recognized_btn.setToolTip(
            "Markiert alle Clips, in denen ein Objekt (Person/Tier/Fahrzeug) bestätigt\n"
            "erkannt wurde -- z.B. um sie gesammelt in einen anderen Ordner zu verschieben."
        )
        mark_recognized_btn.clicked.connect(self._mark_all_recognized)
        invert_btn = QPushButton("Markierung umkehren", self)
        invert_btn.clicked.connect(self._invert_marks)
        unmark_all_btn = QPushButton("Alle demarkieren", self)
        unmark_all_btn.clicked.connect(self._unmark_all)
        actions_row.addWidget(mark_all_btn)
        actions_row.addWidget(mark_recognized_btn)
        actions_row.addWidget(invert_btn)
        actions_row.addWidget(unmark_all_btn)
        actions_row.addStretch(1)
        root.addLayout(actions_row)

        file_actions_row = QHBoxLayout()
        move_btn = QPushButton("Markierte verschieben…", self)
        move_btn.clicked.connect(self._move_marked)
        copy_btn = QPushButton("Markierte kopieren…", self)
        copy_btn.clicked.connect(self._copy_marked)
        delete_btn = QPushButton("Markierte in Papierkorb löschen", self)
        delete_btn.clicked.connect(self._delete_marked)
        file_actions_row.addWidget(move_btn)
        file_actions_row.addWidget(copy_btn)
        file_actions_row.addWidget(delete_btn)
        file_actions_row.addStretch(1)
        root.addLayout(file_actions_row)

        summary_row = QHBoxLayout()
        self.marked_summary_label = QLabel("", self)
        summary_row.addWidget(self.marked_summary_label)
        summary_row.addStretch(1)
        root.addLayout(summary_row)

        bottom_row = QHBoxLayout()
        self.status_label = QLabel("", self)
        self.detector_label = QLabel("", self)
        bottom_row.addWidget(self.status_label, stretch=1)
        bottom_row.addWidget(self.detector_label)
        root.addLayout(bottom_row)

    def _show_about_dialog(self):
        dialog = AboutDialog(self)
        dialog.exec()

    @contextmanager
    def _no_sort(self):
        """Deaktiviert die Tabellensortierung waehrend mehrerer Zellaenderungen
        an EINER Zeile -- sonst koennte ein automatisches Neusortieren (Qt
        sortiert bei aktivierter Sortierung nach jeder Datenaenderung neu)
        mitten in der Aktualisierung den Zeilenindex verschieben, sodass
        nachfolgende Zellen der falschen (nun dort befindlichen) Zeile
        zugewiesen wuerden. Verschachtelbar: nur der aeusserste Aufruf
        schaltet die Sortierung tatsaechlich wieder ein."""
        was_enabled = self.table.isSortingEnabled()
        if was_enabled:
            self.table.setSortingEnabled(False)
        try:
            yield
        finally:
            if was_enabled:
                self.table.setSortingEnabled(True)

    # -- Ordnerwahl & Laden ----------------------------------------------

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Ordner mit Aufnahmen wählen")
        if not folder:
            return
        self.folder_edit.setText(folder)
        self.db.set_setting("last_folder", folder)
        self._load_folder(Path(folder))

    def _load_folder(self, folder: Path):
        self.current_folder = folder
        self._stopped_early = False
        self.analyze_btn.setText("Analysieren")
        self._refresh_table()
        self._start_folder_scan()

    def _start_folder_scan(self):
        if self.current_folder is None or self.scan_worker is not None:
            return
        self.analyze_btn.setEnabled(False)
        self.status_label.setText("Scanne Ordner (inkl. Unterordner)…")
        self.scan_worker = FolderScanWorker(DB_PATH, self.current_folder, self)
        self.scan_worker.finished_scan.connect(self._on_scan_finished)
        self.scan_worker.start()

    def _on_scan_finished(self, found: int):
        self.scan_worker = None
        self.analyze_btn.setEnabled(True)
        self._refresh_table()

    def _refresh_table(self):
        if self.current_folder is None:
            return
        rows = self.db.videos_for_folder(str(self.current_folder))
        with self._no_sort():
            self._updating_table = True
            self.table.setRowCount(0)
            for row in rows:
                self._append_row(row)
            self._updating_table = False
        self.status_label.setText(f"{len(rows)} Aufnahme(n) im Ordner.")
        self._update_marked_summary()

    def _append_row(self, row):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self._fill_row(r, row)

    def _fill_row(self, r: int, row):
        """Setzt/aktualisiert alle Zellen einer Zeile aus einem DB-Datensatz --
        gemeinsam genutzt beim initialen Aufbau UND beim Live-Update waehrend
        einer laufenden Analyse (dann wird NICHT die ganze Tabelle neu
        aufgebaut, damit Scrollposition/Auswahl des Nutzers erhalten bleiben)."""
        with self._no_sort():

            def cell(col, numeric=False) -> QTableWidgetItem:
                item = self.table.item(r, col)
                if item is None:
                    item = NumericItem() if numeric else QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(r, col, item)
                return item

            marked_item = cell(COL_MARKED, numeric=True)
            marked_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            marked_item.setCheckState(Qt.Checked if row["marked"] else Qt.Unchecked)
            marked_item.setData(SORT_VALUE_ROLE, 1 if row["marked"] else 0)
            marked_item.setData(VIDEO_ID_ROLE, row["id"])

            thumb_item = cell(COL_THUMB)
            if row["thumbnail"]:
                pixmap = QPixmap()
                pixmap.loadFromData(row["thumbnail"])
                thumb_item.setData(Qt.DecorationRole, pixmap.scaledToHeight(60, Qt.SmoothTransformation))
            else:
                thumb_item.setData(Qt.DecorationRole, None)

            cell(COL_FILENAME).setText(self._display_name(row))

            size_item = cell(COL_SIZE, numeric=True)
            size_item.setText(_format_size(row["size"]))
            size_item.setData(SORT_VALUE_ROLE, row["size"] if row["size"] is not None else -1)

            duration_item = cell(COL_DURATION, numeric=True)
            duration_item.setText(_format_duration(row["duration"]))
            duration_item.setData(SORT_VALUE_ROLE, row["duration"] if row["duration"] is not None else -1)

            cell(COL_LABEL).setText(LABEL_TEXT.get(row["label"], row["label"]))

            score_item = cell(COL_SCORE, numeric=True)
            score_item.setText("" if row["score"] is None else f"{row['score']:.0f}")
            score_item.setData(SORT_VALUE_ROLE, row["score"] if row["score"] is not None else -1)

            cell(COL_OBJECTS).setText(row["detected_objects"] or "")

            self._colorize_row(r, row["label"])

    def _display_name(self, row) -> str:
        if self.current_folder is None:
            return row["filename"]
        try:
            rel = Path(row["path"]).relative_to(self.current_folder)
        except ValueError:
            return row["filename"]
        return row["filename"] if rel.parent == Path(".") else rel.as_posix()

    def _colorize_row(self, r: int, label: str):
        """Zeigt ausschliesslich das Erkennungsergebnis an -- rot fuer
        'keine Bewegung', gruen fuer ein bestaetigtes Objekt. Ob die Zeile
        zur Aktion markiert ist, wird allein durch die Checkbox in Spalte
        "M" angezeigt und beeinflusst diese Farbe bewusst NICHT."""
        color = None
        if label == "real":
            color = QColor(REAL_ROW_COLORS["dark"])
        elif label == "no_motion":
            color = QColor(NO_MOTION_ROW_COLORS["dark"])
        with self._no_sort():
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item is not None:
                    item.setBackground(color if color else QColor(0, 0, 0, 0))

    def _video_id_for_row(self, row: int) -> int | None:
        item = self.table.item(row, COL_MARKED)
        return item.data(VIDEO_ID_ROLE) if item is not None else None

    def _find_row_for_video(self, video_id: int) -> int | None:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, COL_MARKED)
            if item is not None and item.data(VIDEO_ID_ROLE) == video_id:
                return r
        return None

    # -- Analyse ----------------------------------------------------------

    def _on_analyze_clicked(self):
        if self.current_folder is None or self.worker is not None:
            return
        if self._stopped_early:
            # Fortsetzen einer zuvor gestoppten Analyse -- keine Rueckfrage,
            # es werden ohnehin nur die noch ungeprueften Videos verarbeitet.
            self._start_analysis()
            return

        already_analyzed = self.db.conn.execute(
            "SELECT COUNT(*) as c FROM videos WHERE folder = ? AND label != 'unanalyzed'",
            (str(self.current_folder),),
        ).fetchone()["c"]

        if already_analyzed > 0:
            box = QMessageBox(self)
            box.setWindowTitle("Erneut prüfen?")
            box.setText(
                f"{already_analyzed} Aufnahme(n) in diesem Ordner wurden bereits geprüft.\n\n"
                "Sollen diese erneut analysiert werden? Dabei gehen bisherige automatische "
                "und manuelle Markierungen für diese Aufnahmen verloren."
            )
            reanalyze_btn = box.addButton("Alle erneut prüfen", QMessageBox.AcceptRole)
            box.addButton("Nur ungeprüfte", QMessageBox.AcceptRole)
            cancel_btn = box.addButton("Abbrechen", QMessageBox.RejectRole)
            box.setDefaultButton(cancel_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn:
                return
            if clicked is reanalyze_btn:
                self.db.conn.execute(
                    "UPDATE videos SET label = 'unanalyzed', score = NULL, "
                    "detected_objects = '', thumbnail = NULL, marked = 0 WHERE folder = ?",
                    (str(self.current_folder),),
                )
                self.db.conn.commit()
                self._refresh_table()

        self._start_analysis()

    def _start_analysis(self):
        if self.current_folder is None or self.worker is not None:
            return
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.analyze_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._stopped_early = False
        config = AnalysisConfig()
        self.worker = AnalysisWorker(DB_PATH, self.current_folder, config, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.video_started.connect(self._on_video_started)
        self.worker.video_done.connect(self._on_video_analyzed)
        self.worker.detector_status.connect(self._on_detector_status)
        self.worker.finished_all.connect(self._on_analysis_finished)
        self.worker.start()

    def _stop_analysis(self):
        if self.worker is None:
            return
        self.worker.stop()
        self._stopped_early = True
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Stoppe nach dem aktuellen Video…")

    def _on_detector_status(self, available: bool):
        if available:
            self.detector_label.setText("Objekterkennung: aktiv (YOLOv8n)")
            self.detector_label.setToolTip("")
        else:
            self.detector_label.setText("Objekterkennung: nicht verfügbar")
            self.detector_label.setToolTip(
                "YOLOv8n konnte nicht geladen werden (z.B. fehlende Internetverbindung\n"
                "beim ersten Herunterladen der Gewichte, oder `ultralytics` nicht installiert).\n"
                "Es wird nur die Bewegungsheuristik verwendet — unsichere Fälle werden zur\n"
                "manuellen Prüfung markiert statt automatisch verworfen."
            )

    def _on_progress(self, done: int, total: int, current_name: str):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(done)
        self.status_label.setText(f"Analysiere ({done}/{total}): {current_name}")

    def _on_video_started(self, video_id: int):
        row = self._find_row_for_video(video_id)
        if row is None:
            return
        color = QColor(PROCESSING_ROW_COLORS["dark"])
        with self._no_sort():
            for c in range(self.table.columnCount()):
                item = self.table.item(row, c)
                if item is not None:
                    item.setBackground(color)
        if self.auto_scroll_checkbox.isChecked():
            item0 = self.table.item(row, COL_MARKED)
            if item0 is not None:
                self.table.scrollToItem(item0, QAbstractItemView.PositionAtCenter)

    def _on_video_analyzed(self, video_id: int):
        row = self._find_row_for_video(video_id)
        if row is None:
            return
        record = self.db.conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if record is None:
            return
        self._updating_table = True
        self._fill_row(row, record)
        self._updating_table = False
        self._update_marked_summary()
        if self._current_row() == row:
            self._refresh_side_panel_for(record)

    def _on_analysis_finished(self):
        self.progress_bar.setVisible(False)
        self.stop_btn.setEnabled(False)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Fortsetzen" if self._stopped_early else "Analysieren")
        self.worker = None

    # -- Auswahl & Vorschau -------------------------------------------------

    def _current_row(self) -> int | None:
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if len(rows) != 1:
            return None
        return next(iter(rows))

    def _selected_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self.table.selectedIndexes()})

    def _on_selection_changed(self):
        row = self._current_row()
        if row is None:
            self.preview.clear()
            self._current_preview_path = None
            self.info_label.setText("Kein Clip ausgewählt (oder Mehrfachauswahl).")
            self.mark_checkbox.setEnabled(False)
            return
        video_id = self._video_id_for_row(row)
        if video_id is None:
            return
        record = self.db.conn.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        if record is None:
            return
        self.preview.load(record["path"])
        self._current_preview_path = record["path"]
        self._refresh_side_panel_for(record)

    def _refresh_side_panel_for(self, record):
        """Aktualisiert nur Info-Text und Markiert-Checkbox, OHNE die Vorschau
        neu zu laden -- wichtig fuer Live-Updates waehrend der Analyse: der
        Nutzer soll ein bereits laufendes Preview-Video nicht neu starten,
        nur weil im Hintergrund gerade dessen Analyse-Ergebnis eintrifft."""
        label_text = LABEL_TEXT.get(record["label"], record["label"])
        score = "?" if record["score"] is None else f"{record['score']:.0f}"
        objects = record["detected_objects"] or "keine"
        self.info_label.setText(
            f"<b>{record['filename']}</b><br>"
            f"Klassifikation: {label_text} (Konfidenz {score}/100)<br>"
            f"Erkannte Objekte: {objects}"
        )
        self.mark_checkbox.setEnabled(True)
        self.mark_checkbox.blockSignals(True)
        self.mark_checkbox.setChecked(bool(record["marked"]))
        self.mark_checkbox.blockSignals(False)

    def _on_mark_checkbox_changed(self, state):
        row = self._current_row()
        if row is None:
            return
        video_id = self._video_id_for_row(row)
        if video_id is None:
            return
        marked = state == Qt.Checked.value if isinstance(state, int) else bool(state)
        self._set_marked_for_rows([row], marked)

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if self._updating_table or item.column() != COL_MARKED:
            return
        row = item.row()
        video_id = item.data(VIDEO_ID_ROLE)
        if video_id is None:
            return
        marked = item.checkState() == Qt.Checked
        selected = self._selected_rows()
        rows = selected if len(selected) > 1 and row in selected else [row]
        self._set_marked_for_rows(rows, marked)

    def _set_marked_for_rows(self, rows: list[int], marked: bool):
        """Setzt die Markierung fuer alle uebergebenen Zeilen einheitlich --
        genutzt sowohl fuer eine einzelne Zeile als auch fuer eine per
        Shift/Strg getroffene Mehrfachauswahl, damit Markieren/Demarkieren
        (Checkbox-Klick, Leertaste) auf die GESAMTE Auswahl wirkt, nicht nur
        auf die zuletzt angeklickte Zeile."""
        if not rows:
            return
        self._updating_table = True
        with self._no_sort():
            for row in rows:
                item = self.table.item(row, COL_MARKED)
                if item is None:
                    continue
                video_id = item.data(VIDEO_ID_ROLE)
                if video_id is None:
                    continue
                self.db.set_marked(video_id, marked)
                item.setCheckState(Qt.Checked if marked else Qt.Unchecked)
                item.setData(SORT_VALUE_ROLE, 1 if marked else 0)
        self._updating_table = False
        self._update_marked_summary()
        current = self._current_row()
        if current is not None and current in rows:
            self.mark_checkbox.blockSignals(True)
            self.mark_checkbox.setChecked(marked)
            self.mark_checkbox.blockSignals(False)

    # -- Massen-Markierung --------------------------------------------------

    def _mark_all_false_alarms(self):
        if self.current_folder is None:
            return
        self.db.conn.execute(
            "UPDATE videos SET marked = 1 WHERE folder = ? AND label IN ('false_alarm', 'no_motion')",
            (str(self.current_folder),),
        )
        self.db.conn.commit()
        self._refresh_table()

    def _mark_all_recognized(self):
        if self.current_folder is None:
            return
        self.db.conn.execute(
            "UPDATE videos SET marked = 1 WHERE folder = ? AND label = 'real'",
            (str(self.current_folder),),
        )
        self.db.conn.commit()
        self._refresh_table()

    def _invert_marks(self):
        if self.current_folder is None:
            return
        self.db.invert_marks(str(self.current_folder))
        self._refresh_table()

    def _unmark_all(self):
        if self.current_folder is None:
            return
        self.db.mark_all(str(self.current_folder), False)
        self._refresh_table()

    def _marked_rows(self):
        if self.current_folder is None:
            return []
        return self.db.conn.execute(
            "SELECT * FROM videos WHERE folder = ? AND marked = 1", (str(self.current_folder),)
        ).fetchall()

    def _update_marked_summary(self):
        if self.current_folder is None:
            self.marked_summary_label.setText("")
            return
        marked = self.db.conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(duration), 0) as dur, COALESCE(SUM(size), 0) as sz "
            "FROM videos WHERE folder = ? AND marked = 1",
            (str(self.current_folder),),
        ).fetchone()
        total = self.db.conn.execute(
            "SELECT COALESCE(SUM(size), 0) as sz FROM videos WHERE folder = ?",
            (str(self.current_folder),),
        ).fetchone()
        count = marked["c"]
        minutes, seconds = divmod(int(round(marked["dur"] or 0)), 60)
        marked_mb = (marked["sz"] or 0) / (1024 * 1024)
        total_mb = (total["sz"] or 0) / (1024 * 1024)
        text = (
            f"{count} Video(s) markiert (Länge: {minutes:02d}:{seconds:02d} = "
            f"{marked_mb:.1f} MB von {total_mb:.1f} MB gesamt)"
        ).replace(".", ",")
        self.marked_summary_label.setText(text)

    # -- Datei-Aktionen -------------------------------------------------

    def _release_preview_if_among(self, rows):
        """Schliesst die Vorschau, falls der gerade angezeigte/abgespielte
        Clip Teil der zu bearbeitenden Dateien ist -- unter Windows haelt der
        Mediaplayer die Datei sonst offen, wodurch Verschieben/Loeschen mit
        einem Freigabefehler fehlschlaegt."""
        if self._current_preview_path is None:
            return
        paths = {row["path"] for row in rows}
        if self._current_preview_path in paths:
            self.preview.clear()
            self._current_preview_path = None
            self.info_label.setText("Vorschau geschlossen (Datei wird gerade bearbeitet).")
            self.mark_checkbox.setEnabled(False)
            QApplication.processEvents()

    def _move_marked(self):
        rows = self._marked_rows()
        if not rows:
            QMessageBox.information(self, "Keine Auswahl", "Es sind keine Aufnahmen markiert.")
            return
        target = QFileDialog.getExistingDirectory(self, "Zielordner für markierte Aufnahmen wählen")
        if not target:
            return
        self._release_preview_if_among(rows)
        target_dir = Path(target)
        errors = []
        moved_ids = []
        for row in rows:
            src = Path(row["path"])
            try:
                shutil.move(str(src), str(target_dir / src.name))
                moved_ids.append(row["id"])
            except OSError as exc:
                errors.append(f"{src.name}: {exc}")
        if moved_ids:
            self.db.delete_videos(moved_ids)
        self._refresh_table()
        self._report_errors("Verschieben", errors, len(moved_ids))

    def _copy_marked(self):
        rows = self._marked_rows()
        if not rows:
            QMessageBox.information(self, "Keine Auswahl", "Es sind keine Aufnahmen markiert.")
            return
        target = QFileDialog.getExistingDirectory(self, "Zielordner für Kopien wählen")
        if not target:
            return
        self._release_preview_if_among(rows)
        target_dir = Path(target)
        errors = []
        copied = 0
        for row in rows:
            src = Path(row["path"])
            try:
                shutil.copy2(str(src), str(target_dir / src.name))
                copied += 1
            except OSError as exc:
                errors.append(f"{src.name}: {exc}")
        self._report_errors("Kopieren", errors, copied)

    def _delete_marked(self):
        rows = self._marked_rows()
        if not rows:
            QMessageBox.information(self, "Keine Auswahl", "Es sind keine Aufnahmen markiert.")
            return
        answer = QMessageBox.question(
            self,
            "In Papierkorb löschen?",
            f"{len(rows)} markierte Aufnahme(n) in den Papierkorb verschieben?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._release_preview_if_among(rows)
        from send2trash import send2trash

        errors = []
        deleted_ids = []
        for row in rows:
            src = Path(row["path"])
            try:
                send2trash(str(src))
                deleted_ids.append(row["id"])
            except OSError as exc:
                errors.append(f"{src.name}: {exc}")
        if deleted_ids:
            self.db.delete_videos(deleted_ids)
        self._refresh_table()
        self._report_errors("Löschen", errors, len(deleted_ids))

    def _report_errors(self, action: str, errors: list, success_count: int):
        self.status_label.setText(f"{action}: {success_count} erfolgreich, {len(errors)} Fehler.")
        if errors:
            QMessageBox.warning(self, f"Fehler beim {action}", "\n".join(errors))

    # -- Tastenkuerzel ----------------------------------------------------

    def _select_relative_row(self, delta: int):
        row_count = self.table.rowCount()
        if row_count == 0:
            return
        current = self._current_row()
        if current is None:
            new_row = 0 if delta > 0 else row_count - 1
        else:
            new_row = current + delta
            if new_row < 0 or new_row >= row_count:
                return
        self.table.setCurrentCell(new_row, COL_FILENAME)
        item = self.table.item(new_row, COL_MARKED)
        if item is not None:
            self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)

    def _toggle_mark_current(self):
        rows = self._selected_rows()
        if not rows:
            return
        # Bei gemischter Auswahl (manche markiert, manche nicht) zuerst
        # ALLE markieren, statt nur die Einzelzeile umzuschalten -- gleiches
        # Verhalten wie z.B. bei einem "Alle auswaehlen"-Kontrollkaestchen.
        any_unmarked = any(
            self.table.item(r, COL_MARKED).checkState() != Qt.Checked
            for r in rows
            if self.table.item(r, COL_MARKED) is not None
        )
        self._set_marked_for_rows(rows, any_unmarked)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Space and event.isAutoRepeat():
                # Gehaltene Leertaste soll nicht wiederholt umschalten.
                return True
            if self._handle_shortcut_key(key, obj):
                return True
        return super().eventFilter(obj, event)

    def _handle_shortcut_key(self, key: int, focus_widget) -> bool:
        if key == Qt.Key_Space:
            if isinstance(focus_widget, QAbstractButton):
                return False
            self._toggle_mark_current()
            return True
        if key in (Qt.Key_Down, Qt.Key_Up):
            if isinstance(focus_widget, QComboBox):
                return False
            self._select_relative_row(1 if key == Qt.Key_Down else -1)
            return True
        if key in (Qt.Key_Left, Qt.Key_Right):
            if isinstance(focus_widget, QComboBox):
                return False
            self.preview.step_speed(1 if key == Qt.Key_Right else -1)
            return True
        return False

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        if self.worker is not None and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        if self.scan_worker is not None and self.scan_worker.isRunning():
            self.scan_worker.wait(3000)
        self.db.close()
        super().closeEvent(event)
