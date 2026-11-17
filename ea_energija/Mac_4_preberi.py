"""MAC: PREBERI ZAPISE Z ESP32 po seji in jih pripravi za prenos.

Pred zagonom: seja na RIGOL-u je končana, stikalo v + vodniku ODPRTO, nato
priklopite USB kabel na Mac (ESP32 se zažene in izpisuje zapise). Skripta:
  - prebere izpis v prenos/<SEJA>/esp32.txt (nova mapa; nič se ne prepiše),
  - izpiše povzetek zapisov (stanje seje, trajanja, doseženi cilji),
  - preveri nastavitve plošče, ki jih je program sam zapisal,
  - po želji primerja zagone z gostiteljskim prevodom istega jedra (K1),
  - v mapo skopira prevod_info.json.
Nato mapo prenos/<SEJA> prenesite na računalnik z RIGOL-om (USB ključ, omrežna
mapa ...) in tam poženite PC_3_analiza.py.

Ukaz za Terminal:  python3 Mac_4_preberi.py --seja 2026-11-18_kampanja

NE pošiljajte ukaza 'n' v Serial Monitor, dokler zapisi niso preneseni in
preverjeni.
"""
import argparse
import os
import shutil
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402
import naprava  # noqa: E402
import zajem  # noqa: E402

# ---- nastavitve (v PyCharmu spremenite tukaj; v Terminalu jih lahko podate kot argumente) ----
SEJA = "2026-11-18_kampanja"      # ISTO ime kot v PC_2_snemaj.py (datum_vrsta)
PORT = ""                         # prazno = samodejno
PRIMERJAJ_Z_GOSTITELJEM = True    # K1; potrebuje prevajalnik C++ (c++), sicer se preskoči
CAS_BRANJA_S = 900                # najdaljše čakanje na celoten izpis

_ap = argparse.ArgumentParser(description="Preberi zapise z ESP32 v prenos/<seja>")
_ap.add_argument("--seja", default=SEJA)
_ap.add_argument("--port", default=PORT)
_ap.add_argument("--brez-gostitelja", action="store_true", help="preskoči primerjavo z gostiteljem")
_ap.add_argument("--cas", type=int, default=CAS_BRANJA_S, help="najdaljše čakanje (s)")
_a = _ap.parse_args()
SEJA, PORT, CAS_BRANJA_S = _a.seja, _a.port, _a.cas
PRIMERJAJ_Z_GOSTITELJEM = PRIMERJAJ_Z_GOSTITELJEM and not _a.brez_gostitelja

mapa = os.path.join("prenos", SEJA)
if os.path.exists(os.path.join(mapa, "esp32.txt")):
    sys.exit(f"{mapa}/esp32.txt že obstaja. Surovih podatkov ne prepisujem: spremenite SEJA.")
port = naprava.najdi_vrata(PORT)
if not port:
    sys.exit("Ne najdem serijskih vrat ESP32 (USB priklopljen? Zaprt Serial Monitor v IDE?).")
ok = zajem.preberi(argparse.Namespace(port=port, baud=115200, mapa=mapa, cas=CAS_BRANJA_S))
if not ok:
    sys.exit("Branje ni uspelo. Pri polni kampanji traja izpis več minut: povečajte CAS_BRANJA_S.")
esp = os.path.join(mapa, "esp32.txt")
print("\n" + "=" * 72)
try:
    param, rez = zajem.preberi_esp(esp)
except zajem.NapakaAnalize as e:
    sys.exit(f"esp32.txt je shranjen, a ga ni mogoče prebrati: {e}")
napake = izvor.napake_plosce(param["fqbn"])
print(f"Prevod:  {param['prevod']}\nFQBN:    {param['fqbn']}")
print("Nastavitve plošče: " + ("V REDU" if not napake else "NAPAKA: " + "; ".join(napake)))
if "#SAMO," in open(esp, encoding="utf-8", errors="replace").read():
    print("To je izpis samopreizkusa; analizira ga PC_3_analiza.py.")
else:
    zajem.povzetek_zapisov(argparse.Namespace(esp_txt=esp))
    if PRIMERJAJ_Z_GOSTITELJEM and shutil.which("c++"):
        print("\n--- primerjava z gostiteljskim prevodom (K1) ---")
        subprocess.run([sys.executable, os.path.join("gostitelj", "primerjaj_z_napravo.py"), esp])
    elif PRIMERJAJ_Z_GOSTITELJEM:
        print("\n(Prevajalnika C++ ni: primerjava z gostiteljem preskočena.)")
info = os.path.join("prevodi", izvor.ime_mape_prevoda(param["prevod"]), "prevod_info.json")
if os.path.isfile(info):
    shutil.copy(info, os.path.join(mapa, "prevod_info.json"))
    print("\nprevod_info.json skopiran v mapo prenosa.")
else:
    print(f"\nOPOZORILO: {info} ne obstaja (program ni bil pripravljen s Mac_2_pripravi.py na "
          "tem Macu); prevod_info.json manjka.")
print(f"\nPrenesite mapo  {os.path.abspath(mapa)}  na računalnik z RIGOL-om.")
