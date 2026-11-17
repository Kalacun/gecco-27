"""W7 (PyCharm, Run): T ZA KAMPANJO iz preizkusa verige (zapiše ea_T.h).

Najprej poženite z ZAPISI = False in preglejte predlog; nato ZAPISI = True.
Potem v PyCharmu Git -> Commit (ea_T.h in morebitne spremembe nastavitev),
v seja_nastavitve.py VRSTA = "kampanja" in W2.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402
import seja  # noqa: E402

# ---- nastavitve ----
SEJA = ""          # prazno = aktivna seja (mora biti preizkus verige); sicer npr. "2026-11-18_veriga"
ZAPISI = False     # True = zapiši ea_T.h (po pregledu predloga)
PREPISI = False    # True = prepiši obstoječi ea_T.h

try:
    ime = seja.izbrana(SEJA)
except seja.NapakaSeje as e:
    sys.exit(str(e))
sys.exit(naprava.nastavi_T(os.path.join(seja.mapa_seje(ime), "esp32.txt"), ZAPISI, PREPISI))
