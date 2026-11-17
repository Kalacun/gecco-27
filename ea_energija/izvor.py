#!/usr/bin/env python3
"""Skupno za Mac (priprava programa) in računalnik z RIGOL-om (analiza):
oznaka prevoda iz izvorne kode, generirana datoteka ea_prevod.h in
preverjanje, da se izvorna koda na obeh računalnikih ujema.

Oznaka prevoda (EA_PREVOD_ID), ki jo program izpiše v glavi izpisa in katere
CRC je v vsakem zapisu:

    git:<revizija>[+spremembe] src:<12 znakov SHA-256 izvornih datotek> nacrt:<n> red:<r>

Zgostitev (SHA-256) je čez vsebine datotek IZVORNE (po vrsti), pri čemer se
konci vrstic CRLF štejejo kot LF, da se zgostitev ne spremeni, če git na
Windows pretvori konce vrstic. Datoteka ea_T.h je del izvorne kode, če
obstaja. Računalnik z RIGOL-om ob vsaki seji shrani kopije izvornih datotek
in analiza zgostitev ponovno izračuna: če se razlikuje od tiste v oznaki,
koda na računalniku ni tista, ki je bila prevedena in naložena.
"""
import hashlib
import os
import re
import subprocess
import sys


def pripravi_konzolo():
    """Izpis s šumniki ne sme sesuti skripte v konzoli, ki ne zna UTF-8 (Windows)."""
    for tok in (sys.stdout, sys.stderr):
        try:
            tok.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


pripravi_konzolo()

MAPA = os.path.dirname(os.path.abspath(__file__))
IZVORNE_STALNE = ("ea_energija.ino", "ea_jedro.h", "ea_premiki.h")
IZVORNE_NEOBVEZNE = ("ea_T.h",)

# Nastavitve plošče (meni Tools v Arduino IDE), zapisane v celoti. Program v
# glavo izpisa zapiše FQBN, s katerim je bil preveden (makro ARDUINO_FQBN),
# analiza pa preveri, da so spodnje vrednosti v njem.
PLOSCA = {"CPUFreq": "240", "FlashMode": "qio", "FlashFreq": "80", "FlashSize": "4M",
          "PartitionScheme": "default", "DebugLevel": "none", "PSRAM": "disabled",
          "LoopCore": "1", "EventsCore": "1"}
FQBN = "esp32:esp32:esp32:" + ",".join(f"{k}={v}" for k, v in PLOSCA.items())

# Meni Tools v Arduino IDE 2: vrstica po vrstica, kot jo mora videti uporabnik.
MENI_IDE = (("Board", "ESP32 Dev Module"), ("CPU Frequency", "240MHz (WiFi/BT)"),
            ("Flash Mode", "QIO"), ("Flash Frequency", "80MHz"), ("Flash Size", "4MB (32Mb)"),
            ("Partition Scheme", "Default 4MB with spiffs (1.2MB APP/1.5MB SPIFFS)"),
            ("PSRAM", "Disabled"), ("Core Debug Level", "None"),
            ("Arduino Runs On", "Core 1"), ("Events Run On", "Core 1"),
            ("Erase All Flash Before Sketch Upload", "Disabled"))


def izvorne_datoteke():
    """Imena izvornih datotek, ki so del oznake (ea_T.h samo, če obstaja)."""
    return list(IZVORNE_STALNE) + [i for i in IZVORNE_NEOBVEZNE
                                   if os.path.isfile(os.path.join(MAPA, i))]


def sha256_vsebine(vsebina):
    return hashlib.sha256(vsebina.replace(b"\r\n", b"\n")).hexdigest()


def zgostitev_izvora(mapa=MAPA, imena=None):
    """Vrne (skupna zgostitev, {ime: zgostitev}) za datoteke v mapi. Manjkajoča
    stalna datoteka sproži FileNotFoundError."""
    if imena is None:
        imena = list(IZVORNE_STALNE) + [i for i in IZVORNE_NEOBVEZNE
                                        if os.path.isfile(os.path.join(mapa, i))]
    skupna = hashlib.sha256()
    po_datotekah = {}
    for ime in imena:
        with open(os.path.join(mapa, ime), "rb") as f:
            vsebina = f.read().replace(b"\r\n", b"\n")
        skupna.update(vsebina)
        po_datotekah[ime] = hashlib.sha256(vsebina).hexdigest()
    return skupna.hexdigest(), po_datotekah


def git_stanje():
    """(revizija ali "", ali se izvorne datoteke razlikujejo od revizije ali None).
    Brez nameščenega programa git vrne ("", None)."""
    try:
        r = subprocess.run(["git", "-C", MAPA, "rev-parse", "HEAD"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    except OSError:
        return "", None
    revizija = r.stdout.strip() if r.returncode == 0 else ""
    if not revizija:
        return "", None
    s = subprocess.run(["git", "-C", MAPA, "status", "--porcelain", "--"]
                       + izvorne_datoteke(), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return revizija, bool(s.stdout.strip())


def oznaka_prevoda(nacrt, red):
    """Vrne (oznaka, podrobnosti)."""
    skupna, po_datotekah = zgostitev_izvora()
    revizija, spremenjeno = git_stanje()
    git = (revizija[:12] + ("+spremembe" if spremenjeno else "")) if revizija else "neznano"
    oznaka = f"git:{git} src:{skupna[:12]} nacrt:{nacrt} red:{red}"
    return oznaka, {"git_revizija": revizija or None, "git_spremembe": spremenjeno,
                    "izvorne_datoteke": izvorne_datoteke(), "sha256_izvornih": po_datotekah,
                    "sha256_skupna": skupna}


def ime_mape_prevoda(oznaka):
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", oznaka)


def zapisi_prevod_h(nacrt, red):
    """Ustvari ea_prevod.h (ustvarjena datoteka, v .gitignore): oznaka
    prevoda, načrt in vrstni red. Program ga vključi na začetku."""
    oznaka, podrobnosti = oznaka_prevoda(nacrt, red)
    with open(os.path.join(MAPA, "ea_prevod.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write("// USTVARJENO s pripravi.py ali prevedi.py; ne urejajte, ne dodajajte v git.\n"
                f'#define EA_PREVOD_ID "{oznaka}"\n'
                f"#define NACRT {nacrt}\n#define VRSTNI_RED {red}\n")
    return oznaka, podrobnosti


def preberi_prevod_h():
    """Vrne (oznaka, nacrt, red) iz obstoječe ea_prevod.h ali None."""
    pot = os.path.join(MAPA, "ea_prevod.h")
    if not os.path.isfile(pot):
        return None
    with open(pot, encoding="utf-8") as f:
        b = f.read()
    m = re.search(r'#define EA_PREVOD_ID "([^"]+)"', b)
    n = re.search(r"#define NACRT (\d)", b)
    r = re.search(r"#define VRSTNI_RED (\d)", b)
    if not (m and n and r):
        return None
    return m.group(1), int(n.group(1)), int(r.group(1))


def src_iz_oznake(oznaka):
    """12 znakov zgostitve izvora iz oznake prevoda ali None (npr. 'rocno ...')."""
    m = re.search(r"\bsrc:([0-9a-f]{12})\b", oznaka)
    return m.group(1) if m else None


def razclenitev_fqbn(fqbn):
    """{možnost: vrednost} iz FQBN-ja 'esp32:esp32:esp32:A=1,B=2'."""
    deli = fqbn.split(":", 3)
    if len(deli) < 4:
        return {}
    return dict(kv.split("=", 1) for kv in deli[3].split(",") if "=" in kv)


def napake_plosce(fqbn, zahtevano=None):
    """Seznam neskladnosti med FQBN-jem programa in zahtevanimi nastavitvami."""
    zahtevano = PLOSCA if zahtevano is None else zahtevano
    if not fqbn.startswith("esp32:esp32:esp32"):
        return [f"plošča ni 'ESP32 Dev Module' (FQBN {fqbn})"]
    m = razclenitev_fqbn(fqbn)
    napake = []
    for k, v in zahtevano.items():
        if k not in m:
            napake.append(f"v FQBN manjka nastavitev {k} (zahtevano {v})")
        elif m[k] != v:
            napake.append(f"{k} = {m[k]}, zahtevano {v}")
    return napake
