from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

SPEED_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
DEFAULT_SPEED_INDEX = SPEED_STEPS.index(1.0)

MODE_ONCE = "once"
MODE_LOOP = "loop"
MODE_AUTO_NEXT = "auto_next"

MODE_LABELS = [
    (MODE_ONCE, "Einmal abspielen"),
    (MODE_LOOP, "Wiederholen (Loop)"),
    (MODE_AUTO_NEXT, "Automatisch nächstes Video"),
]
DEFAULT_MODE = MODE_LOOP

# Ton wird oberhalb von 1x Geschwindigkeit gesperrt (siehe _update_volume_lock) --
# rote Einfaerbung des Reglers, damit die Sperre optisch sofort auffaellt.
_VOLUME_LOCKED_QSS = """
QSlider::groove:horizontal { background: #7a3b3b; height: 4px; }
QSlider::handle:horizontal { background: #c0392b; width: 12px; margin: -5px 0; border-radius: 6px; }
"""
_VOLUME_LOCKED_TOOLTIP = (
    "Ton ist bei erhöhter Geschwindigkeit (über 1x) gesperrt -- eine aktive\n"
    "Audioausgabe kann auf manchen Systemen die Wiedergabe verzögern oder\n"
    "blockieren. Tempo wieder auf 1x oder langsamer stellen, um Ton zu nutzen."
)
_VOLUME_TOOLTIP = (
    "Lautstärke der Videovorschau -- standardmäßig stumm,\n"
    "damit das Durchsehen vieler Clips nicht ungewollt Ton abspielt."
)


def _format_ms(ms: int) -> str:
    total_seconds = max(0, ms) // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _format_speed(rate: float) -> str:
    text = f"{rate:.2f}".rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')}x"


class PreviewPlayer(QWidget):
    """Videovorschau mit Play/Pause, Positions-Schieberegler, Wiedergabemodus
    (einmal/Loop/automatisch naechstes Video) und Geschwindigkeitsregler."""

    request_next = Signal()  # im Modus "Automatisch naechstes Video" bei Clip-Ende

    def __init__(self, parent=None):
        super().__init__(parent)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setMinimumHeight(240)

        self.player = QMediaPlayer(self)
        self.player.setVideoOutput(self.video_widget)
        # Bewusst KEIN QAudioOutput beim Start anhaengen: manche Systeme mit
        # ungewoehnlicher Audio-Hardware (z.B. mehrere Profi-Interfaces)
        # verzoegern oder blockieren die Wiedergabe, sobald ueberhaupt eine
        # Audio-Ausgabe am Player haengt -- selbst bei Lautstaerke 0. Die
        # Ausgabe wird deshalb erst bei Bedarf (Regler > 0) erzeugt und bei
        # Stummschaltung wieder entfernt, siehe _on_volume_changed.
        self.audio_output = None
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        self.play_button = QPushButton("▶", self)
        self.play_button.setFixedWidth(36)
        self.play_button.setToolTip("Wiedergabe starten/pausieren")
        self.play_button.clicked.connect(self.toggle_play)

        self.position_slider = QSlider(Qt.Horizontal, self)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.player.setPosition)

        self.time_label = QLabel("00:00 / 00:00", self)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.position_slider, stretch=1)
        controls.addWidget(self.time_label)

        self.mode_combo = QComboBox(self)
        for value, label in MODE_LABELS:
            self.mode_combo.addItem(label, value)
        self.mode_combo.setCurrentIndex(next(i for i, (v, _) in enumerate(MODE_LABELS) if v == DEFAULT_MODE))
        self.mode_combo.setToolTip(
            "Was nach Ende eines Clips passiert:\n"
            "Einmal abspielen -- stoppt am Ende.\n"
            "Wiederholen -- spielt denselben Clip erneut ab.\n"
            "Automatisch nächstes Video -- springt zum nächsten Clip in der Liste."
        )

        self.speed_slider = QSlider(Qt.Horizontal, self)
        self.speed_slider.setRange(0, len(SPEED_STEPS) - 1)
        self.speed_slider.setValue(DEFAULT_SPEED_INDEX)
        self.speed_slider.setFixedWidth(100)
        self.speed_slider.valueChanged.connect(self._on_speed_slider_changed)
        self.speed_label = QLabel(_format_speed(SPEED_STEPS[DEFAULT_SPEED_INDEX]), self)
        self.speed_label.setFixedWidth(42)
        speed_box = QHBoxLayout()
        speed_box.addWidget(QLabel("Tempo:", self))
        speed_box.addWidget(self.speed_slider)
        speed_box.addWidget(self.speed_label)

        self.volume_slider = QSlider(Qt.Horizontal, self)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(0)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.setToolTip(_VOLUME_TOOLTIP)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_label = QLabel("Stumm", self)
        self.volume_label.setFixedWidth(42)
        volume_box = QHBoxLayout()
        volume_box.addWidget(QLabel("Ton:", self))
        volume_box.addWidget(self.volume_slider)
        volume_box.addWidget(self.volume_label)

        second_row = QHBoxLayout()
        second_row.addWidget(QLabel("Nach Ende:", self))
        second_row.addWidget(self.mode_combo, stretch=1)
        second_row.addLayout(speed_box)
        second_row.addLayout(volume_box)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_widget, stretch=1)
        layout.addLayout(controls)
        layout.addLayout(second_row)

    def load(self, path: str, autoplay: bool = True):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.setPlaybackRate(SPEED_STEPS[self.speed_slider.value()])
        if autoplay:
            self.player.play()

    def clear(self):
        self.player.stop()
        self.player.setSource(QUrl())

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def playback_mode(self) -> str:
        return self.mode_combo.currentData()

    def step_speed(self, delta: int):
        new_value = max(0, min(len(SPEED_STEPS) - 1, self.speed_slider.value() + delta))
        self.speed_slider.setValue(new_value)

    def _on_speed_slider_changed(self, index: int):
        rate = SPEED_STEPS[index]
        self.speed_label.setText(_format_speed(rate))
        self.player.setPlaybackRate(rate)
        self._update_volume_lock(rate)

    def _update_volume_lock(self, rate: float):
        """Sperrt den Ton-Regler oberhalb von 1x -- eine aktive Audioausgabe
        kann bei erhoehter Geschwindigkeit die Wiedergabe destabilisieren
        (siehe Regression durch den Ton-Regler). Rote Einfaerbung macht die
        Sperre sofort erkennbar statt den Regler nur stillschweigend zu
        deaktivieren."""
        locked = rate > 1.0
        was_locked = not self.volume_slider.isEnabled()
        if locked:
            if self.volume_slider.value() != 0:
                self.volume_slider.setValue(0)  # schaltet Ton ueber _on_volume_changed sauber ab
            self.volume_slider.setEnabled(False)
            self.volume_slider.setStyleSheet(_VOLUME_LOCKED_QSS)
            self.volume_label.setText("Gesperrt")
            self.volume_label.setStyleSheet("color: #e0554a;")
            self.volume_slider.setToolTip(_VOLUME_LOCKED_TOOLTIP)
        elif was_locked:
            self.volume_slider.setEnabled(True)
            self.volume_slider.setStyleSheet("")
            self.volume_label.setStyleSheet("")
            self.volume_slider.setToolTip(_VOLUME_TOOLTIP)
            self._on_volume_changed(self.volume_slider.value())

    def _on_volume_changed(self, value: int):
        if value > 0:
            if self.audio_output is None:
                self.audio_output = QAudioOutput(self)
                self.player.setAudioOutput(self.audio_output)
            self.audio_output.setVolume(value / 100.0)
        elif self.audio_output is not None:
            self.player.setAudioOutput(None)
            self.audio_output = None
        if self.volume_slider.isEnabled():
            self.volume_label.setText("Stumm" if value == 0 else f"{value}%")

    def _on_state_changed(self, state):
        self.play_button.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_position_changed(self, position: int):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        self.time_label.setText(f"{_format_ms(position)} / {_format_ms(self.player.duration())}")

    def _on_duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)

    def _on_media_status_changed(self, status):
        if status != QMediaPlayer.EndOfMedia:
            return
        mode = self.playback_mode()
        if mode == MODE_LOOP:
            self.player.setPosition(0)
            self.player.play()
        elif mode == MODE_AUTO_NEXT:
            self.request_next.emit()
        # MODE_ONCE: nichts zu tun, Player bleibt am Ende stehen.
