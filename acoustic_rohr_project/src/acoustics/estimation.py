import numpy as np

def wave_number(freq_hz: np.ndarray, c: float) -> np.ndarray:
    # Berechnet die Wellenzahl aus der Frequenz f und
    # Phasegeschwindigkeit pro meter pro Sekunde c. Die Wellenzahl k ist definiert als:
    # k = 2*pi*f / c
    return 2.0 * np.pi * freq_hz / c

def estimate_forward_reflected_three_mics_ls(P1, P2, P3, freqs_hz, cfg):
    # Berechnet die Wellenzahl k(f) für alle Frequenzen
    k = wave_number(freqs_hz, cfg.c)
    # speichert die geschätzten A- und B-Werte für alle Frequenzen
    A_est = np.zeros_like(P1, dtype=complex)
    B_est = np.zeros_like(P1, dtype=complex)
    residual_norm = np.zeros(len(freqs_hz))

    # Löse für jede Frequenz das lineare Gleichungssystem A @ [A; B] = b mit den Messungen P1, P2, P3
    for i in range(len(freqs_hz)):
        M = np.array([
            [np.exp(-1j * k[i] * cfg.x1), np.exp(1j * k[i] * cfg.x1)],
            [np.exp(-1j * k[i] * cfg.x2), np.exp(1j * k[i] * cfg.x2)],
            [np.exp(-1j * k[i] * cfg.x3), np.exp(1j * k[i] * cfg.x3)]
        ], dtype=complex)

        b = np.array([P1[i], P2[i], P3[i]], dtype=complex)
        solution, residuals, _, _ = np.linalg.lstsq(M, b, rcond=None)

        # Lösung speichern:
        # solution[0] = geschätztes A 
        # solution[1] = geschätztes B
        A_est[i], B_est[i] = solution

        if len(residuals) > 0:
            residual_norm[i] = np.sqrt(residuals[0])
        else:
            residual_norm[i] = np.linalg.norm(M @ solution - b)

    # Rückgabe:
    # A_est        = geschätzte hinlaufende Welle
    # B_est        = geschätzte reflektierte Welle
    # residual_norm = Güte der Anpassung
    return A_est, B_est, residual_norm

