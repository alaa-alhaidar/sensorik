"""
Reine Signalverarbeitung für das Akustik-Messsystem.

Diese Datei enthält keine GUI-Abhängigkeiten:
- kein PySide6
- kein QMessageBox
- kein PlotWidget
- kein Import aus gui.py

Die GUI ruft diese Funktionen auf und zeigt/loggt danach die Ergebnisse.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np

from estimation import estimate_forward_reflected_three_mics_ls

import numpy as np


def record_signal(
    duration,
    using_simulation,
    generate_simulated_signal,
    create_focusrite,
):
    if using_simulation:
        raw_signal = generate_simulated_signal(duration)
        print(
            f"Simulierte Signale: signal.shape={raw_signal.shape}, "
            f"signal.dtype={raw_signal.dtype}"
        )
        return np.asarray(raw_signal, dtype=np.float32), None

    focusrite = create_focusrite()
    raw_signal = focusrite.record_input(duration=duration)
    print(
        f"Aufnahme von Focusrite: signal.shape={raw_signal.shape}, "
        f"signal.dtype={raw_signal.dtype}"
    )
   
    return np.asarray(raw_signal, dtype=np.float32), focusrite


def prepare_recording_signal(
    signal: np.ndarray,
    num_channels: int,
    calibration: dict[int, float] | None = None,
) -> np.ndarray:
    """Konvertiert Aufnahme zu (samples, channels), prüft sie und wendet Kalibrierung an."""
    signal = np.asarray(signal, dtype=np.float32)

    if signal.size == 0:
        raise ValueError(
            "Leeres Signal: Die Aufnahme hat 0 Samples geliefert. "
            "Prüfe Scarlett-Eingang, macOS-Mikrofonberechtigung und Sample-Rate."
        )

    if signal.ndim == 1:
        signal = signal[:, np.newaxis]

    if signal.shape[0] < 2:
        raise ValueError(f"Signal ist zu kurz. Samples={signal.shape[0]}")

    if signal.shape[1] < num_channels:
        raise ValueError(
            f"Für die Auswertung werden {num_channels} Eingangskanäle benötigt. "
            f"Das Gerät liefert nur {signal.shape[1]}."
        )

    signal = signal[:, :num_channels].copy()

    if calibration is not None:
        for ch in range(num_channels):
            signal[:, ch] *= float(calibration.get(ch + 1, 1.0))

    return signal


def debug_signal_print(signal: np.ndarray, prefix: str = "Aufgenommenes Signal") -> None:
    """Kompakte Debug-Ausgabe für die Konsole."""
    print(f"{prefix}: signal.shape={signal.shape}, signal.dtype={signal.dtype}")
    print(
        f"Signal min={signal.min():.6e}, max={signal.max():.6e}, "
        f"mean={signal.mean():.6e}, std={signal.std():.6e}"
    )

    for ch in range(signal.shape[1]):
        print(f"Reelle Werte Mikrofon {ch + 1}: {signal[:5, ch]}")

# measure_at_frequency_by_f0 nimmt ein Zeit-Signal von einem Mikrofon und berechnet nur den Anteil bei einer bestimmten Frequenz f0 
def measure_at_frequency_by_f0(
    signal_1d: np.ndarray,
    f0: float,
    sample_rate: float,
) -> tuple[complex, float, float, float]:
    """Berechnet komplexe Amplitude P, Betrag, Phase und RMS bei f0."""
    x = np.asarray(signal_1d, dtype=np.float64).flatten()

    if x.size == 0:
        raise ValueError("Leeres Signal.")
    if f0 <= 0:
        raise ValueError("f0 muss größer als 0 sein.")
    if sample_rate <= 0:
        raise ValueError("sample_rate muss größer als 0 sein.")

    n = x.size
    t = np.arange(n, dtype=np.float64) / float(sample_rate)
    ref = np.exp(-1j * 2.0 * np.pi * float(f0) * t)

    # Komplexe Projektion auf die Referenzfrequenz f0.
    # Faktor 2/n liefert die lineare Sinus-Amplitude.
    P = (2.0 / n) * np.sum(x * ref)

    amplitude = float(np.abs(P))
    phase = float(np.angle(P))
    rms = float(np.sqrt(np.mean(x**2))) # effektiver Wert des Signals

    return P, amplitude, phase, rms


def measure_three_mics_at_frequency_by_f0(
    signal: np.ndarray,
    f0: float,
    sample_rate: float,
    num_channels: int = 3,
) -> dict[str, Any]:
    """Berechnet P, Betrag, Phase und RMS für drei Mikrofone."""
    signal = prepare_recording_signal(signal, num_channels=num_channels)

    result: dict[str, Any] = {}
    for i in range(1, num_channels + 1):
        P, amp, phase, rms = measure_at_frequency_by_f0(
            signal[:, i - 1],
            f0=f0,
            sample_rate=sample_rate,
        )
        result[f"P{i}"] = P
        result[f"amp{i}"] = amp
        result[f"phase{i}"] = phase
        result[f"rms{i}"] = rms

    return result


def compute_fft_from_signal(
    signal: np.ndarray,
    sample_rate: float,
    f0: float,
    num_channels: int = 3,
) -> dict[str, Any]:
    """Berechnet FFT-Beträge für alle Mikrofone mit Hanning-Fenster."""
    signal = prepare_recording_signal(signal, num_channels=num_channels)

    n = signal.shape[0]
    if n < 2:
        raise ValueError("Signal ist zu kurz für FFT.")
    if sample_rate <= 0:
        raise ValueError("sample_rate muss größer als 0 sein.")

    freqs = np.fft.rfftfreq(n, d=1.0 / float(sample_rate))
    window = np.hanning(n)
    window_norm = float(np.sum(window))
    if abs(window_norm) < 1e-30:
        window_norm = float(n)

    f0_index = int(np.argmin(np.abs(freqs - float(f0))))
    fft_buffers: list[np.ndarray] = []
    log_entries: list[tuple[str, str]] = [("FFT-Auswertung mit Hanning-Fenster", "title")]

    for ch in range(num_channels):
        x = signal[:, ch]
        spectrum = np.fft.rfft(x * window)
        amp = 2.0 * np.abs(spectrum) / window_norm
        fft_buffers.append(amp.astype(np.float32))
        log_entries.append(
            (
                f"Mikrofon {ch + 1},FFT-Amplitude bei "
                f"{freqs[f0_index]:.1f} Hz = {amp[f0_index]:.6e}",
                "Info",
            )
        )

    return {
        "freqs": freqs.astype(np.float32),
        "fft_buffers": fft_buffers,
        "f0_index": f0_index,
        "log_entries": log_entries,
    }


def build_wave_config(c: float, x1: float, x2: float, x3: float) -> SimpleNamespace:
    """Erzeugt die Konfiguration für die Wellenzerlegung."""
    positions = [x1, x2, x3]
    if c <= 0:
        raise ValueError("SPEED_OF_SOUND muss größer als 0 sein.")
    if len(set(positions)) != 3:
        raise ValueError("MIC_X1, MIC_X2 und MIC_X3 müssen unterschiedlich sein.")
    return SimpleNamespace(c=c, x1=x1, x2=x2, x3=x3)

# Berechnet hinlaufende Welle A, rücklaufende Welle B, Reflexionsfaktor r = B/A, Reflexionsgrad R = |r|², Dissipation D = 1 - R
def compute_forward_reflected_results(
    m: dict[str, Any],
    f0: float,
    cfg: SimpleNamespace,
) -> dict[str, Any]:
    """Berechnet A, B, Reflexionsgrad und Dissipation aus P1, P2, P3."""
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
    r_complex = B0 / (A0 + 1e-12)
    r_abs = float(np.abs(r_complex))
    r_phase = float(np.angle(r_complex))

    R = r_abs**2
    D = 1.0 - R

    return {
        "A": A0,
        "A_abs": float(np.abs(A0)),
        "A_phase": float(np.angle(A0)),
        "B": B0,
        "B_abs": float(np.abs(B0)),
        "B_phase": float(np.angle(B0)),
        "r_complex": r_complex,
        "r_abs": r_abs,
        "r_phase": r_phase,
        "B_over_A": r_abs,
        "reflection_energy": R,
        "dissipation": D,
        "dissipation_percent": D * 100.0,
        "residual": float(residual[0]),
    }


def build_mic_result_dict(m: dict[str, Any], f0: float, num_mics: int = 3) -> dict[str, Any]:
    """Bereitet Mikrofonwerte für die Ergebnisanzeige vor."""
    phase_ref = m["phase1"]
    result: dict[str, Any] = {}

    for i in range(1, num_mics + 1):
        phase_shift = m[f"phase{i}"] - phase_ref
        result[f"P{i}"] = m[f"P{i}"]
        result[f"amp{i}"] = m[f"amp{i}"]
        result[f"phase{i}"] = m[f"phase{i}"]
        result[f"rms{i}"] = m[f"rms{i}"]
        result[f"phase_shift{i}"] = phase_shift
        result[f"phase_shift_deg{i}"] = float(np.degrees(phase_shift))
        result[f"time_shift_ms{i}"] = float(phase_shift / (2.0 * np.pi * f0) * 1000.0)

    return result


def format_measurement_logs(
    duration: float,
    num_samples: int,
    sample_rate: float,
    f0: float,
) -> list[tuple[str, str]]:
    """Log-Texte für Messeinstellungen."""
    freq_resolution = sample_rate / num_samples
    return [
        ("Messeinstellungen", "title"),
        (f"Aufnahmdauer: {duration:.0f} s", "Info"),
        (f"Samples pro Mikrofon: {num_samples}", "Info"),
        (f"Sample-Rate: {sample_rate:.1f} Hz", "Info"),
        (f"Messfrequenz: {f0:.2f} Hz", "Info"),
        (f"Frequenzauflösung Δf = fs / N = 1 / T = {freq_resolution:.3f} Hz", "Info"),
    ]


def format_microphone_logs(m: dict[str, Any], num_channels: int = 3) -> list[tuple[str, str]]:
    """Log-Texte für Mikrofon-Amplituden und Phasen."""
    entries: list[tuple[str, str]] = [("Messergebnisse", "title")]
    amp_ref = m["amp1"]
    phase_ref = m["phase1"]

    for i in range(1, num_channels + 1):
        amp = m[f"amp{i}"]
        phase = m[f"phase{i}"]

        amp_diff_abs = abs(amp - amp_ref)
        amp_diff_percent_abs = abs((amp / (amp_ref + 1e-12) - 1.0) * 100.0)

        phase_shift = phase - phase_ref
        phase_shift_abs = abs(phase_shift)
        phase_shift_deg_abs = abs(np.degrees(phase_shift))
        phase_shift_percent = phase_shift_abs / (2.0 * np.pi) * 100.0

        entries.extend(
            [
                (f"Mikrofon {i}", "title"),
                (f"Betrag |P{i}| = {amp:.6e}", "Info"),
                (f"Betrag-Abweichung zu Mikrofon 1 = {amp_diff_abs:.6e}", "Info"),
                (f"Betrag-Abweichung in Prozent = {amp_diff_percent_abs:.3f} %", "Info"),
                (f"Phase(P{i}) = {phase:.6f} rad = {np.degrees(phase):.2f}°", "Info"),
                (
                    f"Phase-Abweichung zu Mikrofon 1 = {phase_shift_abs:.6f} rad "
                    f"= {phase_shift_deg_abs:.3f}°",
                    "Info",
                ),
                (
                    f"Phase-Abweichung in Prozent einer Periode = {phase_shift_percent:.3f} %",
                    "Info",
                ),
            ]
        )

    return entries


def format_wave_logs(wave: dict[str, Any]) -> list[tuple[str, str]]:
    """Log-Texte für A/B-Wellenzerlegung und Reflexion."""
    A0 = wave["A"]
    B0 = wave["B"]
    r = wave["r_complex"]

    return [
        ("Wellenzerlegung: hinlaufende und rücklaufende Welle", "title"),
        (f"Hinlaufende Welle A = {A0.real:.6e} + j({A0.imag:.6e})", "Info"),
        (f"|A| = {wave['A_abs']:.6e}", "Info"),
        (f"Phase(A) = {wave['A_phase']:.6f} rad = {np.degrees(wave['A_phase']):.2f}°", "Info"),
        (f"Rücklaufende Welle B = {B0.real:.6e} + j({B0.imag:.6e})", "Info"),
        (f"|B| = {wave['B_abs']:.6e}", "Info"),
        (f"Phase(B) = {wave['B_phase']:.6f} rad = {np.degrees(wave['B_phase']):.2f}°", "Info"),
        (f"Komplexer Reflexionsfaktor r = B/A = {r.real:.6e} + j({r.imag:.6e})", "Info"),
        (f"|r| = |B/A| = {wave['r_abs']:.6f}", "Info"),
        (f"Phase(r) = {wave['r_phase']:.6f} rad = {np.degrees(wave['r_phase']):.2f}°", "Info"),
        (f"Reflexionsgrad R = |r|² = {wave['reflection_energy']:.6f}", "Info"),
        (f"Dissipation D = 1 - R = {wave['dissipation']:.6f}", "Info"),
        (f"Dissipation = {wave['dissipation_percent']:.3f} %", "Info"),
        (f"Residuum Least Squares = {wave['residual']:.6e}", "Info"),
    ]


def process_recorded_signal(
    raw_signal: np.ndarray,
    duration: float,
    f0: float,
    sample_rate: float,
    num_channels: int,
    calibration: dict[int, float],
    wave_cfg: SimpleNamespace,
) -> dict[str, Any]:
    """Komplette Auswertung einer Aufnahme, aber ohne GUI und ohne Aufnahme-Hardware."""
    signal = prepare_recording_signal(raw_signal, num_channels, calibration)
    debug_signal_print(signal)

    m = measure_three_mics_at_frequency_by_f0(signal, f0, sample_rate, num_channels)
    wave = compute_forward_reflected_results(m, f0, wave_cfg)
    fft = compute_fft_from_signal(signal, sample_rate, f0, num_channels)
    mic_results = build_mic_result_dict(m, f0, num_channels)

    log_entries: list[tuple[str, str]] = []
    log_entries += format_measurement_logs(duration, signal.shape[0], sample_rate, f0)
    log_entries += format_microphone_logs(m, num_channels)
    log_entries += format_wave_logs(wave)
    log_entries += fft["log_entries"]

    return {
        "signal": signal,
        "m": m,
        "wave": wave,
        "fft": fft,
        "mic_results": mic_results,
        "log_entries": log_entries,
    }
