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

for _tok in (sys.stdout, sys.stderr):          # šumniki v konzoli Windows ne smejo sesuti izpisa
    try:
        _tok.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

ODMIK, VELIKOST = 0x290000, 0x160000          # particija "spiffs" v privzeti shemi 4 MB
NVS_ODMIK, NVS_VELIKOST = 0x9000, 0x5000
STARI = struct.Struct("<6BH5If20f")            # 112 bajtov (prevodi od 13. 11. 2026)
# Še starejša oblika (commit 68a0325, prevodi 12. 11. 2026): alg, zagon (2 x uint8),
# np_konec (uint16), fe, gen, cas_ms, fe_cilj, ms_cilj (5 x uint32), best, konv[20].
STARI_108 = struct.Struct("<2BH5If20f")        # 108 bajtov
BLOK = 4096                                     # velikost bloka LittleFS
ALG = {0: "DE", 1: "jDE", 2: "LSHADE"}
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
    with open(izhod_csv, "x", newline="", encoding="utf-8") as f:
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


def _veljaven_112(t):
    alg, zagon, poskus, poz, ogrev, _r, np_k, fe, gen, cas, fec, msc, best = t[:13]
    return (alg <= 2 and poz <= 2 and ogrev <= 1 and poskus <= 7 and 1 <= np_k <= 5000
            and 0 < fe < 10**9 and 0 < gen <= fe and 1000 <= cas <= 3600000
            and best == best and 0 <= best < 1e30 and fec <= fe)


def _veljaven_108(t):
    alg, zagon, np_k, fe, gen, cas, fec, msc, best = t[:9]
    return (alg <= 2 and 1 <= np_k <= 5000 and 0 < fe < 10**9 and 0 < gen <= fe
            and 1000 <= cas <= 3600000 and best == best and 0 <= best < 1e30 and fec <= fe)


def _zapisi_v_bloku(blok, oblika, veljaven):
    zap = []
    for k in range(len(blok) // oblika.size):
        t = oblika.unpack_from(blok, k * oblika.size)
        if not veljaven(t):
            break
        zap.append(t)
    return zap


def obnovi_izbrisane(particija):
    """Poišče v particiji LittleFS bloke, ki vsebujejo zapise (tudi izbrisanih
    datotek: LittleFS ob brisanju podatkov ne prepiše, dokler bloka ne uporabi
    znova). Vsak dodani zapis je stari program zapisal v nov blok s celotno
    vsebino datoteke, zato je vsaka seja vrsta blokov z 1, 2, 3 ... zapisi.
    Vrne najdaljše različice: seznam slovarjev (oblika, blok, zapisi), kjer
    nobena ni začetni del druge. Datoteke, daljše od enega bloka (37 oz.
    38 zapisov), se tako ne obnovijo v celoti; to se izpiše."""
    kandidati = []
    for b in range(len(particija) // BLOK):
        blok = particija[b * BLOK:(b + 1) * BLOK]
        for ime, oblika, veljaven in (("112", STARI, _veljaven_112), ("108", STARI_108, _veljaven_108)):
            zap = _zapisi_v_bloku(blok, oblika, veljaven)
            if zap:
                kandidati.append({"oblika": ime, "blok": b, "zapisi": zap,
                                  "bajti": blok[:len(zap) * oblika.size]})
                break
    najdaljse = []
    for k in kandidati:
        if any(d is not k and d["oblika"] == k["oblika"] and len(d["bajti"]) > len(k["bajti"])
               and d["bajti"].startswith(k["bajti"]) for d in kandidati):
            continue                          # začetni del daljše različice
        if any(d["oblika"] == k["oblika"] and d["bajti"] == k["bajti"] for d in najdaljse):
            continue                          # enaka različica v drugem bloku
        k["polna"] = len(k["zapisi"]) == BLOK // (STARI.size if k["oblika"] == "112"
                                                  else STARI_108.size)
        najdaljse.append(k)
    return najdaljse


def _pisi_csv(pot, oblika, zapisi):
    with open(pot, "x", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["i", "alg", "alg_ime", "zagon", "poskus", "poz", "ogrev", "np_konec", "fe",
                    "gen", "cas_ms", "fe_cilj", "ms_cilj", "best"]
                   + [f"konv_{k + 1}" for k in range(20)])
        for i, d in enumerate(zapisi):
            if oblika == "112":
                alg, zagon, poskus, poz, ogrev, _r, np_k, fe, gen, cas, fec, msc, best = d[:13]
                konv = d[13:]
            else:
                alg, zagon, np_k, fe, gen, cas, fec, msc, best = d[:9]
                poskus = poz = ogrev = ""
                konv = d[9:]
            w.writerow([i, alg, ALG.get(alg, "?"), zagon, poskus, poz, ogrev, np_k, fe, gen, cas,
                        fec, msc, repr(best)] + [repr(x) for x in konv])


def zgodovina_nvs(nvs):
    """Vrstni red vnosov v imenskem prostoru programa (stanje, resetov, prevod),
    tudi izbrisanih. Vrne seznam (stanje_vnosa, ključ, vrednost)."""
    vrste = {0x01: "U8", 0x21: "STR"}
    izhod = []
    for st in range(len(nvs) // BLOK):
        stran = nvs[st * BLOK:(st + 1) * BLOK]
        if struct.unpack_from("<I", stran, 0)[0] == 0xFFFFFFFF:
            continue
        bitna = stran[32:64]
        i = 0
        while i < 126:
            bs = (bitna[i // 4] >> ((i % 4) * 2)) & 3
            e = stran[64 + i * 32:64 + (i + 1) * 32]
            if bs == 3 or e == b"\xff" * 32:
                i += 1
                continue
            vrsta = vrste.get(e[1])
            kljuc = e[8:24].split(b"\0")[0].decode(errors="replace")
            if kljuc in ("stanje", "resetov", "prevod", "napaka_e"):
                if vrsta == "U8":
                    vred = str(e[24])
                elif vrsta == "STR":
                    n = struct.unpack_from("<H", e, 24)[0]
                    vred = stran[64 + (i + 1) * 32:64 + (i + 1) * 32 + n].split(b"\0")[0].decode(
                        errors="replace")
                else:
                    vred = e[24:32].hex()
                izhod.append(("veljaven" if bs == 2 else "izbrisan", kljuc, vred))
            i += max(1, e[2]) if e[2] not in (0, 0xFF) else 1
    return izhod


STANJA = {"1": "seja teče", "2": "končana", "3": "napaka", "4": "pripravljen (zapisi pobrisani)"}


def obnova(particija, nvs, mapa):
    """Zapiše obnovljene različice in zgodovino NVS v mapo (nova)."""
    os.makedirs(mapa)
    vrste = obnovi_izbrisane(particija)
    vrstice = ["OBNOVA IZBRISANIH ZAPISOV iz kopije flasha",
               "Podatki so iz blokov LittleFS, ki jih program ni več uporabljal (izbrisana datoteka",
               "rez.bin). Vsak zapis je bil zapisan z istim programom kot ob meritvi, zato so vrednosti",
               "nespremenjene; manjka pa podatek, kateri seji in kateremu posnetku RIGOL pripadajo.",
               "Sejo prepoznate po številu zapisov, vrstnem redu algoritmov in primerjavi z izpisi",
               "esp32.txt, če jih imate. Prepis bloka je mogoč samo za datoteke do enega bloka.", ""]
    for n, v in enumerate(sorted(vrste, key=lambda x: (x["oblika"], x["blok"])), start=1):
        ime = f"obnovljeno_{n:02d}_zapis{v['oblika']}B_{len(v['zapisi'])}zapisov.csv"
        _pisi_csv(os.path.join(mapa, ime), v["oblika"], v["zapisi"])
        trajanja = sorted({z[9] if v["oblika"] == "112" else z[5] for z in v["zapisi"]})
        vrstice.append(f"{ime}: blok {v['blok']}, {len(v['zapisi'])} zapisov, oblika "
                       f"{v['oblika']} B, trajanja oken {trajanja[0]}-{trajanja[-1]} ms"
                       + ("  OPOZORILO: blok je poln, datoteka je bila morda daljša"
                          if v["polna"] else ""))
    if not vrste:
        vrstice.append("V particiji ni najti nobenega zapisa.")
    vrstice += ["", "Zgodovina stanja programa v NVS (po vrsti zapisa; izbrisani vnosi so starejši):"]
    for stanje, kljuc, vred in zgodovina_nvs(nvs):
        opis = STANJA.get(vred, "") if kljuc == "stanje" else ""
        vrstice.append(f"  {stanje:8s} {kljuc:8s} = {vred}" + (f"   ({opis})" if opis else ""))
    with open(os.path.join(mapa, "obnovljeno_povzetek.txt"), "x", encoding="utf-8") as f:
        f.write("\n".join(vrstice) + "\n")
    print("\n".join(vrstice))
    return vrste


def main():
    ap = argparse.ArgumentParser(description="Zapisi prejšnjih sej iz kopije flasha ESP32")
    ap.add_argument("kopija", help="kopija celotnega flasha (esptool read-flash 0 0x400000) "
                                   "ali, z --rez-bin, že izvlečena datoteka rez.bin")
    ap.add_argument("--izhod", required=True, help="NOVA mapa za rezultate")
    ap.add_argument("--rez-bin", action="store_true", help="vhod je rez.bin, ne kopija flasha")
    ap.add_argument("--mklittlefs", default="", help="pot do orodja mklittlefs")
    ap.add_argument("--odmik", type=lambda x: int(x, 0), default=ODMIK)
    ap.add_argument("--velikost", type=lambda x: int(x, 0), default=VELIKOST)
    ap.add_argument("--samo-obnova", action="store_true",
                    help="samo obnova izbrisanih zapisov (brez mklittlefs)")
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
    particija = flash[args.odmik:args.odmik + args.velikost]
    # Obnova izbrisanih različic se naredi VEDNO (tudi če rez.bin obstaja): stari
    # program je zapise ob novi seji ali ukazu za brisanje izbrisal, podatki pa
    # ostanejo v blokih, dokler jih LittleFS ne uporabi znova.
    print("\n--- obnova izbrisanih zapisov ---")
    obnova(particija, nvs, os.path.join(args.izhod, "obnovljeno"))
    print("--- konec obnove ---\n")
    if args.samo_obnova:
        return
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
                        "-s", str(args.velikost), slika], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit("mklittlefs ni uspel (particija morda ni LittleFS ali je prazna):\n"
                 + r.stdout + r.stderr)
    datoteke = [os.path.join(k, d) for k, _, dd in os.walk(razpakirano) for d in dd]
    print("Datoteke v datotečnem sistemu ESP32:",
          [(os.path.relpath(d, razpakirano), os.path.getsize(d)) for d in datoteke] or "nobene")
    rez = os.path.join(razpakirano, "rez.bin")
    if not os.path.isfile(rez):
        sys.exit("Trenutno v datotečnem sistemu ni datoteke rez.bin (stari program jo je izbrisal). "
                 "Izbrisane različice, ki so še v flashu, so v mapi 'obnovljeno' (glejte zgoraj).")
    n = pretvori_rez_bin(rez, os.path.join(args.izhod, "stari_zapisi.csv"))
    print(f"Pretvorjenih zapisov: {n} -> {os.path.join(args.izhod, 'stari_zapisi.csv')}")


if __name__ == "__main__":
    main()
