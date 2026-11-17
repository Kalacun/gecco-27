#!/usr/bin/env python3
"""Testi skript W* (en Windows PC za RIGOL in ESP32) brez strojne opreme.

    python -m unittest test_windows -v

Datoteka aktivna_seja.json se pred testom shrani in po njem obnovi; začasne
mape meritev se pobrišejo."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

MAPA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MAPA)
import izvor  # noqa: E402
import naprava  # noqa: E402
import seja  # noqa: E402
import test_zajem as T  # noqa: E402


def zazeni(skripta):
    r = subprocess.run([sys.executable, os.path.join(MAPA, skripta)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=MAPA)
    return r.returncode, r.stdout + r.stderr


class TestWindows(unittest.TestCase):
    def setUp(self):
        self.shranjena = open(seja.POT, "rb").read() if os.path.exists(seja.POT) else None
        if os.path.exists(seja.POT):
            os.remove(seja.POT)
        self.pocisti = []

    def tearDown(self):
        for m in self.pocisti:
            shutil.rmtree(m, ignore_errors=True)
        if self.shranjena is not None:
            with open(seja.POT, "wb") as f:
                f.write(self.shranjena)
        elif os.path.exists(seja.POT):
            os.remove(seja.POT)

    def test_brez_aktivne_seje_skripte_povedo_kaj_storiti(self):
        for skripta in ("W4_snemaj.py", "W5_preberi.py", "W6_analiza.py", "W7_nastavi_T.py"):
            koda, izpis = zazeni(skripta)
            self.assertNotEqual(koda, 0, skripta)
            self.assertIn("W2_pripravi_in_nalozi.py", izpis, skripta)

    def test_ime_seje_in_pripone(self):
        s1 = seja.nova_seja("veriga", 0, "git:x", datum="1999-01-02")
        self.assertEqual(s1["seja"], "1999-01-02_veriga")
        os.makedirs(seja.mapa_seje("1999-01-02_veriga"))
        self.pocisti.append(seja.mapa_seje("1999-01-02_veriga"))
        s2 = seja.nova_seja("veriga", 0, "git:x", datum="1999-01-02")
        self.assertEqual(s2["seja"], "1999-01-02_veriga_2")
        self.assertEqual(seja.aktivna()["seja"], "1999-01-02_veriga_2")
        self.assertEqual(seja.izbrana("drugo_ime"), "drugo_ime")

    def test_W4_zavrne_posneto_sejo_in_tuj_program(self):
        s = seja.nova_seja("veriga", 0, "git:ni_ta_program", datum="1999-01-03")
        koda, izpis = zazeni("W4_snemaj.py")
        self.assertNotEqual(koda, 0)
        self.assertIn("ea_prevod.h se ne ujema", izpis)
        os.makedirs(seja.mapa_seje(s["seja"]))
        self.pocisti.append(seja.mapa_seje(s["seja"]))
        koda, izpis = zazeni("W4_snemaj.py")
        self.assertIn("že posneta", izpis)

    def test_esp32_priklopljen(self):
        try:
            import serial.tools.list_ports  # noqa: F401
        except ImportError:                     # brez pyserial: lažni modul za ta test
            import types
            lp = types.ModuleType("serial.tools.list_ports")
            lp.comports = lambda: []
            tools = types.ModuleType("serial.tools")
            tools.list_ports = lp
            ser = types.ModuleType("serial")
            ser.tools = tools
            mods = {"serial": ser, "serial.tools": tools, "serial.tools.list_ports": lp}
            with mock.patch.dict(sys.modules, mods):
                return self._esp32_priklopljen()
        return self._esp32_priklopljen()

    def _esp32_priklopljen(self):
        class P:
            def __init__(self, d):
                self.device, self.description, self.hwid = d, "USB-SERIAL CH340", "USB VID:PID=1A86"
        with mock.patch("serial.tools.list_ports.comports", return_value=[P("COM5")]):
            self.assertTrue(naprava.esp32_priklopljen("COM5"))
            self.assertFalse(naprava.esp32_priklopljen("COM7"))
        with mock.patch("serial.tools.list_ports.comports", return_value=[]):
            self.assertFalse(naprava.esp32_priklopljen("COM5"))

    def test_W8_brez_potrditve_ne_stori_nic(self):
        koda, izpis = zazeni("W8_pobrisi_zapise.py")
        self.assertEqual(koda, 1)
        self.assertIn("nepovratno", izpis)

    def test_W6_analizira_aktivno_sejo(self):
        s = seja.nova_seja("veriga", 0, "git:x", datum="1999-01-04")
        mapa = seja.mapa_seje(s["seja"])
        os.makedirs(mapa)
        self.pocisti.append(mapa)
        for ime in izvor.izvorne_datoteke():
            shutil.copy(os.path.join(MAPA, ime), os.path.join(mapa, ime))
        skupna, _ = izvor.zgostitev_izvora(mapa, izvor.izvorne_datoteke())
        okna = T.sinteticna_okna(6, okno_s=10.0)
        t, p = T.sinteticna_sled(okna)
        T.zapisi_sled(os.path.join(mapa, "rigol.csv"), t, p)
        with open(os.path.join(mapa, "esp32.txt"), "w", encoding="utf-8") as f:
            f.write(T.sinteticni_esp(okna, prevod=f"git:abcdef012345 src:{skupna[:12]} nacrt:0 red:0",
                                     nacin="FE"))
        koda, izpis = zazeni("W6_analiza.py")
        self.assertEqual(koda, 0, izpis)
        self.assertTrue(any(d.startswith("analiza_") for d in os.listdir(mapa)))
        self.assertIn("stanje = koncan", izpis)

    def test_W2_zavrne_napacno_vrsto(self):
        pot = os.path.join(MAPA, "seja_nastavitve.py")
        izvirnik = open(pot, encoding="utf-8").read()
        try:
            with open(pot, "w", encoding="utf-8") as f:
                f.write(izvirnik.replace('VRSTA = "samopreizkus"', 'VRSTA = "nekaj"'))
            koda, izpis = zazeni("W2_pripravi_in_nalozi.py")
            self.assertNotEqual(koda, 0)
            self.assertIn("ni dovoljena", izpis)
            self.assertFalse(os.path.exists(seja.POT))
        finally:
            with open(pot, "w", encoding="utf-8") as f:
                f.write(izvirnik)


if __name__ == "__main__":
    unittest.main()
