import pyvisa

rm = pyvisa.ResourceManager()

print("Gefundene VISA-Geräte:")
resources = rm.list_resources()
print(resources)

for res in resources:
    try:
        inst = rm.open_resource(res)
        inst.timeout = 3000
        print(f"\nTeste {res}")
        print(inst.query("*IDN?"))
        inst.close()
    except Exception as e:
        print(f"Fehler bei {res}: {e}")

rm.close()