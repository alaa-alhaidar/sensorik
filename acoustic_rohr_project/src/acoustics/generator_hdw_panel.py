import pyvisa


class Agilent33120A:
    def __init__(self, resource_name):
        self.resource_name = resource_name
        self.rm = None
        self.inst = None

    def connect(self):
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(self.resource_name)
        self.inst.timeout = 10000
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"
        self.inst.write("*CLS")

    def _require_connection(self):
        if self.inst is None:
            raise RuntimeError("Agilent 33120A ist nicht verbunden.")

    def identify(self):
        self._require_connection()
        return self.inst.query("*IDN?").strip()

    def set_sine(self):
        self._require_connection()
        # Beim 33120A sicherer als FUNC SIN
        self.inst.write("FUNC:SHAP SIN")

    def set_frequency(self, freq_hz):
        self._require_connection()
        self.inst.write(f"FREQ {float(freq_hz)}")

    def set_amplitude(self, voltage_vpp):
        self._require_connection()
        # Einheit ist Vpp
        self.inst.write(f"VOLT {float(voltage_vpp)}")

    def set_output(self, freq_hz, voltage_vpp):
        self._require_connection()
        # Sinus mit Frequenz, Amplitude Vpp und Offset 0 V
        self.inst.write(f"APPL:SIN {float(freq_hz)}, {float(voltage_vpp)}, 0")

    def output_on(self):
        self._require_connection()
        # Der 33120A hat keinen modernen OUTP ON/OFF wie viele neue Generatoren.
        # Deshalb hier nichts senden, um -113 Undefined header zu vermeiden.
        pass

    def output_off(self):
        self._require_connection()
        # Zum "Ausschalten" sehr kleine Amplitude setzen.
        self.inst.write("VOLT 0.05")

    def get_error(self):
        self._require_connection()
        return self.inst.query("SYST:ERR?").strip()

    def clear_error(self):
        self._require_connection()
        self.inst.write("*CLS")

    def close(self):
        if self.inst is not None:
            self.inst.close()
            self.inst = None
        if self.rm is not None:
            self.rm.close()
            self.rm = None