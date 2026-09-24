from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from paths import ASSETS_DIR
from version import VERSION

GITHUB_URL = "https://github.com/Yakobo1970"
WEBSITE_URL = "https://www.undabtanzbar.de"

ABOUT_HTML_DE = f"""
<h2>Video Motion Detektor</h2>
<p><i>Version {VERSION}</i></p>

<h3>Was macht dieses Programm?</h3>
<p>Video Motion Detektor durchsucht die von einer Überwachungskamera aufgezeichneten
Video-Clips automatisch nach echten Bewegungen — Personen, Tieren, Fahrzeugen — und
unterscheidet sie von Fehlalarmen wie Lichtreflexen, Sensorrauschen oder Insekten vor
der Linse. Ziel ist es, aus hunderten oder tausenden automatisch aufgezeichneten Clips
schnell die interessanten herauszufiltern, ohne jede Aufnahme einzeln ansehen zu müssen.</p>

<h3>Kurzanleitung</h3>
<ol>
<li>Ordner mit den Kamera-Aufnahmen wählen (Unterordner werden automatisch einbezogen,
die Dateiliste erscheint sofort).</li>
<li>Auf „Analysieren" klicken. Die Prüfung läuft im Hintergrund; die App bleibt
währenddessen bedienbar (Videos ansehen, markieren, sortieren).</li>
<li>Ergebnis ablesen: <b>grün</b> = ein Objekt wurde erkannt, <b>rot</b> = keine Bewegung
gefunden, <b>farblos</b> = unsicher, bitte manuell ansehen.</li>
<li>Einzelne oder per Umschalt-/Strg-Taste mehrfach ausgewählte Clips markieren
(Checkbox in Spalte „M", oder Leertaste).</li>
<li>Markierte Clips gesammelt verschieben, kopieren oder in den Papierkorb löschen.</li>
<li>Tastenkürzel im Vorschaubereich: Leertaste = Markierung umschalten, Pfeil hoch/runter
= voriges/nächstes Video, Pfeil links/rechts = Wiedergabegeschwindigkeit.</li>
</ol>

<h3>Wie die Erkennung funktioniert</h3>
<p>Die Analyse kombiniert zwei unabhängige Verfahren:</p>
<ul>
<li><b>KI-Objekterkennung</b> (YOLOv8): sucht direkt im Bild nach bekannten
Objektklassen wie Person, Katze, Hund oder Fahrzeug — unabhängig davon, ob überhaupt
„klassische" Bewegung erkannt wurde.</li>
<li><b>Klassische Bewegungserkennung</b> (Hintergrundsubtraktion): dient als
Rückfallebene für Clips ohne erkanntes Objekt, um z. B. ein kurzes Lichtflackern von
einer länger anhaltenden, aber nicht erkannten Bewegung zu unterscheiden.</li>
</ul>

<h3>Wichtiger Hinweis zur Zuverlässigkeit</h3>
<p>Diese Erkennung ist ein <b>Hilfsmittel</b>, kein Ersatz für die eigene Kontrolle,
und <b>nicht zu 100&nbsp;% zuverlässig</b>. Besonders sehr schnelle oder stark
verwischte Bewegungen (z.&nbsp;B. ein huschendes Tier) können übersehen oder falsch
eingeordnet werden. Deshalb markiert das Programm nur die eindeutigsten Fehlalarme
automatisch zur Löschung — alle unsicheren Fälle bleiben zur manuellen Prüfung stehen.
Bitte vor dem endgültigen Löschen immer noch einmal selbst über die markierten Clips
schauen.</p>

<h3>Getestet mit</h3>
<p>LSC Smart PTZ Camera (Action)</p>

<h3>Links</h3>
<p>GitHub: <a href="{GITHUB_URL}">github.com/Yakobo1970</a><br>
Website: <a href="{WEBSITE_URL}">www.undabtanzbar.de</a></p>

<h3>Entwicklung</h3>
<p>Entwickelt von Yakobo1970, mit Claude (Anthropic) als KI-Programmierassistent für
Code, Architektur und Fehlersuche.</p>

<h3>Danksagung</h3>
<p>Ein besonderer Dank geht an unsere Haustiere <b>Luzy</b> (Mischling Jack Russell
Terrier / Zwerglabrador — Temperament und Größe des Terriers, Gefräßigkeit des
Labradors), <b>Neyla</b> (Diva-Schneeball-Katze) und <b>Krümel</b> (die sich, wie der
Name schon sagt, gerne verkrümelt) für ihren unermüdlichen Einsatz als Hauptdarsteller
vor der Kamera — ohne sie hätte es dieses Programm nie gebraucht.</p>
"""

ABOUT_HTML_EN = f"""
<h2>Video Motion Detektor</h2>
<p><i>Version {VERSION}</i></p>

<h3>What does this program do?</h3>
<p>Video Motion Detektor automatically scans video clips recorded by a surveillance
camera for genuine motion — people, animals, vehicles — and tells them apart from
false alarms such as light reflections, sensor noise, or insects in front of the lens.
The goal is to quickly filter the interesting clips out of hundreds or thousands of
automatically recorded files, without having to watch every single one.</p>

<h3>Quick guide</h3>
<ol>
<li>Choose the folder containing the camera recordings (subfolders are included
automatically, and the file list appears immediately).</li>
<li>Click "Analysieren" (Analyze). Analysis runs in the background; the app stays
usable while it runs (watch videos, mark them, sort the list).</li>
<li>Read the result: <b>green</b> = an object was recognized, <b>red</b> = no motion
found, <b>no color</b> = uncertain, please check manually.</li>
<li>Mark a single clip or a multi-selection (Shift/Ctrl) via the checkbox in column
"M", or the space bar.</li>
<li>Move, copy, or send marked clips to the recycle bin in bulk.</li>
<li>Keyboard shortcuts in the preview area: Space = toggle mark, Up/Down =
previous/next video, Left/Right = playback speed.</li>
</ol>

<h3>How the detection works</h3>
<p>The analysis combines two independent methods:</p>
<ul>
<li><b>AI object detection</b> (YOLOv8): looks directly in the frame for known object
classes such as person, cat, dog, or vehicle — regardless of whether "classic" motion
was detected at all.</li>
<li><b>Classic motion detection</b> (background subtraction): serves as a fallback for
clips where no object was recognized, e.g. to tell a brief light flicker apart from
motion that lasted longer but wasn't recognized.</li>
</ul>

<h3>Important note on reliability</h3>
<p>This detection is an <b>aid</b>, not a replacement for checking things yourself, and
it is <b>not 100% reliable</b>. Especially very fast or heavily motion-blurred movement
(e.g. an animal darting through frame) can be missed or misclassified. That's why the
program only auto-marks the clearest false alarms for deletion — every uncertain case
is left marked for manual review. Please always glance over the marked clips once more
before deleting anything for good.</p>

<h3>Tested with</h3>
<p>LSC Smart PTZ Camera (Action)</p>

<h3>Links</h3>
<p>GitHub: <a href="{GITHUB_URL}">github.com/Yakobo1970</a><br>
Website: <a href="{WEBSITE_URL}">www.undabtanzbar.de</a></p>

<h3>Development</h3>
<p>Developed by Yakobo1970, with Claude (Anthropic) as an AI coding assistant for code,
architecture, and debugging.</p>

<h3>Acknowledgements</h3>
<p>Special thanks go to our pets <b>Luzy</b> (Jack Russell Terrier / mini Labrador
mix — the terrier's size and temperament, the Labrador's appetite), <b>Neyla</b> (diva
snowball cat), and <b>Krümel</b> — German for "crumb", a
fitting name since she's always off crumbling away somewhere — for their tireless work
as the camera's leading actors, without whom this program would never have been
necessary.</p>
"""

ABOUT_HTML_FR = f"""
<h2>Video Motion Detektor</h2>
<p><i>Version {VERSION}</i></p>

<h3>À quoi sert ce programme&nbsp;?</h3>
<p>Video Motion Detektor analyse automatiquement les séquences vidéo enregistrées par
une caméra de surveillance afin de distinguer les véritables mouvements — personnes,
animaux, véhicules — des fausses alertes telles que reflets lumineux, bruit du capteur
ou insectes devant l'objectif. L'objectif est de trier rapidement les séquences
intéressantes parmi des centaines, voire des milliers de fichiers enregistrés
automatiquement, sans devoir tous les visionner un par un.</p>

<h3>Guide rapide</h3>
<ol>
<li>Choisissez le dossier contenant les enregistrements de la caméra (les sous-dossiers
sont inclus automatiquement, la liste des fichiers apparaît immédiatement).</li>
<li>Cliquez sur « Analysieren » (Analyser). L'analyse s'exécute en arrière-plan ;
l'application reste utilisable pendant ce temps (regarder les vidéos, les marquer,
trier la liste).</li>
<li>Lisez le résultat&nbsp;: <b>vert</b> = un objet a été reconnu, <b>rouge</b> = aucun
mouvement détecté, <b>sans couleur</b> = incertain, à vérifier manuellement.</li>
<li>Marquez un clip ou une sélection multiple (Maj/Ctrl) via la case à cocher de la
colonne « M », ou la barre d'espace.</li>
<li>Déplacez, copiez ou envoyez à la corbeille les clips marqués, en groupe.</li>
<li>Raccourcis clavier dans la zone d'aperçu&nbsp;: Espace = basculer le marquage,
Haut/Bas = vidéo précédente/suivante, Gauche/Droite = vitesse de lecture.</li>
</ol>

<h3>Comment fonctionne la détection</h3>
<p>L'analyse combine deux méthodes indépendantes&nbsp;:</p>
<ul>
<li><b>Détection d'objets par IA</b> (YOLOv8)&nbsp;: recherche directement dans l'image
des classes d'objets connues telles que personne, chat, chien ou véhicule —
indépendamment de la détection ou non d'un mouvement « classique ».</li>
<li><b>Détection de mouvement classique</b> (soustraction d'arrière-plan)&nbsp;: sert de
solution de repli pour les clips où aucun objet n'a été reconnu, par exemple pour
distinguer un bref scintillement lumineux d'un mouvement plus long mais non reconnu.</li>
</ul>

<h3>Remarque importante sur la fiabilité</h3>
<p>Cette détection est une <b>aide</b>, pas un substitut à une vérification
personnelle, et elle n'est <b>pas fiable à 100&nbsp;%</b>. Les mouvements très rapides
ou fortement flous (par exemple un animal filant à travers l'image) peuvent être
manqués ou mal classés. C'est pourquoi le programme ne marque automatiquement pour
suppression que les fausses alertes les plus évidentes&nbsp;; tous les cas incertains
restent marqués pour une vérification manuelle. Merci de toujours revérifier les clips
marqués avant toute suppression définitive.</p>

<h3>Testé avec</h3>
<p>LSC Smart PTZ Camera (Action)</p>

<h3>Liens</h3>
<p>GitHub&nbsp;: <a href="{GITHUB_URL}">github.com/Yakobo1970</a><br>
Site web&nbsp;: <a href="{WEBSITE_URL}">www.undabtanzbar.de</a></p>

<h3>Développement</h3>
<p>Développé par Yakobo1970, avec Claude (Anthropic) comme assistant de programmation
IA pour le code, l'architecture et le débogage.</p>

<h3>Remerciements</h3>
<p>Un grand merci à nos animaux de compagnie <b>Luzy</b> (croisement Jack Russell
Terrier / mini Labrador — la taille et le tempérament du terrier, l'appétit du
labrador), <b>Neyla</b> (chatte diva « boule de neige ») et <b>Krümel</b> (« miette » en
allemand, un nom bien trouvé puisqu'elle est toujours partie se « débiner ») pour leur
travail acharné en tant que vedettes devant la caméra, sans qui ce programme n'aurait
jamais été nécessaire.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Über Video Motion Detektor {VERSION}")
        self.resize(640, 580)

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        icon_path = ASSETS_DIR / "icon.ico"
        if icon_path.exists():
            icon_label = QLabel(self)
            icon_label.setPixmap(
                QPixmap(str(icon_path)).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            header.addWidget(icon_label)
        title_box = QVBoxLayout()
        title_box.addWidget(QLabel("<b style='font-size:16pt'>Video Motion Detektor</b>", self))
        title_box.addWidget(QLabel(f"Version {VERSION}", self))
        header.addLayout(title_box)
        header.addStretch(1)
        layout.addLayout(header)

        tabs = QTabWidget(self)
        for label, html in (
            ("Deutsch", ABOUT_HTML_DE),
            ("English", ABOUT_HTML_EN),
            ("Français", ABOUT_HTML_FR),
        ):
            browser = QTextBrowser(self)
            browser.setOpenExternalLinks(True)
            browser.setHtml(html)
            tabs.addTab(browser, label)
        layout.addWidget(tabs, stretch=1)

        close_btn = QPushButton("Schließen", self)
        close_btn.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)
