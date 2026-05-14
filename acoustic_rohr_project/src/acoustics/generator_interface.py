class SimulatedGenerator:
    def __init__(self):
        self.connected = False
        self.frequency_hz = 1000.0
        self.voltage_v = 0.2
        self.output_enabled = False
        self.function = "SIN"

    def connect(self):
        self.connected = True

    def _require_connection(self):
        if not self.connected:
            raise RuntimeError("Simulierter Generator ist nicht verbunden.")

    def identify(self):
        self._require_connection()
        return "SIMULATED_GENERATOR, Python, v1.1"

    def set_frequency(self, freq_hz: float):
        self._require_connection()
        self.frequency_hz = float(freq_hz)

    def set_amplitude(self, voltage_v: float):
        self._require_connection()
        self.voltage_v = float(voltage_v)

    def set_sine(self):
        self._require_connection()
        self.function = "SIN"

    def set_output(self, freq_hz: float, voltage_v: float):
        self.set_frequency(freq_hz)
        self.set_amplitude(voltage_v)

    def output_on(self):
        self._require_connection()
        self.output_enabled = True

    def output_off(self):
        self._require_connection()
        self.output_enabled = False

    def close(self):
        self.connected = False
        self.output_enabled = False