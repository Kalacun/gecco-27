"""W6 (PyCharm, Run): ANALIZA seje (privzeto aktivne).

Samopreizkus: preverjanje merilne verige z znanimi obremenitvami. Preizkus verige in
kampanja: povzetek zapisov in celotna analiza. Rezultati so v NOVI podmapi
meritve/<seja>/analiza_<datum>_<ura> (ali samopreizkus_...). Ob vsaki neskladnosti
se analiza ustavi z NAPAKA ANALIZE in razlogom. Ponovna analiza nič ne prepiše.
"""
import argparse
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import seja  # noqa: E402
import zajem  # noqa: E402

# ---- nastavitve ----
SEJA = ""          # prazno = aktivna seja; sicer ime, npr. "2026-11-18_veriga"
GRAFI = True       # grafi (potrebuje matplotlib)
PODROBNO = False   # izpiši vsak zagon

try:
    ime = seja.izbrana(SEJA)
except seja.NapakaSeje as e:
    sys.exit(str(e))
mapa = seja.mapa_seje(ime)
rigol, esp = os.path.join(mapa, "rigol.csv"), os.path.join(mapa, "esp32.txt")
for pot, korak in ((rigol, "W4_snemaj.py"), (esp, "W5_preberi.py")):
    if not os.path.isfile(pot):
        sys.exit(f"Ni {pot}. Najprej {korak}.")
try:
    zajem.kakovost_sledi(mapa)
    print()
    if "#SAMO," in open(esp, encoding="utf-8", errors="replace").read():
        zajem.analiza_samopreizkusa(argparse.Namespace(rigol_csv=rigol, esp_txt=esp,
                                                       nastavitve=zajem.PRIVZETE_NASTAVITVE))
    else:
        zajem.povzetek_zapisov(argparse.Namespace(esp_txt=esp))
        print("\n" + "=" * 72)
        zajem.analiza(argparse.Namespace(rigol_csv=rigol, esp_txt=esp, grafi=GRAFI,
                                         podrobno=PODROBNO, nastavitve=zajem.PRIVZETE_NASTAVITVE))
except zajem.NapakaAnalize as e:
    print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
    sys.exit(2)
