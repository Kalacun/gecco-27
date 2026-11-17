"""W3 (PyCharm, Run): PREVERI, KAJ JE NALOŽENO in ali je ploščica pripravljena za sejo.

Pred zagonom: odklopite USB kabel ESP32, DRŽITE BOOT, priklopite USB, BOOT držite,
poženite skripto in BOOT spustite šele, ko se izpišejo odstotki (okoli 50 s). Če ESP32
ne odgovori, ga skripta sama ponastavi v nalagalnik; zato mora biti BOOT med
"Connecting..." še vedno pritisnjen.
Mora končati z VSE V REDU. Nato odklopite USB kabel ESP32 in poženite W4_snemaj.py.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import naprava  # noqa: E402
import seja  # noqa: E402

sys.exit(naprava.preveri_nalozeno(seja.nastavitve().PORT_ESP32))
