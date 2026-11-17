#!/usr/bin/env python3
"""Testi skript Mac_*.py in PC_*.py: argumenti ukazne vrstice (za kopiranje ukazov iz
LAB_GUIDE_IDE.md) in varnostni izhodi. Strojne opreme ne potrebujejo; nič ne piše
v podatke meritev (začasne mape se po testu pobrišejo).

    python3 -m unittest test_skripte -v
"""
import os
import re
import shutil
import subprocess
import sys
import unittest

MAPA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MAPA)
import izvor  # noqa: E402
import test_zajem as T  # noqa: E402


def zazeni(skripta, *args):
    r = subprocess.run([sys.executable, os.path.join(MAPA, skripta), *args], capture_output=True,
                       text=True, cwd=MAPA)
    return r.returncode, r.stdout + r.stderr


class TestSkripte(unittest.TestCase):
    def setUp(self):
        self.pocisti = []

    def tearDown(self):
        for m in self.pocisti:
            shutil.rmtree(os.path.join(MAPA, m), ignore_errors=True)

    def test_mac2_izpise_ukaze_z_zgostitvijo_in_imenom_seje(self):
        pot = os.path.join(MAPA, "ea_prevod.h")
        stara = open(pot, "rb").read() if os.path.exists(pot) else None
        try:
            koda, izpis = zazeni("Mac_2_pripravi.py", "--vrsta", "samopreizkus", "--datum",
                                 "2026-11-18")
            self.assertEqual(koda, 0, izpis)
            src = izvor.zgostitev_izvora()[0][:12]
            self.assertIn(f"python PC_2_snemaj.py --vrsta samopreizkus --datum 2026-11-18 "
                          f"--src {src}", izpis)
            self.assertIn("python3 Mac_4_preberi.py --seja 2026-11-18_samopreizkus", izpis)
            self.assertIn("python PC_3_analiza.py --seja 2026-11-18_samopreizkus --prenos", izpis)
            self.assertIn("ESP32 Dev Module", izpis)
            self.assertEqual(izvor.preberi_prevod_h()[1:], (2, 0))
        finally:
            if stara is not None:
                open(pot, "wb").write(stara)
            elif os.path.exists(pot):
                os.remove(pot)

    def test_mac2_zavrne_neznano_vrsto_in_kampanjo_brez_ea_T(self):
        koda, _ = zazeni("Mac_2_pripravi.py", "--vrsta", "neznana")
        self.assertEqual(koda, 2)
        if not os.path.exists(os.path.join(MAPA, "ea_T.h")):
            koda, izpis = zazeni("Mac_2_pripravi.py", "--vrsta", "kampanja")
            self.assertNotEqual(koda, 0)
            self.assertIn("ea_T.h", izpis)

    def test_pc2_zavrne_napacno_zgostitev_in_ne_ustvari_mape(self):
        koda, izpis = zazeni("PC_2_snemaj.py", "--vrsta", "veriga", "--datum", "1999-01-01",
                             "--src", "000000000000")
        self.assertNotEqual(koda, 0)
        self.assertIn("NI ista kot na Macu", izpis)
        self.assertFalse(os.path.exists(os.path.join(MAPA, "meritve", "1999-01-01_veriga")))

    def test_mac5_mac4_pc3_zavrnejo_neobstojece_seje(self):
        for skripta, args in (("Mac_5_nastavi_T.py", ["--seja", "_ni_je"]),
                              ("PC_3_analiza.py", ["--seja", "_ni_je"])):
            koda, izpis = zazeni(skripta, *args)
            self.assertNotEqual(koda, 0, skripta)
            self.assertIn("Ni ", izpis)

    def test_mac4_ne_prepise_obstojecega_esp32_txt(self):
        mapa = os.path.join(MAPA, "prenos", "_test_skripte")
        os.makedirs(mapa)
        self.pocisti.append("prenos")
        with open(os.path.join(mapa, "esp32.txt"), "w") as f:
            f.write("obstaja\n")
        koda, izpis = zazeni("Mac_4_preberi.py", "--seja", "_test_skripte")
        self.assertNotEqual(koda, 0)
        self.assertIn("že obstaja", izpis)
        self.assertEqual(open(os.path.join(mapa, "esp32.txt")).read(), "obstaja\n")

    def test_mac6_brez_potrditve_ne_stori_nic(self):
        koda, izpis = zazeni("Mac_6_pobrisi_zapise.py")
        self.assertEqual(koda, 1)
        self.assertIn("nepovratno", izpis)

    def test_pc3_z_argumenti_prenese_in_analizira_sejo_s_pravimi_kopijami_kode(self):
        sess = os.path.join(MAPA, "meritve", "_test_skripte")
        os.makedirs(sess)
        self.pocisti += ["meritve", "prenos"]
        for ime in izvor.izvorne_datoteke():
            shutil.copy(os.path.join(MAPA, ime), os.path.join(sess, ime))
        skupna, _ = izvor.zgostitev_izvora(sess, izvor.izvorne_datoteke())
        oznaka = f"git:abcdef012345 src:{skupna[:12]} nacrt:0 red:0"
        okna = T.sinteticna_okna(6, okno_s=10.0)
        t, p = T.sinteticna_sled(okna)
        T.zapisi_sled(os.path.join(sess, "rigol.csv"), t, p)
        prenos = os.path.join(MAPA, "prenos", "_test_skripte")
        os.makedirs(prenos)
        with open(os.path.join(prenos, "esp32.txt"), "w") as f:
            f.write(T.sinteticni_esp(okna, prevod=oznaka, nacin="FE"))
        koda, izpis = zazeni("PC_3_analiza.py", "--seja", "_test_skripte", "--prenos", prenos,
                             "--brez-grafov")
        self.assertEqual(koda, 0, izpis)
        self.assertIn("Skopirano: esp32.txt", izpis)
        self.assertTrue(any(d.startswith("analiza_") for d in os.listdir(sess)))
        # druga seja z drugačno kodo na računalniku: analiza se ustavi
        with open(os.path.join(sess, "ea_jedro.h"), "a") as f:
            f.write("// spremenjeno\n")
        koda, izpis = zazeni("PC_3_analiza.py", "--seja", "_test_skripte", "--prenos", prenos,
                             "--brez-grafov")
        self.assertEqual(koda, 2, izpis)
        self.assertIn("ni ista kot na računalniku, ki je", izpis)


if __name__ == "__main__":
    unittest.main()
