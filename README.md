# Video Motion Detektor

Windows-Tool, das die Aufnahmen einer Überwachungskamera auf **echte Bewegungen**
(Personen, Hunde, Katzen, Fahrzeuge …) prüft und von Fehlalarmen
(Lichtreflexe, Sensorrauschen, Insekten vor der Linse) trennt – damit man
hunderte automatisch aufgezeichnete Clips schnell durchsehen und aussortieren kann.

Fertiger Windows-Installer (kein separates Python nötig, die KI-Gewichte sind enthalten):
[**Neueste Version herunterladen**](https://github.com/Yakobo1970/VideoMotionDetektor/releases/latest)

Mehr Infos: <https://www.undabtanzbar.de/software/>

## Bedienung

1. Ordner mit den Kamera-Clips wählen – Unterordner werden einbezogen, die Dateiliste
   erscheint sofort (mit Größe und Länge).
2. „Analysieren“ klicken. Die Prüfung läuft im Hintergrund (Stop/Fortsetzen möglich),
   die gerade geprüfte Zeile ist gelb, die Liste scrollt auf Wunsch mit.
3. Ergebnis ablesen: **grün** = Objekt erkannt, **rot** = keine Bewegung gefunden,
   **farblos** = unsicher, bitte ansehen. Die Konfidenz-Spalte zeigt, wie sicher die
   Einschätzung ist.
4. Clips ansehen (Videovorschau mit Loop/nächstes Video, Tempo bis 10×, Ton) und
   markieren – einzeln oder per Shift/Strg-Mehrfachauswahl.
5. Markierte Clips verschieben, kopieren oder in den Papierkorb löschen. Die Statuszeile
   zeigt Anzahl, Länge und Größe der markierten Clips.

Tastenkürzel: **Leertaste** = Markierung umschalten, **↑/↓** = voriges/nächstes Video,
**←/→** = Wiedergabetempo. Alle Spalten sind per Klick auf den Kopf sortierbar.

## Funktionsweise

Zwei unabhängige Verfahren (`engine/motion_analysis.py`):

1. **Objekterkennung** (YOLOv8n): läuft auf gleichmäßig über den ganzen Clip
   verteilten Stichproben – unabhängig von der Bewegungserkennung. Für Katze, Hund
   und Vogel gilt eine abgesenkte Erkennungsschwelle.
2. **Klassische Bewegungserkennung** (OpenCV, Hintergrundsubtraktion) als Rückfallebene
   für Clips ohne erkanntes Objekt: unterscheidet kurzes Flackern, großflächige
   Helligkeitswechsel und länger anhaltende, aber unerkannte Bewegung.

**Nicht zu 100 % zuverlässig:** Sehr schnelle oder stark verwischte Bewegungen
(z. B. eine durchs Bild huschende Katze) können übersehen werden. Deshalb wird nur
der eindeutigste Fehlalarm (großflächiger, diffuser Helligkeitswechsel) automatisch
markiert – alles Unsichere bleibt zur manuellen Prüfung unmarkiert. Vor dem
endgültigen Löschen bitte immer selbst gegenprüfen.

Ergebnisse liegen in einer lokalen SQLite-Datenbank
(`%LOCALAPPDATA%\VideoMotionDetektor\videomotiondetektor.db`), ein Ordner muss
nicht bei jedem Start neu analysiert werden. Getestet mit einer LSC Smart PTZ Camera.

## Aus dem Quellcode starten

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Die YOLOv8n-Gewichte (`yolov8n.pt`, ~6 MB) lädt ultralytics beim ersten Analyse-Lauf
automatisch nach `%LOCALAPPDATA%\VideoMotionDetektor\models\`, oder sie liegen vorab
in `assets\models\`.

## Installer selbst bauen

```
.venv\Scripts\pip install pyinstaller
.venv\Scripts\pyinstaller --noconfirm VideoMotionDetektor.spec
"C:\Program Files\Inno Setup 7\ISCC.exe" installer\VideoMotionDetektor.iss
```

Ergebnis: `dist_installer\VideoMotionDetektor-<Version>-Setup.exe`.

## Lizenz

MIT für den Code dieses Projekts, siehe [LICENSE](LICENSE). Die Objekterkennung nutzt
Ultralytics YOLOv8 (AGPL-3.0) – Details ebenfalls in der LICENSE.

Entwickelt von Yakobo1970 mit Claude (Anthropic) als KI-Programmierassistent.
