#!/usr/bin/env python3
"""Test orodja stari_zapisi.py s SINTETIČNO sliko flasha (ni meritev).

    python3 -m unittest test_stari_zapisi -v

Sliko datotečnega sistema ustvari mklittlefs iz paketa esp32; če orodja ni,
se test z datotečnim sistemom preskoči."""
import csv
import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stari_zapisi  # noqa: E402

SKRIPTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stari_zapisi.py")


def stari_zapis(i):
    return stari_zapisi.STARI.pack(i % 3, i // 3, 0, i % 3, 0, 0, 100, 1000 + i, 10 + i, 10000 + i,
                                   0, 0, 1.5 * (i + 1), *[float(20 - k) for k in range(20)])


class TestStariZapisi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mapa = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def beri(self, pot):
        with open(pot, newline="") as f:
            return list(csv.DictReader(f))

    def test_pretvorba_rez_bin(self):
        rez = os.path.join(self.mapa, "rez.bin")
        with open(rez, "wb") as f:
            f.write(b"".join(stari_zapis(i) for i in range(7)))
        izhod = os.path.join(self.mapa, "izhod")
        subprocess.run([sys.executable, SKRIPTA, rez, "--rez-bin", "--izhod", izhod], check=True,
                       capture_output=True)
        v = self.beri(os.path.join(izhod, "stari_zapisi.csv"))
        self.assertEqual(len(v), 7)
        self.assertEqual((v[4]["alg_ime"], v[4]["zagon"], v[4]["fe"], v[4]["cas_ms"], v[4]["best"]),
                         ("jDE", "1", "1004", "10004", "7.5"))
        self.assertEqual((v[0]["konv_1"], v[0]["konv_20"]), ("20.0", "1.0"))
        # izhodna mapa se nikoli ne prepiše
        r = subprocess.run([sys.executable, SKRIPTA, rez, "--rez-bin", "--izhod", izhod],
                           capture_output=True)
        self.assertNotEqual(r.returncode, 0)

    def test_iz_kopije_celotnega_flasha(self):
        orodje = stari_zapisi.najdi_mklittlefs("")
        if not orodje:
            self.skipTest("mklittlefs ni nameščen")
        vir = os.path.join(self.mapa, "vir")
        os.makedirs(vir)
        with open(os.path.join(vir, "rez.bin"), "wb") as f:
            f.write(b"".join(stari_zapis(i) for i in range(21)))
        slika = os.path.join(self.mapa, "fs.bin")
        subprocess.run([orodje, "-c", vir, "-b", "4096", "-p", "256",
                        "-s", str(stari_zapisi.VELIKOST), slika], check=True, capture_output=True)
        flash = bytearray(b"\xff" * 0x400000)
        with open(slika, "rb") as f:
            flash[stari_zapisi.ODMIK:stari_zapisi.ODMIK + stari_zapisi.VELIKOST] = f.read()
        oznaka = b"Nov 13 2026 10:13:58"
        flash[stari_zapisi.NVS_ODMIK + 64:stari_zapisi.NVS_ODMIK + 64 + len(oznaka)] = oznaka
        kopija = os.path.join(self.mapa, "kopija_flash.bin")
        with open(kopija, "wb") as f:
            f.write(flash)
        izhod = os.path.join(self.mapa, "izhod")
        r = subprocess.run([sys.executable, SKRIPTA, kopija, "--izhod", izhod],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Nov 13 2026 10:13:58", r.stdout)
        self.assertIn("Pretvorjenih zapisov: 21", r.stdout)
        v = self.beri(os.path.join(izhod, "stari_zapisi.csv"))
        self.assertEqual((len(v), v[20]["alg_ime"], v[20]["fe"]), (21, "LSHADE", "1020"))
        with open(kopija, "rb") as f:
            self.assertEqual(f.read(), bytes(flash))             # kopija ni spremenjena

    def test_prekratka_kopija_je_zavrnjena(self):
        kopija = os.path.join(self.mapa, "kratka.bin")
        with open(kopija, "wb") as f:
            f.write(b"\xff" * 0x100000)
        r = subprocess.run([sys.executable, SKRIPTA, kopija, "--izhod",
                            os.path.join(self.mapa, "izhod")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("cela", r.stderr)


if __name__ == "__main__":
    unittest.main()
