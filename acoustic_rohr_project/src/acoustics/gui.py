import sys
import json
from pathlib import Path
import time
from datetime import datetime
from types import SimpleNamespace
import wave
import sounddevice as sd



import numpy as np
import pyqtgraph as pg

from simulated_generator import SimulatedGenerator
from automation import (

    run_frequency_sweep_steps,
    run_automatic_frequency_sweep_steps,
)

from generator_hdw_panel import Agilent33120A

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


from focusrite_interface import FocusriteInterface


from signal_process import (
    build_wave_config,
    process_recorded_signal,
    record_signal,
    compute_fft_from_signal as sp_compute_fft_from_signal,
    compute_forward_reflected_results as sp_compute_forward_reflected_results,
    build_mic_result_dict as sp_build_mic_result_dict,
    format_microphone_logs,
    format_wave_logs,
    prepare_recording_signal,
    estimate_f0_from_fft,
    
)

# Feste Parameter für die automatische Messung
SWEEP_START_FREQ = 350.0
SWEEP_STOP_FREQ = 2050.0
SWEEP_STEP_FREQ = 50.0

'''
TARGET_AMP = 0.0002 V  = 0.2 mV  = 200 µV
TARGET_AMP = 0.0150 V  = 15 mV   = 15000 µV
TARGET_AMP = 0.1500 V  = 150 mV  = 150000 µV

'''
TARGET_AMP = 0.0002 # 0.0002 200 µV . In Labore 0,150 
AMP_TOLERANCE = 0.01
MAX_AUTO_STEPS = 10
MIN_GENERATOR_VOLTAGE = 0.05 # 0.05 50 mV
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
FFT_MAX_FREQ = 3000

# Feste Rohr-/Mikrofonparameter
SPEED_OF_SOUND = 344.0

# Rehung ist X1 am weitesten von Abschluss entfernt, X3 am nächsten
MIC_X1 = -0.145
MIC_X2 = -0.085
MIC_X3 = -0.05

'''
D = 0   → harte Wand, volle Reflexion
D = 1   → volle Absorption, keine Reflexion
D = 0.64 → 64 % Energieverlust, 36 % Reflexion
'''
REFLECTION_FACTOR_SIM = 1.0  # harte Wand

# bei 1000 Hz: 6.4 µV bei 0.2 V Generator-Spannung, BeI 2000 hZ und 500 hZ ist auch ungefähr 6.4 µV (6,4 1,5 1,8)
CALIBRATION = {
    1: 1,
    2: 1,
    3: 1,
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
    def __init__(self, mic_results, f0=None, parent=None):
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

        if f0 is None:
            title_text = "komplexe Schalldruck-Amplituden der Mikrofone (P)"
        else:
            title_text = (
                "komplexe Schalldruck-Amplituden der Mikrofone (P) "
                f"bei f0 = {float(f0):.2f} Hz"
            )

        title = QLabel(title_text)
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

# plot zerlegte Wellen im Ortsbereich, also a(x), b(x) und p(x) = a(x) + b(x)
class WaveDecompositionDialog(QDialog):
    def __init__(self, wave, f0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wellenzerlegung")
        self.resize(1200, 900)

        layout = QVBoxLayout()

        back_button = QPushButton("← Zurück")
        back_button.setMaximumWidth(220)
        back_button.clicked.connect(self.close)
        layout.addWidget(back_button)

        title = QLabel(f"Wellenzerlegung bei f0 = {float(f0):.2f} Hz. " f"Welenlänge λ in mm= {SPEED_OF_SOUND / float(f0) * 1000:.3f} mm")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: blue;")
        layout.addWidget(title)

        # -------------------------------------------------
        # Grunddaten
        # -------------------------------------------------
        A_abs = wave["A_abs"]
        A_phase = wave["A_phase"]

        B_abs = wave["B_abs"]
        B_phase = wave["B_phase"]

        f0 = float(f0)
        k = 2.0 * np.pi * f0 / SPEED_OF_SOUND
        lam = SPEED_OF_SOUND / f0 # Wellenlänge in Meter

        # Plot beginnt links vor M3 und geht rechts ca. 2 Wellenlängen weiter
        x_min = 0 - (SPEED_OF_SOUND / float(f0))
        x_max = 0 #max(MIC_X1, MIC_X2, MIC_X3) + 2.0 * lam

        # x in Meter für Rechnung
        x = np.linspace(x_min, x_max, 1000)

        # x in mm für Anzeige
        x_mm = x * 1000.0
        x_min_mm = x_min * 1000.0
        x_max_mm = x_max * 1000.0

        
        # Sinusförmige Ortsverläufe bei t = 0
        a_x = A_abs * np.cos(-k * x + A_phase)   # hinlaufende Welle
        b_x = B_abs * np.cos(+k * x + B_phase)   # rücklaufende Welle
        p_x = a_x + b_x                          # Gesamtsignal

        # Darstellung in µV
        a_uv = a_x * 1e6
        b_uv = b_x * 1e6
        p_uv = p_x * 1e6

        

        '''
                # -------------------------------------------------
        # Einzelwerte ohne Sinus-Ortsverlauf
        # A und B sind komplexe Einzelwerte bei f0.
        # Hier wird nur ihr Betrag als konstante Linie gezeigt.
        # -------------------------------------------------
        A_complex = wave["A"]
        B_complex = wave["B"]
        P_sum_complex = A_complex + B_complex

        a_uv = np.ones_like(x_mm) * (np.abs(A_complex) * 1e6)
        b_uv = np.ones_like(x_mm) * (np.abs(B_complex) * 1e6)
        p_uv = np.ones_like(x_mm) * (np.abs(P_sum_complex) * 1e6)
        '''


        # -------------------------------------------------
        # Box 1: Wellen im Rohr
        # -------------------------------------------------
        wave_box = QGroupBox("Hinlaufende und rücklaufende Welle im Rohr")
        wave_layout = QVBoxLayout()

        wave_plot = pg.PlotWidget(title="Wellenzerlegung im Ortsbereich")
        wave_plot.setLabel("bottom", "Rohrposition x [mm]")
        wave_plot.setLabel("left", "Amplitude [µV]")
        wave_plot.getAxis("bottom").enableAutoSIPrefix(False)
        wave_plot.getAxis("left").enableAutoSIPrefix(False)
        wave_plot.setMouseEnabled(x=True, y=True)
        wave_plot.showGrid(x=True, y=True)
        wave_plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")

        wave_plot.plot(
            x_mm,
            a_uv,
            pen=pg.mkPen("c", width=2),
            name="a(x) hinlaufend"
        )

        wave_plot.plot(
            x_mm,
            b_uv,
            pen=pg.mkPen("m", width=2),
            name="b(x) rücklaufend"
        )

        wave_plot.plot(
            x_mm,
            p_uv,
            pen=pg.mkPen("g", width=2),
            name="p(x) = a(x) + b(x)"
        )
        # -------------------------------------------------
        # Werte an den Mikrofonpositionen markieren
        # Die Welle ist nur Hilfskurve; die Werte bei M1/M2/M3 sind wichtig.
        # -------------------------------------------------
        mic_positions = [
            (MIC_X1, "M1"),
            (MIC_X2, "M2"),
            (MIC_X3, "M3"),
        ]

        for mic_x, mic_name in mic_positions:
            mic_x_mm = mic_x * 1000.0

            # Werte der Kurven genau an der Mikrofonposition
            a_mic = A_abs * np.cos(-k * mic_x + A_phase) * 1e6
            b_mic = B_abs * np.cos(+k * mic_x + B_phase) * 1e6
            p_mic = a_mic + b_mic

            # Punkt auf a(x)
            wave_plot.plot(
                [mic_x_mm],
                [a_mic],
                pen=None,
                symbol="o",
                symbolSize=10,
                symbolBrush="c",
                symbolPen=pg.mkPen("w", width=1),
            )

            # Punkt auf b(x)
            wave_plot.plot(
                [mic_x_mm],
                [b_mic],
                pen=None,
                symbol="o",
                symbolSize=10,
                symbolBrush="m",
                symbolPen=pg.mkPen("w", width=1),
            )

            # Punkt auf p(x)
            wave_plot.plot(
                [mic_x_mm],
                [p_mic],
                pen=None,
                symbol="o",
                symbolSize=12,
                symbolBrush="g",
                symbolPen=pg.mkPen("w", width=1),
            )

            # Werte als Text direkt neben p(x)-Punkt
            value_text = pg.TextItem(
                f"{mic_name}\n"
                f"a={a_mic:.1f} µV\n"
                f"b={b_mic:.1f} µV\n"
                f"p={p_mic:.1f} µV",
                color="w",
                anchor=(0, 1)
            )
            value_text.setPos(mic_x_mm + 3.0, p_mic + 10.0)
            wave_plot.addItem(value_text)

        wave_plot.setXRange(x_min_mm, x_max_mm, padding=0)

        # Mikrofonpositionen markieren
        y_values = np.concatenate([a_uv, b_uv, p_uv])
        y_top = float(np.max(y_values))
        y_bottom = float(np.min(y_values))
        y_span = max(abs(y_top - y_bottom), 1.0)

        

        mic_marks = [
            (MIC_X1, "M1", 0.85),
            (MIC_X2, "M2", 0.70),
            (MIC_X3, "M3", 0.55),
        ]

        for mic_x, name, frac in mic_marks:
            mic_x_mm = mic_x * 1000.0

            line = pg.InfiniteLine(pos=mic_x_mm, angle=90, movable=False)
            wave_plot.addItem(line)

            text = pg.TextItem(name)
            text.setPos(mic_x_mm, y_bottom + frac * y_span)
            wave_plot.addItem(text)

        wave_layout.addWidget(wave_plot)
        wave_box.setLayout(wave_layout)

        # -------------------------------------------------
        # Box 2: RMS-Pegel in dBµV
        # -------------------------------------------------
        db_box = QGroupBox("RMS-Pegel der hin- und rücklaufenden Welle")
        db_layout = QVBoxLayout()

        db_plot = pg.PlotWidget(title="RMS-Pegel in dBµV")
        db_plot.setLabel("bottom", "Rohrposition x [mm]")
        db_plot.setLabel("left", "Pegel [dBµV]")
        db_plot.getAxis("bottom").enableAutoSIPrefix(False)
        db_plot.getAxis("left").enableAutoSIPrefix(False)
        db_plot.setMouseEnabled(x=False, y=True)
        db_plot.showGrid(x=True, y=True)
        db_plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")

        eps = 1e-30
        u_ref = 1e-6  # dBµV

        # RMS = Spitzenwert / √2
        # A_RMS = |A| / √2
        # B_RMS = |B| / √2

        A_rms = A_abs / np.sqrt(2.0) # RMS-Wert der hinlaufenden Welle
        B_rms = B_abs / np.sqrt(2.0) # RMS-Wert der rücklaufenden Welle

        A_dbuv = 20.0 * np.log10((A_rms + eps) / u_ref) # Math 20 * log10(U / U_ref)
        B_dbuv = 20.0 * np.log10((B_rms + eps) / u_ref)

        A_db_line = np.ones_like(x_mm) * A_dbuv
        B_db_line = np.ones_like(x_mm) * B_dbuv

        db_plot.plot(
            x_mm,
            A_db_line,
            pen=pg.mkPen("c", width=3),
            name=f"A_RMS = {A_dbuv:.2f} dBµV"
        )

        db_plot.plot(
            x_mm,
            B_db_line,
            pen=pg.mkPen("m", width=3),
            name=f"B_RMS = {B_dbuv:.2f} dBµV"
        )

        db_plot.setXRange(x_min_mm, x_max_mm, padding=0)

        db_layout.addWidget(db_plot)
        db_box.setLayout(db_layout)

        # -------------------------------------------------
        # Beide Boxen anzeigen
        # -------------------------------------------------
        layout.addWidget(wave_box)
        layout.addWidget(db_box)

        self.setLayout(layout)


class AutomationAnalysisDialog(QDialog):
    """Live-Anzeige für den automatischen Frequenz-Sweep."""

    def __init__(self, target_amp, tolerance=AMP_TOLERANCE, parent=None):
        super().__init__(parent)
        self.target_amp_uv = float(target_amp) * 1e3
        self.tolerance = float(tolerance)
        self.lower_tolerance_uv = self.target_amp_uv * (1.0 - self.tolerance)
        self.upper_tolerance_uv = self.target_amp_uv * (1.0 + self.tolerance)
        self.setWindowTitle("Automation über Frequenz")
        self.resize(1400, 900)
        self.setStyleSheet(
            "QDialog { background: white; } "
            "QGroupBox { background: white; font-weight: bold; "
            "border: 1px solid #cfcfcf; border-radius: 6px; "
            "margin-top: 10px; padding-top: 8px; }"
        )

        self.frequencies = []
        self.a_abs_uv = []
        self.b_abs_uv = []
        self.voltages = []

        layout = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        self.back_button.clicked.connect(self._request_close)
        top_layout.addWidget(self.back_button)
        top_layout.addStretch()
        self.voltage_data_button = QPushButton("Daten anzeigen")
        self.voltage_data_button.setMaximumWidth(220)
        self.voltage_data_button.clicked.connect(self.show_voltage_data_dialog)
        top_layout.addWidget(self.voltage_data_button)
        layout.addLayout(top_layout)

        ab_box = QGroupBox("Hinlaufende Welle über Frequenz")
        ab_box.setAlignment(Qt.AlignHCenter)
        ab_layout = QVBoxLayout(ab_box)
        self.ab_plot = pg.PlotWidget(background="w")
        self._style_plot(self.ab_plot, "Frequenz [Hz]", "Amplitude [mV]")
        self.ab_plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")
        self.a_curve = self.ab_plot.plot(
            [], [],
            pen=pg.mkPen("r", width=3),
            symbol="o",
            symbolSize=6,
            symbolBrush="r",
            symbolPen=pg.mkPen("r"),
            name="|A(f)| hinlaufend"
        )

        self.tolerance_band = pg.LinearRegionItem(
            values=(self.lower_tolerance_uv, self.upper_tolerance_uv),
            orientation=pg.LinearRegionItem.Horizontal,
            movable=False,
            brush=pg.mkBrush(255, 235, 120, 90),
            pen=pg.mkPen(230, 190, 0, width=1),
        )
        self.tolerance_band.setZValue(-10)
        self.ab_plot.addItem(self.tolerance_band)
        self.ab_plot.plot(
            [],
            [],
            pen=pg.mkPen(230, 190, 0, width=8),
            name=f"Toleranzbereich ±{self.tolerance * 100.0:.1f} %",
        )

        self.target_line = pg.InfiniteLine(
            pos=self.target_amp_uv,
            angle=0,
            movable=False,
            pen=pg.mkPen((80, 80, 80), width=2, style=Qt.DashLine),
            label=f"Ziel |A| = {self.target_amp_uv:.1f} mV",
            labelOpts={"position": 0.92, "color": (60, 60, 60)},
        )
        self.ab_plot.addItem(self.target_line)
        ab_layout.addWidget(self.ab_plot)

        voltage_box = QGroupBox("Benötigte Generator-Spannung je Frequenz")
        voltage_box.setAlignment(Qt.AlignHCenter)
        voltage_layout = QVBoxLayout(voltage_box)
        self.voltage_plot = pg.PlotWidget(background="w")
        self._style_plot(self.voltage_plot, "Frequenz [Hz]", "Generator-Spannung [V]")
        self.voltage_plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")
        self.voltage_curve = self.voltage_plot.plot(
            [], [], pen=pg.mkPen("b", width=3), symbol="o", symbolSize=7,
            name="U(f) für Zielamplitude"
        )
        voltage_layout.addWidget(self.voltage_plot)

        layout.addWidget(ab_box, 1)
        layout.addWidget(voltage_box, 1)

        self._install_hover(
            self.ab_plot,
            lambda: (
                self.frequencies,
                [("|A|", self.a_abs_uv, " mV")],
            ),
        )
        self._install_hover(
            self.voltage_plot,
            lambda: (
                self.frequencies,
                [("U", self.voltages, " V")],
            ),
        )

    def _request_close(self):
        """Beendet die laufende Automation und schließt das Live-Fenster."""
        parent = self.parent()
        if parent is not None:
            parent.sweep_cancel_requested = True
        self.close()

    def closeEvent(self, event):
        parent = self.parent()
        if parent is not None:
            parent.sweep_cancel_requested = True
        super().closeEvent(event)

    def show_voltage_data_dialog(self):
        if not self.frequencies or not self.voltages:
            QMessageBox.information(
                self,
                "Keine Daten",
                "Es sind noch keine Automation-Daten vorhanden.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Benötigte Spannung")
        dialog.resize(520, 520)

        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setRowCount(len(self.frequencies))
        table.setHorizontalHeaderLabels(["Frequenz [Hz]", "Benötigte Spannung [V]"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        for row, (frequency, voltage) in enumerate(zip(self.frequencies, self.voltages)):
            frequency_item = QTableWidgetItem(f"{float(frequency):.1f}")
            voltage_item = QTableWidgetItem(f"{float(voltage):.4f}")
            frequency_item.setTextAlignment(Qt.AlignCenter)
            voltage_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, frequency_item)
            table.setItem(row, 1, voltage_item)

        close_button = QPushButton("Schließen")
        close_button.clicked.connect(dialog.close)

        layout.addWidget(table)
        layout.addWidget(close_button)
        dialog.exec()

    @staticmethod
    def _style_plot(plot, xlabel, ylabel):
        plot.setLabel("bottom", xlabel, color="k")
        plot.setLabel("left", ylabel, color="k")
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.setMouseEnabled(x=True, y=True)
        for axis_name in ("bottom", "left"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen("k"))
            axis.setTextPen(pg.mkPen("k"))
            axis.enableAutoSIPrefix(False)

    def clear_data(self):
        self.frequencies.clear()
        self.a_abs_uv.clear()
        self.b_abs_uv.clear()
        self.voltages.clear()
        self.a_curve.setData([], [])
        self.voltage_curve.setData([], [])

    def append_frequency_result(self, item):
        self.frequencies.append(float(item["frequency"]))
        self.a_abs_uv.append(float(item["A_abs"]) * 1e3)
        self.voltages.append(float(item["voltage"]))

        x = np.asarray(self.frequencies, dtype=float)
        self.a_curve.setData(x, np.asarray(self.a_abs_uv, dtype=float))
        self.voltage_curve.setData(x, np.asarray(self.voltages, dtype=float))

        if x.size:
            x_min = float(np.min(x))
            x_max = float(np.max(x))
            if x_min == x_max:
                margin = max(20.0, abs(x_min) * 0.05)
                x_min -= margin
                x_max += margin
            self.ab_plot.setXRange(x_min, x_max, padding=0.03)
            self.voltage_plot.setXRange(x_min, x_max, padding=0.03)

            all_ab = np.asarray(
                    self.a_abs_uv
                    + [self.target_amp_uv, self.lower_tolerance_uv, self.upper_tolerance_uv],
                    dtype=float,
                )
            y_min = float(np.min(all_ab))
            y_max = float(np.max(all_ab))
            y_span = max(y_max - y_min, 1.0)
            self.ab_plot.setYRange(max(0.0, y_min - 0.12 * y_span), y_max + 0.15 * y_span, padding=0)

            v = np.asarray(self.voltages, dtype=float)
            v_min = float(np.min(v))
            v_max = float(np.max(v))
            v_span = max(v_max - v_min, max(v_max * 0.1, 0.01))
            self.voltage_plot.setYRange(max(0.0, v_min - 0.12 * v_span), v_max + 0.15 * v_span, padding=0)

    def _install_hover(self, plot, data_getter):
        marker = pg.ScatterPlotItem(
            [], [], symbol="o", size=13,
            brush=pg.mkBrush(255, 255, 255),
            pen=pg.mkPen("k", width=2),
        )
        plot.addItem(marker)
        label = pg.TextItem(
            "", color="k",
            fill=pg.mkBrush(255, 255, 255, 235),
            border=pg.mkPen(80, 80, 80), anchor=(0, 1),
        )
        label.hide()
        plot.addItem(label)

        def on_mouse_moved(scene_pos):
            if not plot.sceneBoundingRect().contains(scene_pos):
                marker.setData([], [])
                label.hide()
                return

            frequencies, series = data_getter()
            if not frequencies:
                marker.setData([], [])
                label.hide()
                return

            mouse_point = plot.getPlotItem().vb.mapSceneToView(scene_pos)
            x = np.asarray(frequencies, dtype=float)
            index = int(np.argmin(np.abs(x - mouse_point.x())))
            x_range = plot.getPlotItem().vb.viewRange()[0]
            y_range = plot.getPlotItem().vb.viewRange()[1]
            x_tolerance = max((x_range[1] - x_range[0]) * 0.015, 1.0)
            y_tolerance = max((y_range[1] - y_range[0]) * 0.03, 1e-9)
            if abs(x[index] - mouse_point.x()) > x_tolerance:
                marker.setData([], [])
                label.hide()
                return

            values = []
            for name, data, suffix in series:
                if index < len(data):
                    values.append((name, float(data[index]), suffix))
            if not values:
                marker.setData([], [])
                label.hide()
                return

            hover_value = min(
                (value for _, value, _ in values),
                key=lambda value: abs(value - mouse_point.y()),
            )
            if abs(hover_value - mouse_point.y()) > y_tolerance:
                marker.setData([], [])
                label.hide()
                return

            marker.setData([x[index]], [hover_value])
            lines = [f"f = {x[index]:.1f} Hz"]
            lines.extend(f"{name} = {value:.4f}{suffix}" for name, value, suffix in values)
            label.setText("\n".join(lines))
            label.setPos(x[index], hover_value)
            label.show()

        plot.scene().sigMouseMoved.connect(on_mouse_moved)
        if not hasattr(self, "_hover_items"):
            self._hover_items = []
        self._hover_items.append((plot, marker, label, on_mouse_moved))


class FrequencyAnalysisDialog(QDialog):
    """Live-Dashboard mit vier Messdiagrammen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Live-Wellenanalyse")
        self.resize(1600, 1000)
        self.setStyleSheet(
            "QDialog { background: white; } "
            "QGroupBox { background: white; font-weight: bold; "
            "border: 1px solid #cfcfcf; border-radius: 6px; "
            "margin-top: 10px; padding-top: 8px; }"
        )

        self.frequencies = []
        self.reflection = []
        self.dissipation = []
        self.a_abs_uv = []
        self.b_abs_uv = []
        self.a_rms_dbuv = []
        self.b_rms_dbuv = []
        self.frequency_items = []
        self.last_wave = None
        self.last_frequency = None

        main_layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.back_button = QPushButton("← Zurück")
        self.back_button.setMaximumWidth(220)
        self.back_button.clicked.connect(self._request_close)
        self.status_label = QLabel("Noch keine Messdaten")
        self.status_label.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #003cff;"
        )
        top.addWidget(self.back_button)
        top.addStretch()
        self.wave_data_button = QPushButton("Daten anzeigen")
        self.wave_data_button.setMaximumWidth(220)
        self.wave_data_button.clicked.connect(self.show_wave_data_dialog)
        top.addWidget(self.wave_data_button)
        main_layout.addLayout(top)

        row_top = QHBoxLayout()
        row_bottom = QHBoxLayout()

        # Box 1: Reflexion und Dissipation gemeinsam
        self.rd_plot = self._make_plot(
            "Reflexionsgrad und Dissipationsgrad über Frequenz",
            "Frequenz [Hz]",
            "R, D",
        )
        self.reflection_curve = self.rd_plot.plot(
            [], [], pen=pg.mkPen("b", width=3), symbol="o", symbolSize=6,
            name="R = |r|² = |B/A|²"
        )
        self.dissipation_curve = self.rd_plot.plot(
            [], [], pen=pg.mkPen("r", width=3), symbol="o", symbolSize=6,
            name="D = 1 - R"
        )
        self.rd_plot.setYRange(0.0, 1.0, padding=0.05)

        # Box 2: Beträge A und B über Frequenz
        self.ab_plot = self._make_plot(
            "Hin- und rücklaufende Welle über Frequenz",
            "Frequenz [Hz]",
            "Amplitude [µV]",
        )
        self._move_legend_bottom_left(self.ab_plot)
        self.a_curve = self.ab_plot.plot(
            [], [], pen=pg.mkPen("c", width=3), symbol="o", symbolSize=5,
            name="|A(f)| hinlaufend"
        )
        self.b_curve = self.ab_plot.plot(
            [], [], pen=pg.mkPen("m", width=3), symbol="o", symbolSize=5,
            name="|B(f)| rücklaufend"
        )

        # Box 3: alter Ortsplot mit M1, M2, M3
        self.spatial_plot = self._make_plot(
            "Wellenzerlegung im Ortsbereich",
            "Rohrposition x [mm]",
            "Momentanwert [µV]",
        )

        # Box 4: RMS-Pegel als ortsunabhängige, horizontale Linien.
        # Für den jeweils aktuellen Frequenzschritt sind |A| und |B| entlang
        # des idealisierten Rohres konstant; deshalb werden zwei gerade Linien
        # über der Rohrposition dargestellt.
        self.rms_plot = self._make_plot(
            "Ortsverlauf der stehenden Welle",
            "Rohrposition x [mm]",
            "|P<sub>rek</sub>(x)| [µV]",
        )
        self.a_rms_curve = self.rms_plot.plot(
            [], [], pen=pg.mkPen("c", width=3),
            name="A_RMS hinlaufend"
        )
        self.b_rms_curve = self.rms_plot.plot(
            [], [], pen=pg.mkPen("m", width=3),
            name="B_RMS rücklaufend"
        )
        self.rms_x_mm = np.array([], dtype=float)
        self.current_a_rms_dbuv = None
        self.current_b_rms_dbuv = None

        # Hover-Anzeigen: Beim Bewegen über einen Messpunkt werden
        # Frequenz und die zugehörigen Werte direkt am Punkt gezeigt.
        self._install_frequency_hover(
            self.rd_plot,
            lambda: (
                self.frequencies,
                [("R", self.reflection), ("D", self.dissipation)],
            ),
            value_suffix="",
        )
        self._install_frequency_hover(
            self.ab_plot,
            lambda: (
                self.frequencies,
                [("|A|", self.a_abs_uv), ("|B|", self.b_abs_uv)],
            ),
            value_suffix=" µV",
        )
        self._install_rms_position_hover()

        row_top.addWidget(self._box("Reflexion und Dissipation", self.rd_plot))
        row_top.addWidget(self._box("A und B über Frequenz", self.ab_plot))
        row_bottom.addWidget(self._box("Wellenzerlegung mit M1, M2, M3", self.spatial_plot))
        self.rms_box = self._box("RMS hin- und rücklaufend", self.rms_plot)
        row_bottom.addWidget(self.rms_box)

        main_layout.addLayout(row_top, 1)
        main_layout.addLayout(row_bottom, 1)

    def _request_close(self):
        """Beendet den laufenden Sweep und schließt das Live-Fenster."""
        parent = self.parent()
        if parent is not None:
            parent.sweep_cancel_requested = True
        self.close()

    def closeEvent(self, event):
        parent = self.parent()
        if parent is not None:
            parent.sweep_cancel_requested = True
        event.accept()

    @staticmethod
    def _format_complex(value):
        value = complex(value)
        sign = "+" if value.imag >= 0 else "-"
        return f"{value.real:.6e} {sign} {abs(value.imag):.6e}j"

    @staticmethod
    def _format_complex_uv(value):
        value = complex(value) * 1e6
        sign = "+" if value.imag >= 0 else "-"
        return f"{value.real:.3f} {sign} {abs(value.imag):.3f}j"

    @staticmethod
    def _format_swr(gamma):
        gamma = float(gamma)
        if gamma >= 1.0:
            return "∞"
        return f"{(1.0 + gamma) / (1.0 - gamma):.6f}"

    def show_wave_data_dialog(self):
        if not self.frequency_items:
            QMessageBox.information(
                self,
                "Keine Daten",
                "Es sind noch keine Analyse-Daten vorhanden.",
            )
            return

        item = self.frequency_items[-1]
        wave = item.get("wave")
        if wave is None and item.get("step_results"):
            wave = item["step_results"][-1].get("wave")
        if wave is None:
            QMessageBox.information(
                self,
                "Keine Daten",
                "Für diese Analyse sind keine Wellen-Daten vorhanden.",
            )
            return

        f0 = float(item.get("frequency", self.last_frequency or 0.0))
        A = complex(wave["A"])
        B = complex(wave["B"])
        A_abs = float(wave["A_abs"])
        B_abs = float(wave["B_abs"])
        gamma = float(abs(wave.get("r_abs", item.get("B_over_A", B_abs / (A_abs + 1e-30)))))
        R = float(wave.get("reflection_energy", gamma**2))
        D = float(wave.get("dissipation", 1.0 - R))
        residual = float(wave.get("residual", item.get("residual", 0.0)))
        wavelength = SPEED_OF_SOUND / f0 if f0 > 0 else 0.0
        wave_number = 2.0 * np.pi / wavelength if wavelength > 0 else 0.0
        p_max = A_abs + B_abs
        p_min = abs(A_abs - B_abs)

        r_complex = wave.get("r_complex")
        if r_complex is None:
            r_complex = B / (A + 1e-30)
        r_complex = complex(r_complex)

        rows = [
            ("Frequenz", f"{f0:.3f}", "Hz"),
            ("A komplex", self._format_complex(A), "V"),
            ("A komplex", self._format_complex_uv(A), "µV"),
            ("A Betrag |A|", f"{A_abs * 1e6:.3f}", "µV"),
            ("A Phase", f"{np.degrees(float(wave['A_phase'])):.3f}", "°"),
            ("B komplex", self._format_complex(B), "V"),
            ("B komplex", self._format_complex_uv(B), "µV"),
            ("B Betrag |B|", f"{B_abs * 1e6:.3f}", "µV"),
            ("B Phase", f"{np.degrees(float(wave['B_phase'])):.3f}", "°"),
            ("r = B/A komplex", self._format_complex(r_complex), ""),
            ("Reflexionsfaktor |r|", f"{gamma:.6f}", ""),
            ("r Phase", f"{np.degrees(float(wave.get('r_phase', np.angle(r_complex)))):.3f}", "°"),
            ("Reflexionsgrad R = |r|²", f"{R:.6f}", ""),
            ("Reflexion", f"{R * 100.0:.3f}", "%"),
            ("Dissipation D = 1 - R", f"{D:.6f}", ""),
            ("Dissipation", f"{D * 100.0:.3f}", "%"),
            ("SWR", self._format_swr(gamma), ""),
            ("p_max = |A| + |B|", f"{p_max * 1e6:.3f}", "µV"),
            ("p_min = ||A| - |B||", f"{p_min * 1e6:.3f}", "µV"),
            ("Wellenlänge λ", f"{wavelength * 1000.0:.3f}", "mm"),
            ("Wellenzahl k", f"{wave_number:.6f}", "rad/m"),
            ("Residuum", f"{residual:.6e}", ""),
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Analyse-Daten")
        dialog.resize(760, 720)

        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(["Messgröße", "Wert", "Einheit"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        for row, (name, value, unit) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(value))
            table.setItem(row, 2, QTableWidgetItem(unit))

        close_button = QPushButton("Schließen")
        close_button.clicked.connect(dialog.close)

        layout.addWidget(table)
        layout.addWidget(close_button)
        dialog.exec()

    def _install_frequency_hover(self, plot, data_getter, value_suffix=""):
        """Zeigt beim Hover den nächstgelegenen Messpunkt mit seinen Werten."""
        marker = pg.ScatterPlotItem(
            [], [],
            symbol="o",
            size=13,
            brush=pg.mkBrush(255, 255, 255),
            pen=pg.mkPen("k", width=2),
        )
        plot.addItem(marker)

        label = pg.TextItem(
            "",
            color="k",
            fill=pg.mkBrush(255, 255, 255, 230),
            border=pg.mkPen(80, 80, 80),
            anchor=(0, 1),
        )
        label.hide()
        plot.addItem(label)

        def on_mouse_moved(scene_pos):
            if not plot.sceneBoundingRect().contains(scene_pos):
                marker.setData([], [])
                label.hide()
                return

            frequencies, series = data_getter()
            if not frequencies:
                marker.setData([], [])
                label.hide()
                return

            mouse_point = plot.getPlotItem().vb.mapSceneToView(scene_pos)
            x = np.asarray(frequencies, dtype=float)
            index = int(np.argmin(np.abs(x - mouse_point.x())))

            # Nur anzeigen, wenn der Mauszeiger in der Nähe eines vorhandenen
            # Messpunktes liegt. Der Abstand wird aus der aktuellen Ansicht
            # für x- und y-Achse berechnet.
            x_range = plot.getPlotItem().vb.viewRange()[0]
            y_range = plot.getPlotItem().vb.viewRange()[1]
            x_tolerance = max((x_range[1] - x_range[0]) * 0.015, 1.0)
            y_tolerance = max((y_range[1] - y_range[0]) * 0.03, 1e-9)
            if abs(x[index] - mouse_point.x()) > x_tolerance:
                marker.setData([], [])
                label.hide()
                return

            values = []
            for name, data in series:
                if index < len(data):
                    values.append((name, float(data[index])))

            if not values:
                marker.setData([], [])
                label.hide()
                return

            hover_value = min(
                (value for _, value in values),
                key=lambda value: abs(value - mouse_point.y()),
            )
            if abs(hover_value - mouse_point.y()) > y_tolerance:
                marker.setData([], [])
                label.hide()
                return

            marker.setData([x[index]], [hover_value])
            lines = [f"f = {x[index]:.1f} Hz"]
            lines.extend(
                f"{name} = {value:.3f}{value_suffix}"
                for name, value in values
            )
            label.setText("\n".join(lines))
            label.setPos(x[index], hover_value)
            label.show()

        plot.scene().sigMouseMoved.connect(on_mouse_moved)

        # Referenzen behalten, damit PyQt die Objekte und Callback-Funktionen
        # während der gesamten Lebensdauer des Dialogs nicht freigibt.
        if not hasattr(self, "_hover_items"):
            self._hover_items = []
        self._hover_items.append((plot, marker, label, on_mouse_moved))


    def _install_rms_position_hover(self):
        """Zeigt beim Hover die aktuellen horizontalen RMS-Werte."""
        marker_a = pg.ScatterPlotItem(
            [], [], symbol="o", size=12,
            brush=pg.mkBrush("c"), pen=pg.mkPen("k", width=1),
        )
        marker_b = pg.ScatterPlotItem(
            [], [], symbol="o", size=12,
            brush=pg.mkBrush("m"), pen=pg.mkPen("k", width=1),
        )
        self.rms_plot.addItem(marker_a)
        self.rms_plot.addItem(marker_b)

        label = pg.TextItem(
            "", color="k",
            fill=pg.mkBrush(255, 255, 255, 235),
            border=pg.mkPen(80, 80, 80), anchor=(0, 1),
        )
        label.hide()
        self.rms_plot.addItem(label)

        def on_mouse_moved(scene_pos):
            plot = self.rms_plot
            if not plot.sceneBoundingRect().contains(scene_pos):
                marker_a.setData([], [])
                marker_b.setData([], [])
                label.hide()
                return

            if (
                self.rms_x_mm.size == 0
                or self.current_a_rms_dbuv is None
                or self.current_b_rms_dbuv is None
            ):
                marker_a.setData([], [])
                marker_b.setData([], [])
                label.hide()
                return

            mouse_point = plot.getPlotItem().vb.mapSceneToView(scene_pos)
            x_min = float(self.rms_x_mm[0])
            x_max = float(self.rms_x_mm[-1])
            if not (x_min <= mouse_point.x() <= x_max):
                marker_a.setData([], [])
                marker_b.setData([], [])
                label.hide()
                return

            y_range = plot.getPlotItem().vb.viewRange()[1]
            y_tolerance = max((y_range[1] - y_range[0]) * 0.03, 1e-9)
            distances = [
                abs(float(self.current_a_rms_dbuv) - mouse_point.y()),
                abs(float(self.current_b_rms_dbuv) - mouse_point.y()),
            ]
            if min(distances) > y_tolerance:
                marker_a.setData([], [])
                marker_b.setData([], [])
                label.hide()
                return

            x_pos = float(mouse_point.x())

            marker_a.setData([x_pos], [self.current_a_rms_dbuv])
            marker_b.setData([x_pos], [self.current_b_rms_dbuv])
            label.setText(
                f"x = {x_pos:.1f} mm\n"
                f"A_RMS = {self.current_a_rms_dbuv:.3f} dBµV\n"
                f"B_RMS = {self.current_b_rms_dbuv:.3f} dBµV"
            )
            label.setPos(x_pos, self.current_a_rms_dbuv)
            label.show()

        self.rms_plot.scene().sigMouseMoved.connect(on_mouse_moved)
        if not hasattr(self, "_hover_items"):
            self._hover_items = []
        self._hover_items.append(
            (self.rms_plot, marker_a, marker_b, label, on_mouse_moved)
        )

    @staticmethod
    def _box(title, plot):
        box = QGroupBox()
        layout = QVBoxLayout(box)
        layout.addWidget(plot)
        return box

    @staticmethod
    def _make_plot(title, xlabel, ylabel):
        plot = pg.PlotWidget(background="w")
        plot.setTitle(title, color="k")
        plot.setLabel("bottom", xlabel, color="k")
        plot.setLabel("left", ylabel, color="k")
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")
        plot.setMouseEnabled(x=True, y=True)
        for axis_name in ("bottom", "left"):
            axis = plot.getAxis(axis_name)
            axis.setPen(pg.mkPen("k"))
            axis.setTextPen(pg.mkPen("k"))
            axis.enableAutoSIPrefix(False)
        plot.getPlotItem().titleLabel.item.setDefaultTextColor("black")
        return plot

    @staticmethod
    def _add_top_right_legend(plot):
        legend = plot.addLegend(
            offset=(-10, 10),
            brush=pg.mkBrush(255, 255, 255, 245),
            pen=pg.mkPen(130, 130, 130),
            labelTextColor=(0, 0, 0),
            labelTextSize="12pt",
        )
        legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-10, 10))
        legend.setZValue(1000)
        return legend

    @staticmethod
    def _add_bottom_left_legend(plot):
        legend = plot.addLegend(
            offset=(10, -8),
            brush=pg.mkBrush(255, 255, 255, 245),
            pen=pg.mkPen(130, 130, 130),
            labelTextColor=(0, 0, 0),
            labelTextSize="12pt",
        )
        legend.anchor(itemPos=(0, 1), parentPos=(0, 1), offset=(10, -8))
        legend.setZValue(1000)
        return legend

    @staticmethod
    def _add_bottom_right_legend(plot):
        legend = plot.addLegend(
            offset=(-10, -10),
            brush=pg.mkBrush(255, 255, 255, 245),
            pen=pg.mkPen(130, 130, 130),
            labelTextColor=(0, 0, 0),
            labelTextSize="12pt",
        )
        legend.anchor(itemPos=(1, 1), parentPos=(1, 1), offset=(-10, -10))
        legend.setZValue(1000)
        return legend

    @staticmethod
    def _move_legend_bottom_left(plot):
        legend = plot.getPlotItem().legend
        if legend is None:
            return
        legend.anchor(itemPos=(0, 1), parentPos=(0, 1), offset=(10, -8))
        legend.setZValue(1000)

    def clear_data(self):
        self.frequencies.clear()
        self.reflection.clear()
        self.dissipation.clear()
        self.a_abs_uv.clear()
        self.b_abs_uv.clear()
        self.a_rms_dbuv.clear()
        self.b_rms_dbuv.clear()
        self.frequency_items.clear()
        self.rms_x_mm = np.array([], dtype=float)
        self.current_a_rms_dbuv = None
        self.current_b_rms_dbuv = None
        self.a_rms_curve.setData([], [])
        self.b_rms_curve.setData([], [])
        self.last_wave = None
        self.last_frequency = None
        self._refresh_frequency_curves()
        self.spatial_plot.clear()
        self.spatial_plot.addLegend(offset=(10, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")
        self.status_label.setText("Sweep gestartet …")

    def append_frequency_result(self, item):
        f = float(item["frequency"])
        A_abs = float(item["A_abs"])
        B_abs = float(item["B_abs"])
        R = float(np.clip(item["reflection_energy"], 0.0, 1.0))
        D = float(np.clip(
            item.get("dissipation", item.get("dissipation_percent", 0.0) / 100.0),
            0.0,
            1.0,
        ))

        eps = 1e-30
        A_rms = A_abs / np.sqrt(2.0)
        B_rms = B_abs / np.sqrt(2.0)
        A_dbuv = 20.0 * np.log10((A_rms + eps) / 1e-6)
        B_dbuv = 20.0 * np.log10((B_rms + eps) / 1e-6)

        self.frequencies.append(f)
        self.reflection.append(R)
        self.dissipation.append(D)
        self.a_abs_uv.append(A_abs * 1e6)
        self.b_abs_uv.append(B_abs * 1e6)
        self.a_rms_dbuv.append(A_dbuv)
        self.b_rms_dbuv.append(B_dbuv)
        self.frequency_items.append(item)
        self.current_a_rms_dbuv = float(A_dbuv)
        self.current_b_rms_dbuv = float(B_dbuv)

        wave = item.get("wave")
        if wave is None and item.get("step_results"):
            wave = item["step_results"][-1].get("wave")

        if wave is not None:
            self.last_wave = wave
            self.last_frequency = f
            self._update_spatial_wave(wave, f)

        self._refresh_frequency_curves()
        self.status_label.setText(
            f"f = {f:.1f} Hz | R = {R:.3f} | D = {D:.3f}"
        )

    def set_single_frequency_result(self, item):
        self.clear_data()
        self.append_frequency_result(item)

        f = float(item["frequency"])
        A_uv = float(item["A_abs"]) * 1e6
        B_uv = float(item["B_abs"]) * 1e6
        R = float(np.clip(item["reflection_energy"], 0.0, 1.0))
        D = float(np.clip(
            item.get("dissipation", item.get("dissipation_percent", 0.0) / 100.0),
            0.0,
            1.0,
        ))
        gamma = float(abs(item.get("B_over_A", item.get("r_abs", np.sqrt(R)))))
        if gamma >= 1.0:
            swr = np.inf
            swr_plot_value = 20.0
            swr_label = "∞"
        else:
            swr = (1.0 + gamma) / (1.0 - gamma)
            swr_plot_value = float(swr)
            swr_label = f"{swr:.3f}"

        self.rd_plot.clear()
        self._add_top_right_legend(self.rd_plot)
        self.rd_plot.setTitle(
            "Reflexionskennwerte bei f = {:.2f} Hz".format(f),
            color="k",
        )
        self.rd_plot.showAxis("bottom")
        self.rd_plot.showAxis("left")
        self.rd_plot.showGrid(x=True, y=True, alpha=0.25)
        r_bar = pg.BarGraphItem(
            x=[R / 2.0],
            y=[1.0],
            width=R,
            height=0.45,
            brush=pg.mkBrush("b"),
            pen=pg.mkPen("b"),
        )
        d_bar = pg.BarGraphItem(
            x=[D / 2.0],
            y=[0.0],
            width=D,
            height=0.45,
            brush=pg.mkBrush("r"),
            pen=pg.mkPen("r"),
        )
        self.rd_plot.addItem(r_bar)
        self.rd_plot.addItem(d_bar)
        self.rd_plot.plot([R], [1.0], pen=None, symbol="o", symbolBrush="b", name=f"R = {R:.3f}")
        self.rd_plot.plot([D], [0.0], pen=None, symbol="o", symbolBrush="r", name=f"D = {D:.3f}")
        self.rd_plot.plot([], [], pen=None, symbol="o", symbolBrush=pg.mkBrush(120, 60, 220), name=f"|r| = {gamma:.3f}")
        self.rd_plot.plot([], [], pen=None, symbol="o", symbolBrush=pg.mkBrush(255, 170, 0), name=f"SWR = {swr_label}")
        self.rd_plot.setLabel("bottom", "Wert")
        self.rd_plot.setLabel("left", "")
        self.rd_plot.getAxis("left").setTicks([[(1.0, "R"), (0.0, "D")]])
        x_max = max(1.0, R, D) * 1.15
        self.rd_plot.setXRange(0.0, x_max, padding=0.05)
        self.rd_plot.setYRange(-0.7, 1.7, padding=0)
        r_text = pg.TextItem(f"R = {R:.3f}", color="k", anchor=(0, 0.5))
        d_text = pg.TextItem(f"D = {D:.3f}", color="k", anchor=(0, 0.5))
        r_text.setPos(min(R + 0.03 * x_max, x_max * 0.95), 1.0)
        d_text.setPos(min(D + 0.03 * x_max, x_max * 0.95), 0.0)
        self.rd_plot.addItem(r_text)
        self.rd_plot.addItem(d_text)

        self.ab_plot.clear()
        self._add_bottom_right_legend(self.ab_plot)
        self.ab_plot.setTitle(
            f"Hin- und rücklaufende Welle bei f = {f:.2f} Hz",
            color="k",
        )
        max_amp = max(A_uv, B_uv, 1.0)
        a_bar = pg.BarGraphItem(
            x=[A_uv / 2.0],
            y=[1.0],
            width=A_uv,
            height=0.45,
            brush=pg.mkBrush("c"),
            pen=pg.mkPen("c"),
        )
        b_bar = pg.BarGraphItem(
            x=[B_uv / 2.0],
            y=[0.0],
            width=B_uv,
            height=0.45,
            brush=pg.mkBrush("m"),
            pen=pg.mkPen("m"),
        )
        self.ab_plot.addItem(a_bar)
        self.ab_plot.addItem(b_bar)
        self.ab_plot.plot([A_uv], [1.0], pen=None, symbol="o", symbolBrush="c", name=f"|A| = {A_uv:.3f} µV")
        self.ab_plot.plot([B_uv], [0.0], pen=None, symbol="o", symbolBrush="m", name=f"|B| = {B_uv:.3f} µV")
        self.ab_plot.setLabel("bottom", "Amplitude [µV]")
        self.ab_plot.setLabel("left", "")
        self.ab_plot.getAxis("left").setTicks([[(1.0, "|A|"), (0.0, "|B|")]])
        self.ab_plot.setXRange(0.0, max_amp * 1.15, padding=0)
        self.ab_plot.setYRange(-0.7, 1.7, padding=0)
        a_text = pg.TextItem(f"|A| = {A_uv:.3f} µV", color="k", anchor=(0, 0.5))
        b_text = pg.TextItem(f"|B| = {B_uv:.3f} µV", color="k", anchor=(0, 0.5))
        a_text.setPos(A_uv + 0.03 * max_amp, 1.0)
        b_text.setPos(B_uv + 0.03 * max_amp, 0.0)
        self.ab_plot.addItem(a_text)
        self.ab_plot.addItem(b_text)
        self._update_spatial_swr_wave(item, f, gamma, swr_label)

    def set_single_wave(self, wave, f0):
        self.last_wave = wave
        self.last_frequency = float(f0)
        self._update_spatial_wave(wave, float(f0))
        self.status_label.setText(f"Wellenzerlegung bei f = {float(f0):.1f} Hz")

    def _update_spatial_swr_wave(self, item, f0, gamma, swr_label):
        wave = item.get("wave")
        if wave is None and item.get("step_results"):
            wave = item["step_results"][-1].get("wave")
        if wave is None:
            return

        f0 = float(f0)
        k = 2.0 * np.pi * f0 / SPEED_OF_SOUND
        tube_length = 0.8
        x = np.linspace(-tube_length, 0.0, 2000)
        x_mm = x * 1000.0

        p_abs_uv = np.abs(
            wave["A"] * np.exp(-1j * k * x)
            + wave["B"] * np.exp(1j * k * x)
        ) * 1e6

        max_uv = float(np.max(p_abs_uv))
        min_uv = float(np.min(p_abs_uv))

        plot = self.rms_plot
        plot.clear()
        self._add_bottom_right_legend(plot)
        plot.setTitle(
            "Ortsverlauf der stehenden Welle |P<sub>rek</sub>(x)| "
            f"bei f = {f0:.2f} Hz",
            color="k",
        )
        plot.setLabel("bottom", "Rohrposition x [mm]")
        plot.setLabel("left", "|P<sub>rek</sub>(x)| [µV]")

        plot.plot(
            x_mm,
            p_abs_uv,
            pen=pg.mkPen(0, 90, 220, width=3),
            name=(
                "|P<sub>rek</sub>(x)|, "
                f"SWR = {swr_label}"
            ),
        )
        plot.plot(
            x_mm,
            np.ones_like(x_mm) * max_uv,
            pen=pg.mkPen("r", width=2, style=Qt.DashLine),
            name=f"p<sub>max</sub> = {max_uv:.3f} µV",
        )
        plot.plot(
            x_mm,
            np.ones_like(x_mm) * min_uv,
            pen=pg.mkPen("g", width=2, style=Qt.DashLine),
            name=f"p<sub>min</sub> = {min_uv:.3f} µV",
        )

        wavelength_mm = SPEED_OF_SOUND / f0 * 1000.0
        half_wavelength_mm = wavelength_mm / 2.0
        min_indices = np.flatnonzero(
            (p_abs_uv[1:-1] <= p_abs_uv[:-2])
            & (p_abs_uv[1:-1] <= p_abs_uv[2:])
        ) + 1
        if min_indices.size:
            plot_center_mm = float((x_mm[0] + x_mm[-1]) / 2.0)
            valid_min_indices = [
                index
                for index in min_indices
                if float(x_mm[index]) + wavelength_mm <= float(x_mm[-1])
            ]
            if not valid_min_indices:
                valid_min_indices = list(min_indices)

            start_index = min(
                valid_min_indices,
                key=lambda index: abs(float(x_mm[index]) - plot_center_mm),
            )
            lambda_start_mm = float(x_mm[start_index])
            lambda_end_mm = min(lambda_start_mm + half_wavelength_mm, float(x_mm[-1]))
        else:
            visible_length_mm = float(x_mm[-1] - x_mm[0])
            lambda_line_length_mm = min(half_wavelength_mm, visible_length_mm)
            lambda_center_mm = float((x_mm[0] + x_mm[-1]) / 2.0)
            lambda_start_mm = lambda_center_mm - lambda_line_length_mm / 2.0
            lambda_end_mm = lambda_center_mm + lambda_line_length_mm / 2.0
        lambda_center_mm = (lambda_start_mm + lambda_end_mm) / 2.0
        lambda_y = max_uv * 0.78
        tick_height = max(max_uv * 0.04, 0.25)

        lambda_pen = pg.mkPen("r", width=2)
        plot.plot([lambda_start_mm, lambda_end_mm], [lambda_y, lambda_y], pen=lambda_pen)
        plot.plot(
            [lambda_start_mm, lambda_start_mm],
            [lambda_y - tick_height, lambda_y + tick_height],
            pen=lambda_pen,
        )
        plot.plot(
            [lambda_end_mm, lambda_end_mm],
            [lambda_y - tick_height, lambda_y + tick_height],
            pen=lambda_pen,
        )
        lambda_label = pg.TextItem(
            f"λ/2 = {half_wavelength_mm:.1f} mm",
            color="r",
            anchor=(0.5, 0.0),
        )
        lambda_label.setPos(lambda_center_mm, lambda_y - tick_height * 1.4)
        plot.addItem(lambda_label)

        full_lambda_line_length_mm = min(wavelength_mm, float(x_mm[-1] - x_mm[0]))
        full_lambda_start_mm = lambda_start_mm
        full_lambda_end_mm = full_lambda_start_mm + full_lambda_line_length_mm
        if full_lambda_end_mm > float(x_mm[-1]):
            full_lambda_end_mm = float(x_mm[-1])
            full_lambda_start_mm = full_lambda_end_mm - full_lambda_line_length_mm
        full_lambda_center_mm = (full_lambda_start_mm + full_lambda_end_mm) / 2.0
        full_lambda_y = max_uv * 0.94
        full_lambda_pen = pg.mkPen("r", width=2, style=Qt.DashLine)
        plot.plot(
            [full_lambda_start_mm, full_lambda_end_mm],
            [full_lambda_y, full_lambda_y],
            pen=full_lambda_pen,
        )
        plot.plot(
            [full_lambda_start_mm, full_lambda_start_mm],
            [full_lambda_y - tick_height, full_lambda_y + tick_height],
            pen=full_lambda_pen,
        )
        plot.plot(
            [full_lambda_end_mm, full_lambda_end_mm],
            [full_lambda_y - tick_height, full_lambda_y + tick_height],
            pen=full_lambda_pen,
        )
        full_lambda_label = pg.TextItem(
            f"λ = {wavelength_mm:.1f} mm",
            color="r",
            anchor=(0.5, 0.0),
        )
        full_lambda_label.setPos(full_lambda_center_mm, full_lambda_y - tick_height * 1.4)
        plot.addItem(full_lambda_label)

        plot.setXRange(float(x_mm[0]), float(x_mm[-1]), padding=0)
        plot.setYRange(0.0, max(max_uv * 1.15, 1.0), padding=0)
        self.status_label.setText(
            f"f = {f0:.1f} Hz | |B/A| = {gamma:.3f} | SWR = {swr_label}"
        )

    def set_results(self, results):
        self.clear_data()
        for item in results:
            self.append_frequency_result(item)
        if results:
            self.status_label.setText(f"{len(results)} Frequenzpunkte geladen")

    def _refresh_frequency_curves(self):
        x = np.asarray(self.frequencies, dtype=float)
        self.reflection_curve.setData(x, np.asarray(self.reflection, dtype=float))
        self.dissipation_curve.setData(x, np.asarray(self.dissipation, dtype=float))
        self.a_curve.setData(x, np.asarray(self.a_abs_uv, dtype=float))
        self.b_curve.setData(x, np.asarray(self.b_abs_uv, dtype=float))
        if x.size:
            x_min = float(np.min(x))
            x_max = float(np.max(x))
            if x_min == x_max:
                margin = max(20.0, abs(x_min) * 0.05)
                x_min -= margin
                x_max += margin
            for plot in (self.rd_plot, self.ab_plot):
                plot.setXRange(x_min, x_max, padding=0.03)

    def _update_spatial_wave(self, wave, f0):
        """Zeichnet den bisherigen Ortsplot live mit M1, M2 und M3."""
        A_abs = float(wave["A_abs"])
        A_phase = float(wave["A_phase"])
        B_abs = float(wave["B_abs"])
        B_phase = float(wave["B_phase"])
        f0 = float(f0)

        k = 2.0 * np.pi * f0 / SPEED_OF_SOUND
        x_min = -SPEED_OF_SOUND / f0
        x_max = 0.0
        x = np.linspace(x_min, x_max, 1000)
        x_mm = x * 1000.0

        # RMS-Plot: zwei gerade Linien über derselben Rohrposition.
        eps = 1e-30
        A_rms_dbuv = 20.0 * np.log10((A_abs / np.sqrt(2.0) + eps) / 1e-6)
        B_rms_dbuv = 20.0 * np.log10((B_abs / np.sqrt(2.0) + eps) / 1e-6)
        self.rms_x_mm = x_mm.copy()
        self.current_a_rms_dbuv = float(A_rms_dbuv)
        self.current_b_rms_dbuv = float(B_rms_dbuv)
        self.a_rms_curve.setData(
            x_mm, np.full_like(x_mm, A_rms_dbuv, dtype=float),
            name=f"A_RMS = {A_rms_dbuv:.2f} dBµV",
        )
        self.b_rms_curve.setData(
            x_mm, np.full_like(x_mm, B_rms_dbuv, dtype=float),
            name=f"B_RMS = {B_rms_dbuv:.2f} dBµV",
        )
        self.rms_plot.setXRange(float(x_mm[0]), float(x_mm[-1]), padding=0)
        self.rms_plot.setTitle(
            f"RMS-Pegel bei f = {f0:.2f} Hz",
            color="k",
        )

        a_uv = A_abs * np.cos(-k * x + A_phase) * 1e6
        b_uv = B_abs * np.cos(+k * x + B_phase) * 1e6
        p_uv = a_uv + b_uv

        plot = self.spatial_plot
        plot.clear()
        self._add_bottom_right_legend(plot)
        plot.setTitle(
            f"Momentaufnahme der Wellenzerlegung im Ortsbereich bei f = {f0:.2f} Hz, "
            f"λ = {SPEED_OF_SOUND / f0 * 1000.0:.3f} mm",
            color="k",
        )
        plot.setLabel("left", "Momentanwert [µV]", color="k")

        plot.plot(x_mm, a_uv, pen=pg.mkPen("c", width=2), name="a(x) hinlaufend")
        plot.plot(x_mm, b_uv, pen=pg.mkPen("m", width=2), name="b(x) rücklaufend")
        plot.plot(x_mm, p_uv, pen=pg.mkPen("g", width=2), name="p(x) = a(x) + b(x)")

        y_values = np.concatenate([a_uv, b_uv, p_uv])
        y_min = float(np.min(y_values))
        y_max = float(np.max(y_values))
        y_span = max(y_max - y_min, 1.0)

        for index, (mic_x, mic_name) in enumerate(
            [(MIC_X1, "M1"), (MIC_X2, "M2"), (MIC_X3, "M3")]
        ):
            mic_x_mm = mic_x * 1000.0
            a_mic = A_abs * np.cos(-k * mic_x + A_phase) * 1e6
            b_mic = B_abs * np.cos(+k * mic_x + B_phase) * 1e6
            p_mic = a_mic + b_mic

            plot.addItem(pg.InfiniteLine(
                pos=mic_x_mm,
                angle=90,
                movable=False,
                pen=pg.mkPen((120, 120, 0), width=1),
            ))

            plot.plot([mic_x_mm], [a_mic], pen=None, symbol="o", symbolSize=8,
                      symbolBrush="c", symbolPen=pg.mkPen("k"))
            plot.plot([mic_x_mm], [b_mic], pen=None, symbol="o", symbolSize=8,
                      symbolBrush="m", symbolPen=pg.mkPen("k"))
            plot.plot([mic_x_mm], [p_mic], pen=None, symbol="o", symbolSize=10,
                      symbolBrush="g", symbolPen=pg.mkPen("k"))

            text = pg.TextItem(
                f"{mic_name}\na={a_mic:.1f} µV\nb={b_mic:.1f} µV\np={p_mic:.1f} µV",
                color="k",
                anchor=(0, 1),
            )
            text.setPos(mic_x_mm + 2.0, p_mic + (0.08 + 0.03 * index) * y_span)
            plot.addItem(text)

        plot.setXRange(x_min * 1000.0, x_max * 1000.0, padding=0)
        plot.setYRange(y_min - 0.12 * y_span, y_max + 0.20 * y_span, padding=0)

'''
Die Klasse StartScreen ist das Hauptmenü der Anwendung, das große Buttons für die verschiedenen Funktionen bietet:
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

        group = QGroupBox("Agilent 33120A")
        group_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.resource_edit = QLineEdit("GPIB0::12::INSTR")
        self.gen_connect_button = QPushButton("Verbinden")
        self.gen_id_button = QPushButton("ID lesen")

        row1.addWidget(QLabel("Ressource"))
        row1.addWidget(self.resource_edit)
        row1.addWidget(self.gen_connect_button)
        row1.addWidget(self.gen_id_button)

        row2 = QHBoxLayout()
        self.freq_edit = QLineEdit(str(int(DEFAULT_MEASUREMENT_F0)))
        self.amp_edit = QLineEdit("0.05")
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
                self.generator = Agilent33120A(resource)
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

            if amp < MIN_GENERATOR_VOLTAGE or amp > MAX_GENERATOR_VOLTAGE:
                raise ValueError(
                    f"Amplitude muss zwischen {MIN_GENERATOR_VOLTAGE:.6f} V "
                    f"und {MAX_GENERATOR_VOLTAGE:.1f} V liegen."
    )

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
        self.wave_dialog = None
        self.frequency_analysis_dialog = None
        self.recording_analysis_dialog = None
        self.automation_analysis_dialog = None
        self.sweep_cancel_requested = False
        self.last_result = None

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
     

        self.f0_detected_label = QLabel("Freq. : - Hz")
        row1.addWidget(self.f0_detected_label)
        self.f0_detected_label.setStyleSheet("font-size: 20px; font-weight: bold; color: blue;")

        row1.addStretch()

        row3 = QHBoxLayout()
        self.audio_start_button = QPushButton("▶ Live")
        self.audio_stop_button = QPushButton("■ Stop")
        self.record_button = QPushButton("● Aufnahme")
        self.show_log_button = QPushButton("📋 Log")
        self.show_results_button = QPushButton("Komplexspektrum anzeigen")
        self.auto_start_button = QPushButton("⚙ Automation")
        self.sweep_button = QPushButton("↻ Frequenzschleife")
    

        row3.addWidget(self.audio_start_button)
        row3.addWidget(self.audio_stop_button)
        row3.addWidget(self.record_button)
        row3.addWidget(self.show_log_button)
        row3.addWidget(self.show_results_button)
        row3.addWidget(self.auto_start_button)
        row3.addWidget(self.sweep_button)
        

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
            fft_plot.setLabel("left", "|FFT| [dBµV]")
            fft_plot.getAxis("left").enableAutoSIPrefix(False)
            fft_plot.showGrid(x=True, y=True)
            fft_plot.setMouseEnabled(x=True, y=False)
            fft_curve = fft_plot.plot([], [], pen="y")
            fft_plot.setXRange(-FFT_MAX_FREQ, FFT_MAX_FREQ, padding=0)
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
        self.audio_start_button.clicked.connect(self.start_audio)
        self.audio_stop_button.clicked.connect(self.stop_audio)
        self.record_button.clicked.connect(self.on_record_clicked)
        self.sample_rate_combo.currentTextChanged.connect(self.refresh_time_axis_only)
        self.show_log_button.clicked.connect(self.show_log_window)
        self.show_results_button.clicked.connect(self.show_results_window)
        self.measurement_duration_edit.editingFinished.connect(self.refresh_time_axis_only)


    def show_wave_window(self):
        """Zeigt nur die Wellenzerlegung der letzten Einzelmessung."""
        if self.last_result is None:
            QMessageBox.information(
                self,
                "Keine Ergebnisse",
                "Bitte zuerst eine Aufnahme durchführen.",
            )
            return

        self.wave_dialog = WaveDecompositionDialog(
            wave=self.last_result["wave"],
            f0=self.last_result["f0"],
            parent=self,
        )
        self.wave_dialog.show()
        self.wave_dialog.raise_()
        self.wave_dialog.activateWindow()

    def prepare_automation_dashboard(self):
        """Öffnet die Live-Anzeige für den automatischen Frequenz-Sweep."""
        if self.automation_analysis_dialog is None:
            self.automation_analysis_dialog = AutomationAnalysisDialog(
                target_amp=TARGET_AMP,
                tolerance=AMP_TOLERANCE,
                parent=self,
            )

        self.sweep_cancel_requested = False
        self.sweep_results = []
        self.automation_analysis_dialog.clear_data()
        self.automation_analysis_dialog.show()
        self.automation_analysis_dialog.raise_()
        self.automation_analysis_dialog.activateWindow()
        QApplication.processEvents()
        self.automation_analysis_dialog.repaint()
        QApplication.processEvents()

    def update_automation_dashboard(self, frequency_result, all_results=None):
        """Aktualisiert A/B und gefundene Spannung nach jeder Frequenz."""
        if self.sweep_cancel_requested:
            return

        if self.automation_analysis_dialog is None:
            self.automation_analysis_dialog = AutomationAnalysisDialog(
                target_amp=TARGET_AMP,
                tolerance=AMP_TOLERANCE,
                parent=self,
            )
            self.automation_analysis_dialog.show()

        self.automation_analysis_dialog.append_frequency_result(frequency_result)
        if all_results is not None:
            self.sweep_results = list(all_results)
        else:
            self.sweep_results = getattr(self, "sweep_results", []) + [frequency_result]

        self.automation_analysis_dialog.repaint()
        self.automation_analysis_dialog.ab_plot.repaint()
        self.automation_analysis_dialog.voltage_plot.repaint()
        QApplication.processEvents()

    def prepare_live_frequency_dashboard(self):
        """Wird ausschließlich beim Klick auf Frequenzschleife aufgerufen."""
        if self.frequency_analysis_dialog is None:
            self.frequency_analysis_dialog = FrequencyAnalysisDialog(parent=self)

        self.sweep_cancel_requested = False
        self.sweep_results = []
        self.frequency_analysis_dialog.clear_data()
        self.frequency_analysis_dialog.show()
        self.frequency_analysis_dialog.raise_()
        self.frequency_analysis_dialog.activateWindow()

        # Das Fenster muss vor Beginn der blockierenden Messschleife sichtbar
        # und vollständig gezeichnet werden.
        QApplication.processEvents()
        self.frequency_analysis_dialog.repaint()
        QApplication.processEvents()

    def update_live_frequency_dashboard(self, frequency_result, all_results=None):
        """Fügt nach jeder vollständig gemessenen Frequenz einen Punkt hinzu."""
        if self.sweep_cancel_requested:
            return

        if self.frequency_analysis_dialog is None:
            self.frequency_analysis_dialog = FrequencyAnalysisDialog(parent=self)
            self.frequency_analysis_dialog.show()

        self.frequency_analysis_dialog.append_frequency_result(frequency_result)
        if all_results is not None:
            self.sweep_results = list(all_results)
        else:
            self.sweep_results = getattr(self, "sweep_results", []) + [frequency_result]

        # Sofortiges Neuzeichnen aller vier Plots nach jedem Frequenzschritt.
        self.frequency_analysis_dialog.repaint()
        for plot in (
            self.frequency_analysis_dialog.rd_plot,
            self.frequency_analysis_dialog.ab_plot,
            self.frequency_analysis_dialog.spatial_plot,
            self.frequency_analysis_dialog.rms_plot,
        ):
            plot.repaint()
        QApplication.processEvents()

    def set_fft_xrange_around_f0(self, f0=None):
        for plot in self.fft_plot_widgets:
            plot.setXRange(-FFT_MAX_FREQ, FFT_MAX_FREQ, padding=0)

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

        freqs = []
        reflection = []
        dissipation = []

        for item in self.sweep_results:
            f = float(item["frequency"])
            freqs.append(f)

            # -----------------------------
            # Reflexion R = |B/A|²
            # -----------------------------
            if "reflection_energy" in item:
                R = float(item["reflection_energy"])
            elif "r_abs" in item:
                R = float(item["r_abs"]) ** 2
            elif "B_over_A" in item:
                R = float(item["B_over_A"]) ** 2
            else:
                R = 0.0

            # Werte begrenzen
            R = float(np.clip(R, 0.0, 1.0))

          

            # -----------------------------
            # Dissipation Δ = 1 - R - T
            # -----------------------------
            if "dissipation" in item:
                D = float(item["dissipation"])
            elif "dissipation_percent" in item:
                D = float(item["dissipation_percent"]) / 100.0
            else:
                D = 1.0 - R 

            D = float(np.clip(D, 0.0, 1.0))

            reflection.append(R)
            dissipation.append(D)

        freqs = np.array(freqs, dtype=float)
        reflection = np.array(reflection, dtype=float)
        dissipation = np.array(dissipation, dtype=float)

        # -------------------------------------------------
        # Dialog
        # -------------------------------------------------
        dialog = QDialog(self)
        dialog.setWindowTitle("Reflexion und Dissipation")
        dialog.resize(1200, 750)

        layout = QVBoxLayout()

        plot = pg.PlotWidget(title="Reflexionsgrad und Dissipationsgrad über Frequenz")
        plot.setLabel("bottom", "Frequenz [Hz]")
        plot.setLabel("left", "R, Δ")
        plot.getAxis("bottom").enableAutoSIPrefix(False)
        plot.getAxis("left").enableAutoSIPrefix(False)
        plot.showGrid(x=True, y=True)
        plot.addLegend(offset=(350, 10), labelTextColor=(0, 0, 0), labelTextSize="12pt")

        # -------------------------------------------------
        # Kurven wie im Beispiel
        # -------------------------------------------------
        plot.plot(
            freqs,
            reflection,
            pen=pg.mkPen("b", width=2),
            symbol="o",
            symbolSize=4,
            symbolBrush="b",
            name="R = |B/A|²"
        )

        plot.plot(
            freqs,
            dissipation,
            pen=pg.mkPen("y", width=2),
            symbol="o",
            symbolSize=4,
            symbolBrush="w",
            name="Dissipation:Δ = 1 - R"
        )

        plot.setYRange(0.0, 1.0, padding=0.05)

        if len(freqs) > 0:
            plot.setXRange(float(np.min(freqs)), float(np.max(freqs)), padding=0.03)

        # -------------------------------------------------
        # Max. damping markieren
        # -------------------------------------------------
        idx_max = int(np.argmax(dissipation))
        f_max = float(freqs[idx_max])
        d_max = float(dissipation[idx_max])

        max_text = pg.TextItem(
            f"Max. damping\nf = {f_max:.1f} Hz\nΔ = {d_max:.3f}",
            color="k",
            anchor=(0, 1)
        )
        max_text.setPos(f_max, d_max)
        plot.addItem(max_text)

        max_marker = pg.ScatterPlotItem(
            [f_max],
            [d_max],
            symbol="o",
            size=14,
            brush="w",
            pen=pg.mkPen("k", width=2)
        )
        plot.addItem(max_marker)

        # -------------------------------------------------
        # Formel im Plot
        # -------------------------------------------------
        formula_text = pg.TextItem(
            "Dissipation\nΔ = 1 - R",
            color="k",
            anchor=(0, 0)
        )

        x_formula = float(freqs[0] + 0.25 * (freqs[-1] - freqs[0]))
        y_formula = 0.55
        formula_text.setPos(x_formula, y_formula)
        plot.addItem(formula_text)

        layout.addWidget(plot)

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
        return float(self.current_f0)

    
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

        # Frequenzgang der simulierten Quelle / Messstrecke.
        # Bei konstanter Generator-Spannung ist |A(f)| nicht konstant.
        source_response = (
            0.72
            + 0.18 * np.exp(-((f0 - 650.0) / 300.0) ** 2)
            + 0.14 * np.exp(-((f0 - 1450.0) / 380.0) ** 2)
        )
        A_abs = 5.0e-4 * generator_voltage * source_response

        # -------------------------------------------------
        # Frequenzabhängiges Reflexionsmodell
        # -------------------------------------------------
        # r_abs ist |B|/|A|
        # Wertebereich ungefähr 0.2 bis 0.95
        r_abs = (
            0.35
            + 0.35 * np.exp(-((f0 - 500.0) / 250.0) ** 2)
            + 0.25 * np.exp(-((f0 - 1600.0) / 300.0) ** 2)
        )

        r_abs = float(np.clip(r_abs, 0.05, 0.95))

        # Frequenzabhängige Reflexionsphase
        r_phase = -0.8 + 0.0025 * f0

        B_abs = r_abs * A_abs

        A_sim = A_abs * np.exp(1j * 0.2)
        B_sim = B_abs * np.exp(1j * r_phase)

        positions = [MIC_X1, MIC_X2, MIC_X3]
        audio = np.zeros((n, self.num_channels), dtype=np.float64)

        rng = np.random.default_rng(12345)
        noise_level = 2.0e-12

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
            plot.setXRange(-FFT_MAX_FREQ, FFT_MAX_FREQ, padding=0)

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

            # delay, live wirkt durch die Pufferung etwas verzögert,
            self.last_mode = "live"
            self.timer.start(100) # bei 100 Bsp. alle 100 ms aktualisieren

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
        search_start = 0  #int(0.1 * sample_rate)
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

        f0 = estimate_f0_from_fft(signal, self._get_sample_rate())
        self.f0_detected_label.setText(f"f0: {float(f0):.2f} Hz")

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
            self.show_recording_analysis_window(result)

        except Exception as e:
            QMessageBox.critical(self, "Eingabe-Fehler", str(e))


    def run_measurement(self, duration, f0=None):
        self.timer.stop()

        if f0 is not None:
            self.current_f0 = float(f0)

        if self.focusrite is not None:
            self.focusrite.stop_input_stream()
            self.focusrite = None

        measurement_start = time.monotonic()
        raw_signal, self.focusrite = record_signal(
            duration=duration,
            using_simulation=self._using_simulation(),
            generate_simulated_signal=self._generate_simulated_signal,
            create_focusrite=self._create_focusrite,
        )
        remaining = float(duration) - (time.monotonic() - measurement_start)
        if remaining > 0:
            time.sleep(remaining)

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
        self.last_result = result

        f0 = result["f0"]

        self.f0_detected_label.setText(f"f0: {float(f0):.2f} Hz")

        self.update_time_plot(result["signal"], f0)

        self.fft_freq_axis = result["fft"]["freqs"]
        self.fft_buffers = result["fft_buffers"] if "fft_buffers" in result else result["fft"]["fft_buffers"]
        self._refresh_fft_plots()

        self._write_log_entries(result["log_entries"])

        self.results_dialog = ComplexResultsDialog(
            result["mic_results"],
            f0=f0,
            parent=self,
        )

    def show_recording_analysis_window(self, result):
        f0 = float(result["f0"])
        wave = result["wave"]
        item = {
            "frequency": f0,
            "A_abs": wave["A_abs"],
            "B_abs": wave["B_abs"],
            "B_over_A": wave["B_over_A"],
            "r_abs": wave["r_abs"],
            "reflection_energy": wave["reflection_energy"],
            "dissipation": wave["dissipation"],
            "dissipation_percent": wave["dissipation_percent"],
            "wave": wave,
            "step_results": [{"wave": wave}],
        }

        self.recording_analysis_dialog = FrequencyAnalysisDialog(parent=self)
        self.recording_analysis_dialog.set_single_frequency_result(item)
        self.recording_analysis_dialog.setWindowTitle("Analyse der Aufnahme")
        self.recording_analysis_dialog.show()
        self.recording_analysis_dialog.raise_()
        self.recording_analysis_dialog.activateWindow()

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
            ylabel="|FFT| [dBµV]",
            parent=self,
        )
        dialog.plot_widget.setXRange(-FFT_MAX_FREQ, FFT_MAX_FREQ, padding=0)

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
        self.signal_screen.auto_start_button.clicked.connect(self.run_automatic_measurement)
        self.signal_screen.sweep_button.clicked.connect(self.run_frequency_sweep)

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

            self.stack.setCurrentWidget(self.signal_screen)

            duration = self.signal_screen._get_measurement_duration()
            start_voltage = float(self.generator_screen.amp_edit.text())

            self.signal_screen.log(
                f"Frequenzschleife: Aufnahmezeit pro Frequenz = {duration:.3f} s",
                category="title",
            )

            frequencies = np.arange(
                SWEEP_START_FREQ,
                SWEEP_STOP_FREQ,
                SWEEP_STEP_FREQ,
            )

            # Beim Klick auf "Frequenzschleife" wird das Live-Fenster sofort
            # geöffnet. Danach ergänzt jeder abgeschlossene Frequenzschritt
            # alle vier Diagramme um die neuen Messdaten.
            self.signal_screen.prepare_live_frequency_dashboard()
            QApplication.processEvents()

            sweep_results = run_frequency_sweep_steps(
                generator=generator,
                frequencies=frequencies,
                voltage=start_voltage,
                duration=duration,
                measure_once=self.signal_screen.run_measurement,
                compute_wave=self.signal_screen.compute_forward_reflected_results,
                on_frequency_result=self.signal_screen.update_live_frequency_dashboard,
                should_cancel=lambda: self.signal_screen.sweep_cancel_requested,
            )

            for sweep_item in sweep_results:
                f0 = sweep_item["frequency"]

                self.signal_screen.log(
                    f"Frequenzschleife: f = {f0:.1f} Hz",
                    category="title",
                )

                for step_item in sweep_item["step_results"]:
                    # Keine erneute FFT-/Zeitplot-Aktualisierung nach dem Sweep.
                    # Die Live-Daten wurden bereits im Frequenz-Dashboard dargestellt.
                    self.signal_screen.log(
                        f"Schritt {step_item['step']}: "
                        f"f = {f0:.1f} Hz, "
                        f"U = {step_item['voltage']:.4f} V"
                    )
                    self.signal_screen.log(
                        f"|A(f)| = {step_item['measured_A_abs']:.6e} V"
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
            json_path = self._save_sweep_results_json(
                sweep_results=sweep_results,
                mode="frequency",
                duration=duration,
                start_voltage=start_voltage,
            )

            self.signal_screen.log(
                "Frequenzschleife abgeschlossen.",
                category="title",
            )
            self.signal_screen.log(
                f"Sweep-JSON gespeichert: {json_path}",
                category="Info",
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

    @staticmethod
    def _complex_to_json(value):
        value = complex(value)
        return {
            "real": float(value.real),
            "imag": float(value.imag),
            "abs": float(abs(value)),
            "phase_rad": float(np.angle(value)),
            "phase_deg": float(np.degrees(np.angle(value))),
        }

    @staticmethod
    def _swr_from_reflection_factor(reflection_factor):
        reflection_factor = float(reflection_factor)
        if reflection_factor >= 1.0:
            return None
        return float((1.0 + reflection_factor) / (1.0 - reflection_factor))

    def _build_sweep_frequency_json(self, item):
        frequency = float(item["frequency"])
        wave = item.get("wave")
        if wave is None and item.get("step_results"):
            wave = item["step_results"][-1].get("wave")
        if wave is None:
            raise ValueError(f"Keine Wellen-Daten für f = {frequency:.1f} Hz.")

        A_abs = float(wave["A_abs"])
        B_abs = float(wave["B_abs"])
        reflection_factor = float(wave.get("r_abs", item.get("B_over_A", 0.0)))
        reflection_energy = float(wave.get("reflection_energy", reflection_factor**2))
        dissipation = float(wave.get("dissipation", 1.0 - reflection_energy))
        wavelength = SPEED_OF_SOUND / frequency
        wave_number = 2.0 * np.pi / wavelength

        steps = []
        for step in item.get("step_results", []):
            step_wave = step.get("wave", {})
            steps.append({
                "step": int(step.get("step", len(steps) + 1)),
                "generator_voltage_v": float(step.get("voltage", item.get("voltage", 0.0))),
                "measured_A_abs_v": float(step.get("measured_A_abs", step_wave.get("A_abs", A_abs))),
                "relative_error": float(step.get("relative_error", 0.0)),
                "target_reached": bool(step.get("ok", item.get("target_reached", True))),
            })

        return {
            "frequency_hz": frequency,
            "generator_voltage_v": float(item.get("voltage", steps[-1]["generator_voltage_v"] if steps else 0.0)),
            "A": self._complex_to_json(wave["A"]),
            "B": self._complex_to_json(wave["B"]),
            "A_abs_v": A_abs,
            "A_abs_uv": A_abs * 1e6,
            "A_phase_rad": float(wave["A_phase"]),
            "A_phase_deg": float(np.degrees(float(wave["A_phase"]))),
            "B_abs_v": B_abs,
            "B_abs_uv": B_abs * 1e6,
            "B_phase_rad": float(wave["B_phase"]),
            "B_phase_deg": float(np.degrees(float(wave["B_phase"]))),
            "r_complex": self._complex_to_json(wave.get("r_complex", complex(wave["B"]) / (complex(wave["A"]) + 1e-30))),
            "reflection_factor_abs": reflection_factor,
            "reflection_factor_phase_rad": float(wave.get("r_phase", 0.0)),
            "reflection_factor_phase_deg": float(np.degrees(float(wave.get("r_phase", 0.0)))),
            "swr": self._swr_from_reflection_factor(reflection_factor),
            "reflection_energy_R": reflection_energy,
            "reflection_percent": reflection_energy * 100.0,
            "dissipation_D": dissipation,
            "dissipation_percent": dissipation * 100.0,
            "p_max_v": A_abs + B_abs,
            "p_max_uv": (A_abs + B_abs) * 1e6,
            "p_min_v": abs(A_abs - B_abs),
            "p_min_uv": abs(A_abs - B_abs) * 1e6,
            "wavelength_m": wavelength,
            "wavelength_mm": wavelength * 1000.0,
            "wave_number_rad_per_m": float(wave_number),
            "residual": float(wave.get("residual", item.get("residual", 0.0))),
            "target_reached": bool(item.get("target_reached", True)),
            "steps": steps,
        }

    def _save_sweep_results_json(self, sweep_results, mode, duration, start_voltage):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = Path(__file__).resolve().parents[2] / "sweep_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"{mode}_sweep_{timestamp}.json"

        payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "purpose": "Referenzdaten für späteren Vergleich",
            "settings": {
                "duration_s": float(duration),
                "start_voltage_v": float(start_voltage),
                "sweep_start_freq_hz": float(SWEEP_START_FREQ),
                "sweep_stop_freq_hz": float(SWEEP_STOP_FREQ),
                "sweep_step_freq_hz": float(SWEEP_STEP_FREQ),
                "target_amp_v": float(TARGET_AMP),
                "amp_tolerance": float(AMP_TOLERANCE),
                "min_generator_voltage_v": float(MIN_GENERATOR_VOLTAGE),
                "max_generator_voltage_v": float(MAX_GENERATOR_VOLTAGE),
                "max_auto_steps": int(MAX_AUTO_STEPS),
            },
            "constants": {
                "speed_of_sound_m_per_s": float(SPEED_OF_SOUND),
                "mic_positions_m": {
                    "x1": float(MIC_X1),
                    "x2": float(MIC_X2),
                    "x3": float(MIC_X3),
                },
                "calibration": {str(key): float(value) for key, value in CALIBRATION.items()},
                "num_channels": int(NUM_CHANNELS),
            },
            "frequencies": [
                self._build_sweep_frequency_json(item)
                for item in sweep_results
            ],
        }

        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        return path
            
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

            start_voltage = float(self.generator_screen.amp_edit.text())

            if start_voltage <= 0 or start_voltage > MAX_GENERATOR_VOLTAGE:
                raise ValueError(
                    f"Generatorspannung muss größer 0 und maximal {MAX_GENERATOR_VOLTAGE:.1f} V sein."
                )

            self.stack.setCurrentWidget(self.signal_screen)

            duration = self.signal_screen._get_measurement_duration()

            self.signal_screen.log(
                f"Automation: Aufnahmezeit pro Messschritt = {duration:.3f} s",
                category="title",
            )

            frequencies = np.arange(
                SWEEP_START_FREQ,
                SWEEP_STOP_FREQ,
                SWEEP_STEP_FREQ,
            )

            self.signal_screen.prepare_automation_dashboard()
            QApplication.processEvents()

            sweep_results = run_automatic_frequency_sweep_steps(
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
                on_frequency_result=self.signal_screen.update_automation_dashboard,
                should_cancel=lambda: self.signal_screen.sweep_cancel_requested,
            )

            for sweep_item in sweep_results:
                f0 = float(sweep_item["frequency"])

                self.signal_screen.log(
                    f"Automation bei f = {f0:.1f} Hz",
                    category="title",
                )

                for step_item in sweep_item["step_results"]:
                    self.signal_screen.log(
                        f"Schritt {step_item['step']}: "
                        f"U = {step_item['voltage']:.4f} V, "
                        f"|A| = {format_voltage(step_item['measured_A_abs'])}, "
                        f"Fehler = {step_item['relative_error']:.3f}"
                    )

                if sweep_item["target_reached"]:
                    self.signal_screen.log(
                        f"Ziel {format_voltage(TARGET_AMP)} erreicht.",
                        category="title",
                    )
                else:
                    self.signal_screen.log(
                        f"Ziel {format_voltage(TARGET_AMP)} nicht erreicht.",
                        category="title",
                    )

                QApplication.processEvents()

            self.signal_screen.sweep_results = sweep_results
            json_path = self._save_sweep_results_json(
                sweep_results=sweep_results,
                mode="automatic",
                duration=duration,
                start_voltage=start_voltage,
            )

            self.signal_screen.log(
                "Automatischer Frequenz-Sweep abgeschlossen.",
                category="title",
            )
            self.signal_screen.log(
                f"Sweep-JSON gespeichert: {json_path}",
                category="Info",
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
