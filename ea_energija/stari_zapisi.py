#!/usr/bin/env python3
"""Reši zapise PREJŠNJIH sej iz varnostne kopije flasha ESP32.

Uporaba (glej LAB_GUIDE.md, korak A):

  1) varnostna kopija celotnega flasha (nič se ne spremeni na ESP32):
       esptool --chip esp32 --port <VRATA> --baud 460800 read-flash 0 0x400000 kopija_flash.bin
  2) python3 stari_zapisi.py kopija_flash.bin --izhod stare_meritve_esp32

Skripta iz kopije izreže particijo z datotečnim sistemom (privzeta shema
"Default 4MB with spiffs": odmik 0x290000, velikost 0x160000), jo razpakira
z orodjem mklittlefs (del paketa esp32 za Arduino) in datoteko rez.bin
pretvori v stari_zapisi.csv. Kopija flasha in razpakirane datoteke ostanejo
nespremenjene v izhodni mapi; nič se ne prepiše (izhodna mapa mora biti nova).

OBLIKA ZAPISA: zapis programa pred revizijo (commit 4d7c5cc, 112 bajtov):
  alg, zagon, poskus, poz, ogrev, rezerva (6 x uint8), np_konec (uint16),
  fe, gen, cas_ms, fe_cilj, ms_cilj (5 x uint32), best (float), konv[20] (float).
Imena funkcij in dimenzije niso v zapisu (bile so v tabeli POSKUSI takratnega
programa); stolpec "poskus" je indeks v tej tabeli.

OPOZORILO: ti podatki so nastali s programom, ki ga je revizija ocenila kot
pomanjkljivega (nepremaknjeni funkciji, en cilj 1e-6 pod natančnostjo
izračuna, časovni proračun). Hranite jih kot arhiv, ne kot rezultate za članek.
"""
import argparse
import csv
import glob
import os
import re
import struct
import subprocess
import sys

ODMIK, VELIKOST = 0x290000, 0x160000          # particija "spiffs" v privzeti shemi 4 MB
NVS_ODMIK, NVS_VELIKOST = 0x9000, 0x5000
STARI = struct.Struct("<6BH5If20f")            # 112 bajtov
ALG = {0: "DE", 1: "jDE", 2: "LSHADE"}


def najdi_mklittlefs(podan):
    kandidati = [podan]
    for koren in (os.path.expanduser("~/Library/Arduino15"),
                  os.path.expandvars(r"%LOCALAPPDATA%\Arduino15"),
                  os.path.expanduser("~/.arduino15")):
        kandidati += sorted(glob.glob(os.path.join(koren, "packages", "esp32", "tools",
                                                   "mklittlefs", "*", "mklittlefs*")))
    for k in kandidati:
        if k and os.path.isfile(k):
            return k
    return None


def pretvori_rez_bin(pot, izhod_csv):
    """Pretvori rez.bin (stari 112-bajtni zapisi) v CSV. Vrne število zapisov."""
    with open(pot, "rb") as f:
        podatki = f.read()
    if len(podatki) % STARI.size:
        print(f"OPOZORILO: velikost {len(podatki)} B ni večkratnik {STARI.size} B. Datoteka ni v "
              "obliki programa pred revizijo (ali je zadnji zapis nepopoln). Pretvorim cele zapise; "
              "preverite vrednosti.")
    n = len(podatki) // STARI.size
    with open(izhod_csv, "x", newline="") as f:
        w = csv.writer(f)
        w.writerow(["i", "alg", "alg_ime", "zagon", "poskus", "poz", "ogrev", "np_konec", "fe",
                    "gen", "cas_ms", "fe_cilj", "ms_cilj", "best"]
                   + [f"konv_{k + 1}" for k in range(20)])
        for i in range(n):
            d = STARI.unpack_from(podatki, i * STARI.size)
            alg, zagon, poskus, poz, ogrev, _rez, np_konec, fe, gen, cas_ms, fe_c, ms_c, best = d[:13]
            w.writerow([i, alg, ALG.get(alg, "?"), zagon, poskus, poz, ogrev, np_konec, fe, gen,
                        cas_ms, fe_c, ms_c, repr(best)] + [repr(x) for x in d[13:]])
    return n


def main():
    ap = argparse.ArgumentParser(description="Zapisi prejšnjih sej iz kopije flasha ESP32")
    ap.add_argument("kopija", help="kopija celotnega flasha (esptool read-flash 0 0x400000) "
                                   "ali, z --rez-bin, že izvlečena datoteka rez.bin")
    ap.add_argument("--izhod", required=True, help="NOVA mapa za rezultate")
    ap.add_argument("--rez-bin", action="store_true", help="vhod je rez.bin, ne kopija flasha")
    ap.add_argument("--mklittlefs", default="", help="pot do orodja mklittlefs")
    ap.add_argument("--odmik", type=lambda x: int(x, 0), default=ODMIK)
    ap.add_argument("--velikost", type=lambda x: int(x, 0), default=VELIKOST)
    args = ap.parse_args()
    os.makedirs(args.izhod, exist_ok=False)            # nikoli v obstoječo mapo
    if args.rez_bin:
        n = pretvori_rez_bin(args.kopija, os.path.join(args.izhod, "stari_zapisi.csv"))
        print(f"Pretvorjenih zapisov: {n} -> {os.path.join(args.izhod, 'stari_zapisi.csv')}")
        return
    with open(args.kopija, "rb") as f:
        flash = f.read()
    if len(flash) < args.odmik + args.velikost:
        sys.exit(f"Kopija ima {len(flash)} B; za particijo pri 0x{args.odmik:x} je potrebnih "
                 f"vsaj {args.odmik + args.velikost} B. Ali je bila prebrana cela (0x400000)?")
    # oznake prevoda in stanje v NVS (samo za informacijo)
    nvs = flash[NVS_ODMIK:NVS_ODMIK + NVS_VELIKOST]
    oznake = sorted({m.decode() for m in re.findall(
        rb"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [ \d]\d \d{4} \d\d:\d\d:\d\d", nvs)})
    print(f"Oznake prevoda, najdene v NVS: {oznake or 'nobene'}")
    slika = os.path.join(args.izhod, "particija_littlefs.bin")
    with open(slika, "xb") as f:
        f.write(flash[args.odmik:args.odmik + args.velikost])
    orodje = najdi_mklittlefs(args.mklittlefs)
    if not orodje:
        sys.exit(f"Particija je shranjena v {slika}, a ne najdem orodja mklittlefs. Podajte "
                 "--mklittlefs <pot> (Arduino15/packages/esp32/tools/mklittlefs/<različica>/).")
    razpakirano = os.path.join(args.izhod, "datoteke")
    os.makedirs(razpakirano)
    r = subprocess.run([orodje, "-u", razpakirano, "-b", "4096", "-p", "256",
                        "-s", str(args.velikost), slika], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("mklittlefs ni uspel (particija morda ni LittleFS ali je prazna):\n"
                 + r.stdout + r.stderr)
    datoteke = [os.path.join(k, d) for k, _, dd in os.walk(razpakirano) for d in dd]
    print("Datoteke v datotečnem sistemu ESP32:",
          [(os.path.relpath(d, razpakirano), os.path.getsize(d)) for d in datoteke] or "nobene")
    rez = os.path.join(razpakirano, "rez.bin")
    if not os.path.isfile(rez):
        sys.exit("Datoteke rez.bin ni: na ESP32 ni shranjenih zapisov (seja se ni začela, "
                 "zapisi so bili pobrisani ali pa jih je program že izbrisal ob ponovnem zagonu).")
    n = pretvori_rez_bin(rez, os.path.join(args.izhod, "stari_zapisi.csv"))
    print(f"Pretvorjenih zapisov: {n} -> {os.path.join(args.izhod, 'stari_zapisi.csv')}")


if __name__ == "__main__":
    main()
