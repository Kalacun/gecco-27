#!/usr/bin/env python3
"""Ustvari ea_premiki.h: fiksne vektorje premika optimuma za testni funkciji.

    python3 generiraj_premike.py            zapiše ea_premiki.h
    python3 generiraj_premike.py --preveri  preveri, da je ea_premiki.h enak
                                            temu, kar bi skripta zapisala

PRAVILO (določeno pred meritvami, 2026-11-16):
  Za vsako funkcijo (0 = Rastrigin, 1 = Rosenbrock) in dimenzijo D iz
  DIMENZIJE je premik o vektor D komponent. Komponenta j:
      velikost = (0,2 + 0,6 * u1) * R      (20 % do 80 % polovičnega razpona R)
      predznak = + če je u2 < 0,5, sicer -
  u1, u2 sta zaporedna izhoda random.Random(seme).random(), kjer je
      seme = OSNOVNO_SEME * 1000 + funkcija * 100 + D.
  Vrednost se zaokroži na enojno natančnost (float) in tako zapiše.
  R = 5,12 (Rastrigin) oziroma 30 (Rosenbrock); meje iskanja se ne spremenijo.

Optimum premaknjene funkcije je v točki x = o, vrednost v optimumu je 0.
Tako optimum ni v središču območja (kjer bi bil pri nepremaknjeni
funkciji Rastrigin) in ni bližje meji kot 20 % polovičnega razpona.
"""
import os
import random
import struct
import sys

OSNOVNO_SEME = 20270101
DIMENZIJE = (10, 20)
POLRAZPON = {0: 5.12, 1: 30.0}
IME = {0: "Rastrigin", 1: "Rosenbrock"}
POT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ea_premiki.h")


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def premik(funkcija, d):
    gen = random.Random(OSNOVNO_SEME * 1000 + funkcija * 100 + d)
    o = []
    for _ in range(d):
        u1, u2 = gen.random(), gen.random()
        velikost = (0.2 + 0.6 * u1) * POLRAZPON[funkcija]
        o.append(f32(velikost if u2 < 0.5 else -velikost))
    return o


def besedilo():
    v = ["// ====================================================================",
         "//  ea_premiki.h - USTVARJENO z generiraj_premike.py; NE UREJAJTE ROČNO.",
         "//  Fiksni vektorji premika optimuma (v flashu, enaki za vse algoritme",
         "//  in vse zagone). Pravilo in seme sta opisana v generiraj_premike.py.",
         f"//  OSNOVNO_SEME = {OSNOVNO_SEME}; komponente: 20-80 % polovičnega razpona,",
         "//  naključen predznak. Preverjanje: python3 generiraj_premike.py --preveri",
         "// ====================================================================",
         "#pragma once",
         f"#define PREMIK_SEME {OSNOVNO_SEME}u   // seme, iz katerega so ustvarjeni premiki", ""]
    for funkcija in (0, 1):
        for d in DIMENZIJE:
            o = premik(funkcija, d)
            v.append(f"// {IME[funkcija]}, D = {d}")
            v.append(f"static const float PREMIK_F{funkcija}_D{d}[{d}] = {{")
            for k in range(0, d, 5):
                v.append("  " + ", ".join(f"{x:.9g}f" if "." in f"{x:.9g}" or "e" in f"{x:.9g}"
                                           else f"{x:.9g}.0f" for x in o[k:k + 5]) + ",")
            v.append("};")
            v.append("")
    v.append("// Vrne tabelo premika za (funkcija, D) ali NULL, če je ni.")
    v.append("static inline const float *premik_za(int funkcija, int d) {")
    for funkcija in (0, 1):
        for d in DIMENZIJE:
            v.append(f"  if (funkcija == {funkcija} && d == {d}) return PREMIK_F{funkcija}_D{d};")
    v.append("  return NULL;")
    v.append("}")
    return "\n".join(v) + "\n"


if __name__ == "__main__":
    if "--preveri" in sys.argv:
        with open(POT, encoding="utf-8") as f:
            enako = f.read() == besedilo()
        print("ea_premiki.h je enak ustvarjenemu." if enako else
              "NAPAKA: ea_premiki.h se razlikuje od tega, kar ustvari skripta.")
        sys.exit(0 if enako else 1)
    with open(POT, "w", encoding="utf-8") as f:
        f.write(besedilo())
    print(f"Zapisano: {POT}")
