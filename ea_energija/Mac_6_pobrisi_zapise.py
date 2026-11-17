"""MAC: POBRIŠI ZAPISE na ESP32, da lahko isti program znova požene sejo.

Potrebno samo, ko ponovite sejo z ISTIM prevodom (isto oznako): nalaganje
programa z drugo oznako prevoda zapise pobriše samo. Pred brisanjem MORAJO biti
zapisi prebrani (Mac_4_preberi.py), preneseni na računalnik z RIGOL-om in
preverjeni. Brisanja ni mogoče razveljaviti.

Priklopite USB (stikalo RIGOL-a odprto) in nastavite POTRJUJEM = True.
Po brisanju se nova seja začne ob naslednjem vklopu z RIGOL-om.
Ukaz za Terminal:  python3 Mac_6_pobrisi_zapise.py --potrjujem
"""
import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
PORT = ""                  # prazno = samodejno
POTRJUJEM = False          # True = potrjujem, da so zapisi prebrani, preneseni in preverjeni

ap = argparse.ArgumentParser(description="Pobriši zapise na ESP32 (nepovratno)")
ap.add_argument("--port", default=PORT)
ap.add_argument("--potrjujem", action="store_true", default=POTRJUJEM)
a = ap.parse_args()
sys.exit(naprava.pobrisi(a.port, a.potrjujem))
