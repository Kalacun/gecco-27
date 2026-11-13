
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import zajem  # noqa: E402

# ---- nastavitve (po potrebi spremenite) ----
MAPA = "meritve_test_veriga"            # kam se shranijo podatki
PROGRAM = "test_veriga/test_veriga.ino"  # MORA biti isti program, kot je na ESP32
RIGOL = ""                              # prazno = samodejno; ali npr. "USB0::0x1AB1::0x0E11::DP8E214600333::INSTR"

sys.argv = ["zajem.py", "poskus", "--ino", PROGRAM, "--mapa", MAPA]
if RIGOL:
    sys.argv += ["--rigol", RIGOL]
zajem.main()
