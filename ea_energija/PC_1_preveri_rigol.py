
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import pyvisa  # noqa: E402

for zaledje in ("", "@py"):          # najprej NI-VISA / UltraSigma, nato pyvisa-py
    try:
        rm = pyvisa.ResourceManager(zaledje) if zaledje else pyvisa.ResourceManager()
        naprave = rm.list_resources()
    except Exception as e:  # noqa: BLE001
        print(f"VISA zaledje '{zaledje or 'sistemsko'}': {e}")
        continue
    print(f"VISA zaledje '{zaledje or 'sistemsko'}': {naprave}")
    for n in naprave:
        try:
            inst = rm.open_resource(n)
            inst.timeout = 3000
            print(f"  {n}\n    *IDN?  -> {inst.query('*IDN?').strip()}")
            print(f"    APPL?  -> {inst.query(':APPL? CH1').strip()}")
            print(f"    MEAS   -> {inst.query(':MEAS:ALL? CH1').strip()}  (V, A, W)")
            inst.close()
        except Exception as e:  # noqa: BLE001
            print(f"  {n}: {e}")
    if naprave:
        break
else:
    print("\nNobene naprave. Preverite USB kabel RIGOL-a in namestitev NI-VISA.")
    sys.exit(1)
