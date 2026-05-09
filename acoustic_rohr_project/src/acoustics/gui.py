import sys
from pathlib import Path
from types import SimpleNamespace
import wave

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import numpy as np
import pyqtgraph as pg

from automation import (
    mean_microphone_amplitude,
    update_voltage_from_amplitude,
    amplitude_reached_target,
)

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QGroupBox,
    QStackedWidget,
    QDialog,
    QSizePolicy
)

from generator_interface import TektronixAFG320
from focusrite_interface import FocusriteInterface
from estimation import estimate_forward_reflected_three_mics_ls

TARGET_AMP = 6.0e-5
AMP_TOLERANCE = 0.05
MAX_AUTO_STEPS = 5
MIN_GENERATOR_VOLTAGE = 0.01
MAX_GENERATOR_VOLTAGE = 1.0

NUM_CHANNELS = 3

# Signalquelle
SOURCE_SIMULATION = "Simulation"
SOURCE_SCARLETT = "Audio-Interface"

# Feste Messparameter
DEFAULT_MEASUREMENT_F0 = 1000.0 # Periode von 1 ms, 0,001 s
MEASUREMENT_DURATION = 1.0
WINDOW_SECONDS = MEASUREMENT_DURATION
DISPLAY_PERIODS = 5

# FFT-Anzeige
FFT_MAX_FREQ = 2000

# Feste Rohr-/Mikrofonparameter
SPEED_OF_SOUND = 343.0
MIC_X1 = 0.000
MIC_X2 = 0.050
MIC_X3 = 0.100


class SignalPlotDialog(QDialog):
    def __init__(self, title, x, y, xlabel="Zeit [s]", ylabel="Signal", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1400, 550)

        layout = QVBoxLayout()

        self.plot_widget = pg.PlotWidget(title=title)
        self.plot_widget.setLabel("bottom", xlabel)
        self.plot_widget.setLabel("left", ylabel)
        self.plot_widget.setMouseEnabled(x=True, y=False)
        self.plot_widget.showGrid(x=True, y=False)
        self.plot_widget.plot(x, y, pen="y")
        self.plot_widget.enableAutoRange(False) # Automatischer Zoom, damit die Daten gut sichtbar sind
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

class LogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Log")
        self.resize(1500, 1000)

        layout = QVBoxLayout()
        top_layout = QHBoxLayout()
        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        self.back_button.clicked.connect(self.close)

        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)

        layout.addWidget(self.log_view)
        self.setLayout(layout)

    def append(self, text):
        self.log_view.append(text)

class ComplexResultsDialog(QDialog):
    def __init__(self, mic_results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messergebnisse")
        self.resize(1500, 1000)

        layout = QVBoxLayout()
        top_layout = QHBoxLayout()

        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        self.back_button.clicked.connect(self.close)

        top_layout.addWidget(self.back_button)
        top_layout.addStretch()

        layout.addLayout(top_layout)

        title = QLabel("komplexe Schalldruck-Amplituden der Mikrofone (P)")
        title.setStyleSheet("font-size: 22px;")
        layout.addWidget(title)

        # -----------------------------
        # Oben: 3 Mikrofone nebeneinander
        # -----------------------------
        mic_row = QHBoxLayout()

        mic_max = max(
            abs((mic_results["P1"] * 1e6).real), abs((mic_results["P1"] * 1e6).imag),
            abs((mic_results["P2"] * 1e6).real), abs((mic_results["P2"] * 1e6).imag),
            abs((mic_results["P3"] * 1e6).real), abs((mic_results["P3"] * 1e6).imag),
            1.0
        )

        for i in range(3):
            box = QGroupBox(f"Mikrofon {i+1}")
            box_layout = QVBoxLayout()

            plot = pg.PlotWidget(title=f"P{i + 1}")

            # Plot-Fenster wirklich quadratisch halten
            plot_size = 430
            plot.setMinimumSize(plot_size, plot_size)
            plot.setMaximumSize(plot_size, plot_size)
            plot.setFixedSize(plot_size, plot_size)

            # Nicht vom Layout strecken lassen
            plot.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Fixed
            )

            # Datenachsen 1:1 halten
            plot.setAspectLocked(True, ratio=1)
            plot.getViewBox().setAspectLocked(True, ratio=1)
            
            plot.setLabel("bottom", "Realteil [µV]")
            plot.setLabel("left", "Imaginärteil [µV]")
            plot.showGrid(x=True, y=True)
            plot.setMouseEnabled(x=True, y=True)

            # Null-Linien
            vline = pg.InfiniteLine(pos=0, angle=90)
            hline = pg.InfiniteLine(pos=0, angle=0)
            plot.addItem(vline)
            plot.addItem(hline)

            P = mic_results[f"P{i+1}"]
            P_plot = P * 1e6

            plot.plot([0, P_plot.real], [0, P_plot.imag], pen="r")
            plot.plot([P_plot.real], [P_plot.imag], pen="r", symbol="o", symbolSize=15, symbolBrush="r",thickness=3)

            # Für alle drei Plots dieselbe quadratische Skala
            plot_limit = 2.0 * mic_max
            plot.setXRange(-plot_limit, plot_limit, padding=0)
            plot.setYRange(-plot_limit, plot_limit, padding=0)
            plot.enableAutoRange(x=False, y=False)

            box_layout.addWidget(plot)

            info = QLabel()
            P = mic_results[f"P{i+1}"]
            P_uv = P * 1e6

            info.setText(
                f"Spektrum bei P{i+1}​(f0​) = {P_uv.real:.3f} + j ({P_uv.imag:.3f}) µV\n"
                f"Realteil = {P_uv.real:.3f} µV\n"
                f"Imaginärteil = {P_uv.imag:.3f} µV\n"
                f"Betrag = {abs(P_uv):.3f} µV\n"
                f"Phase = {mic_results[f'phase{i+1}']:.6f} rad\n"
                f"RMS = {mic_results[f'rms{i+1}']:.6e} V\n"
                f"Phasenverschiebung in Rad = {mic_results[f'phase_shift{i+1}']:.6f} rad\n"
                f"Phasenverschiebung in Grad = {mic_results[f'phase_shift_deg{i+1}']:.2f}°\n"
                f"Zeitverschiebung = {mic_results[f'time_shift_ms{i+1}']:.3f} ms\n\n"
                
            )
            info.setStyleSheet("font-size: 16px; padding: 8px; background: white;")
            box_layout.addWidget(info)

            box.setLayout(box_layout)
            mic_row.addWidget(box)

        layout.addLayout(mic_row)
        self.setLayout(layout)

class StartScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(30)
        layout.setContentsMargins(50, 50, 50, 50)

        title = QLabel("Akustik-Messsystem")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 32px; font-weight: bold; margin-bottom: 30px;")
        layout.addWidget(title)

        layout.addStretch()

        self.auto_button = QPushButton("Automatische Messung\n(Generator + Audio-Interface)")
        self.auto_button.setMinimumHeight(80)
        self.auto_button.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.auto_button)

        self.generator_button = QPushButton("Signalgenerator")
        self.generator_button.setMinimumHeight(80)
        self.generator_button.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.generator_button)

        self.signal_button = QPushButton("Signalanalyse")
        self.signal_button.setMinimumHeight(80)
        self.signal_button.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.signal_button)

        layout.addStretch()
        self.setLayout(layout)


class GeneratorScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.generator = None
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        title = QLabel("Hardware-Generator Steuerung")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 20px 0;")
        main_layout.addWidget(title)

        group = QGroupBox("Tektronix AFG320")
        group_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.resource_edit = QLineEdit("GPIB0::10::INSTR")
        self.gen_connect_button = QPushButton("Verbinden")
        self.gen_id_button = QPushButton("ID lesen")
        row1.addWidget(QLabel("Ressource"))
        row1.addWidget(self.resource_edit)
        row1.addWidget(self.gen_connect_button)
        row1.addWidget(self.gen_id_button)

        row2 = QHBoxLayout()
        self.freq_edit = QLineEdit(str(int(DEFAULT_MEASUREMENT_F0)))
        self.amp_edit = QLineEdit("0.2")
        self.gen_sine_button = QPushButton("Sinus")
        self.gen_send_button = QPushButton("Werte senden")
        row2.addWidget(QLabel("Frequenz [Hz]"))
        row2.addWidget(self.freq_edit)
        row2.addWidget(QLabel("Spannung [V]"))
        row2.addWidget(self.amp_edit)
        row2.addWidget(self.gen_sine_button)
        row2.addWidget(self.gen_send_button)

        row3 = QHBoxLayout()
        self.gen_on_button = QPushButton("Output ON")
        self.gen_off_button = QPushButton("Output OFF")
        self.gen_close_button = QPushButton("Trennen")

        row3.addWidget(self.gen_on_button)
        row3.addWidget(self.gen_off_button)
        row3.addWidget(self.gen_close_button)

        group_layout.addLayout(row1)
        group_layout.addLayout(row2)
        group_layout.addLayout(row3)
        group.setLayout(group_layout)
        main_layout.addWidget(group)

        main_layout.addWidget(QLabel("Log:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(350)
        main_layout.addWidget(self.log_box)

        main_layout.addStretch()
        self.setLayout(main_layout)

    def _connect_signals(self):
        self.gen_connect_button.clicked.connect(self.connect_generator)
        self.gen_id_button.clicked.connect(self.read_generator_id)
        self.gen_sine_button.clicked.connect(self.set_generator_sine)
        self.gen_send_button.clicked.connect(self.send_generator_values)
        self.gen_on_button.clicked.connect(self.generator_output_on)
        self.gen_off_button.clicked.connect(self.generator_output_off)
        self.gen_close_button.clicked.connect(self.disconnect_generator)

    def log(self, text):
        self.log_box.append(text)

    def connect_generator(self):
        try:
            resource = self.resource_edit.text().strip()

            if not resource:
                raise ValueError("Bitte GPIB-Ressource eingeben.")

            self.generator = TektronixAFG320(resource)
            self.generator.connect()

            self.log(f"Generator verbunden: {resource}")

        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def read_generator_id(self):
        try:
            if self.generator is None:
                raise RuntimeError("Generator ist noch nicht verbunden.")
            self.log(f"Generator ID: {self.generator.identify()}")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def set_generator_sine(self):
        try:
            if self.generator is None:
                raise RuntimeError("Generator ist noch nicht verbunden.")
            self.generator.set_sine()
            self.log("Sinus gesetzt.")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def send_generator_values(self):
        try:
            if self.generator is None:
                raise RuntimeError("Generator ist noch nicht verbunden.")

            freq = float(self.freq_edit.text())
            amp = float(self.amp_edit.text())

            if amp < 0 or amp > 1.0:
                raise ValueError("Amplitude muss zwischen 0.0 und 1.0 V liegen.")

            self.generator.set_output(freq, amp)
            self.log(f"Gesendet: f={freq:.3f} Hz, U={amp:.3f} V")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def generator_output_on(self):
        try:
            if self.generator is None:
                raise RuntimeError("Generator ist noch nicht verbunden.")
            self.generator.output_on()
            self.log("Output ON")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def generator_output_off(self):
        try:
            if self.generator is None:
                raise RuntimeError("Generator ist noch nicht verbunden.")
            self.generator.output_off()
            self.log("Output OFF")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def disconnect_generator(self):
        try:
            if self.generator is not None:
                self.generator.close()
                self.generator = None
                self.log("Generator getrennt.")
        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))

    def cleanup(self):
        self.disconnect_generator()


class SignalAnalysisScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_f0 = DEFAULT_MEASUREMENT_F0
        self.focusrite = None
        self.devices = []
        self.num_channels = NUM_CHANNELS
        self.window_seconds = WINDOW_SECONDS
        self.live_elapsed_samples = 0

        self.plot_buffers = [] # Speicher für die Zeitplots, wird bei Start oder Aufnahme aktualisiert
        self.time_axis = np.array([], dtype=np.float32) # Zeitachse für die Zeitplots, wird bei Start oder Aufnahme aktualisiert    
        self.time_plot_widgets = []
        self.time_plot_curves = [] # Referenzen auf die PlotDataItem-Objekte der Zeitplots, damit wir die Daten schnell aktualisieren können

        self.fft_freq_axis = np.array([], dtype=np.float32)
        self.fft_buffers = []
        self.fft_plot_widgets = []
        self.fft_plot_curves = []
        self.open_plot_windows = []
        self.log_dialog = LogDialog(parent=self)
        self.results_dialog = None
        self.last_recording = None
        self.last_chunk = None
        self.last_mode = None

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_audio_plot)

        self._build_ui()
        self._connect_signals()
        self._reset_plot_storage()
        self.refresh_focusrite_devices()
        

    def _build_ui(self):
        main_layout = QVBoxLayout()

        top_layout = QHBoxLayout()
        main_layout.addLayout(top_layout)
        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        

        group = QGroupBox("Signalquelle und Eingang")
        group_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems([SOURCE_SIMULATION, SOURCE_SCARLETT])
        self.source_combo.setCurrentText(SOURCE_SIMULATION)
        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["44100", "48000", "88200", "96000"])
        self.sample_rate_combo.setCurrentText("48000")
        row1.addWidget(QLabel("Signalquelle"))
        row1.addWidget(self.source_combo)
        row1.addWidget(QLabel("Sample Rate [Hz]"))
        row1.addWidget(self.sample_rate_combo)
        row1.addStretch()

        row2 = QHBoxLayout()
        self.device_combo = QComboBox() # Wird später mit den verfügbaren Focusrite-Eingabegeräten gefüllt
        self.refresh_focusrite_button = QPushButton("Eingabegeräte aktualisieren")
        row2.addWidget(QLabel("Eingabegerät"))
        row2.addWidget(self.device_combo)
        row2.addWidget(self.refresh_focusrite_button)

        row3 = QHBoxLayout()
        self.audio_start_button = QPushButton("Live Start")
        self.audio_stop_button = QPushButton("Stop")
        self.record_button = QPushButton("1 s aufnehmen")
        self.show_log_button = QPushButton("Log anzeigen")
        self.show_results_button = QPushButton("Ergebnisse anzeigen")

        row3.addWidget(self.audio_start_button)
        row3.addWidget(self.audio_stop_button)
        row3.addWidget(self.record_button)
        row3.addWidget(self.show_log_button)
        row3.addWidget(self.show_results_button)
        
        group_layout.addLayout(row1)
        group_layout.addLayout(row2)
        group_layout.addLayout(row3)
        group.setLayout(group_layout)
        main_layout.addWidget(group)

        hint = QLabel(
            f"Es wird {MEASUREMENT_DURATION} Sekunde gemessen. Im Zeitplot werden nur {DISPLAY_PERIODS} "
            f"Periode(n) angezeigt, damit Phasenverschiebungen besser sichtbar sind."
        )
        main_layout.addWidget(hint)

        for ch in range(self.num_channels):
            time_plot = pg.PlotWidget(title=f"Zeit Signal - Mikrofon {ch + 1}")
            time_plot.setLabel("bottom", "Zeit [sek]")
            time_plot.setLabel("left", "V")
            time_plot.getAxis("left").enableAutoSIPrefix(False)
            time_plot.showGrid(x=True, y=False)
            time_plot.setMouseEnabled(x=True, y=False)
            time_curve = time_plot.plot([], [], pen="y")
            time_plot.scene().sigMouseClicked.connect(
                lambda event, ch=ch: self.open_time_window(ch)
            )

            fft_plot = pg.PlotWidget(title=f"FFT Betrag - Mikrofon {ch + 1}")
            fft_plot.setLabel("bottom", "Frequenz [Hz]")
            fft_plot.setLabel("left", "|FFT|")
            fft_plot.getAxis("left").enableAutoSIPrefix(False)
            fft_plot.showGrid(x=True, y=False)
            fft_plot.setMouseEnabled(x=True, y=False)
            fft_curve = fft_plot.plot([], [], pen="y")
            fft_plot.setXRange(0, FFT_MAX_FREQ)
            fft_plot.scene().sigMouseClicked.connect(
                lambda event, ch=ch: self.open_fft_window(ch)
            )

            self.time_plot_widgets.append(time_plot)
            self.time_plot_curves.append(time_curve)
            self.fft_plot_widgets.append(fft_plot)
            self.fft_plot_curves.append(fft_curve)

            row = QHBoxLayout()
            row.addWidget(time_plot)
            row.addWidget(fft_plot)
            main_layout.addLayout(row)

        self.setLayout(main_layout)

    def _connect_signals(self):
                self.source_combo.currentTextChanged.connect(self.on_source_changed)
                self.refresh_focusrite_button.clicked.connect(self.refresh_focusrite_devices)
                self.audio_start_button.clicked.connect(self.start_audio)
                self.audio_stop_button.clicked.connect(self.stop_audio)
                self.record_button.clicked.connect(lambda: self.record_for_time(MEASUREMENT_DURATION))
                self.sample_rate_combo.currentTextChanged.connect(self.refresh_time_axis_only)
                self.show_log_button.clicked.connect(self.show_log_window)
                self.show_results_button.clicked.connect(self.show_results_window)

    def show_results_window(self):
            if not hasattr(self, "results_dialog") or self.results_dialog is None:
                QMessageBox.information(
                    self,
                    "Keine Ergebnisse",
                    "Bitte zuerst eine Messung aufnehmen."
                )
                return

            self.results_dialog.show()
            self.results_dialog.raise_()
            self.results_dialog.activateWindow()  

    def show_log_window(self):
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def log(self, text):
        self.log_dialog.append(text)

    def on_source_changed(self):
        self.refresh_focusrite_devices()

    def _get_source_mode(self):
        return self.source_combo.currentText().strip()

    def _using_simulation(self):
        return self._get_source_mode() == SOURCE_SIMULATION

    def _get_sample_rate(self):
        try:
            return float(self.sample_rate_combo.currentText())
        except Exception:
            return 48000.0

    def _get_f0(self):
        if self.current_f0 is None:
            raise ValueError("Keine aktuelle Messfrequenz gesetzt.")

        if self.current_f0 <= 0:
            raise ValueError("Messfrequenz muss größer als 0 Hz sein.")

        return float(self.current_f0)

    def _generate_simulated_signal(self):
        sample_rate = self._get_sample_rate()
        n = int(round(sample_rate * MEASUREMENT_DURATION)) # Anzahl Samples für 1 Sekunde
        t = np.arange(n, dtype=np.float64) / sample_rate # Zeitvektor für 1 Sekunde

        f0 = self._get_f0()
        k = 2.0 * np.pi * f0 / SPEED_OF_SOUND # Wellenzahl k = 2πf/c

        # Beispiel: bekannte hinlaufende und rücklaufende Welle
        A_sim = 1.0e-4 * np.exp(1j * 0.2) # Einlaufende Welle mit Amplitude 1e-4 Pa und Phase 0.2 rad
        B_sim = 3.0e-5 * np.exp(-1j * 0.7) # Rücklaufende Welle mit Amplitude 3e-5 Pa und Phase -0.7 rad

        positions = [MIC_X1, MIC_X2, MIC_X3]
        audio = np.zeros((n, self.num_channels), dtype=np.float64)

        rng = np.random.default_rng(12345)
        noise_level = 2.0e-6

        for ch, x in enumerate(positions):
            P = A_sim * np.exp(-1j * k * x) + B_sim * np.exp(1j * k * x) # A* e^(-j k x) + B * e^(j k x)
            amp = np.abs(P) /2 # 2, da die Amplitude der hinlaufenden oder rücklaufenden Welle jeweils nur die Hälfte der Gesamtamplitude ausmacht
            phase = np.angle(P) # Phase der Gesamtwelle an diesem Mikrofon

            audio[:, ch] = amp * np.cos(2.0 * np.pi * f0 * t + phase) # + Rauschanteil
            audio[:, ch] += noise_level * rng.standard_normal(n) # Weißes Rauschen mit definierter Amplitude

        return audio.astype(np.float32)

    def _reset_plot_storage(self):
        sample_rate = self._get_sample_rate()
        window_samples = max(2, int((self.window_seconds * sample_rate)))

        self.plot_buffers = [
            np.zeros(window_samples, dtype=np.float32)
            for _ in range(self.num_channels)
        ]
        # np.linspace(von 0.0, bis 1.0, Scritte 48000, endpoint=False)
        self.time_axis = np.linspace(
            0.0,
            self.window_seconds,
            window_samples,
            endpoint=False,
            dtype=np.float32,
        )

        self.fft_freq_axis = np.array([], dtype=np.float32)
        self.fft_buffers = [
            np.array([], dtype=np.float32)
            for _ in range(self.num_channels)
        ]

        self._refresh_time_plots()
        self._refresh_fft_plots()

    def _refresh_time_plots(self):
        if not self.time_plot_curves:
            return
        for ch in range(self.num_channels):
            self.time_plot_curves[ch].setData(self.time_axis, self.plot_buffers[ch])

    def _refresh_fft_plots(self):
        if not self.fft_plot_curves:
            return
        for ch in range(self.num_channels):
            self.fft_plot_curves[ch].setData(self.fft_freq_axis, self.fft_buffers[ch])
            if len(self.fft_freq_axis) > 0:
                self.fft_plot_widgets[ch].setXRange(0, FFT_MAX_FREQ)

    def refresh_time_axis_only(self):
        self.live_elapsed_samples = 0
        self._reset_plot_storage()

    def refresh_focusrite_devices(self):
        try:
            self.device_combo.clear()

            if self._using_simulation():
                self.devices = []
                self.device_combo.addItem("Simulation")
                
                return

            temp = FocusriteInterface()
            self.devices = temp.list_focusrite_input_devices()

            if not self.devices:
                self.log("Kein Eingabegerät gefunden.")
                return

            for idx, name, ch in self.devices:
                self.device_combo.addItem(f"Index {idx} | {ch} Eingänge | {name}")
                self.log(f"Gefundenes Eingabegerät: index={idx}, name={name}, inputs={ch}")

            self.device_combo.setCurrentIndex(0)
            self.log("Eingabegeräte aktualisiert.")
        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))

    def get_selected_device_index(self):
        if self._using_simulation():
            return None

        current_index = self.device_combo.currentIndex()

        if current_index < 0 or current_index >= len(self.devices):
            return None

        device_index, _, _ = self.devices[current_index]
        return device_index

    def _create_focusrite(self):
        device_idx = self.get_selected_device_index()
        if device_idx is None:
            raise ValueError("Bitte ein Eingabegerät auswählen.")

        return FocusriteInterface(
            sample_rate=int(self._get_sample_rate()),
            device=device_idx,
            channels=self.num_channels,
        )

    def _get_source_signal(self):
        if self.last_mode == "record" and self.last_recording is not None:
            return self.last_recording

        if self.last_mode == "live" and self.last_chunk is not None:
            return self.last_chunk

        return None

    def start_audio(self):
        try:
            self.timer.stop()

            if self.focusrite is not None:
                self.focusrite.stop_input_stream()
                self.focusrite = None

            self.live_elapsed_samples = 0
            self._reset_plot_storage()

            if self._using_simulation():
                signal = self._generate_simulated_signal()

                self.last_chunk = signal
                self.last_mode = "live"

                f0 = self._get_f0()
                self.update_time_plots(signal, f0)
                self.compute_fft_from_signal(signal)

                self.log("Simulierter Live-Block erzeugt.")
                return

            self.focusrite = self._create_focusrite()
            used_device = self.focusrite.start_input_stream()

            self.last_mode = "live"
            self.timer.start(100)

            self.log(
                f"Live-Stream gestartet: Gerät={used_device}, "
                f"fs={self.focusrite.sample_rate}, "
                f"blocksize={self.focusrite.blocksize}, "
                f"Kanäle=1-{self.num_channels}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))
            
    def stop_audio(self):
        try:
            self.timer.stop()
            if self.focusrite is not None:
                self.focusrite.stop_input_stream()
                self.focusrite = None
            self.log("Live-Stream gestoppt.")
        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))

    def update_time_plots(self, signal, f0):
        sample_rate = self._get_sample_rate()
        num_samples = signal.shape[0]

        samples_per_period = int(round(sample_rate / f0))
        display_samples = int(DISPLAY_PERIODS * samples_per_period)
        display_samples = max(2, min(display_samples, num_samples))

        x = signal[:, 0]  # Mikrofon 1 als Referenz

        # Erste 20 ms überspringen, damit Start-Spitze weg ist
        search_start = int(0.1 * sample_rate)
        search_start = min(search_start, max(0, num_samples - display_samples))

        start = search_start

        # Nulldurchgang mit positiver Steigung suchen
        max_search = num_samples - display_samples - 1

        for i in range(search_start, max_search):
            if x[i] <= 0 and x[i + 1] > 0:
                start = i
                break

        end = start + display_samples

        self.time_axis = np.arange(display_samples, dtype=np.float32) / sample_rate

        for ch in range(self.num_channels):
            self.plot_buffers[ch] = signal[start:end, ch]
            self.time_plot_curves[ch].setData(self.time_axis, self.plot_buffers[ch])
            self.time_plot_widgets[ch].setXRange(0, display_samples / sample_rate, padding=0)
            
    def log_microphone_results(self, m, f0):
        phase_ref = m["phase1"]

        for i in range(1, self.num_channels + 1):
            phase_shift = m[f"phase{i}"] - phase_ref
            phase_shift_deg = np.degrees(phase_shift)
            time_shift_ms = phase_shift / (2.0 * np.pi * f0) * 1000.0

            self.log(
                f"Mikrofon {i}: "
                f"|P{i}| = {m[f'amp{i}']:.6e}, "
                f"Phase = {m[f'phase{i}']:.6f} rad, "
                f"RMS = {m[f'rms{i}']:.6e}, "
                f"Phasenverschiebung zu Mikrofon 1 = {phase_shift:.6f} rad "
                f"({phase_shift_deg:.2f}°), "
                f"Zeitverschiebung = {time_shift_ms:.3f} ms"
            )
    def log_forward_reflected_waves(self, m, f0):
        cfg = self._get_wave_config()
        freqs = np.array([f0], dtype=float)

        A, B, residual = estimate_forward_reflected_three_mics_ls(
            np.array([m["P1"]], dtype=complex),
            np.array([m["P2"]], dtype=complex),
            np.array([m["P3"]], dtype=complex),
            freqs,
            cfg,
        )

        A0 = A[0]
        B0 = B[0]

        self.log("Hinlaufende / rücklaufende Welle:")
        self.log(f"A = {A0}")
        self.log(f"|A| = {np.abs(A0):.6e}")
        self.log(f"Phase A = {np.angle(A0):.6f} rad")
        self.log(f"B = {B0}")
        self.log(f"|B| = {np.abs(B0):.6e}")
        self.log(f"Phase B = {np.angle(B0):.6f} rad")
        self.log(f"Reflexion |B| / |A| = {np.abs(B0) / (np.abs(A0) + 1e-12):.6f}")
        self.log(f"Residuum = {residual[0]:.6e}")

    def record_for_time(self, duration=None):
        try:
            # PySide6 clicked-Signal kann False übergeben.
            # Deshalb bool/None abfangen und auf Standarddauer setzen.
            if duration is None:
                duration = MEASUREMENT_DURATION
                self.log(f"Aufnahme gestartet: Dauer={duration:.3f} s")

            duration = float(duration)

            if duration <= 0:
                raise ValueError(f"Aufnahmedauer muss größer als 0 sein. duration={duration}")

            self.timer.stop()

            if self.focusrite is not None:
                self.focusrite.stop_input_stream()
                self.focusrite = None

            if self._using_simulation():
                signal = self._generate_simulated_signal()
            else:
                self.focusrite = self._create_focusrite()
                signal = self.focusrite.record_input(duration=duration)

            signal = np.asarray(signal, dtype=np.float32)

            if signal.size == 0:
                raise ValueError(
                    "Leeres Signal: Die Aufnahme hat 0 Samples geliefert. "
                    "Prüfe Scarlett-Eingang, macOS-Mikrofonberechtigung und Sample-Rate."
                )

            if signal.ndim == 1:
                signal = signal[:, np.newaxis]

            if signal.shape[0] < 2:
                raise ValueError(
                    f"Signal ist zu kurz. Samples={signal.shape[0]}"
                )

            if signal.shape[1] < self.num_channels:
                raise ValueError(
                    f"Für die Auswertung werden {self.num_channels} Eingangskanäle benötigt. "
                    f"Das Gerät liefert nur {signal.shape[1]}."
                )

            self.last_recording = signal
            self.last_mode = "record"

            f0 = self._get_f0()
            num_samples = signal.shape[0]
            sample_rate = self._get_sample_rate()

            self.update_time_plots(signal, f0)

            freq_resolution = sample_rate / num_samples
            self.log(f"Aufnahme abgeschlossen: Dauer={duration:.0f} s")
            self.log(f"Samples pro Mikrofon: {num_samples}")
            self.log(f"Sample-Rate: {sample_rate:.1f} Hz")
            self.log(f"Messfrequenz: {f0:.2f} Hz")
            self.log(f"Frequenzauflösung Δf = fs / N = 1 / T = {freq_resolution:.3f} Hz")

            self.log("-" * 100)

            m = self.measure_three_mics_at_frequency_local(signal, f0)

            self.log_microphone_results(m, f0)
            self.log("-" * 100)

            self.log_forward_reflected_waves(m, f0)
            self.log("-" * 100)

            self.compute_fft_from_signal(signal)
            self.log("#" * 100)

            mic_results = self.build_mic_result_dict(m, f0)
            self.results_dialog = ComplexResultsDialog(mic_results, parent=self)

            return m

        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))
            return None
    
    def compute_fft_from_signal(self, signal):
        try:
            signal = np.asarray(signal, dtype=np.float64)

            if signal.ndim == 1:
                signal = signal[:, np.newaxis]

            if signal.shape[1] < self.num_channels:
                raise ValueError(
                    f"Für FFT werden {self.num_channels} Kanäle benötigt. "
                    f"Vorhanden: {signal.shape[1]}."
                )

            sample_rate = self._get_sample_rate()
            f0 = self._get_f0()
            n = signal.shape[0] # Anzahl Samples, die in der Aufnahme enthalten sind (z.B. 48000 für 1 Sekunde bei 48 kHz)

            if n < 2:
                raise ValueError("Signal ist zu kurz für FFT.")

            freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate) # Frequenzachsenwerte
            self.fft_freq_axis = freqs.astype(np.float32)
            window = np.hanning(n) # Hanning-Fenster
            window_norm = np.sum(window) # Normierungskonstante

            self.fft_buffers = []
            f0_index = int(np.argmin(np.abs(freqs - f0)))

            for ch in range(self.num_channels):
                
                '''
                    x = signal[:, ch]           # reelle Messwerte vom Mikrofon
                    spectrum = np.fft.rfft(x)   # komplexe Frequenzwerte
                    amp = np.abs(spectrum)      # Betrag / Amplitude
                    phase = np.angle(spectrum)  # Phase
                    np.abs(spectrum)            → Betrag der FFT
                    2.0                         → Korrektur, weil nur positive Frequenzen
                    /window_norm                → Korrektur wegen Hanning-Fenster
                '''

                x = signal[:, ch]
                spectrum = np.fft.rfft(x * window) # Hanning-Fenster anwenden und FFT berechnen damit die Amplituden korrekt bleiben, 

                '''
                spectrum enthält für jede Frequenzlinie einen komplexen Wert:
                Realteil + Imaginärteil j
                '''
                amp = 2.0 * np.abs(spectrum) / window_norm # da wir nur die positiven Frequenzen betrachten, müssen wir mit 2.0 multiplizieren, um die korrekte Amplitude zu erhalten
                self.fft_buffers.append(amp.astype(np.float32))
                self.log(
                    f"Mikrofon {ch + 1},FFT-Amplitude bei {freqs[f0_index]:.1f} Hz = {amp[f0_index]:.6e}"
                )
                

            self._refresh_fft_plots()
            self.log("#" * 100) 
            # 10 FFT-Werte um die Messfrequenz f0 loggen
            half_window = 5
            start_idx = max(0, f0_index - half_window)
            end_idx = min(len(freqs), f0_index + half_window + 1)

            self.log(f"{'Index':>10} | {'Frequenz [Hz]':>18} | {'Abstand zu f0 [Hz]':>18} | {'Amplitude [V]':>18}")
            self.log("-" * 100)

            for idx in range(start_idx, end_idx):
                freq = freqs[idx]
                distance_to_f0 = freq - f0
                self.log(
                    f"{idx:10d} | "
                    f"{freq:18.3f} | "
                    f"{distance_to_f0:18.3f} | "
                    f"{amp[idx]:18.6e}"
                )

            self.log("-" * 100)
        except Exception as e:
            QMessageBox.critical(self, "FFT-Fehler", str(e)) 

    def update_audio_plot(self):
            if self.focusrite is None:
                return

            updated = False

            while not self.focusrite.audio_queue.empty():
                kind, payload = self.focusrite.audio_queue.get()

                if kind == "status":
                    self.log(f"Audio-Status: {payload}")
                    continue

                if kind == "audio":
                    chunk = np.asarray(payload, dtype=np.float32)

                    if chunk.ndim == 1:
                        chunk = chunk[:, np.newaxis]

                    if chunk.shape[1] < self.num_channels:
                        self.log(f"Warnung: nur {chunk.shape[1]} Kanäle empfangen.")
                        continue

                    self.last_chunk = chunk
                    self.last_mode = "live"

                    # Für Live: letzte Samples direkt anzeigen
                    f0 = self._get_f0()
                    sample_rate = self._get_sample_rate()

                    display_seconds = DISPLAY_PERIODS / f0
                    display_samples = int(round(display_seconds * sample_rate))
                    display_samples = max(2, min(display_samples, chunk.shape[0]))

                    self.time_axis = np.arange(display_samples, dtype=np.float32) / sample_rate

                    for ch in range(self.num_channels):
                        self.plot_buffers[ch] = chunk[-display_samples:, ch]
                        self.time_plot_curves[ch].setData(self.time_axis, self.plot_buffers[ch])
                        self.time_plot_widgets[ch].setXRange(0, display_seconds, padding=0)

                    updated = True

            if updated:
                self._refresh_time_plots()

    def measure_at_frequency_local(self, signal, f0):
        signal = np.asarray(signal, dtype=np.float64).flatten() # Sicherstellen, dass es ein 1D-Array ist

        if signal.size == 0:
            raise ValueError("Leeres Signal.")

        if f0 <= 0:
            raise ValueError("f0 muss größer als 0 sein.")

        n = signal.size # Anzahl Samples im Signal (z.B. 48000 für 1 Sekunde bei 48 kHz)
        t = np.arange(n, dtype=np.float64) / self._get_sample_rate() # Zeitachse für die Samples

        ref = np.exp(-1j * 2.0 * np.pi * f0 * t) # Komplexe Referenzschwingung mit Frequenz f0, die über die Zeit läuft
        P = (2.0 / n) * np.sum(signal * ref) # Komplexe Amplitude der Schwingung bei f0, normiert mit 2/n wegen der Amplitudenanpassung (siehe FFT-Berechnung)

        amplitude = np.abs(P)
        phase = np.angle(P)
        rms = np.sqrt(np.mean(signal ** 2))

        return P, amplitude, phase, rms

    def measure_three_mics_at_frequency_local(self, signal, f0):
        signal = np.asarray(signal, dtype=np.float64)

        if signal.ndim == 1:
            signal = signal[:, np.newaxis]

        if signal.shape[1] < self.num_channels:
            raise ValueError(
                f"Es werden {self.num_channels} Kanäle benötigt. "
                f"Vorhanden: {signal.shape[1]}."
            )

        P1, amp1, phase1, rms1 = self.measure_at_frequency_local(signal[:, 0], f0)
        P2, amp2, phase2, rms2 = self.measure_at_frequency_local(signal[:, 1], f0)
        P3, amp3, phase3, rms3 = self.measure_at_frequency_local(signal[:, 2], f0)

        return {
            "P1": P1, "P2": P2, "P3": P3,
            "amp1": amp1, "amp2": amp2, "amp3": amp3,
            "phase1": phase1, "phase2": phase2, "phase3": phase3,
            "rms1": rms1, "rms2": rms2, "rms3": rms3,
        }

    
    def open_time_window(self, ch):
        if ch < 0 or ch >= self.num_channels:
            return
        if len(self.time_axis) == 0 or len(self.plot_buffers[ch]) == 0:
            return

        dialog = SignalPlotDialog(
            title=f"Zeit Signal - Mikrofon {ch + 1}",
            x=self.time_axis.copy(),
            y=np.asarray(self.plot_buffers[ch]).copy(),
            xlabel="Zeit [sek]",
            ylabel="V",
            parent=self,
        )
        dialog.show()
        self.open_plot_windows.append(dialog)

    def open_fft_window(self, ch):
        if ch < 0 or ch >= self.num_channels:
            return
        if len(self.fft_freq_axis) == 0 or len(self.fft_buffers[ch]) == 0:
            return

        dialog = SignalPlotDialog(
            title=f"FFT Betrag - Mikrofon {ch + 1}",
            x=self.fft_freq_axis.copy(),
            y=np.asarray(self.fft_buffers[ch]).copy(),
            xlabel="Frequenz [Hz]",
            ylabel="|FFT|",
            parent=self,
        )
        dialog.plot_widget.setXRange(0, FFT_MAX_FREQ)
        dialog.show()
        self.open_plot_windows.append(dialog)

    def _get_wave_config(self):
        positions = [MIC_X1, MIC_X2, MIC_X3]
        if SPEED_OF_SOUND <= 0:
            raise ValueError("SPEED_OF_SOUND muss größer als 0 sein.")
        if len(set(positions)) != 3:
            raise ValueError("MIC_X1, MIC_X2 und MIC_X3 müssen unterschiedlich sein.")
        return SimpleNamespace(c=SPEED_OF_SOUND, x1=MIC_X1, x2=MIC_X2, x3=MIC_X3)

    def cleanup(self):
        self.stop_audio()

    def build_mic_result_dict(self, m, f0):
        phase_ref = m["phase1"]
        result = {}

        for i in range(1, 4):
            phase_shift = m[f"phase{i}"] - phase_ref
            phase_shift_deg = np.degrees(phase_shift)
            time_shift_ms = phase_shift / (2.0 * np.pi * f0) * 1000.0

            result[f"P{i}"] = m[f"P{i}"]
            result[f"amp{i}"] = m[f"amp{i}"]
            result[f"phase{i}"] = m[f"phase{i}"]
            result[f"rms{i}"] = m[f"rms{i}"]
            result[f"phase_shift{i}"] = phase_shift
            result[f"phase_shift_deg{i}"] = phase_shift_deg
            result[f"time_shift_ms{i}"] = time_shift_ms

        return result
    
    def compute_forward_reflected_results(self, m, f0):
        cfg = self._get_wave_config()
        freqs = np.array([f0], dtype=float)

        A, B, residual = estimate_forward_reflected_three_mics_ls(
            np.array([m["P1"]], dtype=complex),
            np.array([m["P2"]], dtype=complex),
            np.array([m["P3"]], dtype=complex),
            freqs,
            cfg,
        )

        A0 = A[0]
        B0 = B[0]

        return {
            "A": A0,
            "A_abs": np.abs(A0),
            "A_phase": np.angle(A0),
            "B": B0,
            "B_abs": np.abs(B0),
            "B_phase": np.angle(B0),
            "B_over_A": np.abs(B0) / (np.abs(A0) + 1e-12),
            "residual": residual[0],
        }
    
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Akustik-Messsystem")
        self.resize(1500, 1000)

        self.start_screen = StartScreen()
        self.generator_screen = GeneratorScreen()
        self.signal_screen = SignalAnalysisScreen()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.generator_screen)
        self.stack.addWidget(self.signal_screen)

        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.start_screen.generator_button.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.start_screen.signal_button.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        self.generator_screen.back_button.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.signal_screen.back_button.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.start_screen.auto_button.clicked.connect(self.run_automatic_measurement)

    def run_automatic_measurement(self):
        try:
            generator = self.generator_screen.generator

            if generator is None:
                QMessageBox.warning(
                    self,
                    "Generator nicht verbunden",
                    "Bitte zuerst den Generator auf der Generator-Seite verbinden."
                )
                return

            f0 = float(self.generator_screen.freq_edit.text())
            voltage = float(self.generator_screen.amp_edit.text())

            if f0 <= 0:
                raise ValueError("Generatorfrequenz muss größer als 0 Hz sein.")

            if voltage <= 0 or voltage > MAX_GENERATOR_VOLTAGE:
                raise ValueError("Generatorspannung muss größer 0 und maximal 1.0 V sein.")

            self.signal_screen.current_f0 = f0
            self.signal_screen.source_combo.setCurrentText(SOURCE_SCARLETT)
            self.signal_screen.refresh_focusrite_devices()

            self.stack.setCurrentWidget(self.signal_screen)

            generator.set_sine()
            generator.output_on()

            step = 1

            while step <= MAX_AUTO_STEPS:
                generator.set_output(f0, voltage)

                self.signal_screen.log("-" * 100)
                self.signal_screen.log(f"Automatik Schritt {step}")
                self.signal_screen.log(f"Generator: f = {f0:.2f} Hz, U = {voltage:.4f} V")
                m = self.signal_screen.record_for_time()

                if m is None:
                    raise RuntimeError("Messung fehlgeschlagen.")
                
                wave = self.signal_screen.compute_forward_reflected_results(m, f0)
                measured_amp = wave["A_abs"]

                ok, relative_error = amplitude_reached_target(
                    measured_amp,
                    TARGET_AMP,
                    AMP_TOLERANCE,
                )

                self.signal_screen.log(f"Ziel-Amplitude |A| = {TARGET_AMP:.6e}")
                self.signal_screen.log(f"Gemessene hinlaufende Welle |A| = {measured_amp:.6e}")
                self.signal_screen.log(f"Reflexion |B|/|A| = {wave['B_over_A']:.6f}")
                self.signal_screen.log(f"Relativer Fehler = {relative_error:.3f}")

                if ok:
                    self.signal_screen.log("Ziel-Amplitude erreicht.")
                    break

                voltage = update_voltage_from_amplitude(
                    voltage,
                    TARGET_AMP,
                    measured_amp,
                    MIN_GENERATOR_VOLTAGE,
                    MAX_GENERATOR_VOLTAGE,
                )

                self.signal_screen.log(f"Neue Generator-Spannung = {voltage:.4f} V")

                step += 1

            self.signal_screen.record_for_time()
            generator.output_off()
            

        except Exception as e:
            try:
                if self.generator_screen.generator is not None:
                    self.generator_screen.generator.output_off()
            except Exception:
                pass

            QMessageBox.critical(self, "Automatik-Fehler", str(e))
            
    def closeEvent(self, event):
        try:
            self.generator_screen.cleanup()
            self.signal_screen.cleanup()
        finally:
            event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

