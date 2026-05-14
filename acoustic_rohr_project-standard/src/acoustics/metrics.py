import numpy as np

def mean_amplitude_three_mics(P1, P2, P3):
    # Berechnet die mittlere lineare Amplitude der drei Mikrofone.
    # Zuerst wird von jedem komplexen Mikrofonsignal der Betrag genommen,
    # also die Amplitude |P1|, |P2|, |P3|.
    # Danach wird der Mittelwert gebildet.
    return (np.abs(P1) + np.abs(P2) + np.abs(P3)) / 3.0


def voltage_level_db(U, U_ref=1.0):
    # Kleine Zahl, damit log10 nicht mit 0 aufgerufen wird
    eps = 1e-12

    # Berechnet den Spannungspegel in dB:
    # L = 20 * log10(|U| / U_ref)
    #
    # |U|     = Betrag des Signals
    # U_ref   = Referenzspannung, meist 1.0 V
    #
    # Wenn U = U_ref, dann ist der Pegel 0 dB.
    return 20.0 * np.log10((np.abs(U) + eps) / (U_ref + eps))


def relative_complex_error(measured, predicted):
    # Kleine Zahl, damit keine Division durch 0 entsteht
    eps = 1e-12

    # Berechnet den relativen Fehler zwischen gemessenem und
    # vorhergesagtem komplexem Signal.
    #
    # measured  = gemessener komplexer Druck
    # predicted = vom Modell berechneter Druck
    #
    # Formel:
    # Fehler = |measured - predicted| / |measured|
    #
    # Wenn der Fehler klein ist, passt das Modell gut zu den Messdaten.
    return np.abs(measured - predicted) / (np.abs(measured) + eps)