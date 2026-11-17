"""W0 (PyCharm, Run): PREVERI NAMESTITEV na Windows PC, ki je povezan z RIGOL-om in ESP32.

Nič ne spreminja. Preveri Python, pakete, arduino-cli z jedrom esp32 3.3.12, git,
datoteko premikov, serijska vrata ESP32 in napajalnik RIGOL (VISA). Na koncu
požene vse teste, ki ne potrebujejo strojne opreme. Vse mora biti V REDU.
"""
import os
import subprocess
import sys
import unittest

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())
import izvor  # noqa: E402

napake = []


def rezultat(ime, ok, opis=""):
    print(f"  {'V REDU ' if ok else 'NAPAKA '} {ime}" + (f": {opis}" if opis else ""))
    if not ok:
        napake.append(ime)


print("1. Python in paketi")
rezultat("Python", sys.version_info >= (3, 9), sys.version.split()[0])
for paket in ("pyvisa", "serial", "esptool"):
    try:
        __import__(paket)
        rezultat(paket, True)
    except ImportError:
        rezultat(paket, False, "namestite: python -m pip install -r requirements.txt")
try:
    import matplotlib  # noqa: F401
    rezultat("matplotlib (grafi)", True)
except ImportError:
    print("  OPOMBA  matplotlib ni nameščen: analiza dela, grafov ne bo.")

print("2. Arduino (arduino-cli in jedro esp32)")
import prevedi  # noqa: E402
try:
    cli = prevedi.cli_ukaz(prevedi.najdi_cli(""))
    rezultat("arduino-cli", True, cli[0])
    jedra = subprocess.run(cli + ["core", "list"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace").stdout
    vrstica = next((v for v in jedra.splitlines() if v.startswith("esp32:esp32")), "")
    rezultat("jedro esp32 3.3.12", " 3.3.12 " in f" {vrstica} ",
             vrstica.strip() or "ni nameščeno: Arduino IDE -> Boards Manager -> esp32 3.3.12")
except SystemExit as e:
    rezultat("arduino-cli", False, str(e))

print("3. Git (oznaka prevoda)")
revizija, spremembe = izvor.git_stanje()
rezultat("git in skladišče", bool(revizija),
         f"revizija {revizija[:12]}{' (+spremembe)' if spremembe else ''}" if revizija else
         "namestite Git for Windows in kopirajte mapo s skrito mapo .git")

print("4. Izvorna koda")
r = subprocess.run([sys.executable, "generiraj_premike.py", "--preveri"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace")
rezultat("ea_premiki.h", r.returncode == 0)

print("5. ESP32 (serijska vrata)")
try:
    from serial.tools import list_ports
    vrata = list(list_ports.comports())
    for p in vrata:
        print(f"         {p.device}: {p.description}")
    import naprava
    esp = naprava.najdi_vrata("")
    if esp:
        rezultat("ESP32 najden", True, esp)
    else:
        print("  OPOMBA  ESP32 ni priklopljen ali ni prepoznan. To je v redu, če USB kabel ESP32 "
              "ni priklopljen. Sicer: gonilnik CP210x/CH340 (Upravitelj naprav -> Vrata) ali "
              "PORT_ESP32 v seja_nastavitve.py.")
except ImportError:
    pass

print("6. RIGOL (VISA)")
try:
    import pyvisa
    rm = pyvisa.ResourceManager()
    viri = rm.list_resources()
    rigoli = [v for v in viri if "0X1AB1" in v.upper() or "RIGOL" in v.upper()]
    rezultat("RIGOL", len(rigoli) == 1, ", ".join(rigoli) or
             f"ni najden (viri: {list(viri)}); NI-VISA ali UltraSigma, USB kabel, vklop")
    if len(rigoli) == 1:
        inst = rm.open_resource(rigoli[0])
        inst.timeout = 3000
        rezultat("identiteta", True, inst.query("*IDN?").strip())
        inst.close()
except Exception as e:  # noqa: BLE001
    rezultat("RIGOL", False, repr(e))

print("7. Testi brez strojne opreme")
paketi = ["test_zajem", "test_naprava", "test_stari_zapisi", "test_skripte", "test_windows"]
res = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromNames(paketi))
rezultat("testi", res.wasSuccessful())

print("\nVSE V REDU." if not napake else f"\nNAPAKE: {', '.join(napake)}. Popravite jih po LAB_GUIDE_WINDOWS.md.")
sys.exit(0 if not napake else 1)
