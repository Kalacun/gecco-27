"""KORAK 4 (računalnik z RIGOL-om, PyCharm): analiza, ko je esp32.txt v mapi.

esp32.txt prenesete z Maca (prebran prek USB z "python3 zajem.py preberi")
v isto mapo, kjer je rigol.csv (npr. meritve_kampanja1/esp32.txt).

V PyCharmu: nastavite MAPA in kliknite zeleni trikotnik (Run).
Rezultat: porocilo.txt, energija.csv, povzetek.csv, testi.csv,
kontrola.csv, konvergenca_energija.csv in grafi graf_*.png v isti mapi.
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import zajem  # noqa: E402

MAPA = "meritve_test_veriga"   # ali "meritve_kampanja1"

for ime in ("rigol.csv", "esp32.txt"):
    if not os.path.exists(os.path.join(MAPA, ime)):
        print(f"Manjka {MAPA}/{ime}.")
        sys.exit(1)
sys.argv = ["zajem.py", "analiza", f"{MAPA}/rigol.csv", f"{MAPA}/esp32.txt", "--grafi"]
zajem.main()
