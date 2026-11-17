"""W1 (PyCharm, Run): REŠI ZAPISE PREJŠNJIH SEJ s ploščice (kopija celotnega flasha).

Pred zagonom (LAB_GUIDE_WINDOWS.md, korak A): stikalo RIGOL-a ODPRTO; DRŽITE BOOT,
priklopite USB kabel ESP32, BOOT držite, poženite to skripto in tipko spustite,
ko se izpišejo odstotki. Branje traja okoli 6 min; ESP32 se ne ponastavi.
Rezultat: arhiv/<IME>/ (kopija, zgostitev, obnovljeni zapisi). Če ste kopijo že
naredili (npr. na Macu), tega koraka ne ponavljajte.
"""
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402
import seja  # noqa: E402

# ---- nastavitve ----
IME = "flash_" + time.strftime("%Y-%m-%d")       # mapa arhiv/<IME>

sys.exit(naprava.kopija_flash(os.path.join("arhiv", IME), seja.nastavitve().PORT_ESP32))
