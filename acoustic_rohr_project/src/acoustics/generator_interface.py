import pyvisa

rm = pyvisa.ResourceManager()
print(rm.list_resources())

class GeneratorInterface:
    def connect(self):
        raise NotImplementedError

    def identify(self):
        raise NotImplementedError

    def set_frequency(self, freq_hz: float):
        raise NotImplementedError

    def set_amplitude(self, voltage_v: float):
        raise NotImplementedError

    def output_on(self):
        raise NotImplementedError

    def output_off(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError


class TektronixAFG320(GeneratorInterface):
    def __init__(self, resource_name: str, timeout_ms: int = 5000):
        self.resource_name = resource_name
        self.timeout_ms = timeout_ms
        self.rm = None
        self.inst = None

    def connect(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.resource_name)
        self.inst.timeout = self.timeout_ms

    def _require_connection(self):
        if self.inst is None:
            raise RuntimeError("Generator ist nicht verbunden. Erst connect() aufrufen.")

    def identify(self):
        self._require_connection()
        return self.inst.query("*IDN?").strip()

    def set_frequency(self, freq_hz: float):
        self._require_connection()
        self.inst.write(f"SOURce:FREQuency {freq_hz}")

    def set_amplitude(self, voltage_v: float):
        self._require_connection()
        self.inst.write(f"SOURce:VOLTage:AMPLitude {voltage_v}")

    def set_sine(self):
        self._require_connection()
        self.inst.write("SOURce:FUNCtion SINusoid")

    def set_output(self, freq_hz: float, voltage_v: float):
        self.set_frequency(freq_hz)
        self.set_amplitude(voltage_v)

    def output_on(self):
        self._require_connection()
        self.inst.write("OUTPut ON")

    def output_off(self):
        self._require_connection()
        self.inst.write("OUTPut OFF")

    def close(self):
        if self.inst is not None:
            self.inst.close()
            self.inst = None

        if self.rm is not None:
            self.rm.close()
            self.rm = None