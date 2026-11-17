#!/usr/bin/env python3
"""Testi jedra algoritmov na računalniku (isti ea_jedro.h kot na ESP32).

    python3 -m unittest gostitelj/test_gostitelj.py -v     (v mapi ea_energija)

Program se pred testi prevede s prevedi.sh. Rezultati NISO meritve in se
ne smejo uporabiti kot podatki za članek: služijo samo preverjanju kode.
"""
import math
import os
import struct
import subprocess
import sys
import unittest

MAPA = os.path.dirname(os.path.abspath(__file__))
PROGRAM = os.path.join(MAPA, "ea_gostitelj")
M32 = 0xFFFFFFFF


def ukaz(*argumenti):
    return subprocess.run([PROGRAM, *map(str, argumenti)], check=True, capture_output=True,
                          text=True).stdout.split()


# ---- Neodvisna izvedba v Pythonu po referenčni kodi (prng.di.unimi.it/
# ---- xoshiro128plusplus.c) in po pravilu za seme iz ea_jedro.h.
def mesaj32(x):
    x ^= x >> 16
    x = (x * 0x7FEB352D) & M32
    x ^= x >> 15
    x = (x * 0x846CA68B) & M32
    x ^= x >> 16
    return x


def rotl(x, k):
    return ((x << k) | (x >> (32 - k))) & M32


def xoshiro128pp(seme, n):
    s = [mesaj32((seme + (k + 1) * 0x9E3779B9) & M32) for k in range(4)]
    izhod = []
    for _ in range(n):
        izhod.append((rotl((s[0] + s[3]) & M32, 7) + s[0]) & M32)
        t = (s[1] << 9) & M32
        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = rotl(s[3], 11)
    return izhod


def seme_zagona(osnovno, poskus, blok, ogrev):
    return mesaj32(mesaj32(osnovno) ^ ((poskus << 16) | (blok << 8) | ogrev))


def prevedi(*moznosti):
    subprocess.run([os.path.join(MAPA, "prevedi.sh"), *moznosti], check=True,
                   capture_output=True, text=True)


REZ_STOLPCI = ("alg", "funkcija", "D", "blok", "nacin", "proracun", "fe", "gen", "best", "cas_us",
               "np_konec", "seme", "st_tock")
CILJI = (1e1, 1e0, 1e-1, 1e-2, 1e-3, 1e-4)
IMENA = {0: "DE", 1: "jDE", 2: "L-SHADE"}


def pozeni(alg, funkcija, d, blok, nacin, proracun, *moznosti):
    """Požene en zagon. Vrne slovar z REZ, seznamoma cilji [(fe, us)] in
    tocke [(fe, us, best)], sledjo np [(fe, NP, arhiv)] in surovim izpisom."""
    izhod = subprocess.run([PROGRAM, str(alg), str(funkcija), str(d), str(blok), nacin,
                            str(proracun), *moznosti], check=True, capture_output=True,
                           text=True).stdout
    z = {"cilji": [], "tocke": [], "np": [], "izpis": izhod}
    for vr in izhod.splitlines():
        d_ = vr.split()
        if d_[0] == "REZ":
            for k, v in zip(REZ_STOLPCI, d_[1:]):
                z[k] = v if k == "nacin" else float(v) if k == "best" else int(v)
        elif d_[0] == "CILJ":
            z["cilji"].append((int(d_[3]), int(d_[4])))
        elif d_[0] == "TOCKA":
            z["tocke"].append((int(d_[2]), int(d_[3]), float(d_[4])))
        elif d_[0] == "NP":
            z["np"].append((int(d_[1]), int(d_[2]), int(d_[3])))
    return z


def f32(x):
    """Zaokroži na enojno natančnost (kot float na ESP32)."""
    return struct.unpack("f", struct.pack("f", x))[0]


class TestProracun(unittest.TestCase):
    """F1, F2, E2, H4, K4: proračun, cilji in kontrolne točke v skupni funkciji oceni()."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def test_nacin_FE_konca_pri_natanko_FE_max_tudi_sredi_generacije(self):
        # proračuni pod začetno populacijo, na meji generacije in sredi generacije
        for fe_max in (1, 7, 50, 99, 100, 101, 179, 180, 181, 360, 1234, 12345, 100000):
            for alg in (0, 1, 2):
                for funkcija in (0, 1):
                    z = pozeni(alg, funkcija, 10, 1, "fe", fe_max)
                    self.assertEqual(z["fe"], fe_max, (IMENA[alg], funkcija, fe_max))
                    self.assertEqual(z["tocke"][-1][0], fe_max)
                    self.assertTrue(math.isfinite(z["best"]) and z["best"] >= 0.0)

    def test_ponovljivost_deset_zagonov_isto_seme_nacin_FE(self):
        """K4: isti algoritem, problem, seme in FE_max -> FE in rezultat enaka.
        Z navidezno uro je enak celoten izpis, vključno s časi."""
        for alg in (0, 1, 2):
            for funkcija in (0, 1):
                izpisi = {pozeni(alg, funkcija, 10, 4, "fe", 30000, "navidezna")["izpis"]
                          for _ in range(10)}
                self.assertEqual(len(izpisi), 1, (IMENA[alg], funkcija))
                # s pravo uro: enako vse razen časov
                prava = [pozeni(alg, funkcija, 10, 4, "fe", 30000) for _ in range(3)]
                for z in prava:
                    self.assertEqual((z["fe"], z["gen"], z["best"], z["np_konec"]),
                                     (prava[0]["fe"], prava[0]["gen"], prava[0]["best"],
                                      prava[0]["np_konec"]))
                    self.assertEqual([c[0] for c in z["cilji"]], [c[0] for c in prava[0]["cilji"]])
                    self.assertEqual([(t[0], t[2]) for t in z["tocke"]],
                                     [(t[0], t[2]) for t in prava[0]["tocke"]])

    def test_razlicni_bloki_dajo_razlicne_zagone(self):
        a = pozeni(1, 0, 10, 0, "fe", 20000)
        b = pozeni(1, 0, 10, 1, "fe", 20000)
        self.assertNotEqual(a["seme"], b["seme"])
        self.assertNotEqual(a["best"], b["best"])

    def test_kontrolne_tocke_FE_enak_razpored_za_vse_algoritme(self):
        fe_max = 54321
        prav = [fe_max * (k + 1) // 20 for k in range(20)]
        for alg in (0, 1, 2):
            z = pozeni(alg, 0, 10, 2, "fe", fe_max)
            self.assertEqual([t[0] for t in z["tocke"]], prav, IMENA[alg])
            best = [t[2] for t in z["tocke"]]
            self.assertEqual(best, sorted(best, reverse=True))        # ne narašča
            casi = [t[1] for t in z["tocke"]]
            self.assertEqual(casi, sorted(casi))
            self.assertEqual(best[-1], z["best"])

    def test_nacin_CAS_isto_pravilo_ustavitve_za_vse_algoritme(self):
        """Navidezna ura: 10 us na evalvacijo. T = 1000050 us je dosežen pri
        evalvaciji 100005; ura se bere vsakih 16 evalvacij -> konec pri 100016."""
        for alg in (0, 1, 2):
            z = pozeni(alg, 0, 10, 3, "cas", 1000050, "navidezna")
            self.assertEqual(z["fe"], 100016, IMENA[alg])
            self.assertEqual(z["cas_us"], 1000160)
            self.assertEqual(len(z["tocke"]), 20)
            for k, (fe, us, _) in enumerate(z["tocke"]):
                meja = 1000050 * (k + 1) // 20
                self.assertGreaterEqual(us, meja)
                self.assertLess(us - meja, 16 * 10 + 1)       # največ ena perioda ure pozneje
                self.assertEqual(fe % 16, 0)
                self.assertEqual(us, fe * 10)

    def test_nacin_CAS_prava_ura(self):
        for alg in (0, 1, 2):
            z = pozeni(alg, 1, 10, 0, "cas", 300000)
            self.assertGreaterEqual(z["cas_us"], 300000)
            self.assertLess(z["cas_us"], 300000 + 50000)       # daleč pod eno generacijo zamude
            self.assertEqual(len(z["tocke"]), 20)
            self.assertEqual(z["fe"] % 16, 0)

    def test_cilji_prvi_doseg_je_skladen_s_kontrolnimi_tockami(self):
        for alg in (1, 2):
            z = pozeni(alg, 0, 10, 0, "fe", 200000, "navidezna")
            fe_ciljev = [c[0] for c in z["cilji"]]
            dosezeni = [f for f in fe_ciljev if f]
            self.assertEqual(dosezeni, sorted(dosezeni))               # lažji cilj prej
            self.assertEqual(fe_ciljev[:len(dosezeni)], dosezeni)      # brez lukenj v lestvici
            self.assertGreaterEqual(len(dosezeni), 3, IMENA[alg])
            for (fe_c, us_c), prag in zip(z["cilji"], CILJI):
                if not fe_c:
                    self.assertGreater(z["best"], prag)
                    continue
                self.assertEqual(us_c, 1000 - 1000 + fe_c * 10)        # čas ob isti evalvaciji
                for fe_t, _, best_t in z["tocke"]:
                    if fe_t >= fe_c:
                        self.assertLessEqual(best_t, prag)             # po dosegu je best <= prag
                    else:
                        self.assertGreater(best_t, prag)               # pred dosegom še ne

    def test_zacetne_evalvacije_stejejo_in_skupna_nakljucna_stevila(self):
        """Proračun 100 = začetna populacija DE in jDE: oba vidita iste točke
        (isto seme), L-SHADE pa prvih 100 od svojih 180."""
        vrednosti = {alg: pozeni(alg, 0, 10, 6, "fe", 100)["best"] for alg in (0, 1, 2)}
        self.assertEqual(vrednosti[0], vrednosti[1])
        self.assertEqual(vrednosti[0], vrednosti[2])
        self.assertEqual(pozeni(0, 0, 10, 6, "fe", 100)["gen"], 0)


class TestLSHADE(unittest.TestCase):
    """Linearno zmanjševanje populacije in arhiv."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def pricakovan_np(self, delez, np_init):
        return max(4, math.floor(f32(f32((4 - np_init) * f32(delez)) + np_init) + 0.5))

    def preveri(self, z, np_init, delez_od_fe):
        self.assertGreater(len(z["np"]), 50)
        prej = np_init
        for fe, np_, arhiv in z["np"]:
            d = delez_od_fe(fe)
            prav = self.pricakovan_np(d, np_init)
            tocna = (4 - np_init) * d + np_init
            if abs(tocna - math.floor(tocna) - 0.5) > 1e-3:           # ne tik ob meji zaokroževanja
                self.assertEqual(np_, prav, (fe, d))
            self.assertLessEqual(np_, prej)                           # nikoli ne narašča
            self.assertGreaterEqual(np_, 4)
            self.assertLessEqual(arhiv, math.floor(2.6 * np_ + 0.5) + 1)
            prej = np_

    def test_velikost_populacije_sledi_FE_skozi_FE_max(self):
        for d_, np_init in ((10, 180), (20, 360)):
            fe_max = 150000
            z = pozeni(2, 0, d_, 0, "fe", fe_max, "sled")
            self.preveri(z, np_init, lambda fe: f32(f32(fe) * f32(1.0 / fe_max)))
            self.assertLessEqual(z["np_konec"], 5)                    # ob koncu pri NP_min (4 ali 5)

    def test_velikost_populacije_sledi_t_skozi_T(self):
        t_max = 1500000                                               # 150000 evalvacij navidezne ure
        z = pozeni(2, 0, 10, 0, "cas", t_max, "navidezna", "sled")

        def delez(fe):
            # zadnji odčitek ure je pri zadnjem večkratniku 16 evalvacij
            t = (fe // 16) * 16 * 10
            return min(1.0, f32((t >> 6) * f32(64.0 / t_max)))
        self.preveri(z, 180, delez)
        self.assertLessEqual(z["np_konec"], 5)

    def test_zacetna_populacija_je_18D_pri_D_10_in_20(self):
        for d_, np_init in ((10, 180), (20, 360)):
            z = pozeni(2, 1, d_, 0, "fe", np_init)                    # proračun = samo inicializacija
            self.assertEqual((z["fe"], z["gen"], z["np_konec"]), (np_init, 0, np_init))


class TestJedro(unittest.TestCase):
    """Grobi preizkus, da algoritmi konvergirajo (ni primerjava z objavljenimi rezultati)."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def test_jDE_in_LSHADE_dosezeta_1e_2_na_obeh_funkcijah_D10(self):
        for alg in (1, 2):
            for funkcija in (0, 1):
                z = pozeni(alg, funkcija, 10, 0, "fe", 300000)
                self.assertLess(z["best"], 1e-2, (IMENA[alg], funkcija))

    def test_DE_izboljsuje(self):
        z = pozeni(0, 1, 10, 0, "fe", 300000)
        self.assertLess(z["tocke"][-1][2], z["tocke"][0][2] * 1e-3)


class TestTestniFunkciji(unittest.TestCase):
    """E1, E4: premik optimuma in napaka enojne natančnosti blizu optimuma."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def test_tabela_premikov_je_ustvarjena_s_skripto(self):
        skripta = os.path.join(os.path.dirname(MAPA), "generiraj_premike.py")
        r = subprocess.run([sys.executable, skripta, "--preveri"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_optimum_je_v_premiku_stran_od_sredisca_in_mej(self):
        for funkcija, polrazpon in ((0, 5.12), (1, 30.0)):
            for d in (10, 20):
                izpis = [v.split() for v in subprocess.run(
                    [PROGRAM, "premik", str(funkcija), str(d)], check=True, capture_output=True,
                    text=True).stdout.splitlines()]
                f_opt = float(next(v for v in izpis if v[0] == "F_V_OPTIMUMU")[1])
                f_sred = float(next(v for v in izpis if v[0] == "F_V_SREDISCU")[1])
                o = [float(v[2]) for v in izpis if v[0] == "O"]
                self.assertEqual(len(o), d)
                self.assertLess(f_opt, 1e-9, (funkcija, d))      # f(o) = f* = 0 (do zaokrožitve)
                self.assertGreater(f_sred, 100.0, (funkcija, d)) # središče ni optimum
                for x in o:                                      # 20-80 % polovičnega razpona
                    self.assertGreaterEqual(abs(x) / polrazpon, 0.2 - 1e-6)
                    self.assertLessEqual(abs(x) / polrazpon, 0.8 + 1e-6)
                self.assertTrue(any(x > 0 for x in o) and any(x < 0 for x in o))

    def test_neznana_dimenzija_je_zavrnjena(self):
        r = subprocess.run([PROGRAM, "0", "0", "50", "0", "fe", "1000"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ni tabele premika", r.stderr)

    def test_napaka_float_proti_double_blizu_optimuma(self):
        """Meje so izmerjene vrednosti z rezervo (gostiteljska matematična
        knjižnica; na ESP32 se cosf lahko razlikuje za zadnji bit). Rastrigin:
        napaka je absolutna in neodvisna od razdalje do optimuma; Rosenbrock:
        napaka je sorazmerna vrednosti funkcije."""
        def nat(funkcija, d):
            return [(float(v[2]), float(v[3])) for v in (
                vr.split() for vr in subprocess.run(
                    [PROGRAM, "natancnost", str(funkcija), str(d)], check=True,
                    capture_output=True, text=True).stdout.splitlines())]
        self.assertLess(max(n for _, n in nat(0, 10)), 3e-5)     # izmerjeno 1,9e-5
        self.assertLess(max(n for _, n in nat(0, 20)), 8e-5)     # izmerjeno 5,8e-5
        for d in (10, 20):
            for povp, napaka in nat(1, d):
                self.assertLess(napaka / povp, 0.02, (d, povp))  # izmerjeno največ 0,6 %


def red_nakljucni_py(osnovno, poskus, blok, n):
    """Neodvisna izvedba pravila RED_NAKLJUCNI iz ea_jedro.h."""
    p = list(range(n))
    h = mesaj32(mesaj32(osnovno ^ 0xB10C0DE5) ^ ((poskus << 16) | (blok << 8)))
    for i in range(n - 1, 0, -1):
        h = mesaj32((h + 0x9E3779B9) & M32)
        j = h % (i + 1)
        p[i], p[j] = p[j], p[i]
    return p


class TestVrstniRed(unittest.TestCase):
    """H5, BLOCKING: vsak algoritem enkrat na blok, red po dokumentiranem pravilu."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def test_nakljucni_red_enak_neodvisni_izvedbi_in_veljaven(self):
        stevci = {}
        for poskus in range(8):
            for blok in range(0, 256, 3):
                p = [int(v) for v in ukaz("red", "nakljucni", poskus, blok, 3)]
                self.assertEqual(p, red_nakljucni_py(20270101, poskus, blok, 3))
                self.assertEqual(sorted(p), [0, 1, 2])
                stevci[tuple(p)] = stevci.get(tuple(p), 0) + 1
        # 688 blokov: vsaka od 6 permutacij pričakovano 114,7-krat (sigma 9,8)
        self.assertEqual(len(stevci), 6)
        self.assertTrue(all(70 < v < 160 for v in stevci.values()), stevci)

    def test_nakljucni_red_25_blokov_kampanje(self):
        """Realiziran red za 8 celic x 25 blokov: vsak algoritem na vsakem
        položaju približno enako pogosto (ni uravnoteženo natanko)."""
        for poskus in range(8):
            poz = [[0] * 3 for _ in range(3)]
            for blok in range(25):
                for mesto, alg in enumerate(red_nakljucni_py(20270101, poskus, blok, 3)):
                    poz[alg][mesto] += 1
            for alg in range(3):
                self.assertEqual(sum(poz[alg]), 25)
                self.assertTrue(all(2 <= v <= 16 for v in poz[alg]), (poskus, poz))

    def test_uravnotezen_red_vsaka_permutacija_enako_pogosto(self):
        for poskus in (0, 3, 7):
            vrstice = subprocess.run([PROGRAM, "red", "uravnotezen", str(poskus), "30", "3"],
                                     check=True, capture_output=True, text=True).stdout.splitlines()
            self.assertEqual(len(vrstice), 30)
            stevci = {}
            for v in vrstice:
                stevci[v] = stevci.get(v, 0) + 1
            self.assertEqual(sorted(stevci.values()), [5] * 6)
            self.assertNotEqual(vrstice, sorted(vrstice))             # premešano
        a = subprocess.run([PROGRAM, "red", "uravnotezen", "0", "30", "3"], capture_output=True,
                           text=True).stdout
        b = subprocess.run([PROGRAM, "red", "uravnotezen", "1", "30", "3"], capture_output=True,
                           text=True).stdout
        self.assertNotEqual(a, b)                                     # drug poskus, drug red

    def test_uravnotezen_red_zavrne_25_blokov(self):
        r = subprocess.run([PROGRAM, "red", "uravnotezen", "0", "25", "3"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 1)

    def test_permutacije_stirih_algoritmov(self):
        vrstice = subprocess.run([PROGRAM, "red", "uravnotezen", "0", "24", "4"], check=True,
                                 capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(set(vrstice)), 24)                       # vseh 4! permutacij


class TestPrimerjavaZNapravo(unittest.TestCase):
    """K1: orodje za primerjavo naprave z gostiteljem. "Zapisi naprave" so tu
    izhod gostitelja samega (enaki morajo biti do konca) in ena namerno
    spremenjena kopija."""

    @classmethod
    def setUpClass(cls):
        prevedi()
        sys.path.insert(0, MAPA)
        import primerjaj_z_napravo
        cls.orodje = primerjaj_z_napravo

    def zapis(self, i, alg, funkcija, d, blok, fe_max, poskus=0, ogrev=0):
        z = pozeni({"DE": 0, "jDE": 1, "LSHADE": 2}[alg], {"rastrigin": 0, "rosenbrock": 1}[funkcija],
                   d, blok, "fe", fe_max, f"poskus={poskus}", *(["ogrev"] if ogrev else []))
        return {"i": i, "alg": alg, "funkcija": funkcija, "D": d, "zagon": blok, "poskus": poskus,
                "ogrev": ogrev, "nacin": "FE", "proracun": fe_max, "seme": z["seme"],
                "fe": z["fe"], "tocke": [(a, b, float(f"{c:.8e}")) for a, b, c in z["tocke"]]}

    def test_enaki_zapisi_se_ujemajo_do_konca(self):
        zapisi = [self.zapis(0, "DE", "rastrigin", 10, 0, 20000),
                  self.zapis(1, "LSHADE", "rosenbrock", 20, 3, 20000, poskus=5),
                  self.zapis(2, "jDE", "rastrigin", 10, 0, 20000, poskus=2, ogrev=1)]
        v = self.orodje.primerjaj(zapisi)
        self.assertTrue(all(x["seme_enako"] and x["fe_enak"] for x in v))
        self.assertEqual([x["prva_razlika_tocka"] for x in v], [None, None, None])

    def test_seme_je_odvisno_od_poskusa_in_ogrevanja(self):
        a = self.zapis(0, "DE", "rastrigin", 10, 0, 1000)
        b = self.zapis(0, "DE", "rastrigin", 10, 0, 1000, poskus=1)
        c = self.zapis(0, "DE", "rastrigin", 10, 0, 1000, ogrev=1)
        self.assertEqual(len({a["seme"], b["seme"], c["seme"]}), 3)
        self.assertEqual(c["seme"], seme_zagona(20270101, 0, 0, 1))

    def test_razhajanje_in_napacno_seme_sta_odkrita(self):
        z = self.zapis(0, "jDE", "rosenbrock", 10, 1, 20000)
        tocke = list(z["tocke"])
        tocke[7] = (tocke[7][0], tocke[7][1], tocke[7][2] * 1.001)     # razlika pri 8. točki
        v = self.orodje.primerjaj([dict(z, tocke=tocke, seme=z["seme"] + 1)])[0]
        self.assertEqual(v["prva_razlika_tocka"], 8)
        self.assertFalse(v["seme_enako"])

    def test_nacin_CAS_se_ne_primerja(self):
        z = dict(self.zapis(0, "DE", "rastrigin", 10, 0, 1000), nacin="CAS")
        self.assertEqual(self.orodje.primerjaj([z]), [])


class TestGenerator(unittest.TestCase):
    """C1-C4: en generator, dokumentirano pravilo za seme, [0, 1), indeksi v mejah."""

    @classmethod
    def setUpClass(cls):
        prevedi()

    def test_izhodi_enaki_neodvisni_izvedbi(self):
        for seme in (1, 20270101, 0xFFFFFFFF, 0):
            c = [int(v) for v in ukaz("rng", seme, 2000)]
            self.assertEqual(c, xoshiro128pp(seme, 2000), f"seme {seme}")

    def test_pravilo_za_seme_in_enolicnost(self):
        for poskus, blok, ogrev in ((0, 0, 0), (0, 0, 1), (3, 29, 0), (7, 255, 1)):
            self.assertEqual(int(ukaz("seme", poskus, blok, ogrev)[0]),
                             seme_zagona(20270101, poskus, blok, ogrev))
        # vsa semena kampanje (do 8 poskusov x 256 blokov x ogrevanje) so različna
        vsa = {seme_zagona(20270101, p, b, o) for p in range(8) for b in range(256)
               for o in (0, 1)}
        self.assertEqual(len(vsa), 8 * 256 * 2)

    def test_seme_ni_odvisno_od_algoritma_in_je_v_zapisu(self):
        semena = {pozeni(alg, 0, 10, 5, "fe", 500)["seme"] for alg in (0, 1, 2)}
        self.assertEqual(semena, {seme_zagona(20270101, 0, 5, 0)})

    def test_meje_enakomerne_in_indeksov(self):
        najvec, pod_ena, slabih = ukaz("meje")
        self.assertEqual((float(najvec), pod_ena, slabih), (0.99999994, "1", "0"))

    def test_enakomernost_groba(self):
        u = [(v >> 8) / 16777216.0 for v in xoshiro128pp(12345, 200000)]
        self.assertAlmostEqual(sum(u) / len(u), 0.5, delta=0.003)          # sigma = 0,00065
        self.assertTrue(0.0 <= min(u) and max(u) < 1.0)
        kosi = [0] * 10
        for x in u:
            kosi[int(x * 10)] += 1
        self.assertTrue(all(abs(k - 20000) < 600 for k in kosi), kosi)     # sigma = 134


if __name__ == "__main__":
    unittest.main()
