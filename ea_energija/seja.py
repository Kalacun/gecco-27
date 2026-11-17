#!/usr/bin/env python3
"""Aktivna seja za skripte W* (en računalnik za RIGOL in ESP32).

W2_pripravi_in_nalozi.py po uspešnem nalaganju programa zapiše aktivna_seja.json
(ime seje, vrsta, vrstni red, oznaka prevoda). Skripte W3 ... W8 ime seje vzamejo
iz te datoteke, zato ga ni treba nikjer prepisovati. Ime seje je
<datum>_<vrsta>, npr. 2026-11-18_veriga; če taka mapa meritev že obstaja,
dobi pripono _2, _3 ...
"""
import json
import os
import time

import izvor

MAPA = izvor.MAPA
POT = os.path.join(MAPA, "aktivna_seja.json")
NACRT = {"veriga": 0, "kampanja": 1, "samopreizkus": 2}
# Varovalka: snemanje se ustavi najpozneje po tem času, tudi če konca ne zazna.
# Običajno se ustavi samo, 60 s po tem, ko ESP32 konča in globoko zaspi.
NAJDLJE_S = {"samopreizkus": 1800, "veriga": 7200, "kampanja": 86400}

# Protokol iz ea_energija.ino (za izpis napredka med snemanjem).
ZACETNO_SPANJE_S, SPANJE_S, PO_OKNU_S, OGREVANJE, N_ALG = 10, 10, 1, 1, 3
CELICE = [("rastrigin", 10), ("rastrigin", 20), ("rosenbrock", 10), ("rosenbrock", 20)]


def preberi_T(pot=None):
    """T (s) za štiri celice iz ea_T.h ali None, če datoteke ni."""
    import re
    pot = pot or os.path.join(MAPA, "ea_T.h")
    if not os.path.isfile(pot):
        return None
    besedilo = open(pot, encoding="utf-8").read()
    T = {}
    for f, d in CELICE:
        m = re.search(rf"#define\s+T_{f.upper()}_D{d}_US\s+(\d+)", besedilo)
        if not m:
            return None
        T[(f, d)] = int(m.group(1)) / 1e6
    return T


def pricakovano(vrsta, red, T=None):
    """(število merilnih oken, približno trajanje seje v s ali None).
    Kampanja: okno FE traja približno T celice (T je mediana trajanja zagonov
    FE iz preizkusa verige), okno CAS natanko T. Preizkus verige: trajanje
    zagonov FE pred njim ni znano, zato None."""
    if vrsta == "samopreizkus":
        return 0, ZACETNO_SPANJE_S + 4 * (SPANJE_S + 10 + PO_OKNU_S) + \
            3 * (SPANJE_S + 20 + PO_OKNU_S) + SPANJE_S + 5
    blokov = (2 if red == 0 else 6) if vrsta == "veriga" else (25 if red == 0 else 30)
    zagonov_vrstice = N_ALG * (blokov + OGREVANJE)
    if vrsta == "veriga":
        return 5 * zagonov_vrstice, None
    T = T if T is not None else preberi_T()
    if T is None:
        return 8 * zagonov_vrstice, None
    trajanje = ZACETNO_SPANJE_S + sum(2 * zagonov_vrstice * (SPANJE_S + PO_OKNU_S + 0.3 + T[c])
                                      for c in CELICE)
    return 8 * zagonov_vrstice, trajanje


class NapakaSeje(Exception):
    pass


def nastavitve():
    """Prebere seja_nastavitve.py in preveri vrednosti."""
    import importlib
    import seja_nastavitve as n
    n = importlib.reload(n)
    if n.VRSTA not in NACRT:
        raise NapakaSeje(f'VRSTA = "{n.VRSTA}" ni dovoljena; uporabite "samopreizkus", '
                         '"veriga" ali "kampanja" (seja_nastavitve.py).')
    if n.RED not in (0, 1):
        raise NapakaSeje("RED mora biti 0 ali 1 (seja_nastavitve.py).")
    return n


def mapa_seje(ime):
    return os.path.join(MAPA, "meritve", ime)


def nova_seja(vrsta, red, oznaka, datum=None):
    """Določi ime nove seje in ga zapiše v aktivna_seja.json. Vrne slovar."""
    osnova = f"{datum or time.strftime('%Y-%m-%d')}_{vrsta}"
    ime, n = osnova, 1
    while os.path.exists(mapa_seje(ime)):
        n += 1
        ime = f"{osnova}_{n}"
    s = {"seja": ime, "vrsta": vrsta, "red": red, "oznaka_prevoda": oznaka,
         "ustvarjeno": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(POT, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    return s


def aktivna():
    """Aktivna seja ali NapakaSeje, če je ni."""
    if not os.path.isfile(POT):
        raise NapakaSeje("Ni aktivne seje. Najprej poženite W2_pripravi_in_nalozi.py.")
    with open(POT, encoding="utf-8") as f:
        return json.load(f)


def izbrana(ime=""):
    """Ime seje: podano ali aktivno."""
    return ime or aktivna()["seja"]
