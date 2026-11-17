"""MAC: PREVERI, KAJ JE NALOŽENO na ESP32 (po Upload v Arduino IDE).

Prebere program iz flasha ESP32 (ne da bi ga zagnal) in preveri, da vsebuje
oznako prevoda iz ea_prevod.h (Mac_2_pripravi.py) in pravilne nastavitve
plošče. ESP32 po branju OSTANE v nalagalniku: odklopite USB. Seja se začne
šele ob vklopu z RIGOL-om.

Pred zagonom: po Upload ODKLOPITE USB, DRŽITE BOOT, priklopite USB, BOOT držite
še 2 s in spustite. Skripta ESP32 ne ponastavi, zato mora biti v nalagalniku.

NE pritiskajte tipke EN in ne ponastavljajte ESP32 po nalaganju: ob naslednjem
zagonu bi se seja začela na USB napajanju.
Ukaz za Terminal:  python3 Mac_3_preveri_nalaganje.py [--port PORT]
"""
import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
PORT = ""      # prazno = samodejno

ap = argparse.ArgumentParser(description="Preveri, kaj je naloženo na ESP32")
ap.add_argument("--port", default=PORT)
ap.add_argument("--baud", type=int, default=naprava.PRIVZETA_HITROST)
a = ap.parse_args()
sys.exit(naprava.preveri_nalozeno(a.port, baud=a.baud))
