# Video Motion Detektor

Kleines Python/PySide6-Tool, das Überwachungskamera-Aufnahmen auf echte
Bewegungen prüft und Aufnahmen herausfiltert, in denen die Kamera nur
Lichtreflexe, Rauschen oder ähnliche Fehlalarme als Bewegung registriert hat.

## Funktionsweise

Die Analyse (`engine/motion_analysis.py`) läuft zweistufig:

1. **Klassische Bewegungserkennung** (OpenCV, Hintergrundsubtraktion +
   Verfolgung über mehrere Frames): Bewegungsflächen, die nur 1–2 Frames
   sichtbar sind (typisch für Lichtreflexe/Flackern), fallen automatisch
   heraus, ebenso grossflächige, diffuse Helligkeitswechsel (z.B.
   Scheinwerferlicht, Tag/Nacht-Umschaltung).
2. **Objekterkennung** (YOLOv8n, optional): Bestätigt an den verbleibenden,
   zeitlich stabilen Bewegungsspuren, ob tatsächlich ein relevantes Objekt
   (Person, Fahrzeug, Tier) zu sehen ist. Ist `ultralytics` nicht installiert,
   fällt die Analyse auf die reine Heuristik zurück (dann werden unsichere
   Fälle konservativ zur manuellen Prüfung markiert statt automatisch verworfen).

Alle Ergebnisse landen in einer lokalen SQLite-Datenbank
(`%LOCALAPPDATA%\VideoMotionDetektor\videomotiondetektor.db`), sodass ein
Ordner nicht bei jedem Start neu analysiert werden muss.

## Bedienung

1. Ordner mit den Kamera-Clips wählen.
2. "Analysieren" klicken — läuft im Hintergrund, GUI bleibt bedienbar.
3. Fehlalarm-Kandidaten sind in der Liste automatisch markiert (rot) und per
   Vorschau-Player einzeln kontrollierbar. Markierung lässt sich pro Clip,
   für alle automatisch erkannten Fehlalarme, oder umgekehrt (invertiert)
   setzen.
4. Markierte Clips per Knopfdruck verschieben, kopieren oder in den
   Papierkorb löschen (kein endgültiges Löschen ohne Rückfrage).

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Der erste Analyse-Lauf mit aktivierter Objekterkennung lädt einmalig die
YOLOv8n-Gewichte (~6 MB) nach `%LOCALAPPDATA%\VideoMotionDetektor\models\`.
