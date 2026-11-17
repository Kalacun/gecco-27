"""W5 (PyCharm, Run): PREBERI ZAPISE z ESP32 v mapo aktivne seje.

Pred zagonom: seja je končana (W4 je izklopil izhod), stikalo RIGOL-a ODPRTO, USB
kabel ESP32 priklopite BREZ tipke BOOT (ESP32 se zažene in izpisuje zapise).
Skripta zapiše meritve/<seja>/esp32.txt, izpiše povzetek zapisov in preverjanje
nastavitev plošče ter v mapo seje skopira prevod_info.json. Nato: W6_analiza.py.
NE brišite zapisov (W8), dokler analiza ni pregledana.
"""
import argparse
import os
import shutil
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402
import naprava  # noqa: E402
import seja  # noqa: E402
import zajem  # noqa: E402

# ---- nastavitve ----
SEJA = ""            # prazno = aktivna seja; sicer ime, npr. "2026-11-18_veriga"
CAS_BRANJA_S = 900   # najdaljše čakanje na celoten izpis (kampanja: 1-2 min izpisa)

try:
    ime = seja.izbrana(SEJA)
    port_n = seja.nastavitve().PORT_ESP32
except seja.NapakaSeje as e:
    sys.exit(str(e))
mapa = seja.mapa_seje(ime)
port = naprava.najdi_vrata(port_n)
if not port:
    sys.exit("Ne najdem ESP32. Priklopite USB kabel ESP32 (BREZ BOOT).")
ok = zajem.preberi(argparse.Namespace(port=port, baud=115200, mapa=mapa, cas=CAS_BRANJA_S))
if not ok:
    sys.exit("Branje ni uspelo.")
esp = os.path.join(mapa, "esp32.txt")
try:
    param, rez = zajem.preberi_esp(esp)
except zajem.NapakaAnalize as e:
    sys.exit(f"esp32.txt je shranjen, a ga ni mogoče prebrati: {e}")
napake = izvor.napake_plosce(param["fqbn"])
print(f"\nPrevod: {param['prevod']}\nFQBN:   {param['fqbn']}")
print("Nastavitve plošče: " + ("V REDU" if not napake else "NAPAKA: " + "; ".join(napake)))
if "#SAMO," not in open(esp, encoding="utf-8", errors="replace").read():
    zajem.povzetek_zapisov(argparse.Namespace(esp_txt=esp))
info = os.path.join("prevodi", izvor.ime_mape_prevoda(param["prevod"]), "prevod_info.json")
if os.path.isfile(info) and not os.path.exists(os.path.join(mapa, "prevod_info.json")):
    shutil.copy(info, os.path.join(mapa, "prevod_info.json"))
print("\nNaslednji korak: W6_analiza.py")
