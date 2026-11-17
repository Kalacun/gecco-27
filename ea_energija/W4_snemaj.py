"""W4 (PyCharm, Run): SNEMANJE aktivne seje z RIGOL-om.

Pred zagonom: W3 je javil VSE V REDU; USB kabel ESP32 je IZKLOPLJEN (skripta to
preveri); stikalo RIGOL-a ZAPRTO; računalnik na omrežnem napajanju.
Skripta nastavi RIGOL (3,30 V, omejitev 0,5 A), nastavitve prebere nazaj, vklopi
izhod (ESP32 se zažene), snema in po koncu seje izhod izklopi. Med sejo ničesar ne
spreminjajte. Nato: stikalo ODPRTO, USB kabel ESP32 priklopite BREZ BOOT in
poženite W5_preberi.py.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402
import naprava  # noqa: E402
import seja  # noqa: E402
import zajem  # noqa: E402

DOVOLI_PRIKLOPLJEN_USB = False     # True samo, če samodejno zaznavanje vrat napačno najde ESP32

try:
    n = seja.nastavitve()
    s = seja.aktivna()
except seja.NapakaSeje as e:
    sys.exit(str(e))
mapa = seja.mapa_seje(s["seja"])
if os.path.exists(mapa):
    sys.exit(f"Seja {s['seja']} je že posneta ({mapa}). Za novo sejo poženite W2 (ali W8 in W2).")
na_plosci = izvor.preberi_prevod_h()
if na_plosci is None or na_plosci[0] != s["oznaka_prevoda"]:
    sys.exit("ea_prevod.h se ne ujema z aktivno sejo: poženite W2 in W3 znova.")
if naprava.esp32_priklopljen(n.PORT_ESP32) and not DOVOLI_PRIKLOPLJEN_USB:
    sys.exit("USB kabel ESP32 je PRIKLOPLJEN. Med meritvijo ga izklopite (ploščico bi sicer napajala "
             "oba vira). Snemanje se ni začelo.")
print(f"Seja {s['seja']} ({s['vrsta']}), program {s['oznaka_prevoda']}")
oken, trajanje = seja.pricakovano(s["vrsta"], s["red"])
if oken:
    print(f"Načrt: {oken} merilnih oken" + (f", približno {trajanje / 3600:.1f} h" if trajanje
                                             else ""))
elif trajanje:
    print(f"Načrt: približno {trajanje / 60:.0f} min")
print("Snemanje se ustavi SAMO, 60 s po tem, ko ESP32 konča in zaspi; nato izklopi izhod.\n"
      "Vrstica spodaj kaže čas, tok, tok v spanju in sproti prešteta okna (~, samo za\n"
      "orientacijo). Če morate snemanje ustaviti z rdečim kvadratom, na RIGOL-u izklopite\n"
      "izhod CH1 (tipka On/Off), če ga skripta ni.\n")
sys.argv = ["zajem.py", "poskus", "--mapa", mapa, "--najdlje-s", str(seja.NAJDLJE_S[s["vrsta"]])]
if n.RIGOL:
    sys.argv += ["--rigol", n.RIGOL]
sys.argv += ["--pricakovano-oken", str(oken), "--pricakovano-s", str(trajanje or 0)]
zajem.main()
