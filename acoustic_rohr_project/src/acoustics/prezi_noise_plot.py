# prezi_noise_plot.py

import numpy as np
import matplotlib.pyplot as plt
from types import SimpleNamespace

from estimation import (
    estimate_forward_reflected_two_mics_exact,
    estimate_forward_reflected_three_mics_ls,
)

# -----------------------------
# Parameter wie in deinem Code
# -----------------------------
cfg = SimpleNamespace(
    c=344.0,
    x1=-0.050,
    x2=-0.085,
    x3=-0.145,
)

f0 = 1000.0

# -----------------------------
# Simuliertes ideales Signal
# P(x) = A e^(-jkx) + B e^(jkx)
# -----------------------------
A_true = 1.0 * np.exp(1j * 0.2)
B_true = 0.6 * np.exp(-1j * 0.7)

true_ratio = abs(B_true) / abs(A_true)

k = 2.0 * np.pi * f0 / cfg.c
positions = [cfg.x1, cfg.x2, cfg.x3]

P_clean = np.array([
    A_true * np.exp(-1j * k * x) + B_true * np.exp(1j * k * x)
    for x in positions
], dtype=complex)

# -----------------------------
# Noise 0 bis 0.5
# -----------------------------
noise_levels = np.linspace(0.0, 0.6, 60)
n_trials = 400

error_exact = []
error_ls = []

rng = np.random.default_rng(42)

for noise in noise_levels:
    errors_exact_for_noise = []
    errors_ls_for_noise = []

    for _ in range(n_trials):
        noise_vec = noise * (
            rng.standard_normal(3) + 1j * rng.standard_normal(3)
        )

        P_noisy = P_clean + noise_vec

        # Methode 1: lineare Gleichung mit 2 Mikrofonen
        A_exact, B_exact = estimate_forward_reflected_two_mics_exact(
            P_noisy[0],
            P_noisy[1],
            f0,
            cfg,
        )

        # Methode 2: Least-Squares-Methode mit 3 Mikrofonen
        A_ls, B_ls, residual = estimate_forward_reflected_three_mics_ls(
            np.array([P_noisy[0]], dtype=complex),
            np.array([P_noisy[1]], dtype=complex),
            np.array([P_noisy[2]], dtype=complex),
            np.array([f0], dtype=float),
            cfg,
        )

        A_ls = A_ls[0]
        B_ls = B_ls[0]

        ratio_exact = abs(B_exact) / (abs(A_exact) + 1e-12)
        ratio_ls = abs(B_ls) / (abs(A_ls) + 1e-12)

        errors_exact_for_noise.append(abs(ratio_exact - true_ratio))
        errors_ls_for_noise.append(abs(ratio_ls - true_ratio))

    error_exact.append(np.mean(errors_exact_for_noise))
    error_ls.append(np.mean(errors_ls_for_noise))

# -----------------------------
# Plot für Prezi
# -----------------------------
plt.figure(figsize=(8, 8))

plt.plot(
    noise_levels,
    error_exact,
    linewidth=3,
    label="Lineare Gleichung (2 Mikrofone)",
)

plt.plot(
    noise_levels,
    error_ls,
    linewidth=3,
    label="Least Squares (3 Mikrofone)",
)

plt.xlabel("Noise-Level")
plt.ylabel("Mittlerer Fehler von |B/A|")
plt.title("Vergleich der Wellenzerlegung bei f = 1000 Hz")
plt.grid(True, alpha=0.35)
plt.legend()
plt.tight_layout()
plt.show()