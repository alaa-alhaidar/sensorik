import pyvisa


class TektronixAFG320:
    def __init__(self, resource_name):
        self.resource_name = resource_name
        self.rm = None
        self.inst = None

    def connect(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.resource_name)
        self.inst.timeout = 5000

    def _require_connection(self):
        if self.inst is None:
            raise RuntimeError("Generator ist nicht verbunden.")

    def identify(self):
        self._require_connection()
        return self.inst.query("*IDN?").strip()

    def set_frequency(self, freq_hz):
        self._require_connection()
        self.inst.write(f"FREQ {float(freq_hz)}")

    def set_amplitude(self, voltage_v):
        self._require_connection()
        self.inst.write(f"VOLT {float(voltage_v)}")

    def set_sine(self):
        self._require_connection()
        self.inst.write("FUNC SIN")

    def set_output(self, freq_hz, voltage_v):
        self.set_frequency(freq_hz)
        self.set_amplitude(voltage_v)

    def output_on(self):
        self._require_connection()
        self.inst.write("OUTP ON")

    def output_off(self):
        self._require_connection()
        self.inst.write("OUTP OFF")

    def close(self):
        if self.inst is not None:
            self.inst.close()
            self.inst = None
        if self.rm is not None:
            self.rm.close()
            self.rm = None