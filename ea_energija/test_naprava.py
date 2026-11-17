#!/usr/bin/env python3
"""Testi pomožnih funkcij za Mac (naprava.py). Strojne opreme ne potrebujejo.

    python3 -m unittest test_naprava -v

Preizkus s pravo sliko programa se preskoči, če še ni prevoda v prevodi/."""
import glob
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import izvor  # noqa: E402
import naprava  # noqa: E402

OZNAKA = "git:0123456789ab src:ba9876543210 nacrt:1 red:0"


def slika(oznake=(OZNAKA,), fqbni=(izvor.FQBN,), seme=1):
    gen = random.Random(seme)
    deli = [bytes(gen.randrange(256) for _ in range(500))]
    for o in list(oznake) + list(fqbni):
        deli.append(b"\x00" + o.encode() + b"\x00" + bytes(gen.randrange(256) for _ in range(200)))
    return b"".join(deli)


def zapis(fun, d, nacin, cas_s, ogrev=0):
    return {"funkcija": fun, "D": d, "nacin": nacin, "cas_us": int(cas_s * 1e6), "ogrev": ogrev}


class TestSlika(unittest.TestCase):
    def test_pravilna_slika(self):
        ok, sp = naprava.preveri_sliko(slika(), OZNAKA)
        self.assertTrue(ok, sp)
        self.assertIn("V redu", sp[-1])

    def test_druga_oznaka(self):
        ok, sp = naprava.preveri_sliko(slika(("git:ffffffffffff src:000000000000 nacrt:1 red:0",)),
                                       OZNAKA)
        self.assertFalse(ok)
        self.assertIn("pričakovane oznake", "\n".join(sp))

    def test_dve_oznaki_sta_napaka(self):
        ok, sp = naprava.preveri_sliko(
            slika((OZNAKA, "git:ffffffffffff src:000000000000 nacrt:0 red:0")), OZNAKA)
        self.assertFalse(ok)

    def test_napacna_plosca_in_manjkajoc_fqbn(self):
        ok, sp = naprava.preveri_sliko(
            slika(fqbni=(izvor.FQBN.replace("CPUFreq=240", "CPUFreq=80"),)), OZNAKA)
        self.assertFalse(ok)
        self.assertIn("CPUFreq = 80", "\n".join(sp))
        ok, sp = naprava.preveri_sliko(slika(fqbni=()), OZNAKA)
        self.assertFalse(ok)

    def test_rocni_prevod_se_prepozna(self):
        oznake, _ = naprava.poisci_v_sliki(slika(("rocno Nov 17 2026 10:13:58",)))
        self.assertEqual(oznake, ["rocno Nov 17 2026 10:13:58"])

    def test_prava_slika_iz_arduino_cli(self):
        """Slika, ki jo je prevedel prevedi.py: oznaka in FQBN morata biti v njej."""
        slike = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "prevodi", "*", "ea_energija.ino.bin")),
                       key=os.path.getmtime)
        if not slike:
            self.skipTest("ni prevoda v prevodi/")
        with open(slike[-1], "rb") as f:
            vsebina = f.read()
        oznake, fqbni = naprava.poisci_v_sliki(vsebina)
        self.assertEqual(len(oznake), 1, oznake)
        self.assertEqual(fqbni, [izvor.FQBN])
        ok, sp = naprava.preveri_sliko(vsebina, oznake[0])
        self.assertTrue(ok, sp)
        # branje samo prvih APP_BRANJE bajtov slike mora zadoščati
        self.assertLess(len(vsebina), naprava.APP_BRANJE)


class TestEsptool(unittest.TestCase):
    def test_argumenti_brez_ponastavitve(self):
        nova = naprava.esptool_argumenti("COM5", 460800, 0, 0x400000, "k.bin", True)
        self.assertEqual(nova[nova.index("--after") + 1], "no-reset")
        self.assertEqual(nova[nova.index("read-flash") + 1:], ["0x0", "0x400000", "k.bin"])
        stara = naprava.esptool_argumenti("COM5", 460800, 0x10000, 0x70000, "a.bin", False)
        self.assertEqual(stara[stara.index("--after") + 1], "no_reset")
        self.assertIn("read_flash", stara)
        self.assertEqual(stara[stara.index("read_flash") + 1:], ["0x10000", "0x70000", "a.bin"])
        self.assertEqual(nova[nova.index("--before") + 1], "no-reset")
        self.assertEqual(stara[stara.index("--before") + 1], "no_reset")
        for a in (nova, stara):
            self.assertNotIn("hard-reset", a)
            self.assertNotIn("hard_reset", a)
            self.assertNotIn("default-reset", a)
            self.assertNotIn("default_reset", a)

    def test_privzeta_hitrost_brez_spremembe(self):
        self.assertEqual(naprava.PRIVZETA_HITROST, 115200)

    def test_razlaga_napak(self):
        self.assertIn("Povezava se je prekinila", naprava.razlozi_napako(
            "A fatal error occurred: No more data to read from the serial port."))
        self.assertIn("ni v nalagalniku", naprava.razlozi_napako(
            "A fatal error occurred: Failed to connect to ESP32: No serial data received."))
        self.assertIn("zasedena", naprava.razlozi_napako("could not open port: Resource busy"))
        self.assertEqual(naprava.razlozi_napako("kaj drugega"), "")

    def test_neuspelo_branje_ne_pusti_delne_datoteke(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            laz = os.path.join(tmp, "esptool")
            with open(laz, "w") as f:
                f.write("#!/bin/sh\n"
                        'for a; do o="$a"; done\n'
                        'printf x > "$o"\n'
                        'echo "A fatal error occurred: No more data to read from the serial port"\n'
                        "exit 2\n")
            os.chmod(laz, 0o755)
            izhod = os.path.join(tmp, "kopija.bin")
            ok, izpis = naprava.preberi_flash("COM9", 0, 16, izhod, esptool=[laz])
            self.assertFalse(ok)
            self.assertFalse(os.path.exists(izhod))
            self.assertFalse(os.path.exists(izhod + ".delno"))
            self.assertIn("Povezava se je prekinila", izpis)

    def test_uspelo_branje_preimenuje_delno_datoteko(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            laz = os.path.join(tmp, "esptool")
            with open(laz, "w") as f:
                f.write("#!/bin/sh\n" 'for a; do o="$a"; done\n' 'printf abc > "$o"\n' "exit 0\n")
            os.chmod(laz, 0o755)
            izhod = os.path.join(tmp, "kopija.bin")
            ok, _ = naprava.preberi_flash("COM9", 0, 3, izhod, esptool=[laz])
            self.assertTrue(ok)
            self.assertEqual(open(izhod, "rb").read(), b"abc")
            self.assertFalse(os.path.exists(izhod + ".delno"))


class TestT(unittest.TestCase):
    REZ = ([zapis("rastrigin", 10, "FE", t) for t in (3.9, 4.2, 4.0)] +
           [zapis("rastrigin", 10, "FE", 99.0, ogrev=1)] +            # ogrevalni se ne šteje
           [zapis("rastrigin", 20, "FE", t) for t in (8.4, 8.6, 8.5)] +
           [zapis("rosenbrock", 10, "FE", t) for t in (0.3, 0.4, 0.35)] +
           [zapis("rosenbrock", 20, "FE", t) for t in (12.4, 12.6, 12.5)] +
           [zapis("rastrigin", 10, "CAS", 5.0)])                       # CAS se ne šteje

    def test_predlog_T(self):
        p = naprava.predlagaj_T(self.REZ)
        self.assertEqual([(f, d, t) for f, d, _, t in p],
                         [("rastrigin", 10, 4000000), ("rastrigin", 20, 9000000),
                          ("rosenbrock", 10, 1000000), ("rosenbrock", 20, 13000000)])

    def test_ea_T_h(self):
        b = naprava.besedilo_ea_T(naprava.predlagaj_T(self.REZ), "ab" * 32, "git:x", "2026-11-17")
        self.assertIn("#define T_RASTRIGIN_D10_US  4000000ULL", b)
        self.assertIn("#define T_ROSENBROCK_D20_US  13000000ULL", b)
        self.assertIn("SHA-256 " + "ab" * 32, b)

    def test_manjkajoca_celica_je_napaka(self):
        rez = [z for z in self.REZ if not (z["funkcija"] == "rosenbrock" and z["D"] == 20)]
        with self.assertRaisesRegex(ValueError, "manjkajo celice"):
            naprava.besedilo_ea_T(naprava.predlagaj_T(rez), "0" * 64, "x", "d")


class LazniVrata:
    """Testni dvojnik serijskih vrat: vrstice programa po scenariju; 'n' sproži odgovor."""

    def __init__(self, izpis_pred_koncem=3, potrdi=True):
        self.vrstice = [b"#POSKUS ...\n"] + [b"REZ,...\n"] * izpis_pred_koncem + \
            ["#KONEC_IZPISA   ('n' dvakrat = pobriši zapise in pripravi novo sejo)\n".encode()]
        self.poslano = []
        self.potrdi = potrdi

    def readline(self):
        return self.vrstice.pop(0) if self.vrstice else b""

    def write(self, b):
        self.poslano.append(b)
        if len(self.poslano) == 1:
            self.vrstice.append("#Za BRISANJE zapisov in pripravo nove seje pošljite 'n' še "
                                "enkrat.\n".encode())
        elif len(self.poslano) == 2 and self.potrdi:
            self.vrstice.append("#Zapisi pobrisani. Seja se začne ob naslednjem vklopu\n".encode())


class TestBrisanje(unittest.TestCase):
    def test_dvakrat_n_po_koncu_izpisa(self):
        ser = LazniVrata()
        self.assertTrue(naprava.izbrisi_zapise(ser, najdlje_s=5, izpis=lambda x: None))
        self.assertEqual(ser.poslano, [b"n", b"n"])

    def test_brez_potrditve_programa_vrne_false(self):
        ser = LazniVrata(potrdi=False)
        self.assertFalse(naprava.izbrisi_zapise(ser, najdlje_s=0.3, izpis=lambda x: None))
        self.assertLessEqual(len(ser.poslano), 2)

    def test_pred_koncem_izpisa_se_nic_ne_poslje(self):
        ser = LazniVrata()
        ser.vrstice = [b"REZ,...\n"] * 3                      # #KONEC_IZPISA nikoli ne pride
        self.assertFalse(naprava.izbrisi_zapise(ser, najdlje_s=0.3, izpis=lambda x: None))
        self.assertEqual(ser.poslano, [])


class TestKoraki(unittest.TestCase):
    """Koraki, ki so v naprava.py (uporabljajo jih Mac_*.py in ukazna vrstica)."""

    def zapisi_chain(self, nacrt="0", stanje="koncan", crc=1, celice=True):
        rez = []
        for fun, d, tr in (("rastrigin", 10, 4.0), ("rastrigin", 20, 8.0),
                           ("rosenbrock", 10, 5.0), ("rosenbrock", 20, 12.5)):
            if not celice and (fun, d) == ("rosenbrock", 20):
                continue
            rez += [dict(zapis(fun, d, "FE", tr), crc_ok=crc) for _ in range(3)]
        return ({"nacrt": nacrt, "stanje": stanje, "zapisov_nacrt": str(len(rez)),
                 "prevod": "git:x src:y nacrt:0 red:0"}, rez)

    def poganjaj(self, zapisi=False, prepisi=False, **kw):
        import tempfile
        from unittest import mock
        import zajem
        izpis = []
        with tempfile.TemporaryDirectory() as tmp:
            esp = os.path.join(tmp, "esp32.txt")
            open(esp, "w").write("x")
            pot_T = os.path.join(tmp, "ea_T.h")
            with mock.patch.object(zajem, "preberi_esp", return_value=self.zapisi_chain(**kw)), \
                    mock.patch.object(izvor, "MAPA", tmp):
                koda = naprava.nastavi_T(esp, zapisi, prepisi, izpis=izpis.append)
            vsebina = open(pot_T).read() if os.path.exists(pot_T) else None
        return koda, "\n".join(izpis), vsebina

    def test_predlog_brez_zapisa(self):
        koda, izpis, vsebina = self.poganjaj()
        self.assertEqual(koda, 0)
        self.assertIsNone(vsebina)
        self.assertIn("T = 13 s", izpis)                 # 12,5 s -> 13 s

    def test_zapis_ea_T_h(self):
        koda, _, vsebina = self.poganjaj(zapisi=True)
        self.assertEqual(koda, 0)
        self.assertIn("#define T_RASTRIGIN_D10_US  4000000ULL", vsebina)
        self.assertIn("#define T_ROSENBROCK_D20_US  13000000ULL", vsebina)

    def test_nedokoncan_ali_pokvarjen_preizkus_in_manjkajoca_celica(self):
        for kw in ({"stanje": "prekinjen"}, {"nacrt": "1"}, {"crc": 0}, {"celice": False}):
            koda, izpis, vsebina = self.poganjaj(zapisi=True, **kw)
            self.assertEqual(koda, 1, (kw, izpis))
            self.assertIsNone(vsebina, kw)

    def test_obstojeci_ea_T_h_se_ne_prepise(self):
        import tempfile
        from unittest import mock
        import zajem
        izpis = []
        with tempfile.TemporaryDirectory() as tmp:
            esp = os.path.join(tmp, "esp32.txt")
            open(esp, "w").write("x")
            open(os.path.join(tmp, "ea_T.h"), "w").write("STARO\n")
            with mock.patch.object(zajem, "preberi_esp", return_value=self.zapisi_chain()), \
                    mock.patch.object(izvor, "MAPA", tmp):
                self.assertEqual(naprava.nastavi_T(esp, True, False, izpis=izpis.append), 1)
                self.assertEqual(open(os.path.join(tmp, "ea_T.h")).read(), "STARO\n")
                self.assertEqual(naprava.nastavi_T(esp, True, True, izpis=izpis.append), 0)
                self.assertNotEqual(open(os.path.join(tmp, "ea_T.h")).read(), "STARO\n")

    def test_kopija_flash_ne_prepise_mape_in_pobrisi_zahteva_potrditev(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "kopija_flash.bin"), "w").write("x")
            izpis = []
            self.assertEqual(naprava.kopija_flash(tmp, "COM9", izpis=izpis.append), 1)
            self.assertIn("že kopija flasha", izpis[0])
        izpis = []
        self.assertEqual(naprava.pobrisi("COM9", False, izpis=izpis.append), 1)
        self.assertIn("nepovratno", izpis[0])

    def test_ukazna_vrstica(self):
        self.assertEqual(naprava.main(["pobrisi"]), 1)                 # brez --potrjujem


if __name__ == "__main__":
    unittest.main()
