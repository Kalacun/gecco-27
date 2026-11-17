#!/usr/bin/env python3
"""Enotski testi za zajem.py (samo standardna knjižnica).

    python3 -m unittest test_zajem -v          (v mapi ea_energija)

VSI PODATKI V TEH TESTIH SO SINTETIČNI. Sledi moči in zapisi ESP32 se
ustvarijo v začasni mapi iz znanih ravni in trajanj, zato je pravilni
rezultat znan vnaprej. Nobena datoteka z meritvami v repozitoriju se ne
bere ali piše; en test prebere ea_energija.ino, da primerja obliko izpisa
programa z bralnikom.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import random
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import izvor  # noqa: E402
import zajem  # noqa: E402

P_NIZKA_W = 0.012      # sintetična raven spanja
P_VISOKA_W = 0.165     # sintetična raven računanja


def nastavitve():
    """Kopija privzetih nastavitev analize (test jo lahko spremeni)."""
    return zajem.preberi_nastavitve(zajem.PRIVZETE_NASTAVITVE)


def sinteticna_okna(n, pocitek_s=5.0, okno_s=10.0, premor_s=1.3, zacetek_s=12.0):
    """n oken [(t0, t1)] s stalnim počitkom, trajanjem in premorom."""
    okna, x = [], zacetek_s
    for _ in range(n):
        x += pocitek_s
        okna.append((x, x + okno_s))
        x += okno_s + premor_s
    return okna


def sinteticna_sled(okna, dt=0.13, tresenje=0.2, sum_w=0.0, konec_po_s=30.0, seme=1,
                    p_nizka=P_NIZKA_W, p_visoka=P_VISOKA_W):
    """Pravokotni val: p_visoka znotraj oken, p_nizka drugje. Časi vzorcev
    so neenakomerni (dt * U(1 - tresenje, 1 + tresenje)). Vrne (t, p)."""
    gen = random.Random(seme)
    t, p, x = [], [], 0.0
    konec = okna[-1][1] + konec_po_s
    while x < konec:
        visoka = any(a <= x < b for a, b in okna)
        t.append(x)
        p.append((p_visoka if visoka else p_nizka) + (gen.gauss(0, sum_w) if sum_w else 0.0))
        x += dt * gen.uniform(1 - tresenje, 1 + tresenje)
    return t, p


def zapisi_sled(pot, t, p, u=3.3, nacini=None, pol_poizvedbe=0.02):
    """Sintetična sled v zapisu 2 (kot ga piše snemanje) in ob njej
    rigol_nacin.csv. u je število ali seznam napetosti po vzorcih; nacini je
    funkcija časa -> niz (privzeto vedno CV), odčitana vsakih 10 s."""
    us = u if isinstance(u, list) else [u] * len(t)
    with open(pot, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_pred_s", "t_po_s", "U_V", "I_A", "P_W"])
        for ti, pi, ui in zip(t, p, us):
            w.writerow([f"{ti - pol_poizvedbe:.4f}", f"{ti + pol_poizvedbe:.4f}", ui,
                        pi / ui, pi])
    with open(os.path.join(os.path.dirname(pot), "rigol_nacin.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_pred_s", "t_po_s", "nacin"])
        x = 0.0
        while x <= t[-1]:
            w.writerow([f"{x:.4f}", f"{x + 0.04:.4f}", nacini(x) if nacini else "CV"])
            x += 10.0


CILJI = (1e1, 1e0, 1e-1, 1e-2, 1e-3, 1e-4)


def sinteticni_esp(okna, algoritmi=("DE", "jDE", "LSHADE"), spanje_s=5, tock=4, fe=100000,
                   cilji_s=None, nacin="CAS", zapisov_nacrt=None, resetov=1, stanje="koncan",
                   funkcija="rastrigin", prevod="SINTETICNO git:0000000 src:000000000000 "
                   "nacrt:0 red:0", fqbn=None):
    """Besedilo esp32.txt (#POSKUS, REZ, CILJ, TOCKA) za dana okna, v zapisu
    programa z lestvico ciljev. Trajanje zagona je trajanje okna.
    cilji_s[i] = seznam časov (s) prvega dosega ciljev zagona i po lestvici
    (None ali krajši seznam = preostali cilji niso doseženi). Evalvacije
    tečejo enakomerno: fe_do_cilja = fe * t / trajanje."""
    n = len(okna)
    v = [f"#POSKUS nacrt=0 red=nakljucni zagonov={n // len(algoritmi)} spanje={spanje_s}s "
         f"po_oknu=1s ogrevanje=0 tock={tock} ciljev={len(CILJI)} perioda_ure_fe=16 seme=1 "
         f"premik_seme=1 DE_NP=100 JDE_NP=100 stanje={stanje} napaka_v=0 resetov={resetov} "
         f"razlog_zacetka=1 razlog_prekinitve={9 if stanje == 'prekinjen' else 0} "
         f"zapisov_nacrt={n if zapisov_nacrt is None else zapisov_nacrt} velikost_zapisa=488 "
         f"datoteka_B={488 * n} prevod_crc=777 fqbn={fqbn or izvor.FQBN} "
         "cilji=" + ";".join(f"{c:.1e}" for c in CILJI) + f" poskusi={funkcija}/10/CAS/10000000 "
         f"prevod={prevod}",
         "#REZ,i,poskus,funkcija,D,alg,zagon,poz,ogrev,nacin,proracun,fe,gen,best,cas_us,"
         "t_zacetek_us,t_konec_us,np_konec,LS_NP_INIT,seme,crc_ok,razlog_reseta,cpu_mhz,"
         "napake_spanja,pocitek_us,prosta_kopica,sklad_min,prevod_crc"]
    cilj, tocka = ["#CILJ,i,k,prag,fe,us"], ["#TOCKA,i,k,fe,us,best"]
    for i, (a, b) in enumerate(okna):
        alg = algoritmi[i % len(algoritmi)]
        blok, poz = divmod(i, len(algoritmi))
        us = round((b - a) * 1e6)
        zac = round(a * 1e6)
        proracun = fe if nacin == "FE" else us
        v.append(f"REZ,{i},0,{funkcija},10,{alg},{blok},{poz},0,{nacin},{proracun},{fe},1000,"
                 f"1.00000000e-03,{us},{zac},{zac + us},100,180,{1000 + blok},1,1,240,0,"
                 f"{spanje_s * 1000000},150000,5000,777")
        casi = list((cilji_s[i] if cilji_s else None) or [])
        for k, prag in enumerate(CILJI):
            if k < len(casi) and casi[k] is not None:
                us_c = round(casi[k] * 1e6)
                cilj.append(f"CILJ,{i},{k},{prag:.1e},{int(fe * us_c / us)},{us_c}")
            else:
                cilj.append(f"CILJ,{i},{k},{prag:.1e},0,0")
        for k in range(tock):
            best = "1.00000000e-03" if k == tock - 1 else f"{10.0 ** (tock - 1 - k):.8e}"
            tocka.append(f"TOCKA,{i},{k},{fe * (k + 1) // tock},{us * (k + 1) // tock},{best}")
    return "\n".join(v + cilj + tocka + ["#KONEC_IZPISA"]) + "\n"


def sha(pot):
    with open(pot, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pozeni_analizo(mapa, nast=None, preveri_izvor=False):
    """Požene analizo nad mapa/rigol.csv in mapa/esp32.txt. Vrne (pot do
    nove podmape z rezultati, izpis)."""
    # Sintetične seje nimajo kopij izvorne kode: preverjanje izvora je privzeto
    # izklopljeno (testira ga TestIzvorInPlosca z lastnimi nastavitvami).
    if nast is None:
        nast = nastavitve()
    nast["veljavnost"]["preveri_izvor"] = preveri_izvor
    pot_nast = os.path.join(mapa, "nastavitve_test.json")
    with open(pot_nast, "w", encoding="utf-8") as f:
        json.dump(nast, f)
    args = argparse.Namespace(rigol_csv=os.path.join(mapa, "rigol.csv"),
                              esp_txt=os.path.join(mapa, "esp32.txt"), grafi=False,
                              podrobno=False, nastavitve=pot_nast)
    pred = set(os.listdir(mapa))
    izpis = io.StringIO()
    with redirect_stdout(izpis):
        zajem.analiza(args)
    nove = [d for d in set(os.listdir(mapa)) - pred if d.startswith("analiza_")]
    return os.path.join(mapa, nove[0]), izpis.getvalue()


def beri_csv(pot):
    with open(pot, newline="") as f:
        return list(csv.DictReader(f))


class Osnova(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mapa = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def pripravi(self, okna, sled=None, u=3.3, nacini=None, **esp):
        t, p = sled if sled else sinteticna_sled(okna)
        zapisi_sled(os.path.join(self.mapa, "rigol.csv"), t, p, u=u, nacini=nacini)
        with open(os.path.join(self.mapa, "esp32.txt"), "w", encoding="utf-8") as f:
            f.write(sinteticni_esp(okna, **esp))


class TestNastavitve(Osnova):
    def test_manjkajoca_nastavitev_ustavi_analizo(self):
        nast = nastavitve()
        del nast["bazna"]["konec_pred_s"]
        pot = os.path.join(self.mapa, "n.json")
        with open(pot, "w") as f:
            json.dump(nast, f)
        with self.assertRaises(zajem.NapakaAnalize):
            zajem.preberi_nastavitve(pot)

    def test_rezultati_v_novi_mapi_s_kopijo_nastavitev_surovi_podatki_nedotaknjeni(self):
        self.pripravi(sinteticna_okna(6))
        surovi = {ime: sha(os.path.join(self.mapa, ime))
                  for ime in ("rigol.csv", "rigol_nacin.csv", "esp32.txt")}
        izhod, _ = pozeni_analizo(self.mapa)
        for ime, zgostitev in surovi.items():
            self.assertEqual(zgostitev, sha(os.path.join(self.mapa, ime)), ime)
        with open(os.path.join(izhod, "analiza_nastavitve.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["statistika"], nastavitve()["statistika"])
        self.assertTrue(os.path.exists(os.path.join(izhod, "energija.csv")))
        self.assertFalse(os.path.exists(os.path.join(self.mapa, "energija.csv")))


class TestOkna(Osnova):
    """J1: histereza, najkrajše trajanje, parjenje po številu in vrstnem redu."""

    def test_cista_sled_najde_vsa_okna_z_robovi_znotraj_pol_periode(self):
        okna = sinteticna_okna(9)
        t, p = sinteticna_sled(okna, dt=0.13)
        najdeno = zajem.najdi_okna(t, p, nastavitve()["okna"])
        self.assertEqual(len(najdeno["okna"]), 9)
        self.assertEqual(najdeno["kratki"], [])
        for (a, b), (a0, b0) in zip(najdeno["okna"], okna):
            self.assertLess(abs(a - a0), 0.13 * 1.2)   # največ ena (raztresena) perioda
            self.assertLess(abs(b - b0), 0.13 * 1.2)

    def test_histereza_sum_okoli_praga_ne_razbije_okna(self):
        okna = sinteticna_okna(3)
        t, p = sinteticna_sled(okna)
        n = nastavitve()["okna"]
        razpon = P_VISOKA_W - P_NIZKA_W
        # sredi 2. okna moč trikrat pade pod prag vstopa (0,6), a ne pod prag izstopa (0,4)
        k0 = next(k for k, ti in enumerate(t) if ti > okna[1][0] + 4.0)
        for k in (k0, k0 + 2, k0 + 4):
            p[k] = P_NIZKA_W + 0.5 * razpon
        self.assertEqual(len(zajem.najdi_okna(t, p, n)["okna"]), 3)
        # brez histereze (oba praga skoraj enaka) isti šum okno razbije: test ima moč
        brez = dict(n, prag_vstop_delez=0.6, prag_izstop_delez=0.5999)
        vsi = zajem.najdi_okna(t, p, brez)
        self.assertGreater(len(vsi["okna"]) + len(vsi["kratki"]), 3)

    def test_kratek_interval_ni_okno_in_je_zapisan_v_okna_csv(self):
        okna = sinteticna_okna(6)
        skok = (3.0, 3.6)                       # npr. zagon ESP32: 0,6 s visoke moči
        t, p = sinteticna_sled([skok] + okna)
        self.pripravi(okna, sled=(t, p))
        izhod, _ = pozeni_analizo(self.mapa)
        vrste = [v["vrsta"] for v in beri_csv(os.path.join(izhod, "okna.csv"))]
        self.assertEqual(vrste.count("okno"), 6)
        self.assertEqual(vrste.count("kratek_interval"), 1)
        self.assertEqual(len(beri_csv(os.path.join(izhod, "energija.csv"))), 6)

    def test_manjkajoce_okno_ustavi_analizo(self):
        okna = sinteticna_okna(6)
        t, p = sinteticna_sled(okna[:2] + okna[3:])        # v sledi manjka 3. okno
        self.pripravi(okna, sled=(t, p))                   # zapisov je 6
        with self.assertRaisesRegex(zajem.NapakaAnalize, "5 merilnih oken.*6"):
            pozeni_analizo(self.mapa)
        self.assertFalse(any(os.path.exists(os.path.join(self.mapa, d, "energija.csv"))
                             for d in os.listdir(self.mapa)))

    def test_odvecno_okno_ustavi_analizo(self):
        okna = sinteticna_okna(6)
        t, p = sinteticna_sled(okna)
        self.pripravi(okna[:5], sled=(t, p))               # zapisov je samo 5
        with self.assertRaisesRegex(zajem.NapakaAnalize, "6 merilnih oken.*5"):
            pozeni_analizo(self.mapa)

    def test_enako_stevilo_a_zamaknjeno_parjenje_odkrije_premor(self):
        """Eno okno manjka, drugje je eno odveč: število se ujema in vsa okna
        so enako dolga (časovni proračun), zato trajanje ne pomaga. Odkrije
        ga premor med okni."""
        okna = sinteticna_okna(6)
        odvec = (okna[4][1] + 2.0, okna[4][1] + 2.0 + 10.0)   # med 5. in 6. oknom
        v_sledi = sorted(okna[:1] + okna[2:] + [odvec])       # brez 2. okna
        v_sledi[-1] = (odvec[1] + 5.0, odvec[1] + 15.0)       # 6. okno za odvečnim
        t, p = sinteticna_sled(v_sledi)
        self.pripravi(okna, sled=(t, p))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "premor pred oknom"):
            pozeni_analizo(self.mapa)

    def test_neujemanje_trajanja_ustavi_analizo(self):
        okna = sinteticna_okna(6)
        v_sledi = list(okna)
        v_sledi[3] = (okna[3][0], okna[3][1] - 2.0)           # 4. okno v sledi 2 s krajše
        t, p = sinteticna_sled(v_sledi)
        self.pripravi(okna, sled=(t, p))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "okno 3 .*trajanje v sledi"):
            pozeni_analizo(self.mapa)

    def test_sled_ki_se_konca_sredi_okna_ustavi_analizo(self):
        okna = sinteticna_okna(3)
        t, p = sinteticna_sled(okna)
        k = next(k for k, ti in enumerate(t) if ti > okna[2][0] + 5.0)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "konča sredi"):
            zajem.najdi_okna(t[:k], p[:k], nastavitve()["okna"])

    def test_nezaporedni_zapisi_ustavijo_analizo(self):
        okna = sinteticna_okna(6)
        self.pripravi(okna, zapisov_nacrt=5)        # število se ujema, a i=2 manjka
        pot = os.path.join(self.mapa, "esp32.txt")
        with open(pot, encoding="utf-8") as f:
            vrstice = [v for v in f if not v.startswith(("REZ,2,", "CILJ,2,", "TOCKA,2,"))]
        with open(pot, "w", encoding="utf-8") as f:
            f.writelines(vrstice)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "niso zaporedni"):
            pozeni_analizo(self.mapa)

    def test_parjenje_po_vrstnem_redu(self):
        okna = sinteticna_okna(6)
        self.pripravi(okna)
        izhod, _ = pozeni_analizo(self.mapa)
        vrstice = beri_csv(os.path.join(izhod, "energija.csv"))
        self.assertEqual([v["alg"] for v in vrstice], ["DE", "jDE", "LSHADE"] * 2)
        for v, (a, _) in zip(vrstice, okna):
            self.assertLess(abs(float(v["t_zacetek_s"]) - a), 0.2)


class TestEnergija(Osnova):
    """J2, J3, J9: pravokotni val znanih ravni in trajanja mora vrniti znano energijo."""

    def test_pravokotni_val_E2_tocno_E1_znotraj_ene_periode(self):
        okna = sinteticna_okna(6, okno_s=10.0)
        dt = 0.13
        self.pripravi(okna, sled=sinteticna_sled(okna, dt=dt))
        izhod, _ = pozeni_analizo(self.mapa)
        E_prava = P_VISOKA_W * 10.0                          # 1,65 J
        for v in beri_csv(os.path.join(izhod, "energija.csv")):
            # E2: notranji vzorci so vsi na visoki ravni, trajanje je z ESP32 -> točno
            self.assertAlmostEqual(float(v["E2_J"]), E_prava, delta=1e-9 * E_prava)
            # E1: vsak rob je negotov za največ pol (raztresene) periode vzorčenja
            self.assertLess(abs(float(v["E1_J"]) - E_prava), P_VISOKA_W * dt * 1.2)
            self.assertEqual(v["E1_E2_zastavica"], "0")
            self.assertAlmostEqual(float(v["P_notranja_mW"]), P_VISOKA_W * 1000, places=6)
            # neto = bruto - bazna x čas
            self.assertAlmostEqual(float(v["E2_neto_J"]), (P_VISOKA_W - P_NIZKA_W) * 10.0,
                                   delta=1e-9)

    def test_pravokotni_val_s_sumom(self):
        okna = sinteticna_okna(6, okno_s=10.0)
        self.pripravi(okna, sled=sinteticna_sled(okna, sum_w=0.002, seme=7))
        izhod, _ = pozeni_analizo(self.mapa)
        for v in beri_csv(os.path.join(izhod, "energija.csv")):
            # ~60 notranjih vzorcev, sigma 2 mW -> napaka povprečja ~0,26 mW (0,16 %)
            self.assertLess(abs(float(v["E2_J"]) - 1.65) / 1.65, 0.008)
            self.assertLess(abs(float(v["E1_J"]) - 1.65) / 1.65, 0.02)

    def test_energija_okna_neenakomerni_casi(self):
        # moč 1 W na [0, 4], 3 W na [4, 10]; vzorci neenakomerno; okno [0, 10], ESP32 10 s
        t = [0.0, 0.5, 1.5, 3.999, 4.0, 4.1, 6.0, 6.2, 9.0, 10.0]
        p = [1.0, 1.0, 1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]
        n = dict(nastavitve()["energija"], rob_E2_s=0.0, min_vzorcev_E2=2)
        E1, E2, P = zajem.energija_okna(t, p, 0.0, 10.0, 10.0, n)
        self.assertAlmostEqual(E1, 1.0 * 4 + 3.0 * 6, delta=0.002)   # 22 J (skok traja 1 ms)
        self.assertAlmostEqual(P, 2.2, delta=0.0002)
        self.assertAlmostEqual(E2, 22.0, delta=0.002)
        # navadno (neuteženo) povprečje vzorcev bi dalo 2,2 samo po naključju; tu je 2,2 W
        # časovno uteženo, neuteženo pa (4*1 + 6*3)/10 = 2,2 -> preverimo z drugo razporeditvijo
        t2 = [0.0, 3.999, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        p2 = [1.0, 1.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]
        _, _, P2 = zajem.energija_okna(t2, p2, 0.0, 10.0, 10.0, n)
        self.assertAlmostEqual(P2, 2.2, delta=0.0002)                # neuteženo bi bilo 2,56
        self.assertGreater(sum(p2) / len(p2), 2.5)

    def test_razlika_E1_E2_nad_toleranco_oznaci_zagon_a_ga_ne_izloci(self):
        okna = sinteticna_okna(6, okno_s=10.0)
        v_sledi = list(okna)
        v_sledi[2] = (okna[2][0], okna[2][1] + 0.4)          # okno v sledi 0,4 s daljše (4 %)
        self.pripravi(okna, sled=sinteticna_sled(v_sledi))
        izhod, izpis = pozeni_analizo(self.mapa)
        vrstice = beri_csv(os.path.join(izhod, "energija.csv"))
        self.assertEqual([v["E1_E2_zastavica"] for v in vrstice], list("001000"))
        self.assertAlmostEqual(float(vrstice[2]["E1_minus_E2_rel"]), 0.04, delta=0.012)
        self.assertEqual(len(vrstice), 6)
        self.assertIn("označenih zagonov: 1", izpis)

    def test_prekratko_okno_za_E2_ustavi_analizo(self):
        okna = sinteticna_okna(6, okno_s=10.0)
        self.pripravi(okna)
        nast = nastavitve()
        nast["energija"]["rob_E2_s"] = 4.95                  # ostane 0,1 s -> ~1 vzorec
        with self.assertRaisesRegex(zajem.NapakaAnalize, "znotraj robov"):
            pozeni_analizo(self.mapa, nast)

    def test_imena_stolpcev_imajo_enote(self):
        okna = sinteticna_okna(6)
        self.pripravi(okna)
        izhod, _ = pozeni_analizo(self.mapa)
        stolpci = beri_csv(os.path.join(izhod, "energija.csv"))[0].keys()
        brez_enote = {"zagon_i", "poskus", "funkcija", "D", "alg", "ponovitev", "poz", "ogrev",
                      "fe", "gen", "best", "np_konec", "veljaven", "napake_sledi", "seme",
                      "nacin", "proracun", "cpu_mhz", "sklad_min",
                      "E1_minus_E2_rel", "E1_E2_zastavica"}
        for c in stolpci:
            if c not in brez_enote:
                self.assertRegex(c, r"(_J|_mWh|_mW|_s|_B|^uJ_.*na_fe|^ms_|^fe_)", c)


class TestERT(Osnova):
    """J6: ERT = skupni strošek vseh zagonov / število uspešnih; neuspešni niso izpuščeni."""

    def test_ert_rocni_izracun(self):
        # 3 uspešni (strošek do cilja 10, 20, 30) in 2 neuspešna (polni strošek 100, 100)
        self.assertAlmostEqual(zajem.ert([10, 20, 30, 100, 100], [1, 1, 1, 0, 0]), 260 / 3)
        self.assertEqual(zajem.ert([100, 100], [0, 0]), float("inf"))
        self.assertEqual(zajem.ert([7], [1]), 7)

    def test_ert_v_analizi_po_ciljih_FE_J_s(self):
        # 6 oken po 10 s, 165 mW, fe = 100000.
        # DE (i=0,3): i=0 doseže cilj 1e1 pri 4 s in 1e0 pri 8 s, i=3 ničesar.
        # jDE (i=1,4): cilj 1e1 pri 2 s in 6 s; 1e0 samo i=1 pri 5 s.
        # LSHADE (i=2,5): ničesar.
        okna = sinteticna_okna(6, okno_s=10.0)
        self.pripravi(okna, cilji_s=[[4.0, 8.0], [2.0, 5.0], None, None, [6.0], None])
        izhod, _ = pozeni_analizo(self.mapa)
        e = {(v["alg"], float(v["cilj"])): v for v in beri_csv(os.path.join(izhod, "ert.csv"))}
        self.assertEqual(len(e), 3 * 6)                          # vsak algoritem x vsak cilj
        de = e[("DE", 10.0)]
        self.assertEqual((de["n_zagonov"], de["n_uspesnih"]), ("2", "1"))
        self.assertAlmostEqual(float(de["ERT_FE"]), 40000 + 100000)
        self.assertAlmostEqual(float(de["ERT_s"]), 4.0 + 10.0)
        self.assertAlmostEqual(float(de["ERT_J"]), P_VISOKA_W * 14.0, places=6)
        self.assertAlmostEqual(float(e[("DE", 1.0)]["ERT_s"]), 8.0 + 10.0)
        self.assertEqual(float(e[("DE", 0.1)]["ERT_FE"]), float("inf"))
        self.assertAlmostEqual(float(e[("jDE", 10.0)]["ERT_FE"]), (20000 + 60000) / 2)
        self.assertAlmostEqual(float(e[("jDE", 10.0)]["ERT_J"]), P_VISOKA_W * 8.0 / 2, places=6)
        self.assertAlmostEqual(float(e[("jDE", 1.0)]["ERT_s"]), (5.0 + 10.0) / 1)
        self.assertEqual(e[("LSHADE", 10.0)]["n_uspesnih"], "0")
        self.assertEqual(float(e[("LSHADE", 10.0)]["ERT_J"]), float("inf"))
        # povprečja samo po uspešnih zagonih ni v povzetku
        metrike = {v["metrika"] for v in beri_csv(os.path.join(izhod, "povzetek.csv"))}
        self.assertFalse({"ms_do_cilja", "s_do_cilja", "E2_do_cilja_J"} & metrike)
        # cilji.csv: ena vrstica na zagon in cilj
        cilji = beri_csv(os.path.join(izhod, "cilji.csv"))
        self.assertEqual(len(cilji), 6 * 6)
        v0 = [c for c in cilji if c["zagon_i"] == "0" and float(c["cilj"]) == 10.0][0]
        self.assertEqual((v0["dosezen"], v0["fe_do_cilja"]), ("1", "40000"))
        self.assertAlmostEqual(float(v0["E2_do_cilja_J"]), P_VISOKA_W * 4.0, places=6)

    def test_testi_po_ciljih_neuspesni_so_neskoncni(self):
        okna = sinteticna_okna(12, okno_s=10.0)
        # DE nikoli, jDE vedno pri 3 s (cilj 1e1)
        cilji_s = [None, [3.0], None] * 4
        self.pripravi(okna, cilji_s=cilji_s)
        izhod, _ = pozeni_analizo(self.mapa)
        t = {(v["metrika"], v["alg1"], v["alg2"]): v
             for v in beri_csv(os.path.join(izhod, "testi.csv"))}
        v = t[("E2_do_cilja_J@10", "DE", "jDE")]
        self.assertEqual(float(v["A12"]), 1.0)                    # DE (neskončno) vedno slabši
        self.assertLess(float(v["p"]), 0.05)
        self.assertEqual(float(t[("E2_do_cilja_J@10", "DE", "LSHADE")]["p"]), 1.0)  # oba nikoli


class TestZapisiESP(Osnova):
    """Strogo branje izpisa ESP32 in skladnost zapisov (H2, F1, popolnost seje)."""

    def prepisi(self, f):
        pot = os.path.join(self.mapa, "esp32.txt")
        with open(pot, encoding="utf-8") as d:
            besedilo = d.read()
        with open(pot, "w", encoding="utf-8") as d:
            d.write(f(besedilo))

    def test_nepopolna_seja_ustavi_analizo(self):
        okna = sinteticna_okna(6)
        self.pripravi(okna, zapisov_nacrt=9)                      # načrtovanih 9, zapisanih 6
        with self.assertRaisesRegex(zajem.NapakaAnalize, "seja ni popolna: 6 zapisov.*9"):
            pozeni_analizo(self.mapa)

    def test_reset_med_sejo_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6), resetov=2)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "znova zagnal .resetov = 2"):
            pozeni_analizo(self.mapa)

    def test_prekinjena_seja_ustavi_analizo_in_pove_razlog(self):
        self.pripravi(sinteticna_okna(6), stanje="prekinjen", zapisov_nacrt=9, resetov=2)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "stanje = prekinjen.*brownout"):
            pozeni_analizo(self.mapa)

    def test_pokvarjen_zapis_crc_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace(",1001,1,1,240,0,", ",1001,0,1,240,0,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "kontrolna vsota"):
            pozeni_analizo(self.mapa)

    def test_napacna_frekvenca_cpu_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace(",1,1,240,0,", ",1,1,160,0,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "frekvenca CPU 160 MHz"):
            pozeni_analizo(self.mapa)

    def test_neuspelo_spanje_in_prekratek_pocitek_ustavita_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace(",240,0,5000000,", ",240,2,5000000,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "2 spanj pred zagonom"):
            pozeni_analizo(self.mapa)
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace(",240,0,5000000,", ",240,0,1200000,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "počitek pred oknom 1.200 s"):
            pozeni_analizo(self.mapa)

    def test_zapis_iz_drugega_prevoda_in_delni_zapis_ustavita_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace(",150000,5000,777", ",150000,5000,778", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "drugega prevoda"):
            pozeni_analizo(self.mapa)
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace("datoteka_B=2928", "datoteka_B=3000", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "72 odvečnih bajtov"):
            pozeni_analizo(self.mapa)

    def test_cilj_pod_natancnostjo_je_oznacen_in_brez_testa(self):
        okna = sinteticna_okna(12, okno_s=10.0)
        vsi = [[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]] * 12                # vsi cilji doseženi
        self.pripravi(okna, cilji_s=vsi)                           # funkcija rastrigin
        izhod, izpis = pozeni_analizo(self.mapa)
        ert = beri_csv(os.path.join(izhod, "ert.csv"))
        oznaceni = {float(v["cilj"]) for v in ert if v["pod_natancnostjo_vrednotenja"] == "1"}
        self.assertEqual(oznaceni, {1e-4})
        metrike = {v["metrika"] for v in beri_csv(os.path.join(izhod, "testi.csv"))}
        self.assertIn("E2_do_cilja_J@0.001", metrike)
        self.assertNotIn("E2_do_cilja_J@0.0001", metrike)
        self.assertIn("pod natančnostjo vrednotenja", izpis)
        # na funkciji Rosenbrock je cilj 1e-4 testiran in neoznačen
        for ime in ("rigol.csv", "rigol_nacin.csv", "esp32.txt"):
            os.remove(os.path.join(self.mapa, ime))
        self.pripravi(okna, cilji_s=vsi, funkcija="rosenbrock")
        izhod2, _ = pozeni_analizo(self.mapa)
        metrike2 = {v["metrika"] for v in beri_csv(os.path.join(izhod2, "testi.csv"))}
        self.assertIn("E2_do_cilja_J@0.0001", metrike2)
        self.assertTrue(all(v["pod_natancnostjo_vrednotenja"] == "0"
                            for v in beri_csv(os.path.join(izhod2, "ert.csv"))))

    def test_nacin_FE_z_napacnim_stevilom_evalvacij_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6), nacin="FE")
        pozeni_analizo(self.mapa)                                 # skladno: gre skozi
        self.prepisi(lambda b: b.replace(",FE,100000,100000,", ",FE,100000,100016,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "fe = 100016 != FE_max = 100000"):
            pozeni_analizo(self.mapa)

    def test_pokvarjena_vrstica_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b.replace("TOCKA,3,1,", "TOCKA,3,x,", 1))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "nerazumljivo"):
            pozeni_analizo(self.mapa)

    def test_manjkajoca_vrstica_cilja_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: "\n".join(v for v in b.split("\n")
                                         if not v.startswith("CILJ,4,5,")))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "zapis i=4 ima vrstice CILJ"):
            pozeni_analizo(self.mapa)

    def test_star_zapis_je_zavrnjen(self):
        self.pripravi(sinteticna_okna(6))
        self.prepisi(lambda b: b + "KONV,0,DE,0,1.0,1.0\n")
        with self.assertRaisesRegex(zajem.NapakaAnalize, "star zapis"):
            pozeni_analizo(self.mapa)

    def test_povzetek_zapisov_predlaga_T_iz_trajanja_zagonov_FE(self):
        # 6 zagonov FE po 10 s, 12 s, 14 s, 10 s, 12 s, 14 s -> mediana 12 s
        okna, x = [], 12.0
        for trajanje in (10.0, 12.0, 14.0, 10.0, 12.0, 14.0):
            x += 5.0
            okna.append((x, x + trajanje))
            x += trajanje + 1.3
        self.pripravi(okna, nacin="FE")
        izpis = io.StringIO()
        with redirect_stdout(izpis):
            predlogi = zajem.povzetek_zapisov(argparse.Namespace(
                esp_txt=os.path.join(self.mapa, "esp32.txt")))
        self.assertEqual(len(predlogi), 1)
        self.assertAlmostEqual(predlogi[0][1], 12.0)
        self.assertIn("#define T_RASTRIGIN_D10_US  12000000ULL", izpis.getvalue())
        self.assertIn("stanje = koncan, zapisov 6 od načrtovanih 6", izpis.getvalue())

    def test_celica_poskusa_vsebuje_nacin_in_proracun(self):
        self.pripravi(sinteticna_okna(6), nacin="FE")
        izhod, _ = pozeni_analizo(self.mapa)
        v = beri_csv(os.path.join(izhod, "energija.csv"))[0]
        self.assertEqual((v["poskus"], v["nacin"], v["proracun"], v["seme"]),
                         ("rastrigin_D10_FE100000", "FE", "100000", "1000"))
        self.assertEqual((v["cpu_mhz"], v["prosta_kopica_B"], v["sklad_min"]),
                         ("240", "150000", "5000"))
        konv = beri_csv(os.path.join(izhod, "konvergenca_energija.csv"))
        self.assertEqual(len(konv), 6 * 4)
        self.assertEqual((konv[3]["fe"], konv[3]["best"]), ("100000", "0.001"))
        self.assertAlmostEqual(float(konv[3]["E2_J"]), P_VISOKA_W * 10.0, places=6)


class TestSamopreizkus(Osnova):
    """K3: analiza znanih obremenitev. Sintetična sled: štiri ravni moči in
    trije pravokotni delovni cikli s periodo 1 s."""

    RAVNI = {1: 0.120, 2: 0.150, 3: 0.165, 4: 0.140}      # W, sintetično

    def zgradi(self, premik_ure_s=3.0, napaka_cikla=1.0, dt=0.02):
        """Vrne (t, p, besedilo esp32.txt). Časi ESP32 tečejo od 0; sled je
        zamaknjena za premik_ure_s. napaka_cikla pomnoži moč v delovnih ciklih
        (1.0 = natanko pričakovano)."""
        samo, odseki, x = [], [], 10.0
        for ob in (1, 2, 3, 4):
            x += 10.0
            samo.append((1, ob, 0, x, x + 10.0, 1000, 0, 0))
            odseki.append((x, x + 10.0, self.RAVNI[ob]))
            x += 11.0
        for d in (25, 50, 75):
            x += 10.0
            a = x
            for c in range(20):
                odseki.append((a + c, a + c + d / 100.0, self.RAVNI[3] * napaka_cikla))
            samo.append((2, d, 1000, a, a + 20.0, 20, int(20 * d * 1e4), int(20 * (100 - d) * 1e4)))
            x = a + 21.0
        casi = [(3, 1, 200000, 100.0, 100.1, 200000, 0, 0),      # 500 ns na branje ure
                (3, 10, 20000, 101.0, 101.4, 20000, 0, 0)]        # 20 us na evalvacijo
        t, p, y = [], [], 0.0
        gen = random.Random(3)
        while y < x + 20.0:
            moc = P_NIZKA_W
            for a, b, raven in odseki:
                if a <= y - premik_ure_s < b:
                    moc = raven
            t.append(y)
            p.append(moc)
            y += dt * gen.uniform(0.8, 1.2)
        glava = sinteticni_esp(sinteticna_okna(0) or [], zapisov_nacrt=0).split("\n")[:2]
        vrstice = glava + ["#CILJ,i,k,prag,fe,us", "#TOCKA,i,k,fe,us,best",
                           "#SAMOPREIZKUS okno=10s perioda=1000ms spanje=10s zapisov=9",
                           "#SAMO,i,vrsta,id,parameter,t_zacetek_us,t_konec_us,stevec,"
                           "aktivno_us,spanje_us,crc_ok"]
        for i, (vrsta, id_, par, a, b, n, akt, sp) in enumerate(samo + casi):
            vrstice.append(f"SAMO,{i},{vrsta},{id_},{par},{round(a * 1e6)},{round(b * 1e6)},{n},"
                           f"{akt},{sp},1")
        return t, p, "\n".join(vrstice + ["#KONEC_IZPISA"]) + "\n"

    def pozeni(self, **kw):
        t, p, esp = self.zgradi(**kw)
        zapisi_sled(os.path.join(self.mapa, "rigol.csv"), t, p, pol_poizvedbe=0.005)
        with open(os.path.join(self.mapa, "esp32.txt"), "w", encoding="utf-8") as f:
            f.write(esp.replace("spanje=5s", "spanje=10s"))
        args = argparse.Namespace(rigol_csv=os.path.join(self.mapa, "rigol.csv"),
                                  esp_txt=os.path.join(self.mapa, "esp32.txt"),
                                  nastavitve=zajem.PRIVZETE_NASTAVITVE)
        izpis = io.StringIO()
        with redirect_stdout(izpis):
            vrstice, casi = zajem.analiza_samopreizkusa(args)
        return vrstice, casi, izpis.getvalue()

    def test_znane_ravni_in_delovni_cikli(self):
        vrstice, casi, izpis = self.pozeni()
        for v in vrstice[:4]:
            self.assertAlmostEqual(v["P_notranja_mW"], self.RAVNI[v["id"]] * 1000, places=6)
            self.assertLess(abs(v["razlika_rel"]), 0.005)
            self.assertLess(abs(v["rob_zacetek_sled_minus_esp_s"]), 0.03)
            self.assertLess(abs(v["rob_konec_sled_minus_esp_s"]), 0.03)
            self.assertEqual(v["oznaceno"], 0)
        for v, d in zip(vrstice[4:], (0.25, 0.50, 0.75)):
            prava = d * self.RAVNI[3] + (1 - d) * P_NIZKA_W
            self.assertAlmostEqual(v["delez_dela_esp"], d)
            self.assertAlmostEqual(v["P_pricakovana_mW"], prava * 1000, places=6)
            self.assertLess(abs(v["P_trapez_mW"] / 1000 - prava) / prava, 0.01)
            self.assertEqual(v["oznaceno"], 0)
        self.assertRegex(izpis, r"zamik ure sled - ESP32 = (2\.9[89]|3\.0[012])")   # pravi: 3,0 s

    def test_napacna_moc_v_ciklu_je_oznacena(self):
        vrstice, _, izpis = self.pozeni(napaka_cikla=1.25)       # 25 % preveč moči med delom
        self.assertTrue(all(v["oznaceno"] == 1 for v in vrstice[4:]))
        self.assertTrue(all(v["oznaceno"] == 0 for v in vrstice[:4]))
        self.assertIn("OZNAČENO", izpis)

    def test_cas_operacij_in_delez_branja_ure(self):
        _, casi, _ = self.pozeni()
        ura = next(c for c in casi if c["id"] == 1)
        ev = next(c for c in casi if c["id"] == 10)
        self.assertAlmostEqual(ura["ns_na_operacijo"], 500.0)
        self.assertAlmostEqual(ev["ns_na_operacijo"], 20000.0)
        # 500 ns vsakih 16 evalvacij po 20000 ns -> 0,156 %
        self.assertAlmostEqual(ev["delez_branja_ure_na_evalvacijo"], 500 / 16 / 20000)

    def test_nedokoncan_samopreizkus_ustavi_analizo(self):
        t, p, esp = self.zgradi()
        zapisi_sled(os.path.join(self.mapa, "rigol.csv"), t, p, pol_poizvedbe=0.005)
        with open(os.path.join(self.mapa, "esp32.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(v for v in esp.split("\n") if not v.startswith("SAMO,6,")))
        args = argparse.Namespace(rigol_csv=os.path.join(self.mapa, "rigol.csv"),
                                  esp_txt=os.path.join(self.mapa, "esp32.txt"),
                                  nastavitve=zajem.PRIVZETE_NASTAVITVE)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "3 delovni cikli, najdeno 4 in 2"):
            zajem.analiza_samopreizkusa(args)


class TestIzvorInPlosca(Osnova):
    """Sledljivost programa: oznaka prevoda, zgostitev kopij izvorne kode, nastavitve plošče."""

    IMENA = ("ea_energija.ino", "ea_jedro.h", "ea_premiki.h")

    def kopije(self, vsebine=None, konci="\n"):
        """Napiše sintetične 'izvorne' datoteke v mapo seje; vrne oznako z njihovo zgostitvijo."""
        for ime in self.IMENA:
            vs = (vsebine or {}).get(ime, f"// {ime}\nvrstica 1\nvrstica 2\n")
            with open(os.path.join(self.mapa, ime), "wb") as f:
                f.write(vs.replace("\n", konci).encode())
        skupna, _ = izvor.zgostitev_izvora(self.mapa, list(self.IMENA))
        return f"git:abcdef012345 src:{skupna[:12]} nacrt:0 red:0"

    def zazeni(self, prevod, nast=None, fqbn=None):
        self.pripravi(sinteticna_okna(6), prevod=prevod, fqbn=fqbn)
        if nast is None:
            nast = nastavitve()
        return pozeni_analizo(self.mapa, nast, preveri_izvor=True)

    def test_ujemajoca_koda_in_plosca_gresta_skozi(self):
        izhod, _ = self.zazeni(self.kopije())
        self.assertEqual(len(beri_csv(os.path.join(izhod, "energija.csv"))), 6)

    def test_koncnice_vrstic_CRLF_ne_spremenijo_zgostitve(self):
        oznaka = self.kopije()
        self.kopije(konci="\r\n")                       # isti Windows kopija z drugimi konci vrstic
        izhod, _ = self.zazeni(oznaka)
        self.assertEqual(len(beri_csv(os.path.join(izhod, "energija.csv"))), 6)

    def test_spremenjena_kopija_kode_ustavi_analizo(self):
        oznaka = self.kopije()
        self.kopije({"ea_jedro.h": "// drugacna koda\n"})
        with self.assertRaisesRegex(zajem.NapakaAnalize, "ni ista kot na računalniku, ki je"):
            self.zazeni(oznaka)

    def test_manjkajoca_kopija_ustavi_analizo(self):
        oznaka = self.kopije()
        os.remove(os.path.join(self.mapa, "ea_premiki.h"))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "ni kopij izvorne kode"):
            self.zazeni(oznaka)

    def test_ea_T_h_je_del_zgostitve_ce_obstaja(self):
        self.kopije()
        with open(os.path.join(self.mapa, "ea_T.h"), "w") as f:
            f.write("#define T_RASTRIGIN_D10_US 4000000ULL\n")
        skupna, _ = izvor.zgostitev_izvora(self.mapa, list(self.IMENA) + ["ea_T.h"])
        izhod, _ = self.zazeni(f"git:abcdef012345 src:{skupna[:12]} nacrt:0 red:0")
        self.assertTrue(os.path.isdir(izhod))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "ni ista kot"):
            self.zazeni(f"git:abcdef012345 src:{izvor.zgostitev_izvora(self.mapa, list(self.IMENA))[0][:12]}"
                        " nacrt:0 red:0")

    def test_rocni_prevod_je_zavrnjen_razen_ce_dovoljeno(self):
        with self.assertRaisesRegex(zajem.NapakaAnalize, "ročno brez pripravi.py"):
            self.zazeni("rocno Nov 17 2026 10:00:00")
        nast = nastavitve()
        nast["veljavnost"]["dovoli_rocni_prevod"] = True
        izhod, _ = self.zazeni("rocno Nov 17 2026 10:00:00", nast)
        self.assertTrue(os.path.isdir(izhod))

    def test_spremembe_git_so_zavrnjene_razen_ce_dovoljeno(self):
        oznaka = self.kopije().replace("git:abcdef012345", "git:abcdef012345+spremembe")
        with self.assertRaisesRegex(zajem.NapakaAnalize, "\\+spremembe"):
            self.zazeni(oznaka)
        nast = nastavitve()
        nast["veljavnost"]["dovoli_spremembe_git"] = True
        izhod, _ = self.zazeni(oznaka, nast)
        self.assertTrue(os.path.isdir(izhod))

    def test_oznaka_in_glava_se_ne_ujemata(self):
        oznaka = self.kopije().replace("nacrt:0 red:0", "nacrt:1 red:0")
        with self.assertRaisesRegex(zajem.NapakaAnalize, "se ne ujemata"):
            self.zazeni(oznaka)

    def test_napacne_nastavitve_plosce_ustavijo_analizo(self):
        oznaka = self.kopije()
        fqbn = izvor.FQBN.replace("CPUFreq=240", "CPUFreq=160").replace("PSRAM=disabled", "PSRAM=enabled")
        with self.assertRaisesRegex(zajem.NapakaAnalize, "(?s)CPUFreq = 160.*PSRAM = enabled"):
            self.zazeni(oznaka, fqbn=fqbn)

    def test_fqbn_iz_arduino_ide_z_dodatnimi_moznostmi_je_sprejet(self):
        oznaka = self.kopije()
        fqbn = izvor.FQBN + ",JTAGAdapter=default,UploadSpeed=921600,EraseFlash=none,ZigbeeMode=default"
        izhod, _ = self.zazeni(oznaka, fqbn=fqbn)
        self.assertTrue(os.path.isdir(izhod))

    def test_izvor_h_pomozne_funkcije(self):
        self.assertEqual(izvor.src_iz_oznake("git:aaaaaaaaaaaa src:0123456789ab nacrt:0 red:1"),
                         "0123456789ab")
        self.assertIsNone(izvor.src_iz_oznake("rocno Nov 1 2026"))
        self.assertEqual(izvor.razclenitev_fqbn("esp32:esp32:esp32:A=1,B=x")["B"], "x")
        self.assertEqual(izvor.napake_plosce(izvor.FQBN), [])
        self.assertTrue(izvor.napake_plosce("esp32:esp32:esp32s3:CPUFreq=240"))


class TestOblikaIzpisaPrograma(unittest.TestCase):
    """Bralnik in program morata govoriti isti jezik: stolpci, ki jih program
    izpiše (ea_energija.ino, izpisi_vse in izpisi_glavo), so tisti, ki jih
    bralnik zahteva. Programa tu ne poganjamo; primerjamo nize v izvorni kodi."""

    @classmethod
    def setUpClass(cls):
        pot = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ea_energija.ino")
        with open(pot, encoding="utf-8") as f:
            cls.ino = f.read()

    def niz(self, zacetek):
        """Združi sosednje nizovne konstante C, ki se začnejo z danim besedilom."""
        import re
        m = re.search(r'"' + re.escape(zacetek) + r'[^;]*?\)', self.ino, re.S)
        self.assertIsNotNone(m, zacetek)
        return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(0)))

    def test_stolpci_REZ(self):
        glava = self.niz("#REZ,").split(",")
        self.assertEqual(glava[0], "#REZ")
        for c in zajem.OBVEZNI_REZ:
            self.assertIn(c, glava)
        oblika = self.niz("REZ,%d").replace("\\n", "")
        self.assertEqual(len(oblika.split(",")), len(glava))     # toliko polj kot stolpcev

    def test_vrstica_SAMO(self):
        self.assertEqual(self.niz("#SAMO,").split(",")[1:], list(zajem.SAMO_STOLPCI))
        self.assertEqual(len(self.niz("SAMO,%d").split(",")), len(zajem.SAMO_STOLPCI) + 1)

    def test_vrstice_CILJ_in_TOCKA(self):
        self.assertEqual(self.niz("#CILJ,"), "#CILJ,i,k,prag,fe,us")
        self.assertEqual(self.niz("#TOCKA,"), "#TOCKA,i,k,fe,us,best")
        self.assertEqual(len(self.niz("CILJ,%d").split(",")), 6)
        self.assertEqual(len(self.niz("TOCKA,%d").split(",")), 6)

    def test_glava_POSKUS(self):
        glava = self.niz("\\n#POSKUS") + " cilji= poskusi= prevod="
        for k in zajem.OBVEZNA_GLAVA:
            self.assertIn(f"{k}=", glava, k)
        # prevod je zadnji (vsebuje presledke), kot pričakuje bralnik
        self.assertIn('o.printf(" prevod=%s\\n", OZNAKA_PREVODA);', self.ino)


class TestStatistika(unittest.TestCase):
    """J6: vrednosti, izračunane na roko (Phi iz tabel standardne normalne porazdelitve)."""

    def test_mann_whitney_brez_vezi(self):
        # U = 0, mu = 4,5, sigma^2 = 3*3*7/12 = 5,25, z = (4,5 - 0,5)/2,2913 = 1,7457
        # p = 2 (1 - Phi(1,7457)) = 2 (1 - 0,95957) = 0,0809
        self.assertAlmostEqual(zajem.mann_whitney([1, 2, 3], [4, 5, 6]), 0.0809, delta=5e-4)

    def test_mann_whitney_z_vezmi(self):
        # rangi 1,5 1,5 3,5 | 3,5 5,5 5,5; U = 0,5; popravek vezi 3*(2^3-2) = 18
        # sigma^2 = 9/12 * (7 - 18/30) = 4,8; z = (4 - 0,5)/2,1909 = 1,5975; p = 0,1102
        self.assertAlmostEqual(zajem.mann_whitney([1, 1, 2], [2, 3, 3]), 0.1102, delta=5e-4)

    def test_mann_whitney_simetrija_in_neskoncne_vrednosti(self):
        a, b = [1.0, 2.0, 3.0, float("inf")], [4.0, 5.0, float("inf"), float("inf")]
        self.assertAlmostEqual(zajem.mann_whitney(a, b), zajem.mann_whitney(b, a))
        self.assertLess(zajem.mann_whitney(a, b), 1.0)
        self.assertEqual(zajem.mann_whitney([2, 2, 2], [2, 2, 2]), 1.0)

    def test_holm(self):
        # urejeno: 0,01*3 = 0,03; 0,03*2 = 0,06; 0,04*1 = 0,04 -> monotono 0,06
        for dobljeno, prav in zip(zajem.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]):
            self.assertAlmostEqual(dobljeno, prav)
        # NaN ne šteje v velikost družine
        h = zajem.holm([0.01, float("nan"), 0.03])
        self.assertAlmostEqual(h[0], 0.02)
        self.assertAlmostEqual(h[2], 0.03)

    def test_a12_smer(self):
        # pari a > b: (3,2); enaki: (2,2), (3,3) -> (1 + 2*0,5)/9
        self.assertAlmostEqual(zajem.a12([1, 2, 3], [2, 3, 4]), 2 / 9)
        self.assertEqual(zajem.a12([1, 2], [3, 4]), 0.0)     # prvi ima manjše vrednosti
        self.assertEqual(zajem.a12([3, 4], [1, 2]), 1.0)

    def test_hi2_rep_tabelirane_vrednosti(self):
        # kritične vrednosti hi-kvadrat pri 0,05: 3,841 (1), 5,991 (2), 7,815 (3), 9,488 (4)
        for sp, x in ((1, 3.841), (2, 5.991), (3, 7.815), (4, 9.488)):
            self.assertAlmostEqual(zajem.hi2_rep(x, sp), 0.05, delta=2e-4)

    def test_kruskal_wallis(self):
        # rangi 1..9 po skupinah: 6, 15, 24 -> H = 12/90 * (36+225+576)/3 - 30 = 7,2
        # p = exp(-3,6) = 0,02732
        p = zajem.kruskal_wallis([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        self.assertAlmostEqual(p, 0.02732, delta=1e-5)


class TestIzlocitve(Osnova):
    """J7: vsaka izločitev je zapisana z razlogom; pravila ne gledajo izida."""

    def test_brez_izlocitev_je_datoteka_prazna_a_obstaja(self):
        self.pripravi(sinteticna_okna(6))
        izhod, _ = pozeni_analizo(self.mapa)
        self.assertEqual(beri_csv(os.path.join(izhod, "izlocitve.csv")), [])
        self.assertTrue(all(v["veljaven"] == "1"
                            for v in beri_csv(os.path.join(izhod, "energija.csv"))))

    def test_ogrevalni_zagoni_so_izloceni_in_zapisani(self):
        okna = sinteticna_okna(6)
        self.pripravi(okna)
        pot = os.path.join(self.mapa, "esp32.txt")
        with open(pot, encoding="utf-8") as f:
            vrstice = f.read().splitlines()
        for k, v in enumerate(vrstice):                 # zapisa i=0 in i=1 -> ogrev=1
            d = v.split(",")
            if d[0] == "REZ" and d[1] in ("0", "1"):
                d[8] = "1"
                vrstice[k] = ",".join(d)
        with open(pot, "w", encoding="utf-8") as f:
            f.write("\n".join(vrstice) + "\n")
        izhod, _ = pozeni_analizo(self.mapa)
        izl = beri_csv(os.path.join(izhod, "izlocitve.csv"))
        self.assertEqual([(v["zagon_i"], v["razlog"]) for v in izl],
                         [("0", "ogrevalni_zagon"), ("1", "ogrevalni_zagon")])
        veljavni = [v["veljaven"] for v in beri_csv(os.path.join(izhod, "energija.csv"))]
        self.assertEqual(veljavni, list("001111"))

    def test_pravila_ne_gledajo_izida(self):
        osnova = {"ogrev": 0, "best": 1e30, "cilj_dosezen": 0, "fe": 1}
        self.assertEqual(zajem.razlogi_izlocitve(osnova), [])
        self.assertEqual(zajem.razlogi_izlocitve(dict(osnova, best=0.0, cilj_dosezen=1)), [])


class TestVeljavnostSledi(Osnova):
    """J9: vrzel v oknu in način, ki ni CV, sprožita predvideno napako (ali, če je tako
    nastavljeno vnaprej, izločitev z zapisanim razlogom)."""

    def sled_z_vrzeljo(self, okna, od, do):
        t, p = sinteticna_sled(okna)
        ohrani = [k for k, ti in enumerate(t) if not od <= ti < do]
        return [t[k] for k in ohrani], [p[k] for k in ohrani]

    def test_vrzel_v_oknu_ustavi_analizo(self):
        okna = sinteticna_okna(6)
        a = okna[2][0]
        self.pripravi(okna, sled=self.sled_z_vrzeljo(okna, a + 3.0, a + 6.0))   # 3 s brez vzorcev
        with self.assertRaisesRegex(zajem.NapakaAnalize, r"okno 2 \(zapis i=2, LSHADE\): vrzel"):
            pozeni_analizo(self.mapa)

    def test_vrzel_ni_interpolirana_v_energijo(self):
        """Z 'izloci' je zagon z vrzeljo izločen in zapisan; ostali so veljavni."""
        okna = sinteticna_okna(6)
        a = okna[2][0]
        self.pripravi(okna, sled=self.sled_z_vrzeljo(okna, a + 3.0, a + 6.0))
        nast = nastavitve()
        nast["veljavnost"]["ob_vrzeli"] = "izloci"
        izhod, _ = pozeni_analizo(self.mapa, nast)
        izl = beri_csv(os.path.join(izhod, "izlocitve.csv"))
        self.assertEqual([(v["zagon_i"], v["razlog"]) for v in izl], [("2", "vrzel_v_oknu")])
        veljavni = [v["veljaven"] for v in beri_csv(os.path.join(izhod, "energija.csv"))]
        self.assertEqual(veljavni, list("110111"))

    def test_vrzel_med_okni_ne_moti(self):
        okna = sinteticna_okna(6)
        b = okna[2][1]
        self.pripravi(okna, sled=self.sled_z_vrzeljo(okna, b + 2.0, b + 4.0))   # med počitkom
        izhod, _ = pozeni_analizo(self.mapa)
        self.assertEqual(len(beri_csv(os.path.join(izhod, "energija.csv"))), 6)

    def test_nacin_CC_v_oknu_ustavi_analizo(self):
        okna = sinteticna_okna(9)
        a, b = okna[4]
        self.pripravi(okna, nacini=lambda x: "CC" if a - 10 < x < b + 10 else "CV")
        with self.assertRaisesRegex(zajem.NapakaAnalize, "okno 4 .*ni_CV_v_oknu"):
            pozeni_analizo(self.mapa)

    def test_padec_napetosti_v_oknu_ustavi_analizo(self):
        """Tokovna omejitev se pokaže kot padec napetosti, tudi če je med dvema
        odčitkoma načina (ti so vsakih 10 s)."""
        okna = sinteticna_okna(6)
        t, p = sinteticna_sled(okna)
        a = okna[1][0]
        u = [2.9 if a + 4.0 <= ti < a + 4.5 else 3.3 for ti in t]
        self.pripravi(okna, sled=(t, p), u=u)
        with self.assertRaisesRegex(zajem.NapakaAnalize, "okno 1 .*ni_CV_v_oknu"):
            pozeni_analizo(self.mapa)

    def test_CC_z_izloci_je_zapisan_kot_izlocitev(self):
        okna = sinteticna_okna(6)
        t, p = sinteticna_sled(okna)
        a = okna[1][0]
        u = [2.9 if a + 4.0 <= ti < a + 4.5 else 3.3 for ti in t]
        self.pripravi(okna, sled=(t, p), u=u)
        nast = nastavitve()
        nast["veljavnost"]["ob_ne_CV"] = "izloci"
        izhod, _ = pozeni_analizo(self.mapa, nast)
        izl = beri_csv(os.path.join(izhod, "izlocitve.csv"))
        self.assertEqual([(v["zagon_i"], v["razlog"]) for v in izl], [("1", "ni_CV_v_oknu")])

    def test_manjkajoc_zapis_nacina_ustavi_analizo(self):
        self.pripravi(sinteticna_okna(6))
        os.remove(os.path.join(self.mapa, "rigol_nacin.csv"))
        with self.assertRaisesRegex(zajem.NapakaAnalize, "rigol_nacin.csv"):
            pozeni_analizo(self.mapa)


class LazniRigol:
    """Testni dvojnik napajalnika (NI meritev): odgovarja na ukaze SCPI iz
    DP800 Programming Guide in premika simulirano uro za 0,1 s na poizvedbo.
    Tok je 50 mA v intervalu `visok`, sicer 3 mA. Intervali visok, izpad in
    cc so v sekundah od vklopa izhoda (:OUTP CH1,ON)."""

    def __init__(self, visok=(5.0, 15.0), napaka_po_ukazu=None, najvec_tok=None,
                 izpad=None, cc=None, cas_poizvedbe=0.1):
        self.t, self.t_vklopa = 0.0, None
        self.visok, self.izpad, self.cc = visok, izpad, cc
        self.napaka_po_ukazu, self.najvec_tok = napaka_po_ukazu, najvec_tok
        self.cas_poizvedbe = cas_poizvedbe
        self.dnevnik = []                    # (t, "write"/"query", ukaz)
        self.vrsta_napak = []
        self.st = {"U": "0.000", "I": "1.0000", "OVP": "33.000", "OVPs": "OFF",
                   "OCP": "1.1000", "OCPs": "OFF", "izhod": "OFF"}

    def ura(self):
        return self.t

    def v(self, interval):
        """Ali je čas od vklopa izhoda v danem intervalu."""
        if interval is None or self.t_vklopa is None:
            return False
        return interval[0] <= self.t - self.t_vklopa < interval[1]

    def pocakaj(self, s):
        self.t += s

    def write(self, ukaz):
        self.dnevnik.append((self.t, "write", ukaz))
        if self.napaka_po_ukazu and ukaz.startswith(self.napaka_po_ukazu):
            self.vrsta_napak.append('-222,"Data out of range"')
            return
        glava, _, arg = ukaz.partition(" ")
        deli = arg.split(",")
        if glava == ":APPL":
            self.st["U"] = f"{float(deli[1]):.3f}"
            tok = float(deli[2])
            self.st["I"] = f"{min(tok, self.najvec_tok) if self.najvec_tok else tok:.4f}"
        elif glava == ":OUTP:OVP:VAL":
            self.st["OVP"] = f"{float(deli[1]):.3f}"
        elif glava == ":OUTP:OCP:VAL":
            self.st["OCP"] = f"{float(deli[1]):.4f}"
        elif glava == ":OUTP:OVP":
            self.st["OVPs"] = deli[1]
        elif glava == ":OUTP:OCP":
            self.st["OCPs"] = deli[1]
        elif glava == ":OUTP":
            self.st["izhod"] = deli[1]
            if deli[1] == "ON":
                self.t_vklopa = self.t

    def query(self, ukaz):
        self.t += self.cas_poizvedbe
        self.dnevnik.append((self.t, "query", ukaz))
        if ukaz == "*IDN?":
            return "RIGOL TECHNOLOGIES,TESTNI-DVOJNIK,SINTETICNO,00.00\n"
        if ukaz == ":SYST:ERR?":
            return self.vrsta_napak.pop(0) if self.vrsta_napak else '0,"No error"'
        if ukaz.startswith(":MEAS:ALL?"):
            if self.v(self.izpad):
                raise TimeoutError("sinteticni izpad povezave")
            i = 0.0502 if self.v(self.visok) else 0.0031
            return f"3.3001,{i:.4f},{3.3001 * i:.3f}\n"
        if ukaz.startswith(":OUTP:MODE?"):
            return "CC" if self.v(self.cc) else "CV"
        odgovori = {":APPL? CH1,VOLT": "U", ":APPL? CH1,CURR": "I", ":OUTP:OVP:VAL? CH1": "OVP",
                    ":OUTP:OVP? CH1": "OVPs", ":OUTP:OCP:VAL? CH1": "OCP",
                    ":OUTP:OCP? CH1": "OCPs", ":OUTP? CH1": "izhod"}
        if ukaz in odgovori:
            return self.st[odgovori[ukaz]]
        if ukaz in (":OUTP:OVP:QUES? CH1", ":OUTP:OCP:QUES? CH1"):
            return "NO"
        raise AssertionError(f"nepričakovan ukaz: {ukaz}")


class TestSnemanje(Osnova):
    """I1-I8: nastavitve prebrane nazaj, surovi nizi, oba časa, vrzeli, CV/CC, brez prepisa."""

    def setUp(self):
        super().setUp()
        self._spanje = zajem.prepreci_spanje_racunalnika
        zajem.prepreci_spanje_racunalnika = lambda: None
        self.seja = os.path.join(self.mapa, "seja")

    def tearDown(self):
        zajem.prepreci_spanje_racunalnika = self._spanje
        super().tearDown()

    def args(self, **kw):
        a = dict(mapa=self.seja, ino="", kanal="CH1", nastavi=True, napetost=3.30,
                 tok_omejitev=0.5, premor_izklop=5.0, nacin_perioda=10.0, perioda=0.0,
                 prag_visok_ma=20.0, cas_konec_s=20.0, cas_zacetka_s=30.0, najdlje_s=0.0,
                 pusti_vklopljeno=False, rigol="", visa_backend=None)
        a.update(kw)
        return argparse.Namespace(**a)

    def posnemi(self, rigol, **kw):
        from contextlib import redirect_stderr
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            ok = zajem.snemaj_z_instrumentom(rigol, "LAZNI::INSTR", self.args(**kw),
                                             ura=rigol.ura, pocakaj=rigol.pocakaj)
        return ok

    def json(self, ime):
        with open(os.path.join(self.seja, ime), encoding="utf-8") as f:
            return json.load(f)

    def test_nastavitve_so_prebrane_nazaj_in_shranjene(self):
        r = LazniRigol()
        self.assertTrue(self.posnemi(r))
        meta = self.json("meta.json")
        self.assertEqual(meta["rigol_idn"], "RIGOL TECHNOLOGIES,TESTNI-DVOJNIK,SINTETICNO,00.00")
        self.assertEqual(meta["kanal"], "CH1")
        self.assertEqual(meta["prebrano_z_instrumenta"],
                         {"U_nastavljena_V": "3.300", "I_omejitev_A": "0.5000", "OVP_V": "3.600",
                          "OVP_stanje": "ON", "OCP_A": "0.6000", "OCP_stanje": "ON",
                          "izhod": "OFF", "nacin": "CV"})
        self.assertEqual(meta["zahtevano"]["I_omejitev_A"], 0.5)
        konec = self.json("meta_konec.json")
        self.assertEqual(konec["stanje_ob_koncu"]["izhod"], "ON")     # prebrano pred izklopom
        self.assertEqual(r.st["izhod"], "OFF")                        # nato izklopljeno
        self.assertEqual((konec["OVP_sprozen"], konec["OCP_sprozen"]), ("NO", "NO"))

    def test_med_sejo_samo_poizvedbi_meritve_in_nacina(self):
        r = LazniRigol()
        self.posnemi(r)
        vklop = next(k for k, d in enumerate(r.dnevnik) if d[2] == ":OUTP CH1,ON")
        zadnja = max(k for k, d in enumerate(r.dnevnik) if d[2] == ":MEAS:ALL? CH1")
        med_sejo = {d[2] for d in r.dnevnik[vklop + 1:zadnja + 1]}
        self.assertEqual(med_sejo, {":MEAS:ALL? CH1", ":OUTP:MODE? CH1"})
        self.assertFalse(any(d[1] == "write" for d in r.dnevnik[vklop + 1:zadnja + 1]))

    def test_surovi_nizi_in_oba_casa(self):
        r = LazniRigol()
        self.posnemi(r)
        vr = beri_csv(os.path.join(self.seja, "rigol.csv"))
        self.assertEqual(list(vr[0].keys()), ["t_pred_s", "t_po_s", "U_V", "I_A", "P_W"])
        self.assertEqual((vr[0]["U_V"], vr[0]["I_A"], vr[0]["P_W"]), ("3.3001", "0.0031", "0.010"))
        for v in vr:                                   # po - pred = trajanje poizvedbe
            self.assertAlmostEqual(float(v["t_po_s"]) - float(v["t_pred_s"]), 0.1, places=3)
        visoki = [v for v in vr if v["I_A"] == "0.0502"]
        self.assertTrue(90 <= len(visoki) <= 100)      # ~10 s po 0,1 s, brez izpuščanja
        per = self.json("meta_konec.json")["perioda"]
        self.assertAlmostEqual(per["perioda_med_s"], 0.1, places=3)
        self.assertEqual(self.json("meta_konec.json")["vzorcev"], len(vr))

    def test_zavrnjen_ukaz_ustavi_pred_snemanjem(self):
        r = LazniRigol(napaka_po_ukazu=":OUTP:OCP:VAL")
        with self.assertRaisesRegex(zajem.NapakaRigol, "zavrnil ukaz ':OUTP:OCP:VAL"):
            self.posnemi(r)
        self.assertFalse(os.path.exists(os.path.join(self.seja, "rigol.csv")))
        self.assertNotIn(":OUTP CH1,ON", [d[2] for d in r.dnevnik])

    def test_neujemanje_prebrane_omejitve_ustavi(self):
        r = LazniRigol(najvec_tok=0.3)                 # instrument tiho omeji na 0,3 A
        with self.assertRaisesRegex(zajem.NapakaRigol, "I_omejitev_A: zahtevano 0.5"):
            self.posnemi(r)
        self.assertNotIn(":OUTP CH1,ON", [d[2] for d in r.dnevnik])

    def test_omejitev_pod_pol_ampera_je_zavrnjena(self):
        with self.assertRaisesRegex(zajem.NapakaRigol, "pod 0.5 A"):
            self.posnemi(LazniRigol(), tok_omejitev=0.3)

    def test_obstojeca_meritev_se_ne_prepise(self):
        os.makedirs(self.seja)
        pot = os.path.join(self.seja, "rigol.csv")
        with open(pot, "w") as f:
            f.write("prejsnja meritev\n")
        with redirect_stdout(io.StringIO()):
            self.assertFalse(zajem.snemaj(self.args()))        # instrumenta sploh ne odpre
        r = LazniRigol()
        with self.assertRaises(FileExistsError):               # tudi neposredno ne
            self.posnemi(r)
        with open(pot) as f:
            self.assertEqual(f.read(), "prejsnja meritev\n")

    def test_vrzel_je_zabelezena_in_ni_zapolnjena(self):
        r = LazniRigol(izpad=(8.0, 11.0))
        self.posnemi(r)
        vr = beri_csv(os.path.join(self.seja, "rigol.csv"))
        t0s = None
        for a, b in zip(vr, vr[1:]):
            if float(b["t_pred_s"]) - float(a["t_po_s"]) > 1.0:
                t0s = (float(a["t_po_s"]), float(b["t_pred_s"]))
        self.assertIsNotNone(t0s)                              # v sledi je luknja
        dog = beri_csv(os.path.join(self.seja, "rigol_dogodki.csv"))
        vrzeli = [d for d in dog if d["vrsta"] == "vrzel"]
        self.assertEqual(len(vrzeli), 1)
        self.assertAlmostEqual(float(vrzeli[0]["t_s"]), t0s[0], places=3)
        self.assertAlmostEqual(float(vrzeli[0]["trajanje_s"]), t0s[1] - t0s[0], places=3)
        self.assertGreater(float(vrzeli[0]["trajanje_s"]), 3.0)
        self.assertGreaterEqual(sum(d["vrsta"] == "napaka_poizvedbe" for d in dog), 3)
        self.assertEqual(self.json("meta_konec.json")["napak_branja"],
                         sum(d["vrsta"] == "napaka_poizvedbe" for d in dog))

    def test_nacin_CC_je_zabelezen(self):
        r = LazniRigol(cc=(9.0, 31.0))
        self.posnemi(r)
        nacini = [v["nacin"] for v in beri_csv(os.path.join(self.seja, "rigol_nacin.csv"))]
        self.assertIn("CC", nacini)
        self.assertEqual(nacini[0], "CV")
        self.assertEqual(self.json("meta_konec.json")["vzorcev_nacina_ne_CV"], nacini.count("CC"))

    def test_posneta_sled_gre_skozi_analizo(self):
        """Zapis, ki ga piše snemanje, analiza prebere (isti stolpci, sredina poizvedbe)."""
        r = LazniRigol(visok=(5.0, 15.0))
        self.posnemi(r)
        t, p = zajem.preberi_rigol(os.path.join(self.seja, "rigol.csv"))
        okna = zajem.najdi_okna(t, p, nastavitve()["okna"])["okna"]
        self.assertEqual(len(okna), 1)
        self.assertAlmostEqual(okna[0][1] - okna[0][0], 10.0, delta=0.15)

    def test_pravila_konca(self):
        self.assertTrue(self.posnemi(LazniRigol(visok=(5.0, 15.0))))
        self.assertIn("ne računa več", self.json("meta_konec.json")["razlog_konca"])
        self.assertAlmostEqual(self.json("meta_konec.json")["trajanje_s"], 35.0, delta=1.0)

    def test_esp32_ki_ne_zacne_ustavi_snemanje_z_neuspehom(self):
        self.assertFalse(self.posnemi(LazniRigol(visok=(1e9, 1e9))))
        self.assertEqual(self.json("meta_konec.json")["razlog_konca"], "ESP32 ni začel računati")

    def test_najdaljsi_cas_ustavi_snemanje_z_neuspehom(self):
        self.assertFalse(self.posnemi(LazniRigol(visok=(5.0, 1e9)), najdlje_s=40.0))
        self.assertIn("najdaljši čas", self.json("meta_konec.json")["razlog_konca"])

    def test_statistika_period(self):
        st = zajem.statistika_period([0.0, 0.1, 0.2, 0.4])     # periode 0,1 0,1 0,2
        self.assertAlmostEqual(st["perioda_povp_s"], 0.4 / 3)
        self.assertAlmostEqual(st["perioda_med_s"], 0.1)
        self.assertAlmostEqual(st["perioda_max_s"], 0.2)
        self.assertAlmostEqual(st["perioda_std_s"], 0.0577350269, places=6)
        self.assertAlmostEqual(st["fs_povp_Hz"], 7.5)


if __name__ == "__main__":
    unittest.main()
