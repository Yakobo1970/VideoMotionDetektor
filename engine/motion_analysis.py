"""Analysiert Ueberwachungskamera-Clips und unterscheidet echte Bewegungen
(Personen, Fahrzeuge, Tiere) von Fehlalarmen (Lichtreflexe, Rauschen,
Insekten vor der Linse, IR-Umschaltung bei Daemmerung).

Zwei UNABHAENGIGE Signale werden kombiniert:
1. Objekterkennung (YOLOv8n, optional): laeuft auf gleichmaessig ueber den
   GESAMTEN Clip verteilten Stichproben-Frames -- NICHT nur dort, wo die
   klassische Bewegungserkennung bereits eine "persistente Spur" gefunden
   hat. Das ist bewusst so: ein Tier (v.a. Katzen), das sich langsam bewegt,
   sich hinlegt oder nur kurz voll sichtbar ist, bildet oft keine laenger
   anhaltende Bewegungsspur in der Hintergrundsubtraktion -- waere die
   Objekterkennung daran gekoppelt, wuerde sie genau die interessantesten
   Szenen verpassen. Wird IRGENDWO im Clip ein relevantes Objekt erkannt,
   gilt der Clip als echte Bewegung, unabhaengig vom Bewegungsmuster.
2. Klassische Bewegungserkennung (Hintergrundsubtraktion + zeitliche
   Persistenz-Verfolgung) dient nur noch als FALLBACK-Heuristik fuer Clips,
   in denen KEIN Objekt erkannt wurde -- sie unterscheidet dort "sicher nur
   ein kurzer Reflex" von "es hat sich etwas bewegt, aber nicht erkannt".

Wichtig: Ein sehr schnelles Tier (v.a. Katzen) ist oft nur 1-2 Frames lang
als kurzer, verwischter Lichtblitz sichtbar -- das ist anhand von Dauer/
Helligkeit allein NICHT zuverlaessig von einem Reflex/Blinklicht zu
unterscheiden. Deshalb wird nur noch die eine Kategorie automatisch zur
Loeschung vorgeschlagen, die ein einzelnes kleines/schnelles Tier
strukturell nicht erzeugen kann: ein grossflaechiger, diffuser Helligkeits-
wechsel ueber einen Grossteil des Bildes (z.B. Scheinwerferschwenk,
Tag/Nacht-Umschaltung). Alle anderen "kein Objekt erkannt"-Faelle (kurzes
Flackern, gar keine Bewegung gefunden, persistente aber unbestaetigte
Bewegung) bleiben zur manuellen Pruefung UNMARKIERT -- lieber ein paar
Clips mehr manuell ansehen, als eine echte Tieraufnahme automatisch zu
verlieren.

YOLO ist optional: ist `ultralytics` nicht installiert oder das Modell
nicht ladbar, faellt die Analyse auf die reine Heuristik zurueck.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from paths import ASSETS_DIR

MODEL_DIR = Path.home() / "AppData" / "Local" / "VideoMotionDetektor" / "models"

# Objektklassen (COCO-Namen), die als "relevante" Bewegung zaehlen.
RELEVANT_CLASSES = {
    "person",
    "car",
    "truck",
    "bus",
    "motorcycle",
    "bicycle",
    "dog",
    "cat",
    "bird",
    "horse",
}

# Manche Klassen werden von YOLOv8n (kleines Modell) auf CCTV-Bildmaterial
# deutlich unsicherer erkannt als z.B. "person" -- v.a. Katzen sind klein,
# oft in ungewoehnlicher Haltung (liegend, geduckt) und auf Nachtsicht-
# Aufnahmen kontrastarm. Fuer diese Klassen gilt eine abgesenkte Schwelle,
# damit sie nicht systematisch als Fehlalarm durchfallen.
CLASS_CONFIDENCE_OVERRIDES = {
    "cat": 0.15,
    "dog": 0.15,
    "bird": 0.15,
}

# -- Konfiguration ------------------------------------------------------


@dataclass
class AnalysisConfig:
    analysis_width: int = 640  # Frames werden fuer die Analyse herunterskaliert (YOLO-Trainingsaufloesung)
    frame_stride: int = 1  # jeden n-ten Frame fuer die Bewegungsheuristik verarbeiten (1 = alle)
    min_contour_area_frac: float = 0.0004  # Mindestgroesse einer Bewegungsflaeche
    min_track_frames: int = 2  # so viele Frames muss eine Spur ueberleben, um als "persistent" zu gelten
    bg_var_threshold: float = 20.0  # MOG2-Empfindlichkeit -- niedriger = empfindlicher (erwischt auch schwache/kurze Bewegungsunschaerfe)
    max_track_gap: int = 3  # erlaubte Luecke (Frames ohne Match) in einer Spur
    global_change_frac: float = 0.35  # ueber diesem Flaechenanteil: vermutlich Beleuchtungswechsel
    detector_confidence: float = 0.25
    use_object_detector: bool = True
    max_frames_to_scan: int = 6000  # Obergrenze fuer die (teure) Bewegungsheuristik
    max_raw_frames: int = 20000  # harte Sicherheitsgrenze fuers reine Frame-Lesen (korrupte/sehr lange Dateien)
    min_detector_samples: int = 12  # Mindestanzahl Stichproben, auch bei sehr kurzen Clips
    detector_sample_interval_seconds: float = 1.5  # angestrebter Abstand zwischen Stichproben bei laengeren Clips
    max_detector_samples: int = 200  # Obergrenze an YOLO-Aufrufen pro Video (Performance bei sehr langen Clips)


@dataclass
class AnalysisResult:
    score: float  # 0..100, hoeher = sicherer echte Bewegung
    label: str  # 'real' | 'false_alarm' | 'no_motion'
    detected_objects: list = field(default_factory=list)
    thumbnail_jpeg: bytes | None = None
    details: dict = field(default_factory=dict)
    auto_mark: bool = False  # ob der Clip automatisch zur Aktion vorgemerkt werden soll

    @property
    def suggests_false_alarm(self) -> bool:
        return self.label in ("false_alarm", "no_motion")


class _Track:
    """Einfache Bewegungsspur ueber mehrere Frames (Centroid-Distanz-Matching)."""

    __slots__ = ("centroid", "box", "hits", "misses")

    def __init__(self, centroid, box):
        self.centroid = centroid
        self.box = box
        self.hits = 1
        self.misses = 0


_detector_cache = {}


def _load_detector():
    if "model" in _detector_cache:
        return _detector_cache["model"]
    model = None
    try:
        from ultralytics import YOLO

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        weights = MODEL_DIR / "yolov8n.pt"
        bundled = ASSETS_DIR / "models" / "yolov8n.pt"
        if not weights.exists() and bundled.exists():
            shutil.copy2(bundled, weights)
        model = YOLO(str(weights))
    except Exception:
        model = None
    _detector_cache["model"] = model
    return model


def detector_available() -> bool:
    """Ob die optionale YOLO-Objekterkennung geladen werden konnte (erste
    Abfrage laedt/lauft dabei Gewichte nach, das Ergebnis wird gecacht)."""
    return _load_detector() is not None


def probe_duration_seconds(path: Path) -> float | None:
    """Liest nur die Container-Metadaten (Framezahl/FPS), ohne Frames zu
    dekodieren -- schnell genug, um sie schon beim ersten Auflisten einer
    Datei zu ermitteln, noch vor der eigentlichen Bewegungsanalyse."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
    cap.release()
    if fps <= 0 or frame_count <= 0:
        return None
    return frame_count / fps


def _pick_sample_indices(total_frames: int, fps: float, config: AnalysisConfig) -> set[int]:
    """Gleichmaessig verteilte Frame-Indizes fuer die Objekterkennung. Kurze
    Clips bekommen mindestens `min_detector_samples`, damit auch kurz
    sichtbare Objekte kaum eine Chance haben durchzurutschen; laengere Clips
    werden zusaetzlich mit ungefaehr einer Stichprobe pro
    `detector_sample_interval_seconds` abgetastet (sonst wuerden bei einem
    mehrminuetigen Clip riesige unabgedeckte Luecken zwischen den Stichproben
    entstehen) -- nach oben durch `max_detector_samples` begrenzt."""
    if total_frames <= 0:
        return set()
    interval_frames = max(1, int(round(fps * config.detector_sample_interval_seconds))) if fps > 0 else 15
    by_interval = total_frames // interval_frames + 1
    num_samples = min(max(config.min_detector_samples, by_interval), config.max_detector_samples, total_frames)
    if total_frames <= num_samples:
        return set(range(total_frames))
    step = total_frames / num_samples
    return {int(i * step) for i in range(num_samples)}


def analyze_video(path: Path, config: AnalysisConfig | None = None) -> AnalysisResult:
    config = config or AnalysisConfig()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return AnalysisResult(
            0.0, "no_motion", details={"error": "Datei konnte nicht geoeffnet werden"}, auto_mark=False
        )

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    bg_subtractor = cv2.createBackgroundSubtractorMOG2(
        history=200, varThreshold=config.bg_var_threshold, detectShadows=True
    )

    detector = _load_detector() if config.use_object_detector else None
    # Bei bekannter Framezahl: gleichmaessig ueber den ganzen Clip verteilte
    # Stichproben. Ist die Framezahl unbekannt/unzuverlaessig (manche
    # Container liefern das nicht), stattdessen ungefaehr einmal pro
    # Sekunde abtasten -- damit der gesamte Clip abgedeckt bleibt.
    if total_frames_hint > 0:
        sample_indices: set[int] | None = _pick_sample_indices(total_frames_hint, fps, config)
        sample_stride = None
    else:
        sample_indices = None
        sample_stride = max(1, int(round(fps * config.detector_sample_interval_seconds))) if fps > 0 else 15

    tracks: list[_Track] = []
    detected_labels: set[str] = set()
    best_conf = -1.0
    best_thumbnail = None
    best_thumbnail_score = -1.0
    raw_index = -1
    scale = None
    frame_area = None
    large_change_frames = 0
    motion_frames = 0
    total_scanned = 0

    while raw_index + 1 < config.max_raw_frames:
        ok, frame = cap.read()
        if not ok:
            break
        raw_index += 1

        if scale is None:
            h, w = frame.shape[:2]
            scale = config.analysis_width / float(w)
            frame_area = (w * scale) * (h * scale)
        small = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        is_sample = (raw_index in sample_indices) if sample_indices is not None else (raw_index % sample_stride == 0)
        if detector is not None and is_sample and not detected_labels:
            labels, conf = _detect_objects_in_frame(detector, small, config.detector_confidence)
            if labels:
                detected_labels.update(labels)
                best_conf = max(best_conf, conf)
                best_thumbnail = frame
                best_thumbnail_score = conf

        if total_scanned >= config.max_frames_to_scan:
            # Bewegungsheuristik-Obergrenze erreicht -- ab hier nur noch
            # Objekterkennungs-Stichproben (oben), keine weitere (teure)
            # Hintergrundsubtraktion/Konturanalyse mehr.
            continue
        if config.frame_stride > 1 and raw_index % config.frame_stride != 0:
            continue
        total_scanned += 1

        fgmask = bg_subtractor.apply(small)
        # Schatten (Wert 127 bei detectShadows=True) nicht als Bewegung zaehlen.
        _, fgmask = cv2.threshold(fgmask, 200, 255, cv2.THRESH_BINARY)
        # Bewusst KEIN MORPH_OPEN (Erosion+Dilatation) mehr -- das wuerde
        # genau die duennen, kurzlebigen Bewegungsunschaerfe-Streifen eines
        # sehr schnellen Tieres wieder wegradieren. Nur noch dilatieren, um
        # einzelne Rauschpixel zu kleinen, zusammenhaengenden Flaechen zu
        # verschmelzen -- der `min_contour_area_frac`-Schwellenwert filtert
        # danach echtes Ein-Pixel-Rauschen weiterhin heraus.
        fgmask = cv2.dilate(fgmask, np.ones((5, 5), np.uint8), iterations=1)

        changed_frac = float(np.count_nonzero(fgmask)) / frame_area
        if changed_frac > config.global_change_frac:
            # Grossflaechiger, diffuser Helligkeitswechsel -- typisch fuer
            # Scheinwerfer/Reflexe/Tag-Nacht-Umschaltung, kein einzelnes Objekt.
            large_change_frames += 1

        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < config.min_contour_area_frac * frame_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            boxes.append((x, y, w, h))

        if boxes:
            motion_frames += 1
        _update_tracks(tracks, boxes, config.max_track_gap)

        if boxes and best_thumbnail is None:
            best_thumbnail = frame
            best_thumbnail_score = 0.0

    cap.release()

    persistent_tracks = [t for t in tracks if t.hits >= config.min_track_frames]
    thumbnail_jpeg = _encode_thumbnail(best_thumbnail) if best_thumbnail is not None else None

    details = {
        "scanned_frames": total_scanned,
        "raw_frames": raw_index + 1,
        "motion_frames": motion_frames,
        "persistent_tracks": len(persistent_tracks),
        "large_change_frames": large_change_frames,
        "fps": fps,
        "detector_active": detector is not None,
    }

    if detected_labels:
        # Ein erkanntes Objekt ist der staerkste Beleg fuer echte Bewegung --
        # niemals automatisch markieren.
        score = min(100.0, 60.0 + best_conf * 40.0)
        return AnalysisResult(score, "real", sorted(detected_labels), thumbnail_jpeg, details, auto_mark=False)

    if motion_frames == 0:
        # Weder Bewegung noch (falls aktiv) ein Objekt irgendwo im Clip
        # gefunden. WICHTIG: die Kamera hat trotzdem wegen Bewegung
        # ausgeloest -- "wir haben nichts gefunden" heisst hier eher "unsere
        # Heuristik hat etwas Kurzes/Schwaches verpasst" als "es war wirklich
        # nichts". Daher rot (informativ), aber NICHT automatisch markiert.
        return AnalysisResult(5.0, "no_motion", [], thumbnail_jpeg, details, auto_mark=False)

    if not persistent_tracks:
        # Nur kurzlebiges Flackern. Das ist typisch fuer einen Reflex,
        # aber genauso fuer ein sehr schnelles Tier, das nur 1-2 Frames lang
        # als Bewegungsunschaerfe sichtbar ist -- beides laesst sich allein
        # anhand der Kuerze nicht zuverlaessig unterscheiden. Deshalb NICHT
        # automatisch markieren, nur als Verdachtsfall mit niedriger
        # Konfidenz kennzeichnen.
        return AnalysisResult(15.0, "false_alarm", [], thumbnail_jpeg, details, auto_mark=False)

    diffuse_ratio = large_change_frames / max(1, total_scanned)
    if diffuse_ratio > 0.3:
        # Ueberwiegend grossflaechiger, diffuser Wechsel ueber einen Grossteil
        # des Bildes -- das kann ein einzelnes, kleines/schnelles Tier
        # strukturell nicht erzeugen (anders als ein Lichtschwenk/Blitz).
        # Einzige Kategorie, die weiterhin automatisch markiert wird.
        return AnalysisResult(20.0, "false_alarm", [], thumbnail_jpeg, details, auto_mark=True)

    # Persistente, kompakte Bewegung, aber kein bekanntes Objekt erkannt
    # (z.B. Tier von YOLO nicht erkannt) -- als Verdachtsfall kennzeichnen,
    # aber bewusst NICHT automatisch zur Loeschung markieren.
    score = 45.0 if detector is None else 35.0
    return AnalysisResult(score, "false_alarm", [], thumbnail_jpeg, details, auto_mark=False)


def _update_tracks(tracks: list[_Track], boxes: list[tuple], max_gap: int):
    unmatched = list(range(len(boxes)))
    for t in tracks:
        cx, cy = t.centroid
        best_i, best_d = None, 1e9
        for i in unmatched:
            x, y, w, h = boxes[i]
            bcx, bcy = x + w / 2, y + h / 2
            d = (bcx - cx) ** 2 + (bcy - cy) ** 2
            diag = (w + h) ** 2 or 1
            if d < diag * 4 and d < best_d:
                best_d, best_i = d, i
        if best_i is not None:
            x, y, w, h = boxes[best_i]
            t.centroid = (x + w / 2, y + h / 2)
            t.box = (x, y, w, h)
            t.hits += 1
            t.misses = 0
            unmatched.remove(best_i)
        else:
            t.misses += 1

    tracks[:] = [t for t in tracks if t.misses <= max_gap]
    for i in unmatched:
        x, y, w, h = boxes[i]
        tracks.append(_Track((x + w / 2, y + h / 2), (x, y, w, h)))


def _detect_objects_in_frame(detector, frame_bgr, min_conf: float):
    """Laesst YOLO auf dem GESAMTEN (bereits herunterskalierten) Frame
    laufen -- unabhaengig von jeder Bewegungsspur. Fuer Klassen mit
    abgesenkter Schwelle (siehe CLASS_CONFIDENCE_OVERRIDES) wird das Modell
    mit der niedrigsten beteiligten Schwelle aufgerufen, die eigentliche
    Filterung passiert danach pro Klasse."""
    predict_conf = min([min_conf, *CLASS_CONFIDENCE_OVERRIDES.values()])
    try:
        results = detector.predict(frame_bgr, verbose=False, conf=predict_conf)
    except Exception as exc:
        _detector_cache["last_error"] = repr(exc)
        return [], 0.0
    labels = []
    best_conf = 0.0
    for r in results:
        names = r.names
        for box_data in r.boxes:
            cls_id = int(box_data.cls[0])
            conf = float(box_data.conf[0])
            name = names.get(cls_id, str(cls_id))
            if name not in RELEVANT_CLASSES:
                continue
            threshold = CLASS_CONFIDENCE_OVERRIDES.get(name, min_conf)
            if conf < threshold:
                continue
            labels.append(name)
            best_conf = max(best_conf, conf)
    return labels, best_conf


def _encode_thumbnail(frame, max_width: int = 320) -> bytes | None:
    h, w = frame.shape[:2]
    if w > max_width:
        scale = max_width / float(w)
        frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return None
    return buf.tobytes()
