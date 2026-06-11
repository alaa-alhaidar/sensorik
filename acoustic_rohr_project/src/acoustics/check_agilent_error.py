import pyvisa

RESOURCE = "GPIB0::12::INSTR"

rm = pyvisa.ResourceManager()
gen = rm.open_resource(RESOURCE)
gen.timeout = 10000
gen.write_termination = "\n"
gen.read_termination = "\n"

print(gen.query("*IDN?"))

print("Fehlerliste:")
for _ in range(5):
    try:
        print(gen.query("SYST:ERR?").strip())
    except Exception as e:
        print("Kann Fehler nicht lesen:", e)
        break

gen.write("*CLS")
print("Fehler gelöscht mit *CLS")

gen.close()
rm.close()