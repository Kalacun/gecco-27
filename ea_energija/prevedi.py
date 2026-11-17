#!/usr/bin/env python3
"""Ponovljiv prevod (in nalaganje) programa ea_energija.ino z arduino-cli.

    python3 prevedi.py --nacrt 0                      preizkus verige, samo prevod
    python3 prevedi.py --nacrt 0 --nalozi --port COM5 prevod in nalaganje na ESP32
    python3 prevedi.py --nacrt 1 --red 0 --nalozi --port /dev/cu.usbserial-0001

    --nacrt 0  preizkus verige    --nacrt 1  kampanja    --nacrt 2  samopreizkus
    --red   0  naključen vrstni red blokov (privzeto)    --red 1  uravnotežen

Kaj naredi:
  1) preveri, da je ea_premiki.h enak izhodu generiraj_premike.py;
  2) ustvari ea_prevod.h (izvor.py) z OZNAKO PREVODA: revizija git, oznaka "+spremembe",
     če izvorne datoteke niso enake reviziji, zgostitev (SHA-256) izvornih
     datotek, načrt in vrstni red. Program oznako zapiše v glavo izpisa in
     njen CRC v vsak zapis;
  3) prevede z NATANKO določenimi nastavitvami plošče (FQBN spodaj) in z
     opozorili -Wall -Wextra -Wdouble-promotion -Wfloat-conversion; opozorilo
     v izvornih datotekah projekta ustavi prevod;
  4) v prevodi/<oznaka>/ shrani binarno datoteko in prevod_info.json
     (oznaka, revizija, zgostitve, FQBN, različice orodij, zastavice);
  5) z --nalozi program naloži na ESP32.

OPOZORILO: nalaganje programa z DRUGO oznako prevoda pobriše zapise na
ESP32. Zapise prejšnje seje prej preberite (zajem.py preberi).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

import izvor
from izvor import FQBN, ime_mape_prevoda, oznaka_prevoda

MAPA = izvor.MAPA
IZVORNE = tuple(izvor.izvorne_datoteke())
OPOZORILA = "-Wdouble-promotion -Wfloat-conversion"   # -Wall -Wextra doda --warnings all


def najdi_cli(podan):
    kandidati = [podan, os.environ.get("ARDUINO_CLI"), shutil.which("arduino-cli"),
                 "/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/"
                 "arduino-cli",
                 os.path.expandvars(r"%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib"
                                    r"\backend\resources\arduino-cli.exe"),
                 r"C:\Program Files\Arduino IDE\resources\app\lib\backend\resources"
                 r"\arduino-cli.exe",
                 os.path.expanduser("~/.local/bin/arduino-cli"), "/usr/local/bin/arduino-cli"]
    for k in kandidati:
        if k and os.path.isfile(k):
            return k
    sys.exit("Ne najdem arduino-cli. Namestite ga (https://arduino.github.io/arduino-cli) ali "
             "podajte pot: --cli <pot> (Arduino IDE 2 ga vsebuje v mapi resources).")


def cli_ukaz(cli):
    """arduino-cli z nastavitvami Arduino IDE, če obstajajo (isti nameščeni paketi)."""
    nast = os.path.join(os.path.expanduser("~"), ".arduinoIDE", "arduino-cli.yaml")
    return [cli, "--config-file", nast] if os.path.isfile(nast) else [cli]


def pozeni(ukaz, **kw):
    return subprocess.run(ukaz, capture_output=True, text=True, **kw)


def sha256(pot):
    with open(pot, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="Prevod in nalaganje ea_energija.ino")
    ap.add_argument("--nacrt", type=int, choices=(0, 1, 2), required=True,
                    help="0 preizkus verige, 1 kampanja, 2 samopreizkus")
    ap.add_argument("--red", type=int, choices=(0, 1), default=0,
                    help="vrstni red blokov: 0 naključen (privzeto), 1 uravnotežen")
    ap.add_argument("--nalozi", action="store_true", help="po prevodu naloži na ESP32")
    ap.add_argument("--port", default="", help="serijska vrata ESP32 (COM5, /dev/cu.usbserial-…)")
    ap.add_argument("--cli", default="", help="pot do arduino-cli")
    args = ap.parse_args()
    if args.nalozi and not args.port:
        sys.exit("Za --nalozi podajte --port.")

    r = pozeni([sys.executable, os.path.join(MAPA, "generiraj_premike.py"), "--preveri"])
    if r.returncode != 0:
        sys.exit("ea_premiki.h ni enak izhodu generiraj_premike.py:\n" + r.stdout + r.stderr)

    cli = cli_ukaz(najdi_cli(args.cli))
    if args.nacrt == 1 and not os.path.isfile(os.path.join(MAPA, "ea_T.h")):
        sys.exit("Kampanja potrebuje ea_T.h (Mac_5_nastavi_T.py po preizkusu verige).")
    # ea_prevod.h vsebuje oznako prevoda, načrt in vrstni red (isto kot pripravi.py)
    oznaka, podrobnosti = izvor.zapisi_prevod_h(args.nacrt, args.red)
    izhod = os.path.join(MAPA, "prevodi", ime_mape_prevoda(oznaka))
    os.makedirs(izhod, exist_ok=True)
    zastavice = OPOZORILA
    print(f"Oznaka prevoda: {oznaka}")
    if podrobnosti["git_spremembe"]:
        print("OPOZORILO: izvorne datoteke se razlikujejo od revizije git (+spremembe). "
              "Za meritve za članek spremembe najprej shranite v git (commit).")
    ukaz = cli + ["compile", "--fqbn", FQBN, "--warnings", "all",
                  "--build-property", f"compiler.cpp.extra_flags={zastavice}",
                  "--build-path", os.path.join(izhod, "build"), "--output-dir", izhod, MAPA]
    print("Prevajam ...")
    r = pozeni(ukaz)
    dnevnik = r.stdout + r.stderr
    with open(os.path.join(izhod, "prevod_dnevnik.txt"), "w", encoding="utf-8") as f:
        f.write(dnevnik)
    if r.returncode != 0:
        print(dnevnik[-3000:])
        sys.exit("Prevod ni uspel (celoten dnevnik: prevod_dnevnik.txt).")
    nasa = [v for v in dnevnik.splitlines()
            if "warning:" in v and any(i in v for i in IZVORNE + ("ea_prevod.h",))]
    if nasa:
        print("\n".join(nasa))
        sys.exit("Opozorila prevajalnika v izvornih datotekah projekta; odpravite jih.")
    velikost = re.search(r"Sketch uses (\d+) bytes", dnevnik)
    binarna = os.path.join(izhod, "ea_energija.ino.bin")
    info = {"oznaka_prevoda": oznaka, **podrobnosti, "nacrt": args.nacrt, "vrstni_red": args.red,
            "fqbn": FQBN, "zastavice": zastavice, "opozorila": "--warnings all " + OPOZORILA,
            "arduino_cli": pozeni(cli + ["version"]).stdout.strip(),
            "jedra": pozeni(cli + ["core", "list"]).stdout.strip().splitlines(),
            "velikost_programa_B": int(velikost.group(1)) if velikost else None,
            "sha256_binarne": sha256(binarna) if os.path.isfile(binarna) else None,
            "cas_prevoda": time.strftime("%Y-%m-%d %H:%M:%S %z"), "python": sys.version.split()[0],
            "platforma": sys.platform}
    with open(os.path.join(izhod, "prevod_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)
    print(f"Prevedeno: {info['velikost_programa_B']} B, brez opozoril v izvornih datotekah.\n"
          f"Mapa prevoda: {izhod}\n  prevod_info.json skopirajte v mapo z meritvami te seje.")
    if args.nalozi:
        print(f"Nalagam na {args.port} ...")
        r = subprocess.run(cli + ["upload", "--fqbn", FQBN, "--port", args.port,
                                  "--input-dir", izhod, MAPA])
        if r.returncode != 0:
            sys.exit("Nalaganje ni uspelo.")
        print("Naloženo. V Serial Monitorju (115200) mora ESP32 izpisati '#PRIPRAVLJEN prevod="
              f"{oznaka}'. Nato odklopite USB.")


if __name__ == "__main__":
    main()
