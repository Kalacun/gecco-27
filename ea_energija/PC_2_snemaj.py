"""PC (PyCharm): SNEMANJE seje z RIGOL-om. Celoten postopek: LAB_GUIDE.md.

Pred zagonom:
  - na ESP32 je naložen program (Mac_2 -> Upload v Arduino IDE -> Mac_3 je
    javil V REDU), USB kabel je IZKLOPLJEN iz ESP32,
  - RIGOL CH1 je vezan na 3V3/GND in stikalo je ZAPRTO,
  - računalnik je priključen na omrežno napajanje in se ne sme uspavati.
Skripta nastavi RIGOL (3,30 V, omejitev 0,5 A), vsako nastavitev prebere nazaj,
vklopi izhod (ESP32 se zažene), snema in po koncu seje izhod izklopi.
Mapa meritve/<SEJA> mora biti nova: obstoječa meritev se nikoli ne prepiše.
Po koncu odprite stikalo, USB priklopite na Mac in poženite Mac_4_preberi.py.
Ukaz za Terminal:  python PC_2_snemaj.py --vrsta veriga --datum 2026-11-18 --src <12 znakov>
"""
import argparse
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402
import zajem  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
VRSTA = "veriga"                          # "samopreizkus" | "veriga" | "kampanja"
DATUM = time.strftime("%Y-%m-%d")         # ali npr. "2026-11-18"
SRC_NA_MACU = ""                          # 12 znakov "ZGOSTITEV IZVORA", ki jo izpiše Mac_2_pripravi.py
RIGOL = ""                                # prazno = samodejno; ali "USB0::0x1AB1::0x0E11::...::INSTR"
NAJDLJE_S = {"samopreizkus": 1800, "veriga": 7200, "kampanja": 86400}   # varovalka

ap = argparse.ArgumentParser(description="Snemanje seje z RIGOL-om")
ap.add_argument("--vrsta", default=VRSTA, choices=sorted(NAJDLJE_S))
ap.add_argument("--datum", default=DATUM)
ap.add_argument("--src", default=SRC_NA_MACU, help="12 znakov ZGOSTITEV IZVORA iz Mac_2_pripravi.py")
ap.add_argument("--rigol", default=RIGOL)
a = ap.parse_args()
VRSTA, DATUM, SRC_NA_MACU, RIGOL = a.vrsta, a.datum, a.src, a.rigol
SEJA = f"{DATUM}_{VRSTA}"                 # ISTO ime vpišite v Mac_4_preberi.py in PC_3_analiza.py
MAPA = os.path.join("meritve", SEJA)
skupna, _ = izvor.zgostitev_izvora()
revizija, spremenjeno = izvor.git_stanje()
print(f"Seja: {SEJA}\nKoda na tem računalniku: git {revizija[:12] or 'neznano'}"
      f"{'+spremembe' if spremenjeno else ''}, zgostitev izvora {skupna[:12]}")
if SRC_NA_MACU and SRC_NA_MACU != skupna[:12]:
    sys.exit(f"Koda na tem računalniku (src {skupna[:12]}) NI ista kot na Macu (src "
             f"{SRC_NA_MACU}). Kopirajte ea_energija z Maca (ob ea_T.h, če obstaja) ali "
             "izvedite git pull, nato poskusite znova. Snemanje se ni začelo.")
if not SRC_NA_MACU:
    print("OPOZORILO: SRC_NA_MACU ni vpisan; ujemanje kode z Macom se preveri šele pri analizi.")
if os.path.exists(MAPA):
    sys.exit(f"Mapa {MAPA} že obstaja. Surovih podatkov ne prepisujem: spremenite DATUM ali VRSTA.")
sys.argv = ["zajem.py", "poskus", "--mapa", MAPA, "--najdlje-s", str(NAJDLJE_S[VRSTA])]
if RIGOL:
    sys.argv += ["--rigol", RIGOL]
zajem.main()
