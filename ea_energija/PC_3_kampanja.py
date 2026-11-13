"""KORAK 3 (računalnik z RIGOL-om, PyCharm): celotna kampanja (~8,5 h).

Pred zagonom: na ESP32 je naložen ea_energija.ino s končnimi nastavitvami
(Serial Monitor je pokazal #PRIPRAVLJEN), USB kabel je IZKLOPLJEN iz ESP32,
RIGOL CH1 je vezan na 3V3/GND in stikalo je zaprto. Datoteka
ea_energija.ino na TEM računalniku mora biti enaka tisti, ki je bila
naložena (iz nje se prebere načrt in čas trajanja).

V PyCharmu: kliknite zeleni trikotnik (Run) in pustite računalnik
priključen na omrežno napajanje. Skripta prepreči spanje računalnika,
sama izklopi izhod RIGOL-a, ko je ESP32 končal.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import zajem  # noqa: E402

# ---- nastavitve ----
MAPA = "meritve_kampanja1"     # za ponovitev kampanje uporabite novo ime
PROGRAM = "ea_energija.ino"
RIGOL = ""                     # prazno = samodejno

if os.path.exists(os.path.join(MAPA, "rigol.csv")):
    print(f"Mapa {MAPA} že vsebuje rigol.csv. Za novo kampanjo spremenite MAPA, "
          "da ne prepišete obstoječih meritev.")
    sys.exit(1)
sys.argv = ["zajem.py", "poskus", "--ino", PROGRAM, "--mapa", MAPA]
if RIGOL:
    sys.argv += ["--rigol", RIGOL]
zajem.main()
