"""
Simulierter Funktionsgenerator für Tests zuhause.

Diese Klasse hat dieselbe einfache Schnittstelle wie Agilent33120A,
aber sendet keine VISA-/GPIB-Befehle an echte Hardware.

Verwendung in gui.py:
    from simulated_generator import SimulatedGenerator

Dann:
    USE_SIMULATED_GENERATOR = True   # zuhause
    USE_SIMULATED_GENERATOR = False  # Labor mit Agilent
"""


class SimulatedGenerator:
    def __init__(self, start_frequency_hz=1000.0, start_voltage_v=0.2):
        self.frequency_hz = float(start_frequency_hz)
        self.voltage_v = float(start_voltage_v)
        self.output_enabled = False
        self.connected = False

    def connect(self):
        self.connected = True
        self.output_enabled = True

    def _require_connection(self):
        if not self.connected:
            raise RuntimeError("Simulierter Generator ist nicht verbunden.")

    def identify(self):
        self._require_connection()
        return "Simulierter Generator"

    def set_sine(self):
        self._require_connection()
        # In der Simulation ist immer Sinus angenommen.
        pass

    def set_frequency(self, freq_hz):
        self._require_connection()
        self.frequency_hz = float(freq_hz)

    def set_amplitude(self, voltage_v):
        self._require_connection()
        self.voltage_v = float(voltage_v)

    def set_output(self, freq_hz, voltage_v):
        self._require_connection()
        self.frequency_hz = float(freq_hz)
        self.voltage_v = float(voltage_v)
        self.output_enabled = True

    def output_on(self):
        self._require_connection()
        self.output_enabled = True

    def output_off(self):
        self._require_connection()
        self.output_enabled = False

    def get_error(self):
        self._require_connection()
        return "0,No error"

    def clear_error(self):
        self._require_connection()
        pass

    def close(self):
        self.output_enabled = False
        self.connected = False

