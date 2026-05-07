import numpy as np

def correction_factor(target_amp, measured_amp, max_gain):
    # Kleine Zahl, damit es keine Division durch 0 gibt
    eps = 1e-12

    # Korrekturfaktor:
    # Zielamplitude / gemessene Amplitude
    # Wenn gemessene Amplitude klein ist -> K wird größer
    # Wenn gemessene Amplitude groß ist -> K wird kleiner
    K = target_amp / (measured_amp + eps)

    # Begrenzung des Korrekturfaktors:
    # nicht kleiner als 0, nicht größer als max_gain
    return np.clip(K, 0.0, max_gain)


def apply_compensation(P1, P2, P3, K):
    # Wendet die frequenzabhängige Kompensation auf alle 3 Mikrofone an.
    # Jedes Signal wird mit demselben Korrekturfaktor K skaliert.
    return K * P1, K * P2, K * P3


def generator_voltage_from_gain(base_voltage, K):
    # Berechnet die neue Generator-Spannung aus:
    # Grundspannung * Korrekturfaktor
    return base_voltage * K