"""W8 (PyCharm, Run): POBRIŠI ZAPISE na ESP32 (nepovratno), da isti program znova požene sejo.

Samo ko so zapisi prebrani (W5) in analiza pregledana (W6). Nalaganje programa z
drugo oznako (W2 z drugo VRSTA ali spremenjeno kodo) zapise pobriše samo.
Pred zagonom: stikalo RIGOL-a ODPRTO, USB kabel ESP32 priklopljen BREZ BOOT,
POTRJUJEM = True. Nato za novo sejo: W2 (ali W4, če ste ponovno pognali W2).
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402
import seja  # noqa: E402

# ---- nastavitve ----
POTRJUJEM = False   # True = zapisi so prebrani, analizirani in shranjeni

sys.exit(naprava.pobrisi(seja.nastavitve().PORT_ESP32, POTRJUJEM))
