import pyvisa
import time

RESOURCE = "GPIB0::12::INSTR"

rm = pyvisa.ResourceManager()
print("VISA backend:", rm)

gen = rm.open_resource(RESOURCE)

gen.timeout = 10000
gen.write_termination = "\n"
gen.read_termination = "\n"

print("Verbunden mit:", RESOURCE)

try:
    gen.clear()
except Exception as e:
    print("Clear Warnung:", e)

time.sleep(0.5)

print("Sende *IDN?")
gen.write("*IDN?")

try:
    idn = gen.read()
    print("Antwort:", idn)
except Exception as e:
    print("IDN Fehler:", e)

gen.close()
rm.close()