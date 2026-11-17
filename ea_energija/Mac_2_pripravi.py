"""MAC: PRIPRAVA PROGRAMA za nalaganje iz Arduino IDE.

Poženite to skripto VEDNO pred Upload v Arduino IDE (in po vsaki spremembi
kode). Ustvari ea_prevod.h z oznako prevoda (git revizija + zgostitev izvorne
kode), načrtom in vrstnim redom; Arduino IDE ga prebere sam. Izpiše tudi
nastavitve menija Tools, ki jih morate preveriti.

Nato:  1) Arduino IDE: odprite ea_energija/ea_energija.ino, preverite Tools,
          kliknite Upload,
       2) Mac_3_preveri_nalaganje.py.
"""
import argparse
import json
import os
import subprocess
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
VRSTA = "veriga"       # "samopreizkus" | "veriga" (preizkus verige) | "kampanja"
RED = 0                # vrstni red blokov: 0 naključen (25 blokov), 1 uravnotežen (30 blokov)
DATUM = time.strftime("%Y-%m-%d")      # datum seje (za imena v izpisanih ukazih)

ap = argparse.ArgumentParser(description="Priprava programa za nalaganje iz Arduino IDE")
ap.add_argument("--vrsta", default=VRSTA, choices=("samopreizkus", "veriga", "kampanja"))
ap.add_argument("--red", type=int, default=RED, choices=(0, 1))
ap.add_argument("--datum", default=DATUM)
a = ap.parse_args()
VRSTA, RED, DATUM = a.vrsta, a.red, a.datum
SEJA = f"{DATUM}_{VRSTA}"
NACRT = {"veriga": 0, "kampanja": 1, "samopreizkus": 2}
r = subprocess.run([sys.executable, "generiraj_premike.py", "--preveri"], capture_output=True,
                   text=True)
if r.returncode != 0:
    sys.exit("ea_premiki.h ni enak izhodu generiraj_premike.py:\n" + r.stdout + r.stderr)
if VRSTA == "kampanja" and not os.path.isfile("ea_T.h"):
    sys.exit("Kampanja potrebuje ea_T.h: najprej preizkus verige in Mac_5_nastavi_T.py.")

oznaka, podrobnosti = izvor.zapisi_prevod_h(NACRT[VRSTA], RED)
mapa = os.path.join("prevodi", izvor.ime_mape_prevoda(oznaka))
os.makedirs(mapa, exist_ok=True)
with open(os.path.join(mapa, "prevod_info.json"), "w", encoding="utf-8") as f:
    json.dump({"oznaka_prevoda": oznaka, "vrsta": VRSTA, "nacrt": NACRT[VRSTA], "vrstni_red": RED,
               **podrobnosti, "fqbn_zahtevan": izvor.FQBN, "pripravljeno_z": "Mac_2_pripravi.py"},
              f, indent=2, ensure_ascii=False)

print("=" * 72)
print(f"VRSTA: {VRSTA}   vrstni red: {RED}")
print(f"OZNAKA PREVODA:  {oznaka}")
print(f"ZGOSTITEV IZVORA: {podrobnosti['sha256_skupna'][:12]}   (src; vpišite jo v "
      "PC_2_snemaj.py, SRC_NA_MACU)")
print("=" * 72)
if podrobnosti["git_spremembe"]:
    print("OPOZORILO: izvorne datoteke se razlikujejo od revizije git ('+spremembe'). Analiza\n"
          "take seje bo zavrnjena. Najprej:  git add -A ea_energija && git commit -m '...'\n"
          "in nato ponovno poženite to skripto.")
if not podrobnosti["git_revizija"]:
    print("OPOZORILO: mapa ni git skladišče (oznaka 'git:neznano').")
print("\nArduino IDE 2: Tools mora biti natanko tako (nič drugega ni pomembno):")
for k, v in izvor.MENI_IDE:
    print(f"   {k:38s} {v}")
print("\nNato kliknite Upload. Program ob prevajanju sam zavrne napačno frekvenco CPU,\n"
      "debug level in PSRAM; ostale nastavitve plošče preveri analiza iz FQBN v izpisu.")
print(f"""
UKAZI ZA NASLEDNJE KORAKE (kopirajte; ime seje: {SEJA})
  1. Mac, po Upload (Terminal v mapi ea_energija):
       python3 Mac_3_preveri_nalaganje.py
  2. PC, snemanje (PyCharm Terminal v mapi ea_energija; stikalo ZAPRTO, USB izklopljen):
       python PC_2_snemaj.py --vrsta {VRSTA} --datum {DATUM} --src {podrobnosti['sha256_skupna'][:12]}
  3. Mac, po seji (stikalo ODPRTO, USB priklopljen):
       python3 Mac_4_preberi.py --seja {SEJA}
  4. PC, analiza (po prenosu mape prenos/{SEJA}):
       python PC_3_analiza.py --seja {SEJA} --prenos "<pot do mape prenos/{SEJA}>"
""")
