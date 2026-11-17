#!/usr/bin/env python3
"""K1: primerja zagone z ESP32 z zagoni ISTEGA jedra (ea_jedro.h) na računalniku.

    python3 gostitelj/primerjaj_z_napravo.py <mapa>/esp32.txt

Za vsak zagon v načinu FE (isti algoritem, funkcija, D, poskus, blok,
oznaka ogrevanja in FE_max, torej isto seme) požene gostiteljski program
in primerja najboljšo vrednost ob 20 kontrolnih točkah.

Kaj pričakovati: seme in število evalvacij se morata ujemati NATANKO.
Vrednosti se ujemajo na začetku in se nato lahko razidejo, ker se
matematični knjižnici (cosf, logf, tanf ...) in združevanje množenja s
seštevanjem med ESP32 in računalnikom razlikujejo v zadnjem bitu, algoritmi
pa so kaotični. Merilo sprejemljivosti je ujemanje zgodnjih točk in
porazdelitev končnih rezultatov, NE enakost do bita čez cel zagon.
Zagoni v načinu CAS se ne primerjajo (število evalvacij je odvisno od hitrosti).
"""
import os
import struct
import subprocess
import sys

MAPA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(MAPA))
import zajem  # noqa: E402

PROGRAM = os.path.join(MAPA, "ea_gostitelj")
ALG = {"DE": 0, "jDE": 1, "LSHADE": 2}
FUN = {"rastrigin": 0, "rosenbrock": 1}


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def gostitelj(z):
    """Požene gostiteljski program za zapis z. Vrne (seme, fe, [best ob točkah])."""
    ukaz = [PROGRAM, str(ALG[z["alg"]]), str(FUN[z["funkcija"]]), str(z["D"]), str(z["zagon"]),
            "fe", str(z["proracun"]), f"poskus={z['poskus']}"] + (["ogrev"] if z["ogrev"] else [])
    izhod = subprocess.run(ukaz, check=True, capture_output=True, text=True).stdout.splitlines()
    rez = next(v.split() for v in izhod if v.startswith("REZ "))
    tocke = [f32(float(v.split()[4])) for v in izhod if v.startswith("TOCKA ")]
    return int(rez[12]), int(rez[7]), tocke


def primerjaj(zapisi):
    """Za zapise v načinu FE vrne seznam slovarjev: ali se ujemata seme in
    število evalvacij, prva kontrolna točka (1..), pri kateri se best
    razlikuje (None = enako do konca), in končni vrednosti."""
    vrstice = []
    for z in zapisi:
        if z["nacin"] != "FE":
            continue
        seme, fe, tocke = gostitelj(z)
        naprava = [f32(t[2]) for t in z["tocke"]]
        prva = next((k + 1 for k, (a, b) in enumerate(zip(naprava, tocke)) if a != b), None)
        vrstice.append({"i": z["i"], "celica": f"{z['funkcija']}_D{z['D']}", "alg": z["alg"],
                        "blok": z["zagon"], "ogrev": z["ogrev"],
                        "seme_enako": seme == z["seme"], "fe_enak": fe == z["fe"],
                        "prva_razlika_tocka": prva, "best_naprava": naprava[-1],
                        "best_gostitelj": tocke[-1]})
    return vrstice


def mediana(x):
    x = sorted(x)
    return x[len(x) // 2] if x else float("nan")


def porocilo(vrstice):
    print(f"Primerjanih zagonov (način FE): {len(vrstice)}")
    slaba_semena = [v["i"] for v in vrstice if not v["seme_enako"]]
    slabi_fe = [v["i"] for v in vrstice if not v["fe_enak"]]
    print(f"  seme enako pravilu na gostitelju: {len(vrstice) - len(slaba_semena)}/{len(vrstice)}"
          + (f"   NAPAKA pri zapisih {slaba_semena}" if slaba_semena else ""))
    print(f"  število evalvacij enako:          {len(vrstice) - len(slabi_fe)}/{len(vrstice)}"
          + (f"   NAPAKA pri zapisih {slabi_fe}" if slabi_fe else ""))
    print("  celica          alg     zagonov  enako do konca  mediana prve razlike (točka od 20)"
          "  mediana best naprava / gostitelj")
    for celica in sorted({v["celica"] for v in vrstice}):
        for alg in ("DE", "jDE", "LSHADE"):
            g = [v for v in vrstice if v["celica"] == celica and v["alg"] == alg]
            if not g:
                continue
            enaki = sum(v["prva_razlika_tocka"] is None for v in g)
            razl = [v["prva_razlika_tocka"] for v in g if v["prva_razlika_tocka"] is not None]
            print(f"  {celica:15s} {alg:7s} {len(g):7d}  {enaki:14d}  "
                  f"{(str(mediana(razl)) if razl else '-'):>10s}"
                  f"{'':24s}{mediana([v['best_naprava'] for v in g]):.3e} / "
                  f"{mediana([v['best_gostitelj'] for v in g]):.3e}")
    return not slaba_semena and not slabi_fe


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    subprocess.run([os.path.join(MAPA, "prevedi.sh")], check=True)
    _, zapisi = zajem.preberi_esp(sys.argv[1])
    sys.exit(0 if porocilo(primerjaj(zapisi)) else 1)
