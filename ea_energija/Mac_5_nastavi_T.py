"""MAC: ZAPIŠI T za kampanjo (ea_T.h) iz preizkusa verige.

T za način CAS je pri vsaki celici (funkcija, D) mediana trajanja zagonov FE te
celice v preizkusu verige, zaokrožena na celo sekundo. Skripta jo izračuna iz
prenos/<SEJA>/esp32.txt preizkusa verige, izpiše predlog in (ko nastavite
ZAPISI = True) zapiše ea_T.h.

Nato: ea_T.h shranite v git (git add, git commit), kopirajte ea_T.h na
računalnik z RIGOL-om in ponovno poženite Mac_2_pripravi.py (VRSTA = "kampanja").
Ukaz za Terminal:  python3 Mac_5_nastavi_T.py --seja 2026-11-17_veriga [--zapisi] [--prepisi]
"""
import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
SEJA = "2026-11-17_veriga"        # seja preizkusa verige
ZAPISI = False                    # True = zapiši ea_T.h (po pregledu predloga)
PREPISI = False                   # True = prepiši obstoječi ea_T.h

ap = argparse.ArgumentParser(description="T za kampanjo iz preizkusa verige")
ap.add_argument("--seja", default=SEJA)
ap.add_argument("--zapisi", action="store_true", default=ZAPISI)
ap.add_argument("--prepisi", action="store_true", default=PREPISI)
a = ap.parse_args()
sys.exit(naprava.nastavi_T(os.path.join("prenos", a.seja, "esp32.txt"), a.zapisi, a.prepisi))
