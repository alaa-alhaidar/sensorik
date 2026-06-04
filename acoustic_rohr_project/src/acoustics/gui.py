import sys
from pathlib import Path
import time
from types import SimpleNamespace
import sounddevice as sd



import numpy as np
import pyqtgraph as pg

from automation import (
    run_auto_measurement_steps,
    run_frequency_sweep_steps,
)

from estimation import (
    estimate_forward_reflected_three_mics_ls,
)

# PySide6-Importe
from PySide6.QtWidgets import QSpinBox
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
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
)


from generator_interface import SimulatedGenerator
from focusrite_interface import FocusriteInterface
from estimation import estimate_forward_reflected_three_mics_ls
from generator_hdw_panel import TektronixAFG320
from signal_process import (
    build_wave_config,
    process_recorded_signal,
    record_signal,
    measure_at_frequency_by_f0 as sp_measure_at_frequency_by_f0,
    measure_three_mics_at_frequency_by_f0 as sp_measure_three_mics_at_frequency_by_f0,
    compute_fft_from_signal as sp_compute_fft_from_signal,
    compute_forward_reflected_results as sp_compute_forward_reflected_results,
    build_mic_result_dict as sp_build_mic_result_dict,
    format_microphone_logs,
    format_wave_logs,
    prepare_recording_signal,
    
)

# Feste Parameter für die automatische Messung
SWEEP_START_FREQ = 300.0
SWEEP_STOP_FREQ = 2000.0
SWEEP_STEP_FREQ = 53.0

TARGET_AMP = 6.0e-5
AMP_TOLERANCE = 0.05
MAX_AUTO_STEPS = 10
MIN_GENERATOR_VOLTAGE = 0.01
MAX_GENERATOR_VOLTAGE = 2.0
AUTO_STEP_PAUSE_SECONDS = 2.0

NUM_CHANNELS = 3

# Signalquelle
SOURCE_SIMULATION = "Simulation"
SOURCE_SCARLETT = "Audio-Interface"

USE_SIMULATED_GENERATOR = True   # Zuhause / Simulation

# Feste Messparameter
DEFAULT_MEASUREMENT_F0 = 1000.0  # Periode von 1 ms, 0,001 s
MEASUREMENT_DURATION = 1.0   # Standardwert für das Eingabefeld
WINDOW_SECONDS = 1.0          # Standardwert für das Eingabefeld
DISPLAY_PERIODS = 5          # Anzeige: 5 Perioden

# FFT-Anzeige
FFT_MAX_FREQ = 2000
FFT_VIEW_HALF_WIDTH = 200

# Feste Rohr-/Mikrofonparameter
SPEED_OF_SOUND = 344.0
MIC_X1 = -0.050
MIC_X2 = -0.085
MIC_X3 = -0.145

'''
D = 0   → harte Wand, volle Reflexion
D = 1   → volle Absorption, keine Reflexion
D = 0.64 → 64 % Energieverlust, 36 % Reflexion
'''
REFLECTION_FACTOR_SIM = 1.0  # harte Wand

# bei 1000 Hz: 6.4 µV bei 0.2 V Generator-Spannung, BeI 2000 hZ und 500 hZ ist auch ungefähr 6.4 µV
CALIBRATION = {
    1: 6.4,
    2: 6.4,
    3: 6.4,
}

# format_voltage macht aus einem Spannungswert einen schön formatierten String mit Einheiten, z.B. 0.000123 → "123.000 µV"
def format_voltage(value):
    value = float(value)
    abs_value = abs(value)

    if abs_value >= 1.0:
        return f"{value:.4f} V"
    elif abs_value >= 1e-3:
        return f"{value * 1e3:.3f} mV"
    elif abs_value >= 1e-6:
        return f"{value * 1e6:.3f} µV"
    else:
        return f"{value:.6e} V"


'''
Die Klasse SignalPlotDialog ist ein einfaches Dialogfenster, das einen Plot anzeigt. Es wird verwendet, 
um die Zeit-Signal-Daten in einem größeren Fenster darzustellen
'''
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
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.plot(x, y, pen="y")
        self.plot_widget.enableAutoRange(False)  # Automatischer Zoom, damit die Daten gut sichtbar sind
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

'''
Die Klasse LogDialog ist ein Dialogfenster, das eine Tabelle zur Anzeige von Log-Meldungen enthält. Sie bietet eine Methode append(),
mit der neue Log-Einträge hinzugefügt werden können. Jeder Eintrag besteht aus einer Kategorie (z.B. "Info", "Fehler") und einer Meldung.
Die Tabelle hat drei Spalten: eine fortlaufende Nummer, die Kategorie und die eigentliche Meldung. Es gibt auch einen "Zurück"-Button,
um das Dialogfenster zu schließen. Die Tabelle ist so konfiguriert, dass sie nicht bearbeitbar ist und abwechselnd farbige Zeilen zur besseren Lesbarkeit verwendet.
'''
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

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(3)
        self.log_table.setHorizontalHeaderLabels(["Nr.", "Kategorie", "Meldung"])
        self.log_table.verticalHeader().setVisible(False)
        self.log_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.log_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        self.log_table.setAlternatingRowColors(True)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.log_table)
        self.setLayout(layout)

    def append(self, text, category="Info"):
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)

        if category == "title":
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignCenter)
            item.setBackground(Qt.blue)
            item.setForeground(Qt.white)

            self.log_table.setSpan(row, 0, 1, 3)
            self.log_table.setItem(row, 0, item)
            self.log_table.scrollToBottom()
            return

        self.log_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.log_table.setItem(row, 1, QTableWidgetItem(category))
        self.log_table.setItem(row, 2, QTableWidgetItem(str(text)))

        self.log_table.scrollToBottom()

'''
Die Klasse ComplexResultsDialog ist ein Dialogfenster, das die komplexen Schalldruck-Amplituden der drei Mikrofone anzeigt.
Für jedes Mikrofon gibt es einen eigenen Plot, der den Real- und Imaginärteil der Amplitude als Punkt in der komplexen Ebene darstellt.
Zusätzlich werden unter jedem Plot detaillierte Informationen zum Spektrum bei der Messfrequenz, Real- und Imaginärteil, Betrag, Phase, RMS-Wert,
Phasenverschiebung und Zeitverschiebung angezeigt.
'''
class ComplexResultsDialog(QDialog):
    def __init__(self, mic_results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Messergebnisse")
        self.resize(1600, 1000)

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
            abs((mic_results["P1"] * 1e6).real),
            abs((mic_results["P1"] * 1e6).imag),
            abs((mic_results["P2"] * 1e6).real),
            abs((mic_results["P2"] * 1e6).imag),
            abs((mic_results["P3"] * 1e6).real),
            abs((mic_results["P3"] * 1e6).imag),
            1.0,
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
            plot.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

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
            plot.plot(
                [P_plot.real],
                [P_plot.imag],
                pen="r",
                symbol="o",
                symbolSize=5,
                symbolBrush="r",
                thickness=3,
            )

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

'''
Die Klasse StartScreen ist das Hauptmenü der Anwendung, das drei große Buttons für die verschiedenen Funktionen bietet: "Automatische Messung",
"Signalgenerator" und "Signalanalyse".
'''
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

        self.auto_button = QPushButton(
            "Automatische Messung\n(Generator + Audio-Interface)"
        )
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

'''
Die Klasse GeneratorScreen ist die Benutzeroberfläche zur Steuerung des Signalgenerators. 
Sie bietet Eingabefelder für die GPIB-Ressource, Frequenz und Amplitude,
'''
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

            if USE_SIMULATED_GENERATOR:
                self.generator = SimulatedGenerator()
                self.generator.connect()
                self.log("Simulierter Generator verbunden.")
            else:
                self.generator = TektronixAFG320(resource)
                self.generator.connect()
                self.log(f"Hardware-Generator verbunden: {resource}")

        except Exception as e:
            QMessageBox.critical(self, "Generator-Fehler", str(e))
            

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

'''
Die Klasse SignalAnalysisScreen ist die Hauptbenutzeroberfläche für die Signalanalyse. Sie bietet Optionen zur Auswahl der Signalquelle
(Simulation oder Audio-Interface),
'''
class SignalAnalysisScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
      
        
        self.current_f0 = DEFAULT_MEASUREMENT_F0
        self.focusrite = None
        self.devices = []
        self.num_channels = NUM_CHANNELS
        self.window_seconds = WINDOW_SECONDS
        self.live_elapsed_samples = 0

        self.plot_buffers = (
            []
        )  # Speicher für die Zeitplots, wird bei Start oder Aufnahme aktualisiert
        self.time_axis = np.array(
            [], dtype=np.float32
        )  # Zeitachse für die Zeitplots, wird bei Start oder Aufnahme aktualisiert
        self.time_plot_widgets = []
        self.time_plot_curves = (
            []
        )  # Referenzen auf die PlotDataItem-Objekte der Zeitplots, damit wir die Daten schnell aktualisieren können

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
        self.get_f0_from_gui = None

        self.timer = QTimer()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_live_plot)

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
        self.source_combo.setCurrentText(SOURCE_SCARLETT)

        self.sample_rate_combo = QComboBox()
        self.sample_rate_combo.addItems(["44100", "48000", "88200", "96000"])
        self.sample_rate_combo.setCurrentText("48000")

        self.measurement_duration_edit = QLineEdit(str(MEASUREMENT_DURATION))
        self.measurement_duration_edit.setMaximumWidth(80)

        self.display_periods_spin = QSpinBox()
        self.display_periods_spin.setRange(1, 100)
        self.display_periods_spin.setValue(DISPLAY_PERIODS)
        self.display_periods_spin.setMaximumWidth(200)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(400)
        self.device_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.device_combo.setMinimumContentsLength(45)

        self.refresh_focusrite_button = QPushButton("Eingabegeräte aktualisieren")

        row1.addWidget(QLabel("Signalquelle"))
        row1.addWidget(self.source_combo)

        row1.addWidget(QLabel("Sample Rate [Hz]"))
        row1.addWidget(self.sample_rate_combo)

        row1.addWidget(QLabel("Aufnahmezeit [s]"))
        row1.addWidget(self.measurement_duration_edit)

        row1.addWidget(QLabel("Anzeige ∿ "))
        row1.addWidget(self.display_periods_spin)

        row1.addWidget(QLabel("Eingabegerät"))
        row1.addWidget(self.device_combo)

        row1.addWidget(self.refresh_focusrite_button)
     

        self.f0_detected_label = QLabel("gefunden: - Hz")
        row1.addWidget(self.f0_detected_label)

        row1.addStretch()

        row3 = QHBoxLayout()
        self.audio_start_button = QPushButton("▶ Live")
        self.audio_stop_button = QPushButton("■ Stop")
        self.record_button = QPushButton("● Aufnahme")
        self.show_log_button = QPushButton("📋 Log")
        self.show_results_button = QPushButton("Komplexspektrum anzeigen")
        self.auto_start_button = QPushButton("⚙ Automation")
        self.sweep_button = QPushButton("↻ Frequenzschleife")
        self.show_sweep_plot_button = QPushButton("📈 Dissipation")
    

        row3.addWidget(self.audio_start_button)
        row3.addWidget(self.audio_stop_button)
        row3.addWidget(self.record_button)
        row3.addWidget(self.show_log_button)
        row3.addWidget(self.show_results_button)
        row3.addWidget(self.auto_start_button)
        row3.addWidget(self.sweep_button)
        row3.addWidget(self.show_sweep_plot_button)
        

        group_layout.addLayout(row1)
        group_layout.addLayout(row3)
        group.setLayout(group_layout)
        main_layout.addWidget(group)

        hint = QLabel("längere Aufnahmezeit → mehr Samples N → kleinere Δf → feinere Frequenzauflösung")
        main_layout.addWidget(hint)

        for ch in range(self.num_channels):
            time_plot = pg.PlotWidget(title=f"Zeit Signal - Mikrofon {ch + 1}")
            time_plot.setLabel("bottom", "Zeit [sek]")
            time_plot.setLabel("left", "V")
            time_plot.getAxis("left").enableAutoSIPrefix(False)
            time_plot.showGrid(x=True, y=True)
            time_plot.setMouseEnabled(x=True, y=False)
            time_curve = time_plot.plot([], [], pen="y")
            time_plot.scene().sigMouseClicked.connect(
                lambda event, ch=ch: self.open_time_window(ch)
            )

            fft_plot = pg.PlotWidget(title=f"FFT Betrag - Mikrofon {ch + 1}")
            fft_plot.setLabel("bottom", "Frequenz [Hz]")
            fft_plot.setLabel("left", "|FFT|")
            fft_plot.getAxis("left").enableAutoSIPrefix(False)
            fft_plot.showGrid(x=True, y=True)
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
        self.record_button.clicked.connect(self.on_record_clicked)
        self.sample_rate_combo.currentTextChanged.connect(self.refresh_time_axis_only)
        self.show_log_button.clicked.connect(self.show_log_window)
        self.show_results_button.clicked.connect(self.show_results_window)
        self.measurement_duration_edit.editingFinished.connect(self.refresh_time_axis_only)



    def set_fft_xrange_around_f0(self, f0=None):
        if f0 is None:
            f0 = self._get_f0()

        f0 = float(f0)
        sample_rate = self._get_sample_rate()
        nyquist = sample_rate / 2.0

        x_min = max(0.0, f0 - FFT_VIEW_HALF_WIDTH)
        x_max = min(nyquist, f0 + FFT_VIEW_HALF_WIDTH)

        for plot in self.fft_plot_widgets:
            plot.setXRange(x_min, x_max, padding=0)

    # Simulation Generator
    def _get_simulated_generator_values(self):
        """
        Holt Frequenz und Spannung vom simulierten Generator.
        Falls kein Generator verbunden ist, werden Standardwerte benutzt.
        """
        f0 = self._get_f0()
        voltage = 0.2
        output_enabled = True

        if self.get_generator is not None:
            generator = self.get_generator()

            if generator is not None:
                if hasattr(generator, "frequency_hz"):
                    f0 = float(generator.frequency_hz)

                if hasattr(generator, "voltage_v"):
                    voltage = float(generator.voltage_v)

                if hasattr(generator, "output_enabled"):
                    output_enabled = bool(generator.output_enabled)

        return f0, voltage, output_enabled


    def show_results_window(self):
        if not hasattr(self, "results_dialog") or self.results_dialog is None:
            QMessageBox.information(
                self, "Keine Ergebnisse", "Bitte zuerst eine Messung aufnehmen."
            )
            return

        self.results_dialog.show()
        self.results_dialog.raise_()
        self.results_dialog.activateWindow()

    def show_sweep_plot_window(self):

        if not hasattr(self, "sweep_results") or not self.sweep_results:
            QMessageBox.warning(
                self,
                "Keine Sweep-Daten",
                "Bitte zuerst eine Frequenzschleife durchführen."
            )
            return

        freqs = [item["frequency"] for item in self.sweep_results]
        diss = [round(float(item["dissipation_percent"]), 7) for item in self.sweep_results]
        voltages = [round(float(item["voltage"]), 8) for item in self.sweep_results]

        dialog = QDialog(self)
        dialog.setWindowTitle("Sweep-Ergebnisse")
        dialog.resize(1000, 800)

        layout = QVBoxLayout()

        # -------------------------------------------------
        # Plot 1: Generatorspannung
        # -------------------------------------------------
        voltage_plot = pg.PlotWidget(title="Benötigte Generatorspannung über Frequenz")
        voltage_plot.setLabel("bottom", "Frequenz [Hz]")
        voltage_plot.setLabel("left", "Generatorspannung [V]")
        voltage_plot.getAxis("left").enableAutoSIPrefix(False)
        voltage_plot.getAxis("bottom").enableAutoSIPrefix(False)
        voltage_plot.showGrid(x=True, y=True)

        voltage_plot.plot(
            freqs,
            voltages,
            pen=pg.mkPen(width=2),
            symbol="o",
            symbolSize=8
        )

        voltage_text = pg.TextItem("", anchor=(0, 1))
        voltage_text.setZValue(100)
        voltage_text.hide()
        voltage_plot.addItem(voltage_text)

        freqs_np = np.array(freqs, dtype=float)
        voltages_np = np.array(voltages, dtype=float)

        def on_voltage_mouse_moved(pos):
            if not voltage_plot.sceneBoundingRect().contains(pos):
                voltage_text.hide()
                return

            mouse_point = voltage_plot.plotItem.vb.mapSceneToView(pos)
            x_mouse = mouse_point.x()

            idx = int(np.argmin(np.abs(freqs_np - x_mouse)))

            f_val = freqs_np[idx]
            u_val = voltages_np[idx]

            x_range = voltage_plot.viewRange()[0]
            tolerance = (x_range[1] - x_range[0]) * 0.03

            if abs(f_val - x_mouse) <= tolerance:
                voltage_text.setText(
                    f"f = {f_val:.1f} Hz\n"
                    f"U = {u_val:.4f} V"
                )
                voltage_text.setPos(f_val, u_val)
                voltage_text.show()
            else:
                voltage_text.hide()

        voltage_proxy = pg.SignalProxy(
            voltage_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=lambda evt: on_voltage_mouse_moved(evt[0])
        )

        # -------------------------------------------------
        # Plot 2: Dissipation
        # -------------------------------------------------
        diss_plot = pg.PlotWidget(title="Dissipation über Frequenz")
        diss_plot.setLabel("bottom", "Frequenz [Hz]")
        diss_plot.setLabel("left", "Dissipation [%]")
        diss_plot.getAxis("left").enableAutoSIPrefix(False)
        diss_plot.getAxis("bottom").enableAutoSIPrefix(False)
        diss_plot.showGrid(x=True, y=True)

        diss_plot.plot(
            freqs,
            diss,
            pen=pg.mkPen(width=2),
            symbol="o",
            symbolSize=8
        )

        diss_text = pg.TextItem("", anchor=(0, 1))
        diss_text.setZValue(100)
        diss_text.hide()
        diss_plot.addItem(diss_text)

        diss_np = np.array(diss, dtype=float)

        def on_diss_mouse_moved(pos):
            if not diss_plot.sceneBoundingRect().contains(pos):
                diss_text.hide()
                return

            mouse_point = diss_plot.plotItem.vb.mapSceneToView(pos)
            x_mouse = mouse_point.x()

            idx = int(np.argmin(np.abs(freqs_np - x_mouse)))

            f_val = freqs_np[idx]
            d_val = diss_np[idx]

            x_range = diss_plot.viewRange()[0]
            tolerance = (x_range[1] - x_range[0]) * 0.03

            if abs(f_val - x_mouse) <= tolerance:
                diss_text.setText(
                    f"f = {f_val:.1f} Hz\n"
                    f"D = {d_val:.3f} %"
                )
                diss_text.setPos(f_val, d_val)
                diss_text.show()
            else:
                diss_text.hide()

        diss_proxy = pg.SignalProxy(
            diss_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=lambda evt: on_diss_mouse_moved(evt[0])
        )

        # Wichtig: Referenzen speichern, sonst kann Python sie löschen
        dialog.voltage_proxy = voltage_proxy
        dialog.diss_proxy = diss_proxy
        dialog.voltage_text = voltage_text
        dialog.diss_text = diss_text

        layout.addWidget(voltage_plot)
        layout.addWidget(diss_plot)

        dialog.setLayout(layout)
        dialog.exec()

    def _get_measurement_duration(self):
        try:
            duration = float(self.measurement_duration_edit.text())
            if duration <= 0:
                raise ValueError
            return duration
        except Exception:
            raise ValueError("Aufnahmezeit muss eine positive Zahl sein.")

    def show_log_window(self):
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def log(self, text, category="Info"):
        self.log_dialog.append(text, category)

    def on_source_changed(self):
        self.refresh_focusrite_devices()

    def _get_source_mode(self):
        return self.source_combo.currentText().strip()

    def _using_simulation(self):
        return self._get_source_mode() == SOURCE_SIMULATION # True = Simulation, False = Scarlett

    def _get_sample_rate(self):
        try:
            return float(self.sample_rate_combo.currentText())
        except Exception:
            return 48000.0

    def _get_f0(self):
        return 0.0

    
    # Simulation Signal
    def _generate_simulated_signal(self, duration=MEASUREMENT_DURATION):
        sample_rate = self._get_sample_rate()
        duration = float(duration)
        n = int(round(sample_rate * duration))

        t = np.arange(n, dtype=np.float64) / sample_rate

        f0, generator_voltage, output_enabled = self._get_simulated_generator_values()
        self.current_f0 = f0

        k = 2.0 * np.pi * f0 / SPEED_OF_SOUND

        if not output_enabled:
            return np.zeros((n, self.num_channels), dtype=np.float32)

        # Zusammenhang zwischen Generator-Spannung und hinlaufender Welle
        # Beispiel: 0.2 V Generator -> |A| = 1.0e-4
        A_abs = 5.0e-4 * generator_voltage

        # Reflexion: 30 % der hinlaufenden Welle
        B_abs = REFLECTION_FACTOR_SIM * A_abs

        A_sim = A_abs * np.exp(1j * 0.2)
        B_sim = B_abs * np.exp(-1j * 0.7)

        positions = [MIC_X1, MIC_X2, MIC_X3]
        audio = np.zeros((n, self.num_channels), dtype=np.float64)

        rng = np.random.default_rng(12345)
        noise_level = 0.00 #2.0e-6

        for ch, x in enumerate(positions):
            P = A_sim * np.exp(-1j * k * x) + B_sim * np.exp(1j * k * x)

            amp = np.abs(P)
            phase = np.angle(P)

            audio[:, ch] = amp * np.cos(2.0 * np.pi * f0 * t + phase)
            audio[:, ch] += noise_level * rng.standard_normal(n)

        return audio.astype(np.float32)

    def _reset_plot_storage(self):
        sample_rate = self._get_sample_rate()
        self.window_seconds = WINDOW_SECONDS
        window_samples = max(2, int(self.window_seconds * sample_rate))

        self.plot_buffers = [
            np.zeros(window_samples, dtype=np.float32) for _ in range(self.num_channels)
        ]
        # np.linspace(von 0.0, bis 1.0, Schritte 48000, endpoint=False)
        self.time_axis = np.linspace(
            0.0,
            self.window_seconds,
            window_samples,
            endpoint=False,
            dtype=np.float32,
        )

        self.fft_freq_axis = np.array([], dtype=np.float32)
        self.fft_buffers = [
            np.array([], dtype=np.float32) for _ in range(self.num_channels)
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

        for plot in self.fft_plot_widgets:
            plot.setXRange(50, 3000, padding=0)

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
                self.log(
                    f"Gefundenes Eingabegerät: index={idx}, name={name}, inputs={ch}"
                )

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
            if self.get_generator is not None:
                gen = self.get_generator()
                if gen is not None and hasattr(gen, "frequency_hz"):
                    self.current_f0 = float(gen.frequency_hz)

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
                self.update_time_plot(signal, f0)
                self.compute_fft_from_signal(signal)

                self.log("Simulierter Live-Block erzeugt.")
                return

            self.focusrite = self._create_focusrite()
            used_device = self.focusrite.start_input_stream()

            # Delay, live wirkt durch die Pufferung etwas verzögert,
            self.last_mode = "live"
            self.timer.start(50) # alle 50 ms aktualisieren, also ca. 20 mal pro Sekunde.

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

    def get_display_periods(self):
        return self.display_periods_spin.value()
    
    def update_time_plot(self, signal, f0):
        sample_rate = self._get_sample_rate()
        num_samples = signal.shape[0]

        samples_per_period = int(round(sample_rate / f0)) # bsp 48000 / 1000 = 48 Samples pro Periode
        display_periods = self.get_display_periods() # aus gui, z.B. 5 Perioden
        display_samples = int(display_periods * samples_per_period) # bsp 5 Perioden * 48 Samples/Periode = 240 Samples für die Anzeige
        display_samples = max(2, min(display_samples, num_samples)) # mindestens 2 Samples, maximal so viele wie im Signal vorhanden

        x = signal[:, 0]  # Mikrofon 1 als Referenz

        # Erste x ms überspringen, damit Start-Spitze weg ist
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

        dt = 1.0 / sample_rate
        self.time_axis = np.arange(display_samples) * dt

        for ch in range(self.num_channels):
            self.plot_buffers[ch] = signal[start:end, ch]
            self.time_plot_curves[ch].setData(self.time_axis, self.plot_buffers[ch])
            self.time_plot_widgets[ch].setXRange(
                0, display_samples / sample_rate, padding=0
            )

    def update_live_plot(self):
        if self.focusrite is None:
            return

        chunks = []

        while not self.focusrite.audio_queue.empty():
            kind, data = self.focusrite.audio_queue.get()

            if kind == "audio":
                chunks.append(data)
            elif kind == "status":
                self.log(data, category="Warnung")

        if not chunks:
            return

        signal = np.vstack(chunks).astype(np.float32)

        # wichtig: Kalibrierung auch bei Live
        signal = prepare_recording_signal(
            signal,
            num_channels=self.num_channels,
            calibration=CALIBRATION,
        )

        self.last_chunk = signal
        self.last_mode = "live"

        f0 = self._get_f0()

        self.update_time_plot(signal, f0)

        result = sp_compute_fft_from_signal(
            signal=signal,
            sample_rate=self._get_sample_rate(),
            f0=f0,
            num_channels=self.num_channels,
        )

        self.fft_freq_axis = result["freqs"]
        self.fft_buffers = result["fft_buffers"]
        self._refresh_fft_plots()
            
    def _write_log_entries(self, entries):
        for text, category in entries:
            self.log(text, category=category)

    def log_microphone_results(self, m, f0):
        self._write_log_entries(format_microphone_logs(m, self.num_channels))

    def log_forward_reflected_waves(self, m, f0):
        wave = self.compute_forward_reflected_results(m, f0)
        self._write_log_entries(format_wave_logs(wave))

    def on_record_clicked(self):
        try:
            duration = self._get_measurement_duration()
            result = self.run_measurement(duration)
            if result is None:
                return

            self.show_measurement_result(result)

        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))


    def run_measurement(self, duration, f0=None):
        self.timer.stop()

        if f0 is not None:
            self.current_f0 = float(f0)

        if self.focusrite is not None:
            self.focusrite.stop_input_stream()
            self.focusrite = None

        raw_signal, self.focusrite = record_signal(
            duration=duration,
            using_simulation=self._using_simulation(),
            generate_simulated_signal=self._generate_simulated_signal,
            create_focusrite=self._create_focusrite,
        )

        f0 = self._get_f0()
        sample_rate = self._get_sample_rate()

        result = process_recorded_signal(
            raw_signal=raw_signal,
            duration=duration,
            f0=f0,
            sample_rate=sample_rate,
            num_channels=self.num_channels,
            calibration=CALIBRATION,
            wave_cfg=self._get_wave_config(),
        )


        self.last_recording = result["signal"]
        self.last_mode = "record"

        return result

    def show_measurement_result(self, result):
        f0 = result.get("f0", self._get_f0())

        self.f0_detected_label.setText(f"gefunden: {float(f0):.2f} Hz")

        # NICHT mehr ins Eingabefeld schreiben,
        # sonst wird aus Auto-Modus wieder manueller Modus.
        # self.f0_edit.setText(f"{float(f0):.2f}")

        self.log(f"Automatisch bestimmte f0 = {float(f0):.2f} Hz")

        self.update_time_plot(result["signal"], f0)

        self.fft_freq_axis = result["fft"]["freqs"]
        self.fft_buffers = result["fft"]["fft_buffers"]
        self._refresh_fft_plots()

        self._write_log_entries(result["log_entries"])

        self.results_dialog = ComplexResultsDialog(
            result["mic_results"],
            parent=self,
        )

    def compute_fft_from_signal(self, signal):
        try:
            result = sp_compute_fft_from_signal(
                signal=signal,
                sample_rate=self._get_sample_rate(),
                f0=self._get_f0(),
                num_channels=self.num_channels,
            )
            self.fft_freq_axis = result["freqs"]
            self.fft_buffers = result["fft_buffers"]
            self._write_log_entries(result["log_entries"])
            self._refresh_fft_plots()
            return result
        except Exception as e:
            QMessageBox.critical(self, "FFT-Fehler", str(e))
            return None

    def open_time_window(self, ch):
        if ch < 0 or ch >= self.num_channels:
            return
        if len(self.time_axis) == 0 or len(self.plot_buffers[ch]) == 0:
            return

        dialog = SignalPlotDialog(
            title=f"Zeit Signal - Mikrofon {ch + 1}",
            x=self.time_axis.copy(),
            y=np.asarray(self.plot_buffers[ch]).copy(),
            xlabel="Zeit [Sek]",
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
        f0 = self._get_f0()
        sample_rate = self._get_sample_rate()
        nyquist = sample_rate / 2.0

        x_min = max(0.0, f0 - FFT_VIEW_HALF_WIDTH)
        x_max = min(nyquist, f0 + FFT_VIEW_HALF_WIDTH)

        dialog.plot_widget.setXRange(x_min, x_max, padding=0)

        dialog.show()
        self.open_plot_windows.append(dialog)

    def _get_wave_config(self):
        return build_wave_config(SPEED_OF_SOUND, MIC_X1, MIC_X2, MIC_X3)

    def cleanup(self):
        self.stop_audio()
    def build_mic_result_dict(self, m, f0):
        return sp_build_mic_result_dict(m, f0, num_mics=self.num_channels)

    def compute_forward_reflected_results(self, m, f0):
        return sp_compute_forward_reflected_results(m, f0, self._get_wave_config())

    '''
    Die MainWindow-Klasse ist das zentrale Element der Benutzeroberfläche. Sie verwaltet die verschiedenen Bildschirme
    (Start, Generator, Signal) und koordiniert die Interaktionen zwischen ihnen. Sie enthält Funktionen für die automatische
    Messung, die Frequenzschleife und die Aktualisierung der Messfrequenz basierend auf den Eingaben des Generators.
    Außerdem werden hier die Ergebnisse der Messungen geloggt und die entsprechenden Fenster für die Anzeige der Ergebnisse
    geöffnet.
    '''
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Akustik-Messsystem")
        self.resize(1500, 1000)

        self.start_screen = StartScreen()
        self.generator_screen = GeneratorScreen()
        self.signal_screen = SignalAnalysisScreen()
        self.signal_screen.get_generator = lambda: self.generator_screen.generator
        self.signal_screen.get_f0_from_gui = lambda: float(self.generator_screen.freq_edit.text())

        self.generator_screen.freq_edit.textChanged.connect(
            self.update_f0_from_generator
        )
        
        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_screen)
        self.stack.addWidget(self.generator_screen)
        self.stack.addWidget(self.signal_screen)

        layout = QVBoxLayout()
        layout.addWidget(self.stack)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Verbindet die Buttons mit den Funktionen zum Wechseln der Bildschirme und zum Starten der Messungen
        self.start_screen.generator_button.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.start_screen.signal_button.clicked.connect(lambda: self.stack.setCurrentIndex(2))
        self.generator_screen.back_button.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.signal_screen.back_button.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.start_screen.auto_button.clicked.connect(lambda: self.stack.setCurrentWidget(self.signal_screen))
        self.signal_screen.auto_start_button.clicked.connect(self.run_automatic_measurement)
        self.signal_screen.sweep_button.clicked.connect(self.run_frequency_sweep)
        self.signal_screen.show_sweep_plot_button.clicked.connect(self.signal_screen.show_sweep_plot_window)

    '''
    Die Funktion run_frequency_sweep führt eine automatische Frequenzschleife durch, bei der die Generatorfrequenz
    schrittweise von einem Startwert bis zu einem Stopwert erhöht wird. Für jede Frequenz wird die Generatorspannung angepasst,
    um eine Zielamplitude der hinlaufenden Welle |A| zu erreichen. Die Ergebnisse der Messungen werden geloggt und in einer Liste 
    gespeichert, die später für die Anzeige der Sweep-Ergebnisse verwendet wird.
    '''
    def run_frequency_sweep(self):
        try:
            generator = self.generator_screen.generator

            if generator is None:
                QMessageBox.warning(
                    self,
                    "Generator nicht verbunden",
                    "Bitte zuerst den Generator verbinden."
                )
                return

            self.signal_screen.source_combo.setCurrentText(SOURCE_SIMULATION)
            self.stack.setCurrentWidget(self.signal_screen)

            duration = self.signal_screen._get_measurement_duration()
            start_voltage = float(self.generator_screen.amp_edit.text())

            frequencies = np.arange(
                SWEEP_START_FREQ,
                SWEEP_STOP_FREQ + SWEEP_STEP_FREQ,
                SWEEP_STEP_FREQ,
            )

            sweep_results = run_frequency_sweep_steps(
                generator=generator,
                frequencies=frequencies,
                start_voltage=start_voltage,
                target_amp=TARGET_AMP,
                tolerance=AMP_TOLERANCE,
                max_steps=MAX_AUTO_STEPS,
                min_voltage=MIN_GENERATOR_VOLTAGE,
                max_voltage=MAX_GENERATOR_VOLTAGE,
                duration=duration,
                measure_once=self.signal_screen.run_measurement,
                compute_wave=self.signal_screen.compute_forward_reflected_results,
            )

            for sweep_item in sweep_results:
                f0 = sweep_item["frequency"]

                self.signal_screen.log(
                    f"Frequenzschleife: f = {f0:.1f} Hz",
                    category="title",
                )

                for step_item in sweep_item["step_results"]:
                    self.signal_screen.show_measurement_result(
                        step_item["measurement_result"]
                    )

                    self.signal_screen.log(
                        f"Schritt {step_item['step']}: "
                        f"f = {f0:.1f} Hz, "
                        f"U = {step_item['voltage']:.4f} V"
                    )
                    self.signal_screen.log(
                        f"|A| = {step_item['measured_A_abs']:.6e} V, "
                        f"Ziel = {format_voltage(TARGET_AMP)}"
                    )
                    self.signal_screen.log(
                        f"Dissipation = {step_item['wave']['dissipation_percent']:.3f} %"
                    )

                    QApplication.processEvents()

                self.signal_screen.log(
                    f"Frequenz {f0:.1f} Hz abgeschlossen.",
                    category="title",
                )

            self.signal_screen.sweep_results = sweep_results

            self.signal_screen.log(
                "Frequenzschleife abgeschlossen.",
                category="title",
            )

        except Exception as e:
            QMessageBox.critical(self, "Sweep-Fehler", str(e))
            
    def update_f0_from_generator(self):
                    try:
                        f0 = float(self.generator_screen.freq_edit.text())
                        if f0 > 0:
                            self.signal_screen.current_f0 = f0
                    except ValueError:
                        pass
            
    '''
        Die Funktion run_automatic_measurement führt eine automatische Messung durch, bei der die Generatorfrequenz und -spannung
        angepasst werden, um eine Zielamplitude der hinlaufenden Welle |A| zu erreichen. Die Funktion iteriert über mehrere Schritte, 
        in denen die Generatorparameter aktualisiert und die Messungen durchgeführt werden. Die Ergebnisse der Messungen werden 
        geloggt, und die Funktion bricht ab, wenn die Zielamplitude erreicht ist oder die maximale Generatorspannung überschritten wird.
    '''    
    def run_automatic_measurement(self):
        try:
            generator = self.generator_screen.generator

            if generator is None:
                QMessageBox.warning(
                    self,
                    "Generator nicht verbunden",
                    "Bitte zuerst den Generator auf der Generator-Seite verbinden.",
                )
                return

            f0 = float(self.generator_screen.freq_edit.text())
            voltage = float(self.generator_screen.amp_edit.text())

            if f0 <= 0:
                raise ValueError("Generatorfrequenz muss größer als 0 Hz sein.")

            if voltage <= 0 or voltage > MAX_GENERATOR_VOLTAGE:
                raise ValueError(
                    f"Generatorspannung muss größer 0 und maximal {MAX_GENERATOR_VOLTAGE:.1f} V sein."
                )

            self.signal_screen.current_f0 = f0
            self.signal_screen.source_combo.setCurrentText(SOURCE_SIMULATION)
            self.signal_screen.refresh_focusrite_devices()
            self.stack.setCurrentWidget(self.signal_screen)

            duration = self.signal_screen._get_measurement_duration()

            step_results = run_auto_measurement_steps(
                generator=generator,
                f0=f0,
                start_voltage=voltage,
                target_amp=TARGET_AMP,
                tolerance=AMP_TOLERANCE,
                max_steps=MAX_AUTO_STEPS,
                min_voltage=MIN_GENERATOR_VOLTAGE,
                max_voltage=MAX_GENERATOR_VOLTAGE,
                duration=duration,
                measure_once=self.signal_screen.run_measurement,
                compute_wave=self.signal_screen.compute_forward_reflected_results,
            )

            for item in step_results:
                step = item["step"]
                wave = item["wave"]
                measurement_result = item["measurement_result"]

                self.signal_screen.show_measurement_result(measurement_result)

                self.signal_screen.log(
                    f"Automatik Schritt {step}",
                    category="title",
                )
                self.signal_screen.log(
                    f"Generator: f = {item['frequency']:.2f} Hz, U = {item['voltage']:.4f} V"
                )
                self.signal_screen.log(
                    f"Ziel-Amplitude |A| = {format_voltage(TARGET_AMP)}"
                )
                self.signal_screen.log(
                    f"Gemessene hinlaufende Welle |A| = {format_voltage(item['measured_A_abs'])}"
                )
                self.signal_screen.log(
                    f"Relativer Fehler = {item['relative_error']:.3f}"
                )
                self.signal_screen.log(
                    f"Reflexion |B|/|A| = {wave['B_over_A']:.6f}"
                )
                self.signal_screen.log(
                    f"Reflexionsgrad R = {wave['reflection_energy']:.6f}"
                )
                self.signal_screen.log(
                    f"Dissipation = {wave['dissipation_percent']:.3f} %"
                )

                QApplication.processEvents()

                if item["ok"]:
                    self.signal_screen.log(
                        "Ziel-Amplitude |A| erreicht.",
                        category="title",
                    )

            if not step_results[-1]["ok"]:
                self.signal_screen.log(
                    "Ziel-Amplitude |A| nicht erreicht.",
                    category="title",
                )

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

# Die main-Funktion ist der Einstiegspunkt der Anwendung, der die MainWindow-Klasse erstellt und die Qt-Anwendung startet.
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

# Der Einstiegspunkt der Anwendung, der die MainWindow-Klasse erstellt und die Qt-Anwendung startet.
if __name__ == "__main__":
    main()

