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
NAJDLJE_S = {"samopreizkus": 1800, "veriga": 7200, "kampanja": 86400}


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
