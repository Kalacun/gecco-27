# ====================================================================
#  NASTAVITVE SEJE za skripte W2 ... W8 (Windows PC z RIGOL-om in ESP32).
#  Pred vsako novo sejo spremenite VRSTA (in po potrebi RED), shranite
#  (Ctrl+S) in poženite W2_pripravi_in_nalozi.py. Ostale skripte ime seje
#  vzamejo same iz aktivna_seja.json, ki ga zapiše W2.
# ====================================================================

VRSTA = "samopreizkus"   # "samopreizkus" | "veriga" (preizkus verige) | "kampanja"
RED = 0                  # vrstni red blokov: 0 = naključen (25 blokov), 1 = uravnotežen (30 blokov)
PORT_ESP32 = ""          # prazno = samodejno; sicer npr. "COM5" (Upravitelj naprav -> Vrata)
RIGOL = ""               # prazno = samodejno; sicer npr. "USB0::0x1AB1::0x0E11::DP8E...::INSTR"
