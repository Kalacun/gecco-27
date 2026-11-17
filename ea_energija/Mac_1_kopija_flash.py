"""MAC, korak A: REŠI ZAPISE PREJŠNJIH SEJ, preden naložite nov program.

Zakaj: nalaganje programa z drugo oznako prevoda pobriše zapise na ESP32, stari
program pa jih ob vklopu izbriše, če je bila njegova zadnja seja prekinjena.
Ta skripta prebere CEL flash (4 MB) v datoteko, ne da bi se stari program
zagnal, nato iz kopije izvleče stare zapise v stari_zapisi.csv.

Priprava (stikalo v + vodniku RIGOL-a ODPRTO, nič drugega ne napaja ESP32):
  1. držite tipko BOOT na ploščici,
  2. priklopite USB kabel na Mac, BOOT držite še 2 s, spustite,
  3. poženite to skripto (PyCharm: Run, ali: python3 Mac_1_kopija_flash.py).
Skripta ESP32 NE ponastavi (zato morate držati BOOT ob priklopu). Branje traja
okoli 6 min. Po koncu ostane ESP32 v nalagalniku; odklopite USB.
Če branje ne uspe, odklopite USB in ponovite od točke 1; isto IME je dovoljeno,
dokler kopija ni dokončana.

Rezultat: arhiv/<IME>/kopija_flash.bin (+ .sha256), zapisi/stari_zapisi.csv,
razpakirane datoteke. Mapa mora biti nova; nič se ne prepiše.
Ukaz za Terminal:  python3 Mac_1_kopija_flash.py [--ime flash_2026-11-17] [--port PORT]
"""
import argparse
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
IME = "flash_" + time.strftime("%Y-%m-%d")     # mapa arhiv/<IME>
PORT = ""                                       # prazno = samodejno

ap = argparse.ArgumentParser(description="Kopija flasha ESP32 in izvleček starih zapisov")
ap.add_argument("--ime", default=IME)
ap.add_argument("--port", default=PORT)
ap.add_argument("--baud", type=int, default=naprava.PRIVZETA_HITROST,
                help="hitrost (privzeto 115200, najzanesljiveje)")
a = ap.parse_args()
sys.exit(naprava.kopija_flash(os.path.join("arhiv", a.ime), a.port, baud=a.baud))
