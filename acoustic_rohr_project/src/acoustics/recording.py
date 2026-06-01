"""
recording.py

Nur Aufnahme / Signalbeschaffung.

Sie entscheidet nur:
Simulation -> simuliertes Signal erzeugen
Audio-Interface -> Focusrite aufnehmen
"""

import numpy as np


def acquire_recording(duration, using_simulation, generate_simulated_signal, create_focusrite):
    """
    Holt ein Signal entweder aus der Simulation oder vom Audio-Interface.

    Parameter
    ---------
    duration : float
        Aufnahmezeit in Sekunden.
    using_simulation : bool
        True  -> Simulation benutzen
        False -> Audio-Interface benutzen
    generate_simulated_signal : callable
        Funktion aus der GUI/Klasse, die ein simuliertes Signal erzeugt.
        Beispiel: self._generate_simulated_signal
    create_focusrite : callable
        Funktion aus der GUI/Klasse, die ein FocusriteInterface erzeugt.
        Beispiel: self._create_focusrite

    Rückgabe
    --------
    signal : np.ndarray
        Aufgenommenes Signal mit Form (samples, channels).
    focusrite : FocusriteInterface | None
        Nur bei echter Audio-Aufnahme gesetzt. Bei Simulation None.
    source_name : str
        "Simulation" oder "Audio-Interface" für Debug/Log.
    """

    duration = float(duration)
    if duration <= 0:
        raise ValueError(f"Aufnahmedauer muss größer als 0 sein. duration={duration}")

    if using_simulation:
        signal = generate_simulated_signal(duration)
        focusrite = None
        source_name = "Simulation"
    else:
        focusrite = create_focusrite()
        signal = focusrite.record_input(duration=duration)
        source_name = "Audio-Interface"

    signal = np.asarray(signal, dtype=np.float32)

    if signal.ndim == 1:
        signal = signal[:, np.newaxis]

    return signal, focusrite, source_name
