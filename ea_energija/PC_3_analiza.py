"""PC (PyCharm): ANALIZA seje. Celoten postopek: LAB_GUIDE.md.

Potrebuje mapo seje meritve/<SEJA> (rigol.csv ... iz PC_2_snemaj.py) in zapise
ESP32 iz Maca (mapa prenos/<SEJA>, ki jo je naredil Mac_4_preberi.py). Skripta
skopira esp32.txt in prevod_info.json v mapo seje (nič se ne prepiše) in:
  - samopreizkus: preveri merilno verigo z znanimi obremenitvami,
  - preizkus verige in kampanja: povzetek zapisov in celotna analiza.
Rezultati so v NOVI podmapi analiza_<datum>_<ura> ali samopreizkus_<datum>_<ura>.
Ob vsaki neskladnosti se analiza ustavi z NAPAKA ANALIZE in razlogom.
Ukaz za Terminal:  python PC_3_analiza.py --seja 2026-11-18_veriga --prenos "E:/prenos/2026-11-18_veriga"
"""
import os
import shutil
import sys
import argparse

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import zajem  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
SEJA = "2026-11-17_veriga"                 # ime seje (datum_vrsta)
PRENOS = ""                                # mapa z Maca, npr. r"E:\prenos\2026-11-17_veriga";
                                           # prazno, če je esp32.txt že v mapi seje
GRAFI = True                               # grafi (potrebuje matplotlib)
PODROBNO = False                           # izpiši vsak zagon

_ap = argparse.ArgumentParser(description="Analiza seje")
_ap.add_argument("--seja", default=SEJA)
_ap.add_argument("--prenos", default=PRENOS)
_ap.add_argument("--brez-grafov", action="store_true")
_ap.add_argument("--podrobno", action="store_true", default=PODROBNO)
_a = _ap.parse_args()
SEJA, PRENOS, PODROBNO = _a.seja, _a.prenos, _a.podrobno
GRAFI = GRAFI and not _a.brez_grafov

mapa = os.path.join("meritve", SEJA)
if not os.path.isfile(os.path.join(mapa, "rigol.csv")):
    sys.exit(f"Ni {mapa}/rigol.csv. Seja je bila posneta z PC_2_snemaj.py na tem računalniku.")
if PRENOS:
    for ime in ("esp32.txt", "prevod_info.json"):
        vir, cilj = os.path.join(PRENOS, ime), os.path.join(mapa, ime)
        if not os.path.isfile(vir):
            if ime == "esp32.txt":
                sys.exit(f"Ni {vir}.")
            print(f"OPOZORILO: {vir} manjka.")
            continue
        if os.path.exists(cilj):
            with open(vir, "rb") as a, open(cilj, "rb") as b:
                enako = a.read() == b.read()
            print(f"{ime}: v mapi seje že obstaja ({'enak' if enako else 'RAZLIČEN'}); ne prepisujem.")
            if not enako:
                sys.exit("esp32.txt v mapi seje se razlikuje od prenesenega. Preverite.")
            continue
        with open(vir, "rb") as a, open(cilj, "xb") as b:
            b.write(a.read())
        print(f"Skopirano: {ime}")
esp = os.path.join(mapa, "esp32.txt")
if not os.path.isfile(esp):
    sys.exit(f"Ni {esp}. Nastavite PRENOS na mapo, ki jo je naredil Mac_4_preberi.py.")
rigol = os.path.join(mapa, "rigol.csv")
try:
    if "#SAMO," in open(esp, encoding="utf-8", errors="replace").read():
        zajem.analiza_samopreizkusa(argparse.Namespace(rigol_csv=rigol, esp_txt=esp,
                                                       nastavitve=zajem.PRIVZETE_NASTAVITVE))
    else:
        zajem.povzetek_zapisov(argparse.Namespace(esp_txt=esp))
        print("\n" + "=" * 72)
        zajem.analiza(argparse.Namespace(rigol_csv=rigol, esp_txt=esp, grafi=GRAFI,
                                         podrobno=PODROBNO,
                                         nastavitve=zajem.PRIVZETE_NASTAVITVE))
except zajem.NapakaAnalize as e:
    print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
    sys.exit(2)
