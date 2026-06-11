import pyvisa
import time

RESOURCE = "GPIB0::12::INSTR"

rm = pyvisa.ResourceManager()
gen = rm.open_resource(RESOURCE)

gen.timeout = 10000
gen.write_termination = "\n"
gen.read_termination = "\n"

gen.write("*CLS")

print(gen.query("*IDN?"))

gen.write("APPL:SIN 1000, 0.05, 0")

print("Sinus läuft: 1000 Hz, 50 mVpp")
time.sleep(10)

gen.write("VOLT 0.01")
print("Amplitude klein gesetzt")

print("Fehler:", gen.query("SYST:ERR?").strip())

gen.close()
rm.close()