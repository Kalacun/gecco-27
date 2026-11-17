"""W2 (PyCharm, Run): PREVEDI IN NALOŽI program na ESP32 za sejo iz seja_nastavitve.py.

Pred zagonom: v seja_nastavitve.py nastavite VRSTA (in RED), shranite. Stikalo
RIGOL-a ODPRTO. DRŽITE BOOT in priklopite USB kabel ESP32 (tako se pred nalaganjem
ne zažene noben program), tipko lahko spustite.
Skripta: preveri premike, ustvari oznako prevoda, prevede z arduino-cli z zahtevanimi
nastavitvami plošče, naloži, shrani prevodi/<oznaka>/prevod_info.json in določi ime
seje (aktivna_seja.json). Nato: W3_preveri_nalaganje.py.
"""
import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402
import naprava  # noqa: E402
import seja  # noqa: E402

try:
    n = seja.nastavitve()
except seja.NapakaSeje as e:
    sys.exit(str(e))
revizija, spremembe = izvor.git_stanje()
if spremembe:
    print("OPOZORILO: izvorne datoteke niso shranjene v git (oznaka bo '+spremembe' in analiza bo\n"
          "sejo zavrnila). V PyCharmu: Git -> Commit, nato ponovno poženite W2.")
port = naprava.najdi_vrata(n.PORT_ESP32)
if not port:
    sys.exit("Ne najdem ESP32. Priklopite USB kabel ESP32 (z BOOT) ali vpišite PORT_ESP32 v "
             "seja_nastavitve.py (Upravitelj naprav -> Vrata (COM in LPT)).")
print(f"Seja: {n.VRSTA}, vrstni red {n.RED}, ESP32 na {port}\n")
r = subprocess.run([sys.executable, "prevedi.py", "--nacrt", str(seja.NACRT[n.VRSTA]),
                    "--red", str(n.RED), "--nalozi", "--port", port])
if r.returncode != 0:
    sys.exit("\nPrevod ali nalaganje ni uspelo (glejte zgoraj). Seja ni ustvarjena.")
oznaka = izvor.preberi_prevod_h()[0]
s = seja.nova_seja(n.VRSTA, n.RED, oznaka)
print(f"""
NALOŽENO. Aktivna seja: {s['seja']}
Oznaka prevoda: {oznaka}

NE pritiskajte EN in ne odpirajte Serial Monitorja. Naslednji korak:
  1. odklopite USB kabel ESP32,
  2. DRŽITE BOOT, priklopite USB, BOOT držite,
  3. poženite W3_preveri_nalaganje.py in BOOT spustite, ko se izpišejo odstotki.""")
