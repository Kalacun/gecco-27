#!/usr/bin/env python3
"""
zajem.py - snemanje porabe ESP32 z napajalnikom RIGOL in analiza energije
           za algoritme DE, jDE in L-SHADE (program ea_energija.ino).

ESP32 med poskusom NI povezan z računalnikom (napaja ga samo RIGOL).
Skripta zato zagone prepozna iz toka: med spanjem je tok nizek, med
optimizacijo visok. Rezultate algoritmov (vrstice REZ in KONV) ESP32
shrani v flash in jih izpiše, ko ga po poskusu priklopite na USB.

Namestitev:
    pip install pyvisa pyvisa-py pyserial
    pip install matplotlib              (neobvezno: grafi)

Ukazi:
    python zajem.py seznam
    python zajem.py snemaj --rigol "USB0::0x1AB1::...::INSTR" --mapa meritve_X
    python zajem.py preberi --port COM5 --mapa meritve_X
    python zajem.py analiza meritve_X/rigol.csv meritve_X/esp32.txt --grafi

Podrobna navodila so v README.md.
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import time

import izvor

# Kritične vrednosti t-porazdelitve (95 %, dvostransko) za df = 1..30
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

NAN = float("nan")
INF = float("inf")


def odpri_rigol(naslov, backend):
    """Odpre napajalnik. Brez naslova poišče edino napravo RIGOL.
    Najprej poskusi sistemski VISA (NI-VISA, UltraSigma), nato pyvisa-py."""
    import pyvisa
    zaledja = [backend] if backend is not None else ["", "@py"]
    zadnja = None
    for z in zaledja:
        try:
            rm = pyvisa.ResourceManager(z) if z else pyvisa.ResourceManager()
            if not naslov:
                kandidati = [r for r in rm.list_resources() if "0x1AB1" in r.upper()
                             or "RIGOL" in r.upper() or r.startswith("USB")]
                if len(kandidati) != 1:
                    raise RuntimeError(f"najdenih naprav RIGOL: {kandidati}; podajte --rigol")
                naslov = kandidati[0]
            inst = rm.open_resource(naslov)
            inst.timeout = 3000
            return inst, naslov
        except Exception as e:  # noqa: BLE001
            zadnja = e
    raise RuntimeError(f"RIGOL-a ni mogoče odpreti: {zadnja}")


def prepreci_spanje_racunalnika():
    """Računalnik med dolgim snemanjem ne sme zaspati (Windows: API,
    macOS: caffeinate za čas tega procesa)."""
    try:
        if sys.platform == "win32":
            import ctypes
            ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
    except Exception as e:  # noqa: BLE001
        print(f"  opozorilo: ne morem preprečiti spanja računalnika ({e})")


# ======================================================================
#  SNEMANJE z RIGOL-a
# ======================================================================
# Ukazi SCPI so preverjeni v "DP800 Series Programming Guide" (RIGOL,
# izdaja marec 2013): :APPLy (str. 2-6), :MEASure:ALL[:DC]? (2-16),
# :OUTPut:MODE? (2-31), :OUTPut:OCP... (2-32, 2-33), :OUTPut:OVP...
# (2-34, 2-35), :OUTPut[:STATe] (2-35), :SYSTem:ERRor? (2-59).
RAZLICICA_ZAPISA_SLEDI = 2
DATOTEKE_SNEMANJA = ("meta.json", "rigol.csv", "rigol_nacin.csv", "rigol_dogodki.csv",
                     "meta_konec.json")
MIN_TOK_OMEJITEV_A = 0.5       # odločitev projekta: tokovna omejitev >= 0,5 A


class NapakaRigol(Exception):
    """Napajalnik ni v stanju, ki ga zahteva meritev; snemanje se ne začne."""


def preberi_napake_rigol(inst, najvec=20):
    """Izprazni vrsto napak instrumenta (:SYST:ERR?) in vrne seznam napak.
    Odgovor brez napake se začne s številko 0."""
    napake = []
    for _ in range(najvec):
        odg = inst.query(":SYST:ERR?").strip()
        try:
            koda = int(odg.split(",")[0])
        except ValueError:
            napake.append(odg)
            break
        if koda == 0:
            break
        napake.append(odg)
    return napake


def stanje_rigol(inst, k):
    """Prebere nastavitve kanala NAZAJ z instrumenta (ne tistih, ki smo jih
    želeli nastaviti). Vrednosti so nizi, kot jih je vrnil instrument."""
    return {"U_nastavljena_V": inst.query(f":APPL? {k},VOLT").strip(),
            "I_omejitev_A": inst.query(f":APPL? {k},CURR").strip(),
            "OVP_V": inst.query(f":OUTP:OVP:VAL? {k}").strip(),
            "OVP_stanje": inst.query(f":OUTP:OVP? {k}").strip(),
            "OCP_A": inst.query(f":OUTP:OCP:VAL? {k}").strip(),
            "OCP_stanje": inst.query(f":OUTP:OCP? {k}").strip(),
            "izhod": inst.query(f":OUTP? {k}").strip(),
            "nacin": inst.query(f":OUTP:MODE? {k}").strip()}


def nastavi_rigol(inst, k, napetost, tok, ovp, ocp, tol_v=0.005, tol_a=0.005):
    """Izklopi izhod, nastavi napetost, tokovno omejitev, OVP in OCP, po
    VSAKEM ukazu prebere vrsto napak, na koncu vse prebere nazaj in
    primerja z zahtevanim. Ob napaki ali neujemanju sproži NapakaRigol.
    Vrne prebrano stanje (slovar)."""
    preberi_napake_rigol(inst)                      # stare napake niso naše
    for c in (f":OUTP {k},OFF", f":APPL {k},{napetost},{tok}",
              f":OUTP:OVP:VAL {k},{ovp:.3f}", f":OUTP:OVP {k},ON",
              f":OUTP:OCP:VAL {k},{ocp:.3f}", f":OUTP:OCP {k},ON"):
        inst.write(c)
        napake = preberi_napake_rigol(inst)
        if napake:
            raise NapakaRigol(f"Instrument je zavrnil ukaz '{c}': {napake}")
    st = stanje_rigol(inst, k)
    for kljuc, zahtevano, tol in (("U_nastavljena_V", napetost, tol_v),
                                  ("I_omejitev_A", tok, tol_a),
                                  ("OVP_V", ovp, tol_v), ("OCP_A", ocp, tol_a)):
        try:
            odstopanje = abs(float(st[kljuc]) - zahtevano)
        except ValueError:
            raise NapakaRigol(f"Nerazumljiv odgovor instrumenta za {kljuc}: '{st[kljuc]}'")
        if odstopanje > tol:
            raise NapakaRigol(f"{kljuc}: zahtevano {zahtevano}, instrument vrača {st[kljuc]}")
    for kljuc, zahtevano in (("OVP_stanje", "ON"), ("OCP_stanje", "ON"), ("izhod", "OFF")):
        if st[kljuc].upper() != zahtevano:
            raise NapakaRigol(f"{kljuc}: zahtevano {zahtevano}, instrument vrača {st[kljuc]}")
    return st


def statistika_period(casi):
    """Dosežena perioda vzorčenja in njeno tresenje iz časov vzorcev (s)."""
    d = sorted(b - a for a, b in zip(casi, casi[1:]))
    if not d:
        return None
    n = len(d)
    povp = sum(d) / n
    return {"n_period": n, "perioda_povp_s": povp, "perioda_med_s": d[n // 2],
            "perioda_std_s": math.sqrt(sum((x - povp) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0,
            "perioda_min_s": d[0], "perioda_p95_s": d[min(n - 1, int(0.95 * n))],
            "perioda_max_s": d[-1], "fs_povp_Hz": 1.0 / povp if povp > 0 else 0.0}


class ZaznavaKonca:
    """Pravila konca snemanja iz sledi toka, NEODVISNA od tega, koliko toka
    ploščica porabi v spanju (pretvornik USB-UART, LED in regulator na
    ploščici so napajani s 3V3 in lahko porabijo več kot ESP32 sam).

    tla      najnižja drseča mediana (zadnjih 5 vzorcev) toka po prvih
             zacetek_tal_s sekundah od vklopa izhoda: poraba ploščice v spanju.
    računa   vzorec s tokom nad tla + razlika_a. Računanje pri 240 MHz je
             nekaj deset mA nad lahkim spanjem; razlika_a je zato varno pod tem.
    začel    vsaj en vzorec je računal.
    konec    ESP32 je začel IN v zadnjih cas_konec_s sekundah noben vzorec ni
             računal IN v teh sekundah ni vrzeli, daljše od max_vrzel_s (vrzel
             v povezavi ne sme izgledati kot spanje). Med sejo je najdaljši
             premor brez računanja SPANJE_S + PO_OKNU_S (11 s), zato 60 s
             pomeni globoko spanje na koncu seje.
    oken     sproti prešteta obdobja računanja (ločena z več kot 3 s brez
             računanja); samo za izpis napredka, analiza okna določi sama."""

    def __init__(self, razlika_a, cas_konec_s, zacetek_tal_s=3.0, max_vrzel_s=2.0, mediana_n=5):
        self.razlika, self.cas_konec = razlika_a, cas_konec_s
        self.zacetek_tal, self.max_vrzel, self.mediana_n = zacetek_tal_s, max_vrzel_s, mediana_n
        self.tla = None
        self.zacel = False
        self.oken = 0
        self._zadnji = []          # zadnjih mediana_n tokov
        self._nedavni = []         # (t, i) zadnjih cas_konec_s (+ rezerva) sekund
        self._zadnji_racuna = None # čas zadnjega vzorca računanja
        self.zadnji_spanje = None  # čas zadnjega vzorca na ravni spanja

    def prag(self):
        return None if self.tla is None else self.tla + self.razlika

    def dodaj(self, t, i):
        self._zadnji = (self._zadnji + [i])[-self.mediana_n:]
        if t >= self.zacetek_tal and len(self._zadnji) == self.mediana_n:
            med = sorted(self._zadnji)[self.mediana_n // 2]
            if self.tla is None or med < self.tla:
                self.tla = med
        self._nedavni.append((t, i))
        meja = t - self.cas_konec - 5.0
        while self._nedavni and self._nedavni[0][0] < meja:
            self._nedavni.pop(0)
        prag = self.prag()
        if prag is not None and i > prag:
            self.zacel = True
            # novo obdobje računanja: več kot 3 s po zadnjem vzorcu računanja
            # (pisanje v flash 1 s po oknu se tako ne šteje posebej)
            if self._zadnji_racuna is None or t - self._zadnji_racuna > 3.0:
                self.oken += 1
            self._zadnji_racuna = t
        elif prag is not None:
            self.zadnji_spanje = t

    def konec(self, t):
        prag = self.prag()
        if not self.zacel or prag is None:
            return False
        od = t - self.cas_konec
        okno = [(ti, ii) for ti, ii in self._nedavni if ti >= od]
        if not okno or okno[0][0] - od > self.max_vrzel:
            return False
        if any(b[0] - a[0] > self.max_vrzel for a, b in zip(okno, okno[1:])):
            return False
        return all(ii <= prag for _, ii in okno)


def snemaj(args):
    """Odpre napajalnik in posname sejo (glej snemaj_z_instrumentom)."""
    obstojece = [d for d in DATOTEKE_SNEMANJA + ("ea_energija.ino",)
                 if os.path.exists(os.path.join(args.mapa, d))]
    if obstojece and not getattr(args, "_mapa_pripravljena", False):
        print(f"Mapa {args.mapa} že vsebuje meritev ({', '.join(obstojece)}). Surovih podatkov "
              "ne prepisujem: izberite novo mapo (--mapa).")
        return False
    inst, naslov = odpri_rigol(args.rigol, args.visa_backend)
    try:
        return snemaj_z_instrumentom(inst, naslov, args)
    finally:
        inst.close()


def snemaj_z_instrumentom(inst, naslov, args, ura=time.monotonic, pocakaj=time.sleep):
    """Samodejno: nastavi napajalnik in prebere nastavitve nazaj, vklopi
    izhod (ESP32 se zažene in začne poskus), snema, prepozna konec poskusa
    in izhod izklopi. Človek med poskusom ne posega.

    Datoteke v args.mapa (vse se ustvarijo NA NOVO; če katera že obstaja,
    se snemanje ne začne; nobena se pozneje ne odpre za pisanje):
      meta.json          pred začetkom: instrument, zahtevane in NAZAJ
                         prebrane nastavitve, načrt, čas po uri računalnika
      rigol.csv          t_pred_s, t_po_s, U_V, I_A, P_W. Časa sta monotona
                         ura tik pred poizvedbo in tik po njej; U, I, P so
                         nizi natanko tako, kot jih je vrnil instrument v
                         ENEM odgovoru na :MEAS:ALL?. Brez filtriranja,
                         povprečenja ali izpuščanja.
      rigol_nacin.csv    t_pred_s, t_po_s, nacin: odgovor na :OUTP:MODE?
                         (CV, CC, UR) vsakih args.nacin_perioda sekund
      rigol_dogodki.csv  t_s, vrsta, trajanje_s, opis: napake poizvedb,
                         nerazumljivi odgovori, vrsta napak instrumenta in
                         VRZELI (čas brez veljavnega vzorca) z dolžino
      meta_konec.json    po koncu: razlog konca, število vzorcev in napak,
                         dosežena frekvenca vzorčenja in tresenje, končno
                         stanje instrumenta (tudi ali sta se sprožila OVP/OCP)

    Med sejo se instrumentu pošiljata samo poizvedbi :MEAS:ALL? in
    :OUTP:MODE? (ter :SYST:ERR? po neuspeli poizvedbi). Nobena nastavitev
    se med sejo ne spreminja; izhod se vklopi pred prvim vzorcem in izklopi
    po zadnjem. Vrzeli se nikoli ne zapolnijo z izmišljeno vrednostjo."""
    os.makedirs(args.mapa, exist_ok=True)
    poti = {d: os.path.join(args.mapa, d) for d in DATOTEKE_SNEMANJA}
    idn = inst.query("*IDN?").strip()
    print("RIGOL:", idn, "(", naslov, ")")
    k = args.kanal
    ukaz, ukaz_nacin = f":MEAS:ALL? {k}", f":OUTP:MODE? {k}"

    ovp, ocp = args.napetost + 0.3, args.tok_omejitev + 0.1
    if args.nastavi:
        if args.tok_omejitev < MIN_TOK_OMEJITEV_A:
            raise NapakaRigol(f"Tokovna omejitev {args.tok_omejitev} A je pod "
                              f"{MIN_TOK_OMEJITEV_A} A (odločitev projekta).")
        stanje = nastavi_rigol(inst, k, args.napetost, args.tok_omejitev, ovp, ocp)
        pocakaj(args.premor_izklop)         # ESP32 brez napajanja -> čist zagon
    else:
        stanje = stanje_rigol(inst, k)      # ročni način: samo preberemo
    print("Stanje kanala (prebrano z instrumenta):", stanje)

    with open(__file__, "rb") as f:
        import hashlib
        zgostitev = hashlib.sha256(f.read()).hexdigest()
    meta = {"razlicica_zapisa": RAZLICICA_ZAPISA_SLEDI,
            "zacetek_ura_racunalnika": time.strftime("%Y-%m-%d %H:%M:%S %z"),
            "rigol_idn": idn, "naslov": naslov, "kanal": k,
            "nastavljal": bool(args.nastavi),
            "zahtevano": {"U_V": args.napetost, "I_omejitev_A": args.tok_omejitev,
                          "OVP_V": ovp, "OCP_A": ocp},
            "prebrano_z_instrumenta": stanje,
            "ukaz_meritve": ukaz, "ukaz_nacina": ukaz_nacin,
            "nacin_perioda_s": args.nacin_perioda, "perioda_s": args.perioda,
            "zajem_py_sha256": zgostitev, "python": sys.version.split()[0],
            "platforma": sys.platform,
            "pravila_konca": {"cas_konec_s": args.cas_konec_s, "cas_zacetka_s": args.cas_zacetka_s,
                              "najdlje_s": args.najdlje_s, "razlika_mA": args.razlika_ma,
                              "opis": "konec: zadnjih cas_konec_s s noben vzorec toka ni nad "
                                      "tlemi + razlika_mA (tla = najnižja drseča mediana "
                                      "5 vzorcev po 3 s); ESP32 ni začel: noben tak vzorec v "
                                      "cas_zacetka_s s"},
            "stolpci_rigol_csv": "t_pred_s,t_po_s: monotona ura (s od začetka) tik pred "
                                 "poizvedbo in tik po njej; U_V,I_A,P_W: nizi iz enega odgovora"}
    with open(poti["meta.json"], "x", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    prepreci_spanje_racunalnika()
    print(f"Snemam v {poti['rigol.csv']}.  Ctrl+C (PyCharm: rdeči gumb Stop) za ročno "
          "prekinitev.\n")
    zaznava = ZaznavaKonca(args.razlika_ma / 1000.0, args.cas_konec_s)
    pricakovano_oken = getattr(args, "pricakovano_oken", 0) or 0
    pricakovano_s = getattr(args, "pricakovano_s", 0) or 0
    n, napak, n_nacin, ni_cv = 0, 0, 0, 0
    casi = []                  # sredine poizvedb (za statistiko periode)
    zadnji_dober = None        # t_po zadnjega veljavnega vzorca
    v_vrzeli = False
    razlog = "?"
    with open(poti["rigol.csv"], "x", newline="", encoding="utf-8") as f, \
            open(poti["rigol_nacin.csv"], "x", newline="", encoding="utf-8") as fn, \
            open(poti["rigol_dogodki.csv"], "x", newline="", encoding="utf-8") as fd:
        w, wn, wd = csv.writer(f), csv.writer(fn), csv.writer(fd)
        w.writerow(["t_pred_s", "t_po_s", "U_V", "I_A", "P_W"])
        wn.writerow(["t_pred_s", "t_po_s", "nacin"])
        wd.writerow(["t_s", "vrsta", "trajanje_s", "opis"])

        def dogodek(t_s, vrsta, trajanje_s, opis):
            wd.writerow([f"{t_s:.4f}", vrsta, "" if trajanje_s is None else f"{trajanje_s:.4f}",
                         opis])
            fd.flush()

        t0 = ura()
        if args.nastavi:
            inst.write(f":OUTP {k},ON")
        naslednji_nacin = 0.0
        try:
            while True:
                # ---- način CV/CC/UR v stalnih razmikih
                if args.nacin_perioda > 0 and ura() - t0 >= naslednji_nacin:
                    try:
                        ta = ura() - t0
                        nacin = inst.query(ukaz_nacin).strip()
                        tb = ura() - t0
                        wn.writerow([f"{ta:.4f}", f"{tb:.4f}", nacin])
                        fn.flush()
                        n_nacin += 1
                        ni_cv += nacin.upper() != "CV"
                    except Exception as e:  # noqa: BLE001
                        dogodek(ura() - t0, "napaka_poizvedbe_nacina", None, repr(e))
                    naslednji_nacin += args.nacin_perioda
                # ---- vzorec: napetost, tok in moč iz ENE poizvedbe
                ta = ura() - t0
                try:
                    odg = inst.query(ukaz)
                    tb = ura() - t0
                except Exception as e:  # noqa: BLE001
                    napak += 1
                    v_vrzeli = True
                    dogodek(ura() - t0, "napaka_poizvedbe", None, repr(e))
                    try:
                        for vnos in preberi_napake_rigol(inst):
                            dogodek(ura() - t0, "napaka_instrumenta", None, vnos)
                    except Exception as e2:  # noqa: BLE001
                        dogodek(ura() - t0, "napaka_branja_vrste_napak", None, repr(e2))
                    print("\nNapaka RIGOL:", e, file=sys.stderr)
                    pocakaj(0.5)
                    continue
                deli = odg.strip().split(",")
                try:
                    if len(deli) != 3:
                        raise ValueError
                    i = float(deli[1])
                    float(deli[0])
                    p = float(deli[2])
                except ValueError:
                    napak += 1
                    v_vrzeli = True
                    dogodek(tb, "nerazumljiv_odgovor", None, odg.strip())
                    continue
                if v_vrzeli:
                    zac = zadnji_dober if zadnji_dober is not None else 0.0
                    dogodek(zac, "vrzel", ta - zac, "brez veljavnega vzorca")
                    v_vrzeli = False
                w.writerow([f"{ta:.4f}", f"{tb:.4f}"] + [d.strip() for d in deli])
                zadnji_dober = tb
                t = 0.5 * (ta + tb)
                casi.append(t)
                n += 1
                zaznava.dodaj(t, i)
                if n % 20 == 0:
                    f.flush()
                    tla = "   ?  " if zaznava.tla is None else f"{zaznava.tla*1000:6.1f}"
                    oken = f"{zaznava.oken}" + (f"/{pricakovano_oken}" if pricakovano_oken else "")
                    cas = f"{t/60:6.1f} min" + (f" od ~{pricakovano_s/60:.0f}" if pricakovano_s
                                                else "")
                    pozor = ""
                    if zaznava.zadnji_spanje is not None and t - zaznava.zadnji_spanje > 300:
                        # Samo opozorilo: med sejo ESP32 spi vsaj vsakih nekaj deset s.
                        pozor = (f"  POZOR: ESP32 že {(t - zaznava.zadnji_spanje) / 60:.0f} min "
                                 "ne spi (ponovni zagon?)")
                    print(f"\r  {cas}   I = {i*1000:7.2f} mA (spanje {tla} mA)   "
                          f"P = {p*1000:7.1f} mW   oken ~{oken}   vzorcev: {n}{pozor}   ", end="")
                # Pravila konca zavisijo samo od sledi, ne od lokalne kopije
                # programa. Ali je seja popolna, preveri analiza iz glave
                # izpisa ESP32 (načrtovano število zapisov).
                if zaznava.konec(t):
                    razlog = "konec poskusa (ESP32 ne računa več)"
                    break
                if not zaznava.zacel and t > args.cas_zacetka_s:
                    razlog = "ESP32 ni začel računati"
                    break
                if args.najdlje_s > 0 and t > args.najdlje_s:
                    razlog = "presežen najdaljši čas snemanja (--najdlje-s)"
                    break
                if args.perioda > 0:
                    pocakaj(args.perioda)
        except KeyboardInterrupt:
            razlog = "ročno prekinjeno"
        trajanje_snemanja = ura() - t0
        if v_vrzeli:
            zac = zadnji_dober if zadnji_dober is not None else 0.0
            dogodek(zac, "vrzel", trajanje_snemanja - zac, "brez veljavnega vzorca do konca")

    # ---- po zadnjem vzorcu: končno stanje instrumenta, nato izklop izhoda
    konec = {"konec_ura_racunalnika": time.strftime("%Y-%m-%d %H:%M:%S %z"),
             "razlog_konca": razlog, "vzorcev": n, "napak_branja": napak,
             "trajanje_s": trajanje_snemanja, "vzorcev_nacina": n_nacin,
             "vzorcev_nacina_ne_CV": ni_cv, "perioda": statistika_period(casi),
             "tla_spanja_mA": None if zaznava.tla is None else round(zaznava.tla * 1000, 3),
             "oken_zaznanih_med_snemanjem": zaznava.oken}
    try:
        konec["stanje_ob_koncu"] = stanje_rigol(inst, k)
        konec["OVP_sprozen"] = inst.query(f":OUTP:OVP:QUES? {k}").strip()
        konec["OCP_sprozen"] = inst.query(f":OUTP:OCP:QUES? {k}").strip()
        konec["napake_instrumenta_ob_koncu"] = preberi_napake_rigol(inst)
    except Exception as e:  # noqa: BLE001
        konec["napaka_branja_koncnega_stanja"] = repr(e)
    if args.nastavi and not args.pusti_vklopljeno:
        try:
            inst.write(f":OUTP {k},OFF")
        except Exception as e:  # noqa: BLE001
            konec["napaka_izklopa_izhoda"] = repr(e)
            print(f"\nOPOZORILO: izhoda ni bilo mogoče izklopiti ({e}). Izklopite ga ročno!")
    with open(poti["meta_konec.json"], "x", encoding="utf-8") as f:
        json.dump(konec, f, indent=2, ensure_ascii=False)
    per = konec["perioda"]
    print(f"\n{razlog}. Shranjeno: {poti['rigol.csv']}  ({n} vzorcev, napak branja: {napak})")
    if zaznava.tla is not None:
        print(f"Tok v spanju (tla) {zaznava.tla*1000:.2f} mA; obdobij računanja med snemanjem "
              f"~{zaznava.oken}" + (f" (načrt: {pricakovano_oken})" if pricakovano_oken else ""))
    if per:
        print(f"Vzorčenje: {per['fs_povp_Hz']:.2f} Hz povprečno; perioda mediana "
              f"{per['perioda_med_s']*1000:.1f} ms, std (tresenje) {per['perioda_std_s']*1000:.1f} ms, "
              f"p95 {per['perioda_p95_s']*1000:.1f} ms, največ {per['perioda_max_s']*1000:.1f} ms")
    if ni_cv:
        print(f"OPOZORILO: {ni_cv} od {n_nacin} odčitkov načina ni CV (glej rigol_nacin.csv).")
    return razlog.startswith("konec")


# ======================================================================
#  BRANJE REZULTATOV Z ESP32 (namesto ročnega kopiranja iz Serial Monitorja)
# ======================================================================
def najdi_serijska_vrata():
    """Poišče USB-UART vrata ESP32 (macOS/Linux; na Windows podajte COMx)."""
    import glob
    for vzorec in ("/dev/cu.usbserial*", "/dev/cu.SLAB_USBtoUART*", "/dev/cu.wchusbserial*",
                   "/dev/ttyUSB*", "/dev/ttyACM*"):
        najdena = sorted(glob.glob(vzorec))
        if najdena:
            return najdena[0]
    return ""


class _PosixSerijska:
    """Minimalno branje serijskih vrat samo s standardno knjižnico
    (macOS/Linux), če pyserial ni nameščen."""
    def __init__(self, port, baud):
        import termios
        import tty
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        a = termios.tcgetattr(self.fd)
        hitrost = getattr(termios, f"B{baud}")
        a[4] = a[5] = hitrost
        a[2] |= termios.CLOCAL | termios.CREAD
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        self.buf = b""

    def readline(self):
        import select
        konec = time.monotonic() + 1.0
        while b"\n" not in self.buf and time.monotonic() < konec:
            r, _, _ = select.select([self.fd], [], [], 0.2)
            if r:
                try:
                    self.buf += os.read(self.fd, 4096)
                except BlockingIOError:
                    pass
        if b"\n" in self.buf:
            vr, self.buf = self.buf.split(b"\n", 1)
            return vr + b"\n"
        return b""

    def write(self, podatki):
        os.write(self.fd, podatki)

    def close(self):
        os.close(self.fd)


def preberi(args, odpri=None):
    """Prebere en celoten izpis rezultatov (od #POSKUS do #KONEC_IZPISA)
    in ga shrani v <mapa>/esp32.txt. ESP32 izpis ponavlja vsakih 10 s.

    Linij DTR in RTS ne vklopimo, da se ESP32 ob odprtju vrat ne resetira
    ali ne preide v način za nalaganje programa (samodejni reset na
    razvojnih ploščicah). Tudi če se resetira, se rezultati ne izgubijo:
    končan poskus ob vklopu samo izpisuje."""
    if odpri is not None:
        ser = odpri                      # za preizkus brez strojne opreme
    else:
        if not args.port:
            args.port = najdi_serijska_vrata()
            if not args.port:
                print("Ne najdem ESP32. Priklopite USB ali podajte --port.")
                return False
        try:
            import serial
            ser = serial.serial_for_url(args.port, do_not_open=True)
            ser.baudrate = args.baud
            ser.timeout = 1.0
            ser.dtr = False
            ser.rts = False
            ser.open()
        except ImportError:              # brez pyserial (macOS/Linux): termios
            ser = _PosixSerijska(args.port, args.baud)
    os.makedirs(args.mapa, exist_ok=True)
    pot = os.path.join(args.mapa, "esp32.txt")
    if os.path.exists(pot):
        print(f"{pot} že obstaja. Surovih podatkov ne prepisujem: izberite drugo mapo "
              "ali datoteko najprej sami preimenujte.")
        ser.close()
        return False
    print(f"Berem z {args.port} ... (ESP32 izpis ponovi vsakih 10 s, Ctrl+C za prekinitev)")
    vrstice, zajemam = [], False
    konec = time.monotonic() + args.cas
    try:
        while time.monotonic() < konec:
            vr = ser.readline().decode("utf-8", errors="replace").rstrip("\r\n")
            if not vr:
                continue
            if vr.startswith("#POSKUS"):
                vrstice, zajemam = [vr], True        # začetek celotnega bloka
                print("  " + vr)
            elif vr.startswith("#NAPAKA"):
                print("  " + vr)
            elif zajemam:
                vrstice.append(vr)
                if vr.startswith("#KONEC_IZPISA"):
                    break
        else:
            print("Ni celotnega izpisa v predvidenem času. Ali je poskus končan?")
            return False
    except KeyboardInterrupt:
        print("\nPrekinjeno.")
        return False
    finally:
        ser.close()
    with open(pot, "x", encoding="utf-8") as f:
        f.write("\n".join(vrstice) + "\n")
    n_rez = sum(1 for v in vrstice if v.startswith("REZ,"))
    n_cilj = sum(1 for v in vrstice if v.startswith("CILJ,"))
    n_tocka = sum(1 for v in vrstice if v.startswith("TOCKA,"))
    print(f"Shranjeno: {pot}  (REZ: {n_rez}, CILJ: {n_cilj}, TOCKA: {n_tocka})")
    return True


# ======================================================================
#  BRANJE PODATKOV
# ======================================================================
def preberi_rigol(pot):
    """Prebere sled moči. Podpira zapis 2 (t_pred_s, t_po_s: čas vzorca je
    sredina poizvedbe) in stari zapis 1 (t_s). Vrne (t, p)."""
    sled = preberi_sled(pot)
    return sled["t"], sled["p"]


def preberi_sled(pot):
    """Prebere rigol.csv in, če obstaja ob njem, rigol_nacin.csv.
    Vrne slovar: t (sredina poizvedbe), p (W), u (V), nacini [(t, niz)]
    ali None, če datoteke z načinom ni."""
    t, p, u = [], [], []
    with open(pot, newline="", encoding="utf-8") as f:
        bralnik = csv.DictReader(f)
        stolpci = bralnik.fieldnames or []
        if "t_pred_s" in stolpci and "t_po_s" in stolpci:
            cas = lambda vr: 0.5 * (float(vr["t_pred_s"]) + float(vr["t_po_s"]))  # noqa: E731
        elif "t_s" in stolpci:
            cas = lambda vr: float(vr["t_s"])  # noqa: E731
        else:
            raise NapakaAnalize(f"{pot}: neznan zapis sledi (stolpci {stolpci})")
        vrstice = list(bralnik)
    for k, vr in enumerate(vrstice):
        try:
            tk, pk, uk = cas(vr), float(vr["P_W"]), float(vr["U_V"])
        except (TypeError, ValueError):
            if k == len(vrstice) - 1:
                # Snemanje, ki ga je ustavil operacijski sistem (npr. Stop v
                # PyCharmu), lahko pusti nedokončano zadnjo vrstico. Izpustimo
                # samo njo in to izpišemo.
                print(f"OPOMBA: zadnja vrstica {pot} je nedokončana (snemanje je bilo "
                      f"prekinjeno med pisanjem) in ni upoštevana: {dict(vr)}")
                break
            raise NapakaAnalize(f"{pot}: vrstica {k + 2} ni berljiva: {dict(vr)}")
        t.append(tk)
        p.append(pk)
        u.append(uk)
    nacini = None
    pot_nacin = os.path.join(os.path.dirname(os.path.abspath(pot)), "rigol_nacin.csv")
    if os.path.exists(pot_nacin):
        with open(pot_nacin, newline="", encoding="utf-8") as f:
            vrstice_n = list(csv.DictReader(f))
        nacini = []
        for k, vr in enumerate(vrstice_n):
            try:
                nacini.append((0.5 * (float(vr["t_pred_s"]) + float(vr["t_po_s"])),
                               vr["nacin"].strip()))
            except (TypeError, ValueError, AttributeError):
                if k == len(vrstice_n) - 1:
                    print(f"OPOMBA: zadnja vrstica {pot_nacin} je nedokončana in ni upoštevana.")
                    break
                raise NapakaAnalize(f"{pot_nacin}: vrstica {k + 2} ni berljiva: {dict(vr)}")
    return {"t": t, "p": p, "u": u, "nacini": nacini}


def kakovost_sledi(mapa):
    """Kratek povzetek kakovosti posnetka v mapi seje (brez zapisov ESP32):
    vzorčenje, najdaljša vrzel, napetost, način CV in dogodki. Vrne slovar
    in ga izpiše. Uporabno tudi, ko se analiza ustavi."""
    sled = preberi_sled(os.path.join(mapa, "rigol.csv"))
    t, u = sled["t"], sled["u"]
    v = {"vzorcev": len(t)}
    if len(t) > 1:
        razmiki = sorted(b - a for a, b in zip(t, t[1:]))
        v.update(trajanje_s=t[-1] - t[0], fs_Hz=(len(t) - 1) / (t[-1] - t[0]),
                 perioda_med_s=razmiki[len(razmiki) // 2], najdaljsa_vrzel_s=razmiki[-1],
                 U_min_V=min(u), U_max_V=max(u))
    if sled["nacini"] is not None:
        v["odcitkov_nacina"] = len(sled["nacini"])
        v["ne_CV"] = sum(1 for _, nac in sled["nacini"] if nac.upper() != "CV")
    pot_d = os.path.join(mapa, "rigol_dogodki.csv")
    if os.path.exists(pot_d):
        with open(pot_d, newline="", encoding="utf-8") as f:
            dog = list(csv.DictReader(f))
        v["napak_poizvedb"] = sum(1 for d in dog if d.get("vrsta") == "napaka_poizvedbe")
        vrz = [float(d["trajanje_s"]) for d in dog if d.get("vrsta") == "vrzel" and d.get("trajanje_s")]
        v["vrzeli_nad_1s"] = sum(1 for x in vrz if x > 1.0)
    pot_k = os.path.join(mapa, "meta_konec.json")
    if os.path.exists(pot_k):
        with open(pot_k, encoding="utf-8") as f:
            v["razlog_konca"] = json.load(f).get("razlog_konca")
    else:
        v["razlog_konca"] = "ni meta_konec.json (snemanje je bilo ustavljeno od zunaj)"
    print("Posnetek RIGOL-a:")
    if len(t) > 1:
        print(f"  {v['vzorcev']} vzorcev v {v['trajanje_s'] / 60:.1f} min, {v['fs_Hz']:.2f} Hz "
              f"(perioda mediana {v['perioda_med_s'] * 1000:.0f} ms), najdaljša vrzel "
              f"{v['najdaljsa_vrzel_s']:.2f} s, napetost {v['U_min_V']:.3f}-{v['U_max_V']:.3f} V")
    if "ne_CV" in v:
        print(f"  način: {v['odcitkov_nacina']} odčitkov, od tega ne CV: {v['ne_CV']}")
    if "napak_poizvedb" in v:
        print(f"  napak poizvedb: {v['napak_poizvedb']}, vrzeli nad 1 s: {v['vrzeli_nad_1s']}")
    print(f"  konec snemanja: {v['razlog_konca']}")
    return v


def napake_sledi_v_oknu(sled, t0, t1, n):
    """Vnaprej določena pravila o kakovosti sledi v merilnem oknu [t0, t1].
    Vrne seznam razlogov (prazen = okno je v redu):
      vrzel_v_oknu  med zaporednima vzorcema, ki segata v okno, je več kot
                    max_vrzel_s (vrzeli se nikoli ne interpolirajo);
      ni_CV_v_oknu  odčitek načina (:OUTP:MODE?) v oknu, zadnji pred njim
                    ali prvi za njim ni CV, ali pa napetost kateregakoli
                    vzorca v oknu odstopa od U_nazivna_V za več kot
                    U_toleranca_V (napajalnik je bil v tokovni omejitvi).
    Pravila ne uporabljajo izida optimizacije."""
    razlogi = []
    t, u = sled["t"], sled["u"]
    if any(tb - ta > n["max_vrzel_s"] and tb > t0 and ta < t1 for ta, tb in zip(t, t[1:])):
        razlogi.append("vrzel_v_oknu")
    ni_cv = any(abs(ui - n["U_nazivna_V"]) > n["U_toleranca_V"]
                for ti, ui in zip(t, u) if t0 <= ti <= t1)
    if sled["nacini"] is not None:
        pred = [x for x in sled["nacini"] if x[0] < t0][-1:]
        v_oknu = [x for x in sled["nacini"] if t0 <= x[0] <= t1]
        po = [x for x in sled["nacini"] if x[0] > t1][:1]
        ni_cv = ni_cv or any(nac.upper() != "CV" for _, nac in pred + v_oknu + po)
    if ni_cv:
        razlogi.append("ni_CV_v_oknu")
    return razlogi


CELA = {"i", "poskus", "D", "zagon", "poz", "ogrev", "proracun", "fe", "gen", "cas_us",
        "t_zacetek_us", "t_konec_us", "np_konec", "LS_NP_INIT", "seme", "crc_ok",
        "razlog_reseta", "cpu_mhz", "napake_spanja", "pocitek_us", "prosta_kopica",
        "sklad_min", "prevod_crc"}
OBVEZNI_REZ = ("i", "poskus", "funkcija", "D", "alg", "zagon", "poz", "ogrev", "nacin",
               "proracun", "fe", "gen", "best", "cas_us", "t_zacetek_us", "t_konec_us",
               "np_konec", "seme", "crc_ok", "razlog_reseta", "cpu_mhz", "napake_spanja",
               "pocitek_us", "prosta_kopica", "sklad_min", "prevod_crc")
OBVEZNA_GLAVA = ("nacrt", "red", "zagonov", "spanje", "po_oknu", "ogrevanje", "tock", "ciljev",
                 "stanje", "resetov", "razlog_zacetka", "zapisov_nacrt", "velikost_zapisa",
                 "datoteka_B", "prevod_crc", "fqbn", "cilji", "poskusi")
SAMO_STOLPCI = ("i", "vrsta", "id", "parameter", "t_zacetek_us", "t_konec_us", "stevec",
                "aktivno_us", "spanje_us", "crc_ok")
# esp_reset_reason(): vrednosti iz ESP-IDF (esp_system.h)
RAZLOGI_RESETA = {0: "neznan", 1: "vklop napajanja", 2: "zunanji pin", 3: "programski reset",
                  4: "izjema/panic", 5: "nadzornik prekinitev", 6: "nadzornik opravil",
                  7: "drug nadzornik", 8: "deep sleep", 9: "padec napetosti (brownout)",
                  10: "SDIO"}


def preberi_esp(pot):
    """Prebere izpis ESP32 (zajem.py preberi): glavo #POSKUS ter vrstice
    REZ (en zagon), CILJ (prvi doseg vsakega cilja) in TOCKA (kontrolne
    točke). Stolpci REZ se preberejo iz vrstice "#REZ,...".

    STROGO: nerazumljiva vrstica REZ, CILJ ali TOCKA, manjkajoča glava ali
    star zapis (vrstice KONV, stolpec cas_ms) sproži NapakaAnalize; nobena
    vrstica se ne izpusti tiho. Če datoteka vsebuje izpis večkrat (ESP32
    ga ponavlja), morajo biti ponovitve enake.

    Vrne (param, rez). Vsak zapis ima še "cilji": [(prag, fe, us)] po
    lestvici in "tocke": [(fe, us, best)]; fe = 0 pomeni nedosežen cilj."""
    param, rez, cilji, tocke, samo = {}, {}, {}, {}, {}
    stolpci = None
    with open(pot, encoding="utf-8", errors="replace") as f:
        for st, vr in enumerate(f, start=1):
            vr = vr.strip()
            if not vr:
                continue
            if vr.startswith("#POSKUS"):
                glava, _, prevod = vr.partition(" prevod=")
                param = dict(re.findall(r"(\w+)=([^\s]+)", glava))
                param["prevod"] = prevod.strip()
                for kljuc in ("spanje", "po_oknu"):
                    param[kljuc] = param.get(kljuc, "").rstrip("s")
                continue
            if vr.startswith("#SAMOPREIZKUS"):
                param["samopreizkus"] = dict(re.findall(r"(\w+)=([^\s]+)", vr))
                continue
            if vr.startswith("#REZ,"):
                stolpci = vr[1:].split(",")
                continue
            if vr.startswith(("KONV,", "#KONV")):
                raise NapakaAnalize(f"{pot}: star zapis izpisa (vrstice KONV). Ta analiza bere "
                                    "samo izpis programa z lestvico ciljev (REZ, CILJ, TOCKA).")
            if vr.startswith("#"):
                continue
            d = vr.split(",")
            try:
                if d[0] == "REZ":
                    if stolpci is None or len(d) != len(stolpci):
                        raise ValueError("število stolpcev")
                    z = {ime: (int(v) if ime in CELA else float(v) if ime == "best" else v)
                         for ime, v in zip(stolpci[1:], d[1:])}
                    if z["i"] in rez and rez[z["i"]] != z:
                        raise ValueError("ponovljen zapis se razlikuje")
                    rez[z["i"]] = z
                elif d[0] == "CILJ":
                    i, k = int(d[1]), int(d[2])
                    cilji.setdefault(i, {})[k] = (float(d[3]), int(d[4]), int(d[5]))
                elif d[0] == "TOCKA":
                    i, k = int(d[1]), int(d[2])
                    tocke.setdefault(i, {})[k] = (int(d[3]), int(d[4]), float(d[5]))
                elif d[0] == "SAMO":
                    if len(d) != len(SAMO_STOLPCI) + 1:
                        raise ValueError("število stolpcev")
                    z = {ime: int(v) for ime, v in zip(SAMO_STOLPCI, d[1:])}
                    samo[z["i"]] = z
                else:
                    raise ValueError("neznana vrsta vrstice")
            except (ValueError, IndexError) as e:
                raise NapakaAnalize(f"{pot}, vrstica {st}: nerazumljivo ({e}): {vr[:80]}")
    manjka = [k for k in OBVEZNA_GLAVA if k not in param]
    if manjka:
        raise NapakaAnalize(f"{pot}: v glavi #POSKUS manjka {manjka} (ali glave ni).")
    if stolpci is None or any(c not in stolpci for c in OBVEZNI_REZ):
        raise NapakaAnalize(f"{pot}: v vrstici #REZ manjkajo stolpci "
                            f"{[c for c in OBVEZNI_REZ if not stolpci or c not in stolpci]}.")
    n_ciljev, n_tock = int(param["ciljev"]), int(param["tock"])
    for i, z in rez.items():
        c, tk = cilji.get(i, {}), tocke.get(i, {})
        if sorted(c) != list(range(n_ciljev)):
            raise NapakaAnalize(f"{pot}: zapis i={i} ima vrstice CILJ {sorted(c)}, "
                                f"pričakovanih {n_ciljev}.")
        if sorted(tk) != list(range(n_tock)):
            raise NapakaAnalize(f"{pot}: zapis i={i} ima {len(tk)} vrstic TOCKA, "
                                f"pričakovanih {n_tock}.")
        z["cilji"] = [c[k] for k in range(n_ciljev)]
        z["tocke"] = [tk[k] for k in range(n_tock)]
    param["samo"] = [samo[i] for i in sorted(samo)]
    return param, [rez[i] for i in sorted(rez)]


def preveri_izvor_in_plosco(param, surova_mapa, velj_n, plosca_n):
    """Preveri, da je program, ki je dal zapise, sledljiv in da je bil preveden
    z zahtevanimi nastavitvami plošče. Ob neskladnosti NapakaAnalize.

      - oznaka prevoda ni "rocno ..." (ročni prevod brez pripravi.py) in ni
        "+spremembe" (izvorne datoteke se razlikujejo od revizije git), razen
        če nastavitve to dovoljujejo;
      - zgostitev kopij izvornih datotek v mapi seje je enaka tisti v oznaki
        (isto kodo imata računalnik z RIGOL-om in Mac, ki je program naložil);
      - nacrt in red iz oznake sta enaka kot v glavi izpisa;
      - FQBN, s katerim je bil program preveden (makro ARDUINO_FQBN), vsebuje
        zahtevane nastavitve plošče."""
    napake = []
    oznaka = param["prevod"]
    if oznaka.startswith("rocno") and not velj_n["dovoli_rocni_prevod"]:
        napake.append("program je bil preveden ročno brez pripravi.py (oznaka 'rocno ...'): "
                      "izvorne kode ni mogoče povezati z zapisi")
    if "+spremembe" in oznaka and not velj_n["dovoli_spremembe_git"]:
        napake.append("oznaka prevoda vsebuje '+spremembe': izvorne datoteke so se ob "
                      "pripravi razlikovale od revizije git (shranite jih z git commit)")
    m = re.search(r"nacrt:(\d) red:(\d)", oznaka)
    if m:
        red_ime = "uravnotezen" if m.group(2) == "1" else "nakljucni"
        if m.group(1) != param["nacrt"] or red_ime != param["red"]:
            napake.append(f"oznaka prevoda ({oznaka}) in glava (nacrt={param['nacrt']}, "
                          f"red={param['red']}) se ne ujemata")
    if velj_n["preveri_izvor"] and not oznaka.startswith("rocno"):
        src = izvor.src_iz_oznake(oznaka)
        if src is None:
            napake.append("v oznaki prevoda ni zgostitve izvorne kode (src:...)")
        else:
            manjka = [i for i in izvor.IZVORNE_STALNE
                      if not os.path.isfile(os.path.join(surova_mapa, i))]
            if manjka:
                napake.append(f"v mapi seje ni kopij izvorne kode {manjka}; seja ni bila "
                              "posneta z zajem.py poskus (ali so datoteke odstranjene)")
            else:
                imena = list(izvor.IZVORNE_STALNE) + [
                    i for i in izvor.IZVORNE_NEOBVEZNE
                    if os.path.isfile(os.path.join(surova_mapa, i))]
                skupna, _ = izvor.zgostitev_izvora(surova_mapa, imena)
                if skupna[:12] != src:
                    napake.append(f"zgostitev izvorne kode na računalniku ({skupna[:12]}) se "
                                  f"razlikuje od zgostitve v oznaki prevoda ({src}): koda na "
                                  "računalniku z RIGOL-om ni ista kot na računalniku, ki je "
                                  "program prevedel in naložil")
    for n in izvor.napake_plosce(param["fqbn"], plosca_n["fqbn_zahtevano"]):
        napake.append(f"nastavitve plošče: {n}")
    if napake:
        raise NapakaAnalize("Program ni sledljiv ali ni preveden z zahtevanimi nastavitvami:\n  "
                            + "\n  ".join(napake))


def preveri_zapise(param, rez, velj_n, tol_pocitka_s):
    """Notranja skladnost zapisov ESP32, celovitost in popolnost seje. Ob
    neskladnosti sproži NapakaAnalize (nikoli ne nadaljuje s sumljivimi
    zapisi)."""
    napake = []
    nacrt = int(param["zapisov_nacrt"])
    if velj_n["zahtevaj_popolno_sejo"]:
        if param["stanje"] != "koncan":
            napake.append(f"seja se ni končala redno: stanje = {param['stanje']}"
                          + (f", razlog ponovnega zagona: "
                             f"{RAZLOGI_RESETA.get(int(param.get('razlog_prekinitve', 0)), '?')}"
                             if param["stanje"] == "prekinjen" else "")
                          + (f", vrsta napake {param.get('napaka_v', '?')}"
                             if param["stanje"] == "napaka" else ""))
        if len(rez) != nacrt:
            napake.append(f"seja ni popolna: {len(rez)} zapisov, načrtovanih {nacrt}")
    if int(param["resetov"]) != 1 and velj_n["zahtevaj_en_zagon_esp32"]:
        napake.append(f"ESP32 se je med sejo znova zagnal (resetov = {param['resetov']})")
    ostanek = int(param["datoteka_B"]) % int(param["velikost_zapisa"])
    if ostanek:
        napake.append(f"datoteka zapisov ima {ostanek} odvečnih bajtov (delno zapisan zapis)")
    spanje_s = float(param["spanje"])
    for z in rez:
        o = f"zapis i={z['i']} ({z['alg']})"
        if z["crc_ok"] != 1:
            napake.append(f"{o}: napačna kontrolna vsota ali različica (zapis je pokvarjen)")
            continue
        if z["prevod_crc"] != int(param["prevod_crc"]):
            napake.append(f"{o}: zapis je iz drugega prevoda programa")
        if z["cpu_mhz"] != velj_n["cpu_mhz"]:
            napake.append(f"{o}: frekvenca CPU {z['cpu_mhz']} MHz, zahtevana {velj_n['cpu_mhz']}")
        if z["napake_spanja"] != 0:
            napake.append(f"{o}: {z['napake_spanja']} spanj pred zagonom ni uspelo ali jih ni "
                          "zbudil časovnik")
        if z["razlog_reseta"] != int(param["razlog_zacetka"]):
            napake.append(f"{o}: razlog zagona ESP32 {z['razlog_reseta']} ni enak razlogu ob "
                          f"začetku seje {param['razlog_zacetka']}")
        if abs(z["pocitek_us"] / 1e6 - spanje_s) > tol_pocitka_s:
            napake.append(f"{o}: počitek pred oknom {z['pocitek_us'] / 1e6:.3f} s, "
                          f"predpisan {spanje_s} s")
        if z["t_konec_us"] - z["t_zacetek_us"] != z["cas_us"]:
            napake.append(f"{o}: cas_us ni razlika časovnikov")
        if z["nacin"] == "FE" and z["fe"] != z["proracun"]:
            napake.append(f"{o}: način FE, a fe = {z['fe']} != FE_max = {z['proracun']}")
        if z["nacin"] == "CAS" and z["cas_us"] < z["proracun"]:
            napake.append(f"{o}: način CAS, a trajanje {z['cas_us']} us < T = {z['proracun']} us")
        if z["nacin"] not in ("FE", "CAS"):
            napake.append(f"{o}: neznan način '{z['nacin']}'")
        if z["tocke"][-1][0] != z["fe"] and z["nacin"] == "FE":
            napake.append(f"{o}: zadnja kontrolna točka ni pri FE_max")
        if z["tocke"][-1][2] != z["best"]:
            napake.append(f"{o}: best zadnje kontrolne točke ni končni best")
    if napake:
        raise NapakaAnalize("Zapisi ESP32 niso skladni:\n  " + "\n  ".join(napake[:20]))


# ======================================================================
#  ISKANJE ZAGONOV V TOKU IN INTEGRACIJA
# ======================================================================
def ravni_moci(p, n):
    """Raven spanja in raven računanja iz porazdelitve vzorcev moči.
    nizka = kvantil raven_nizka_kvantil; visoka = mediana vzorcev, ki so
    več kot raven_meja_delez razpona nad nizko (kratki skoki z večjo
    močjo zato ne premaknejo ravni)."""
    s = sorted(p)
    nizka = s[int(n["raven_nizka_kvantil"] * (len(s) - 1))]
    vrh = s[int(n["raven_vrh_kvantil"] * (len(s) - 1))]
    meja = nizka + n["raven_meja_delez"] * (vrh - nizka)
    nad = s[next((k for k, v in enumerate(s) if v > meja), len(s) - 1):]
    return nizka, nad[len(nad) // 2]


def najdi_okna(t, p, n):
    """Poišče intervale visoke moči s HISTEREZO: interval se začne, ko moč
    preseže prag vstopa, in konča, ko pade pod (nižji) prag izstopa. Šum
    okoli enega praga zato ne razbije okna na več delov.

    Pragova sta absolutna (prag_vstop_mW, prag_izstop_mW), če sta podana,
    sicer deleža razpona med ravnjo spanja in ravnjo računanja.

    Rob okna (za E1) je trenutek, ko linearno interpolirana moč prečka
    SREDINO med pragoma; išče se v odseku prehoda ali tik pred njim. Če je
    skok med dvema vzorcema, je rob torej na sredini med njima (napaka
    največ pol periode vzorčenja na rob, brez sistematičnega zamika).

    Intervali, krajši od min_trajanje_okna_s, niso merilna okna (zagon
    ESP32, pisanje v flash); vrnejo se posebej in se izpišejo v okna.csv.
    Funkcija NIČESAR ne zavrže tiho in ničesar ne popravlja.

    Vrne slovar: okna, kratki, vstop, izstop, rob, nizka, visoka (moči v W)."""
    if len(t) != len(p) or len(t) < 2:
        raise NapakaAnalize("Sled moči je prazna ali ima različno število časov in vzorcev.")
    if any(tb <= ta for ta, tb in zip(t, t[1:])):
        raise NapakaAnalize("Časi vzorcev v sledi niso strogo naraščajoči.")
    nizka, visoka = ravni_moci(p, n)
    if n["prag_vstop_mW"] is not None and n["prag_izstop_mW"] is not None:
        vstop, izstop = n["prag_vstop_mW"] / 1000.0, n["prag_izstop_mW"] / 1000.0
    elif n["prag_vstop_mW"] is None and n["prag_izstop_mW"] is None:
        vstop = nizka + n["prag_vstop_delez"] * (visoka - nizka)
        izstop = nizka + n["prag_izstop_delez"] * (visoka - nizka)
    else:
        raise NapakaAnalize("Podajte oba absolutna pragova (prag_vstop_mW, prag_izstop_mW) "
                            "ali nobenega.")
    if not vstop > izstop:
        raise NapakaAnalize(f"Prag vstopa ({vstop*1000:.2f} mW) mora biti nad pragom izstopa "
                            f"({izstop*1000:.2f} mW); ravni: spanje {nizka*1000:.2f} mW, "
                            f"računanje {visoka*1000:.2f} mW.")
    rob = 0.5 * (vstop + izstop)

    def cas_roba(k, navzgor, najdlje_nazaj):
        """Čas prečkanja ravni 'rob' v odseku (j-1, j), j <= k, najbližjem k."""
        j = k
        while j > najdlje_nazaj:
            if (p[j - 1] <= rob < p[j]) if navzgor else (p[j - 1] > rob >= p[j]):
                a = (rob - p[j - 1]) / (p[j] - p[j - 1])
                return t[j - 1] + a * (t[j] - t[j - 1])
            j -= 1
        return t[k - 1] + 0.5 * (t[k] - t[k - 1])     # ni prečkanja: sredina odseka

    if p[0] > vstop:
        raise NapakaAnalize("Sled se začne sredi intervala visoke moči; začetek prvega okna "
                            "ni posnet.")
    intervali, v_oknu, zacetek, zadnji = [], False, None, 0
    for k in range(1, len(p)):
        if not v_oknu and p[k - 1] <= vstop < p[k]:
            zacetek, v_oknu, zadnji = cas_roba(k, True, zadnji), True, k
        elif v_oknu and p[k - 1] > izstop >= p[k]:
            intervali.append((zacetek, cas_roba(k, False, zadnji)))
            v_oknu, zadnji = False, k
    if v_oknu:
        raise NapakaAnalize(f"Sled se konča sredi intervala visoke moči (začetek pri "
                            f"{zacetek:.2f} s); snemanje je bilo prekinjeno prezgodaj.")
    okna = [z for z in intervali if z[1] - z[0] >= n["min_trajanje_okna_s"]]
    kratki = [z for z in intervali if z[1] - z[0] < n["min_trajanje_okna_s"]]
    return {"okna": okna, "kratki": kratki, "vstop": vstop, "izstop": izstop, "rob": rob,
            "nizka": nizka, "visoka": visoka}


def upari_okna(okna, rez, spanje_s, po_oknu_s, n):
    """Okno k pripada zapisu k (po ŠTEVILU in VRSTNEM REDU). Preveri:
      1) zapisi REZ so zaporedni (i = 0, 1, 2, ...), brez manjkajočih;
      2) število oken v sledi = število zapisov;
      3) trajanje vsakega okna = čas, ki ga je izmeril ESP32
         (toleranca_trajanja_s);
      4) premor med zaporednima oknoma = spanje + spanje po oknu (obe iz
         glave izpisa ESP32; toleranca_premora_s). Ta pogoj odkrije manjkajoče ali odvečno
         okno tudi, kadar so vsa okna enako dolga (časovni proračun).
    Ob KATERIKOLI neskladnosti sproži NapakaAnalize. Nikoli ne poravnava,
    ne izpušča in ne ugiba."""
    indeksi = [z["i"] for z in rez]
    if indeksi != list(range(len(rez))):
        manjka = sorted(set(range(max(indeksi) + 1)) - set(indeksi)) if indeksi else []
        raise NapakaAnalize(f"Zapisi REZ niso zaporedni od 0 (manjkajo i = {manjka}); "
                            "esp32.txt je nepopoln.")
    if len(okna) != len(rez):
        raise NapakaAnalize(
            f"V sledi moči je {len(okna)} merilnih oken, zapisov REZ pa je {len(rez)}. "
            "Oken in zapisov ne parim, ker ni znano, kateri manjka. Preglejte okna.csv "
            "(vsi najdeni intervali) in števec 'resetov' v esp32.txt.")
    napake = []
    for k, ((t0, t1), z) in enumerate(zip(okna, rez)):
        raz = (t1 - t0) - z["cas_us"] / 1e6
        if abs(raz) > n["toleranca_trajanja_s"]:
            napake.append(f"okno {k} (zapis i={z['i']}, {z['alg']}): trajanje v sledi "
                          f"{t1 - t0:.3f} s, ESP32 {z['cas_us'] / 1e6:.3f} s")
        if k > 0:
            premor = t0 - okna[k - 1][1]
            pricakovan = spanje_s + po_oknu_s
            if abs(premor - pricakovan) > n["toleranca_premora_s"]:
                napake.append(f"okno {k} (zapis i={z['i']}): premor pred oknom {premor:.3f} s, "
                              f"pričakovan {pricakovan:.3f} s")
    if napake:
        raise NapakaAnalize("Okna v sledi se ne ujemajo z zapisi ESP32:\n  " +
                            "\n  ".join(napake))


def interpoliraj(t, p, x):
    if x <= t[0]:
        return p[0]
    if x >= t[-1]:
        return p[-1]
    lo, hi = 0, len(t) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if t[m] <= x:
            lo = m
        else:
            hi = m
    a = (x - t[lo]) / (t[hi] - t[lo]) if t[hi] > t[lo] else 0.0
    return p[lo] + a * (p[hi] - p[lo])


def integriraj(t, p, t0, t1):
    """Trapezna integracija moči na [t0, t1] (robova interpolirana)."""
    if t1 <= t0:
        return 0.0
    tocke = [(t0, interpoliraj(t, p, t0))]
    tocke += [(ti, pi) for ti, pi in zip(t, p) if t0 < ti < t1]
    tocke += [(t1, interpoliraj(t, p, t1))]
    return sum(0.5 * (pa + pb) * (tb - ta)
               for (ta, pa), (tb, pb) in zip(tocke, tocke[1:]))


def energija_okna(t, p, t0, t1, cas_esp_s, n, oznaka="okno"):
    """Dve oceni energije merilnega okna. Vrne (E1_J, E2_J, P_notranja_W).

    E2 (primarna): časovno utežena povprečna moč vzorcev, ki so vsaj
        rob_E2_s znotraj OBEH robov okna, pomnožena s trajanjem, ki ga je
        izmeril ESP32. Ne zavisi od tega, kako natančno sta določena robova.
    E1 (kontrolna): trapezni integral moči po dejanskih (neenakomernih)
        časih vzorcev čez celotno zaznano okno [t0, t1]; vrednosti na
        robovih sta linearno interpolirani.

    Okno, v katerem je znotraj robov manj kot min_vzorcev_E2 vzorcev,
    sproži napako (E2 ne bi bila zanesljiva)."""
    a, b = t0 + n["rob_E2_s"], t1 - n["rob_E2_s"]
    notranji = sum(1 for ti in t if a <= ti <= b)
    if b <= a or notranji < n["min_vzorcev_E2"]:
        raise NapakaAnalize(f"{oznaka}: znotraj robov ({n['rob_E2_s']} s) je samo {notranji} "
                            f"vzorcev (potrebnih {n['min_vzorcev_E2']}); okno traja "
                            f"{t1 - t0:.2f} s.")
    P_notr = integriraj(t, p, a, b) / (b - a)
    return integriraj(t, p, t0, t1), P_notr * cas_esp_s, P_notr


def povprecje(t, p, t0, t1):
    v = [pi for ti, pi in zip(t, p) if t0 <= ti <= t1]
    return sum(v) / len(v) if v else NAN


# ======================================================================
#  STATISTIKA
# ======================================================================
def opisna(x):
    """Povprečje, std, 95 % IZ povprečja, mediana, Q1, Q3, min, max."""
    x = sorted(v for v in x if not math.isnan(v) and not math.isinf(v))
    n = len(x)
    if n == 0:
        return None

    def kv(q):
        h = q * (n - 1)
        k = int(h)
        return x[k] if k >= n - 1 else x[k] + (h - k) * (x[k + 1] - x[k])

    povp = sum(x) / n
    sd = math.sqrt(sum((v - povp) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0
    tk = 1.96 if n > 31 else (T95[n - 2] if n > 1 else 0.0)
    return {"n": n, "povp": povp, "std": sd, "iz95": tk * sd / math.sqrt(n),
            "med": kv(0.5), "q1": kv(0.25), "q3": kv(0.75), "min": x[0], "max": x[-1]}


def range_(v):
    """Rangi s povprečjem pri vezeh (vrne range in popravek za vezi)."""
    urejeno = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    popravek = 0.0
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[urejeno[j + 1]] == v[urejeno[i]]:
            j += 1
        for k in range(i, j + 1):
            r[urejeno[k]] = 0.5 * (i + j) + 1
        tv = j - i + 1
        popravek += tv ** 3 - tv
        i = j + 1
    return r, popravek


def mann_whitney(a, b):
    """Dvostranski Mann-Whitneyjev U-test (Wilcoxonov rank-sum).

    EN SAM, vedno enak postopek (ne zavisi od nameščenih knjižnic):
    normalna aproksimacija porazdelitve U, vezi dobijo povprečni rang,
    varianca je popravljena za vezi, uporabljen je popravek za zveznost
    (0,5). Neskončne vrednosti (neuspešni zagoni) so med seboj vezane in
    slabše od vseh končnih. NaN se izpusti. Vrne p-vrednost."""
    a = [v for v in a if not math.isnan(v)]
    b = [v for v in b if not math.isnan(v)]
    if len(a) < 2 or len(b) < 2:
        return NAN
    if all(v == a[0] for v in a + b):
        return 1.0
    n1, n2 = len(a), len(b)
    r, popravek = range_(a + b)
    u1 = sum(r[:n1]) - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    n = n1 + n2
    sigma2 = n1 * n2 / 12 * ((n + 1) - popravek / (n * (n - 1)))
    if sigma2 <= 0:
        return 1.0
    z = (abs(u1 - mu) - 0.5) / math.sqrt(sigma2)
    return max(0.0, min(1.0, math.erfc(max(z, 0) / math.sqrt(2))))


def hi2_rep(x, sp):
    """Verjetnost, da hi-kvadrat s sp prostostnimi stopnjami preseže x.
    Sklenjena oblika: sp = 1 -> erfc(sqrt(x/2)), sp = 2 -> exp(-x/2), nato
    rekurzija Q(sp + 2) = Q(sp) + (x/2)^(sp/2) e^(-x/2) / Gama(sp/2 + 1)."""
    if x <= 0:
        return 1.0
    q = math.erfc(math.sqrt(x / 2)) if sp % 2 else math.exp(-x / 2)
    k = 1 if sp % 2 else 2
    while k < sp:
        q += math.exp(k / 2 * math.log(x / 2) - x / 2 - math.lgamma(k / 2 + 1))
        k += 2
    return min(1.0, q)


def kruskal_wallis(skupine):
    """Kruskal-Wallisov test (H s popravkom za vezi, hi-kvadrat
    aproksimacija s k - 1 prostostnimi stopnjami). Vrne p-vrednost."""
    skupine = [[v for v in g if not math.isnan(v)] for g in skupine]
    if len(skupine) < 2 or any(len(g) < 2 for g in skupine):
        return NAN
    vse = [v for g in skupine for v in g]
    n = len(vse)
    r, popravek = range_(vse)
    h, i = 0.0, 0
    for g in skupine:
        h += sum(r[i:i + len(g)]) ** 2 / len(g)
        i += len(g)
    h = 12 / (n * (n + 1)) * h - 3 * (n + 1)
    c = 1 - popravek / (n ** 3 - n)
    if c <= 0:
        return 1.0                      # vse vrednosti enake
    return hi2_rep(h / c, len(skupine) - 1)


def a12(a, b):
    """Vargha-Delaneyjev A12: verjetnost, da je naključna vrednost iz a
    večja od naključne vrednosti iz b (0,5 = ni razlike). Pri minimizaciji
    A12 < 0,5 pomeni, da ima a manjše (boljše) vrednosti."""
    a = [v for v in a if not math.isnan(v)]
    b = [v for v in b if not math.isnan(v)]
    if not a or not b:
        return NAN
    vec = sum(1.0 if x > y else 0.5 if x == y else 0.0 for x in a for y in b)
    return vec / (len(a) * len(b))


def ert(stroski, uspehi):
    """Pričakovani čas teka (expected running time) do cilja:

        ERT = vsota stroškov VSEH zagonov / število uspešnih zagonov

    stroski[i] je strošek zagona i do prvega dosega cilja, če je bil
    uspešen, sicer strošek CELOTNEGA zagona (neuspešni zagoni se nikoli ne
    izpustijo: njihov strošek je v števcu). Brez uspešnega zagona je ERT
    neskončen. Enota je enota stroška (FE, J ali s)."""
    if len(stroski) != len(uspehi):
        raise ValueError("stroski in uspehi morata biti enako dolga")
    n_usp = sum(1 for u in uspehi if u)
    return sum(stroski) / n_usp if n_usp else INF


def holm(pvred):
    """Holm-Bonferronijev popravek za DRUŽINO primerjav pvred (padajoči
    postopek, popravljene vrednosti so monotone). Velikost družine je
    število veljavnih (ne-NaN) p-vrednosti."""
    m = sum(1 for v in pvred if not math.isnan(v))
    red = sorted(range(len(pvred)), key=lambda i: (math.isnan(pvred[i]), pvred[i]))
    popr = [NAN] * len(pvred)
    najvecja = 0.0
    for rang, i in enumerate(red):
        if math.isnan(pvred[i]):
            continue
        najvecja = max(najvecja, min(1.0, (m - rang) * pvred[i]))
        popr[i] = najvecja
    return popr


# ======================================================================
#  NASTAVITVE ANALIZE (ena datoteka, shranjena z rezultati)
# ======================================================================
PRIVZETE_NASTAVITVE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "analiza_nastavitve.json")
# Obvezni ključi. V kodi NI privzetih vrednosti: vsak prag pride iz datoteke.
OBVEZNE_NASTAVITVE = {
    "okna": ("raven_nizka_kvantil", "raven_vrh_kvantil", "raven_meja_delez",
             "prag_vstop_delez", "prag_izstop_delez", "prag_vstop_mW", "prag_izstop_mW",
             "min_trajanje_okna_s", "toleranca_trajanja_s", "toleranca_premora_s"),
    "energija": ("rob_E2_s", "min_vzorcev_E2", "toleranca_E1_E2_rel"),
    "veljavnost": ("max_vrzel_s", "U_nazivna_V", "U_toleranca_V", "ob_vrzeli", "ob_ne_CV",
                   "zahtevaj_zapis_nacina", "zahtevaj_popolno_sejo", "zahtevaj_en_zagon_esp32",
                   "cpu_mhz", "preveri_izvor", "dovoli_rocni_prevod", "dovoli_spremembe_git"),
    "plosca": ("fqbn_zahtevano",),
    "bazna": ("zacetek_po_s", "konec_pred_s"),
    "samopreizkus": ("toleranca_rel",),
    "statistika": ("alfa", "osamelci_z", "druzina_holm", "metrike_testov", "cilji_testov",
                   "cilji_pod_natancnostjo"),
}


class NapakaAnalize(Exception):
    """Analiza se ustavi, ker podatki ali nastavitve niso takšni, kot morajo biti."""


def preberi_nastavitve(pot):
    """Prebere analiza_nastavitve.json in preveri, da so vsi ključi prisotni."""
    with open(pot, encoding="utf-8") as f:
        nast = json.load(f)
    for razdelek, kljuci in OBVEZNE_NASTAVITVE.items():
        if razdelek not in nast:
            raise NapakaAnalize(f"{pot}: manjka razdelek '{razdelek}'")
        for k in kljuci:
            if k not in nast[razdelek]:
                raise NapakaAnalize(f"{pot}: manjka nastavitev '{razdelek}.{k}'")
    return nast


# ======================================================================
#  ANALIZA
# ======================================================================
class _Tee:
    """Izpis hkrati na zaslon in v datoteko porocilo.txt."""
    def __init__(self, *tokovi):
        self.tokovi = tokovi

    def write(self, x):
        for t in self.tokovi:
            t.write(x)

    def flush(self):
        for t in self.tokovi:
            t.flush()


def analiza(args):
    """Rezultati gredo v NOVO podmapo analiza_<datum>_<ura> ob surovih
    podatkih, skupaj s kopijo nastavitev. Surove datoteke (rigol.csv,
    esp32.txt) se samo berejo; prejšnje analize se ne prepišejo."""
    import shutil
    pot_nast = getattr(args, "nastavitve", None) or PRIVZETE_NASTAVITVE
    nast = preberi_nastavitve(pot_nast)
    surova = os.path.dirname(os.path.abspath(args.rigol_csv))
    osnova = os.path.join(surova, time.strftime("analiza_%Y%m%d_%H%M%S"))
    mapa, st = osnova, 1
    while True:                                # nikoli v obstoječo mapo
        try:
            os.makedirs(mapa, exist_ok=False)
            break
        except FileExistsError:
            st += 1
            mapa = f"{osnova}_{st}"
    shutil.copy(pot_nast, os.path.join(mapa, "analiza_nastavitve.json"))
    with open(os.path.join(mapa, "porocilo.txt"), "x", encoding="utf-8") as dat:
        stari = sys.stdout
        sys.stdout = _Tee(stari, dat)
        try:
            print(f"Nastavitve analize: {pot_nast} (kopija v {mapa})")
            return _analiza(args, mapa, nast)
        finally:
            sys.stdout = stari


def _analiza(args, mapa, nast):
    sled = preberi_sled(args.rigol_csv)
    t, p = sled["t"], sled["p"]
    velj_n = nast["veljavnost"]
    for kljuc in ("ob_vrzeli", "ob_ne_CV"):
        if velj_n[kljuc] not in ("napaka", "izloci"):
            raise NapakaAnalize(f"veljavnost.{kljuc} mora biti 'napaka' ali 'izloci'")
    if sled["nacini"] is None and velj_n["zahtevaj_zapis_nacina"]:
        raise NapakaAnalize("Ob rigol.csv ni datoteke rigol_nacin.csv (način CV/CC). Brez nje "
                            "ni mogoče preveriti, da je bil napajalnik v načinu CV "
                            "(nastavitev veljavnost.zahtevaj_zapis_nacina).")
    param, rez = preberi_esp(args.esp_txt)
    spanje_s = float(param["spanje"])
    okna_n, bazna_n, stat_n = nast["okna"], nast["bazna"], nast["statistika"]
    energ_n = nast["energija"]
    if not rez:
        raise NapakaAnalize("V esp32.txt ni nobenega zapisa REZ; brez zapisov ESP32 oken "
                            "ni mogoče pripisati algoritmom.")
    preveri_izvor_in_plosco(param, os.path.dirname(os.path.abspath(args.rigol_csv)), velj_n,
                            nast["plosca"])
    preveri_zapise(param, rez, velj_n, okna_n["toleranca_premora_s"])
    najdeno = najdi_okna(t, p, okna_n)
    zagoni, zavrzeni = najdeno["okna"], najdeno["kratki"]
    prag, nizka, visoka = najdeno["rob"], najdeno["nizka"], najdeno["visoka"]
    # Vsi najdeni intervali gredo v okna.csv PRED parjenjem, da jih je ob
    # napaki mogoče pregledati.
    with open(os.path.join(mapa, "okna.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["vrsta", "t_zacetek_s", "t_konec_s", "trajanje_s", "P_povp_mW"])
        for vrsta, sez in (("okno", zagoni), ("kratek_interval", zavrzeni)):
            for a, b in sez:
                w.writerow([vrsta, f"{a:.4f}", f"{b:.4f}", f"{b - a:.4f}",
                            f"{povprecje(t, p, a, b) * 1000:.3f}"])
    print(f"Poskusi: {param['poskusi']}\n  vrstni red = {param['red']}, počitek = {spanje_s} s, "
          f"ogrevanje = {param['ogrevanje']}, cilji = {param['cilji']}, seme = "
          f"{param.get('seme', '?')}\n  prevod = {param['prevod']}\n  ESP32: stanje = "
          f"{param['stanje']}, razlog zagona = "
          f"{RAZLOGI_RESETA.get(int(param['razlog_zacetka']), '?')}, frekvenca CPU = "
          f"{rez[0]['cpu_mhz']} MHz, prosta kopica {min(z['prosta_kopica'] for z in rez)}-"
          f"{max(z['prosta_kopica'] for z in rez)} B, najmanjši prosti sklad "
          f"{min(z['sklad_min'] for z in rez)}")
    fs = (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 else 0
    print(f"Posnetek: {len(t)} vzorcev, {t[-1] - t[0]:.0f} s, {fs:.1f} Hz")
    print(f"Raven spanja ~{nizka*1000:.2f} mW, računanja ~{visoka*1000:.1f} mW; prag vstopa "
          f"{najdeno['vstop']*1000:.1f} mW, izstopa {najdeno['izstop']*1000:.1f} mW, "
          f"rob {prag*1000:.1f} mW")
    print(f"Merilnih oken v sledi: {len(zagoni)}; kratkih intervalov (< "
          f"{okna_n['min_trajanje_okna_s']} s, niso okna): {len(zavrzeni)}; "
          f"zapisov REZ: {len(rez)}   (vsi intervali: okna.csv)")
    upari_okna(zagoni, rez, spanje_s, float(param["po_oknu"]), okna_n)   # ali NapakaAnalize

    # Kakovost sledi v vsakem oknu (vrzeli, način CV). Po nastavitvah se
    # analiza ustavi ali pa se zagon izloči z zapisanim razlogom.
    napake_oken = [napake_sledi_v_oknu(sled, t0, t1, velj_n) for t0, t1 in zagoni]
    usodne = [(k, r) for k, razlogi in enumerate(napake_oken) for r in razlogi
              if velj_n["ob_vrzeli" if r == "vrzel_v_oknu" else "ob_ne_CV"] == "napaka"]
    if usodne:
        raise NapakaAnalize("Sled v merilnih oknih ni veljavna:\n  " + "\n  ".join(
            f"okno {k} (zapis i={rez[k]['i']}, {rez[k]['alg']}): {r}" for k, r in usodne))

    vrstice, konv_vrstice, cilj_vrstice = [], [], []
    for k, (t0, t1) in enumerate(zagoni):
        r = rez[k]
        T = t1 - t0                                  # trajanje okna v sledi
        cas_esp = r["cas_us"] / 1e6                  # trajanje, izmerjeno na ESP32
        E1, E2, P_notr = energija_okna(t, p, t0, t1, cas_esp, energ_n, f"okno {k}")
        raz = (E1 - E2) / E2
        # Bazna poraba: zadnji del počitka pred zagonom (brez prvih sekund
        # po pisanju v flash in zadnjega dela pred začetkom optimizacije).
        P_baza = povprecje(t, p, t0 - spanje_s + bazna_n["zacetek_po_s"],
                           t0 - bazna_n["konec_pred_s"])
        fe = r["fe"]
        v = {
            "zagon_i": r["i"],
            # celica poskusa: funkcija, D, način proračuna in proračun
            "poskus": f"{r['funkcija']}_D{r['D']}_{r['nacin']}{r['proracun']}",
            "funkcija": r["funkcija"],
            "D": r["D"],
            "nacin": r["nacin"],
            "proracun": r["proracun"],               # FE (način FE) ali us (način CAS)
            "alg": r["alg"],
            "ponovitev": r["zagon"],
            "poz": r["poz"],
            "ogrev": r["ogrev"],
            "seme": r["seme"],
            "napake_sledi": ";".join(napake_oken[k]),
            "t_zacetek_s": t0,
            "trajanje_sled_s": T,
            "trajanje_esp_s": cas_esp,
            "usklajenost_s": T - cas_esp,
            "E2_J": E2,                               # PRIMARNA ocena (bruto)
            "E1_J": E1,                               # kontrolna ocena (trapez)
            "E1_minus_E2_rel": raz,
            "E1_E2_zastavica": int(abs(raz) > energ_n["toleranca_E1_E2_rel"]),
            "E2_mWh": E2 / 3.6,                       # 1 mWh = 3,6 J
            "E2_neto_J": E2 - P_baza * cas_esp,       # izpeljano: bruto - bazna x čas
            "P_notranja_mW": P_notr * 1000,
            "P_bazna_mW": P_baza * 1000,
            "pocitek_esp_s": r["pocitek_us"] / 1e6,
            "cpu_mhz": r["cpu_mhz"],
            "prosta_kopica_B": r["prosta_kopica"],
            "sklad_min": r["sklad_min"],
            "fe": fe,
            "gen": r["gen"],
            "uJ_na_fe": E2 / fe * 1e6,
            "uJ_neto_na_fe": (E2 - P_baza * cas_esp) / fe * 1e6,
            "best": r["best"],
            "np_konec": r["np_konec"],
        }
        vrstice.append(v)
        # Lestvica ciljev: prvi doseg (evalvacije, čas ESP32) in energija do
        # cilja po načelu E2 (notranja povprečna moč x čas do cilja).
        for prag, fe_c, us_c in r["cilji"]:
            dosezen = fe_c > 0
            cilj_vrstice.append({
                "zagon_i": r["i"], "poskus": v["poskus"], "alg": r["alg"],
                "ponovitev": r["zagon"], "ogrev": r["ogrev"], "cilj": prag,
                "dosezen": int(dosezen),
                "fe_do_cilja": fe_c if dosezen else NAN,
                "s_do_cilja": us_c / 1e6 if dosezen else NAN,
                "E2_do_cilja_J": P_notr * us_c / 1e6 if dosezen else INF,
                # strošek celotnega zagona (za ERT, kadar cilj ni dosežen)
                "fe_zagona": fe, "s_zagona": cas_esp, "E2_zagona_J": E2})
        # Konvergenca: kontrolne točke (evalvacije, čas ESP32, best) in
        # energija do točke po načelu E2.
        for j, (fe_t, us_t, best_t) in enumerate(r["tocke"], start=1):
            konv_vrstice.append({"poskus": v["poskus"], "alg": r["alg"],
                                 "ponovitev": r["zagon"], "ogrev": r["ogrev"],
                                 "tocka": j, "fe": fe_t, "t_s": us_t / 1e6,
                                 "E2_J": P_notr * us_t / 1e6, "best": best_t})

    if not vrstice:
        print("Ni najdenih zagonov. Preverite rigol.csv in nastavitve analize (razdelek 'okna').")
        return

    # Ujemanje oken in zapisov je že preverjeno (upari_okna). Pravila
    # izločanja so določena vnaprej in ne zavisijo od izida optimizacije.
    # Vsaka izločitev se z razlogom zapiše v izlocitve.csv.
    izlocitve = []
    for v in vrstice:
        razlogi = razlogi_izlocitve(v)
        v["veljaven"] = int(not razlogi)
        for razlog in razlogi:
            izlocitve.append({"zagon_i": v["zagon_i"], "poskus": v["poskus"], "alg": v["alg"],
                              "ponovitev": v["ponovitev"], "razlog": razlog})
    with open(os.path.join(mapa, "izlocitve.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["zagon_i", "poskus", "alg", "ponovitev", "razlog"])
        w.writeheader()                              # datoteka obstaja tudi, ko je prazna
        w.writerows(izlocitve)
    print(f"Izločitve: {len(izlocitve)} (izlocitve.csv)"
          + "".join(f"\n  {r}: {sum(1 for x in izlocitve if x['razlog'] == r)}"
                    for r in sorted({x['razlog'] for x in izlocitve})))

    pot = os.path.join(mapa, "energija.csv")
    with open(pot, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(vrstice[0].keys()))
        w.writeheader()
        w.writerows(vrstice)
    veljavni_i = {v["zagon_i"] for v in vrstice if v["veljaven"]}
    for c in cilj_vrstice:
        c["veljaven"] = int(c["zagon_i"] in veljavni_i)
    for ime, vsebina in (("konvergenca_energija.csv", konv_vrstice), ("cilji.csv", cilj_vrstice)):
        with open(os.path.join(mapa, ime), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(vsebina[0].keys()))
            w.writeheader()
            w.writerows(vsebina)
    oznaceni = [v for v in vrstice if v["E1_E2_zastavica"]]
    najvecja = max(abs(v["E1_minus_E2_rel"]) for v in vrstice)
    print(f"E1 proti E2: največja relativna razlika {100 * najvecja:.3f} %, toleranca "
          f"{100 * energ_n['toleranca_E1_E2_rel']:.3f} %; označenih zagonov: {len(oznaceni)}"
          + (f" (zagon_i: {[v['zagon_i'] for v in oznaceni]}; niso izločeni)" if oznaceni else ""))
    n_ogrev = sum(v["ogrev"] for v in vrstice)
    print(f"Zagoni -> {pot}  (vseh {len(vrstice)}, ogrevalnih {n_ogrev}, "
          f"veljavnih za analizo {sum(v['veljaven'] for v in vrstice)})")
    if args.podrobno:
        for v in vrstice:
            oz = "ogrev" if v["ogrev"] else ("" if v["veljaven"] else "NEVELJ")
            print(f"  {v['zagon_i']:3d} {v['poskus']:15s} {v['alg']:7s} #{v['ponovitev']:<2d} "
                  f"poz {v['poz']}  {v['trajanje_esp_s']:6.2f} s  E2 = {v['E2_J']:7.3f} J  "
                  f"E1 = {v['E1_J']:7.3f} J  P = {v['P_notranja_mW']:6.1f} mW  "
                  f"best = {v['best']:.3e} {oz}")

    # ------------- analiza po poskusih (funkcija, D) -------------
    analiz = [v for v in vrstice if v["veljaven"]]
    skupine = list(dict.fromkeys(v["poskus"] for v in analiz))
    povzetek, testi, kontrola, ert_vrstice = [], [], [], []
    for sk in skupine:
        vr = [v for v in analiz if v["poskus"] == sk]
        cv = [c for c in cilj_vrstice if c["poskus"] == sk and c["veljaven"]]
        pod_nat = {c["cilj"] for c in stat_n["cilji_pod_natancnostjo"]
                   if c["funkcija"] == vr[0]["funkcija"]}
        povzetek_poskusa(sk, vr, cv, povzetek, testi, stat_n, pod_nat)
        ert_vrstice += ert_poskusa(sk, cv, pod_nat)
        kontrola += kontrola_pravicnosti(sk, vr, stat_n["osamelci_z"])

    # Lezenje bazne porabe skozi celoten poskus (temperatura, napajanje)
    baza = [(v["t_zacetek_s"], v["P_bazna_mW"]) for v in vrstice if not math.isnan(v["P_bazna_mW"])]
    if len(baza) > 3:
        n = len(baza)
        mt = sum(x for x, _ in baza) / n
        mp = sum(y for _, y in baza) / n
        sxx = sum((x - mt) ** 2 for x, _ in baza)
        nakl = sum((x - mt) * (y - mp) for x, y in baza) / sxx if sxx else 0
        print(f"\nBazna poraba: povprečje {mp:.2f} mW, lezenje {nakl*3600:+.3f} mW/h "
              f"({100*nakl*3600/mp:+.2f} %/h) skozi {(baza[-1][0]-baza[0][0])/3600:.1f} h")
        kontrola.append({"poskus": "vsi", "kontrola": "lezenje_bazne_mW_na_h",
                         "alg": "", "vrednost": nakl * 3600, "opomba": ""})

    for ime, vsebina in (("povzetek.csv", povzetek), ("testi.csv", testi),
                         ("kontrola.csv", kontrola), ("ert.csv", ert_vrstice)):
        if vsebina:
            with open(os.path.join(mapa, ime), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(vsebina[0].keys()))
                w.writeheader()
                w.writerows(vsebina)
    print(f"\nShranjeno v {mapa}: energija.csv, povzetek.csv, ert.csv, testi.csv, "
          "kontrola.csv, cilji.csv, konvergenca_energija.csv, okna.csv, izlocitve.csv, porocilo.txt")
    if args.grafi:
        grafi(mapa, t, p, zagoni, zavrzeni, prag, vrstice, konv_vrstice, skupine)


ALG_VRSTNI_RED = ("DE", "jDE", "LSHADE")


DRUZINA_HOLM = "pari_algoritmov_v_eni_metriki_in_enem_poskusu"


def povzetek_poskusa(sk, vr, cv, povzetek, testi, stat_n, pod_nat=()):
    """Opisna statistika in testi za en poskus (funkcija, D, način in
    proračun). vr so veljavni zagoni, cv njihove vrstice ciljev."""
    algoritmi = [a for a in ALG_VRSTNI_RED if any(v["alg"] == a for v in vr)]
    po_alg = {a: [v for v in vr if v["alg"] == a] for a in algoritmi}
    # Samo količine, ki so določene za VSAK zagon. Čas in energija do cilja
    # sta določena le za uspešne zagone, zato ju povzema ERT (ert_poskusa),
    # ne povprečje po uspešnih.
    metrike = [("E2_J", "J"), ("E1_J", "J"), ("E2_neto_J", "J"), ("P_notranja_mW", "mW"),
               ("P_bazna_mW", "mW"), ("fe", "FE"), ("uJ_na_fe", "uJ/FE"),
               ("uJ_neto_na_fe", "uJ/FE"), ("best", "")]
    print(f"\n================ {sk} ================")
    print("Povzetek po algoritmih (povprečje ± 95 % IZ | mediana [Q1, Q3])")
    for kljuc, enota in metrike:
        print(f"  {kljuc} [{enota}]")
        for a in algoritmi:
            s = opisna([v[kljuc] for v in po_alg[a]])
            if not s:
                print(f"     {a:7s} -")
                continue
            print(f"     {a:7s} {s['povp']:11.5g} ± {s['iz95']:<10.4g} | "
                  f"{s['med']:.5g} [{s['q1']:.5g}, {s['q3']:.5g}]  n={s['n']}")
            povzetek.append({"poskus": sk, "alg": a, "metrika": kljuc, **s})
    # Neuspeli zagoni imajo energijo do cilja = neskončno, zato so pri
    # rangiranju najslabši (običajna obravnava pri testih "čas do cilja").
    pari = [(a, b) for i, a in enumerate(algoritmi) for b in algoritmi[i + 1:]]
    if not pari:
        return
    # Družina za Holmov popravek je deklarirana v nastavitvah; koda podpira
    # natanko to družino in se ustavi, če nastavitve zahtevajo drugo.
    if stat_n["druzina_holm"] != DRUZINA_HOLM:
        raise NapakaAnalize(f"statistika.druzina_holm = '{stat_n['druzina_holm']}' ni "
                            f"podprta; podprta je '{DRUZINA_HOLM}'.")
    alfa = stat_n["alfa"]
    print("Primerjave (Mann-Whitney U, dvostransko, normalna aproksimacija s popravkom za "
          "vezi in zveznost;\n  Holm po parih algoritmov znotraj ene metrike in enega "
          "poskusa; A12 < 0,5 => prvi ima manjše vrednosti)")
    # Metrike zagona in, za vsak cilj iz statistika.cilji_testov, energija do
    # cilja (neuspešen zagon = neskončno). Vsaka metrika je svoja družina.
    vzorci = [(kljuc, {a: [v[kljuc] for v in po_alg[a]] for a in algoritmi})
              for kljuc in stat_n["metrike_testov"]]
    for cilj in stat_n["cilji_testov"]:
        if cilj in pod_nat:      # cilj pod natančnostjo vrednotenja: brez testa značilnosti
            print(f"  E2_do_cilja_J@{cilj:g}: cilj je pod natančnostjo vrednotenja te funkcije "
                  "(nastavitve); brez testa")
            continue
        vzorci.append((f"E2_do_cilja_J@{cilj:g}",
                       {a: [c["E2_do_cilja_J"] for c in cv
                            if c["alg"] == a and c["cilj"] == cilj] for a in algoritmi}))
    for kljuc, x in vzorci:
        pv = [mann_whitney(x[a], x[b]) for a, b in pari]
        ph = holm(pv)
        print(f"  {kljuc}")
        for (a, b), p0, p1 in zip(pari, pv, ph):
            ef = a12(x[a], x[b])
            zn = "*" if p1 < alfa else " "
            print(f"     {a:7s} vs {b:7s}  p = {p0:.3g}  p_Holm = {p1:.3g} {zn}  A12 = {ef:.2f}")
            testi.append({"poskus": sk, "metrika": kljuc, "alg1": a, "alg2": b, "p": p0,
                          "p_holm": p1, "A12": ef})


def razlogi_izlocitve(v):
    """Vnaprej določena pravila izločanja zagona iz statistike. Vrne seznam
    razlogov (prazen = zagon je veljaven). Pravila ne uporabljajo nobene
    količine, ki opisuje izid optimizacije (best, cilj, FE)."""
    razlogi = []
    if v["ogrev"]:
        razlogi.append("ogrevalni_zagon")            # tako ga označi ESP32
    razlogi += [r for r in v.get("napake_sledi", "").split(";") if r]   # vrzel, ni CV
    return razlogi


def ert_poskusa(sk, cv, pod_nat=()):
    """ERT za vsak algoritem in VSAK cilj lestvice, v FE, J (E2) in s.
    Strošek uspešnega zagona je strošek do prvega dosega cilja, strošek
    neuspešnega je strošek celotnega zagona. cv so vrstice ciljev
    veljavnih zagonov enega poskusa."""
    vrstice = []
    print("ERT (vsota stroškov vseh zagonov / št. uspešnih) po ciljih f - f* <= cilj")
    for a in [a for a in ALG_VRSTNI_RED if any(c["alg"] == a for c in cv)]:
        for cilj in sorted({c["cilj"] for c in cv}, reverse=True):
            z = [c for c in cv if c["alg"] == a and c["cilj"] == cilj]
            usp = [bool(c["dosezen"]) for c in z]
            e_fe = ert([c["fe_do_cilja"] if u else c["fe_zagona"] for c, u in zip(z, usp)], usp)
            e_j = ert([c["E2_do_cilja_J"] if u else c["E2_zagona_J"] for c, u in zip(z, usp)], usp)
            e_s = ert([c["s_do_cilja"] if u else c["s_zagona"] for c, u in zip(z, usp)], usp)
            print(f"     {a:7s} cilj {cilj:7.0e}  uspešnih {sum(usp):2d}/{len(z)}   "
                  f"ERT = {e_fe:.6g} FE = {e_j:.6g} J = {e_s:.6g} s"
                  + ("   [pod natančnostjo vrednotenja]" if cilj in pod_nat else ""))
            vrstice.append({"poskus": sk, "alg": a, "cilj": cilj, "n_zagonov": len(z),
                            "n_uspesnih": sum(usp), "ERT_FE": e_fe, "ERT_J": e_j, "ERT_s": e_s,
                            "pod_natancnostjo_vrednotenja": int(cilj in pod_nat)})
    return vrstice


def kontrola_pravicnosti(sk, vr, osamelci_z):
    """Preveri pogoje za pravično primerjavo: uravnotežen vrstni red,
    vpliv položaja v bloku na moč, enak časovni proračun, osamelci."""
    vrstice = []
    algoritmi = [a for a in ALG_VRSTNI_RED if any(v["alg"] == a for v in vr)]
    print("Kontrola pravičnosti")
    # 1) uravnoteženost: kolikokrat je bil vsak algoritem na vsakem položaju
    pozicije = sorted({v["poz"] for v in vr if v["poz"] >= 0})
    if pozicije:
        print("  položaj v bloku (število zagonov / mediana P_notranja [mW]):")
        for a in algoritmi:
            deli = []
            for z in pozicije:
                m = [v["P_notranja_mW"] for v in vr if v["alg"] == a and v["poz"] == z]
                s = opisna(m)
                deli.append(f"poz{z}: {len(m):2d} / {s['med']:.2f}" if s else f"poz{z}: 0")
                vrstice.append({"poskus": sk, "kontrola": f"stevilo_na_poz{z}", "alg": a,
                                "vrednost": len(m), "opomba": ""})
            # razlika med položaji glede na raztros (Kruskal-Wallis)
            pv = kruskal_wallis([[v["P_notranja_mW"] for v in vr
                                  if v["alg"] == a and v["poz"] == z] for z in pozicije])
            print(f"     {a:7s} " + "   ".join(deli) +
                  (f"   (Kruskal-Wallis p = {pv:.3g})" if not math.isnan(pv) else ""))
            vrstice.append({"poskus": sk, "kontrola": "vpliv_polozaja_p", "alg": a,
                            "vrednost": pv, "opomba": "p < alfa: moč je odvisna od položaja"})
    # 2) enak časovni proračun
    tr = opisna([v["trajanje_esp_s"] for v in vr])
    if tr:
        print(f"  trajanje merilnih oken: {tr['min']:.2f} - {tr['max']:.2f} s "
              f"(mediana {tr['med']:.2f} s)")
    # 3) osamelci (|z| > osamelci_z, Cruz 2021) - samo poročamo, ne izločamo
    for a in algoritmi:
        e = [v["E2_J"] for v in vr if v["alg"] == a]
        s = opisna(e)
        if s and s["std"] > 0:
            osam = [v["zagon_i"] for v in vr if v["alg"] == a
                    and abs(v["E2_J"] - s["povp"]) > osamelci_z * s["std"]]
            if osam:
                print(f"  osamelci E2_J (|z| > {osamelci_z:g}) {a}: zagon_i {osam} (niso izločeni)")
            vrstice.append({"poskus": sk, "kontrola": "osamelci_E2_J", "alg": a,
                            "vrednost": len(osam), "opomba": " ".join(map(str, osam))})
    return vrstice


# ======================================================================
#  GRAFI (neobvezno, potrebuje matplotlib)
# ======================================================================
def grafi(mapa, t, p, zagoni, zavrzeni, prag, vrstice, konv, skupine):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Za grafe namestite matplotlib: pip install matplotlib")
        return
    barve = {"DE": "#1f77b4", "jDE": "#2ca02c", "LSHADE": "#d62728"}

    # 1) potek moči s prepoznanimi zagoni (kontrola segmentacije)
    fig, ax = plt.subplots(figsize=(14, 3.5))
    ax.plot([x / 3600 for x in t], [x * 1000 for x in p], lw=0.4, color="k")
    for (a, b), v in zip(zagoni, vrstice):
        ax.axvspan(a / 3600, b / 3600, color="gray" if v["ogrev"] else barve.get(v["alg"], "gray"),
                   alpha=0.15 if v["ogrev"] else 0.3, lw=0)
    for a, b in zavrzeni:
        ax.axvspan(a / 3600, b / 3600, color="gray", alpha=0.3, hatch="//", lw=0)
    ax.axhline(prag * 1000, ls="--", lw=0.8, color="gray")
    ax.set_xlabel("čas [h]")
    ax.set_ylabel("moč [mW]")
    ax.set_title("Moč ESP32 in prepoznani zagoni (sivo: ogrevanje, šrafirano: zavrženo)")
    fig.tight_layout()
    fig.savefig(os.path.join(mapa, "graf_moc.png"), dpi=150)
    plt.close(fig)

    analiz = [v for v in vrstice if v["veljaven"]]
    if not skupine:
        return
    # 2) konvergenca glede na energijo in 3) energija, po poskusih
    fig2, osi2 = plt.subplots(1, len(skupine), figsize=(4.5 * len(skupine), 4), squeeze=False)
    fig3, osi3 = plt.subplots(2, len(skupine), figsize=(4.5 * len(skupine), 7), squeeze=False)
    for c, sk in enumerate(skupine):
        vr = [v for v in analiz if v["poskus"] == sk]
        algoritmi = [a for a in ALG_VRSTNI_RED if any(v["alg"] == a for v in vr)]
        veljavni = {(v["alg"], v["ponovitev"]) for v in vr}
        kv = [k for k in konv if k["poskus"] == sk and not k["ogrev"]
              and (k["alg"], k["ponovitev"]) in veljavni]
        ax = osi2[0][c]
        for a in algoritmi:
            tocke = sorted({k["tocka"] for k in kv if k["alg"] == a})
            E, med, q1, q3 = [], [], [], []
            for j in tocke:
                g = [k for k in kv if k["alg"] == a and k["tocka"] == j]
                s = opisna([max(k["best"], 1e-12) for k in g])
                e = opisna([k["E2_J"] for k in g])
                E.append(e["med"]); med.append(s["med"]); q1.append(s["q1"]); q3.append(s["q3"])
            if E:
                ax.plot(E, med, marker="o", ms=3, label=a, color=barve.get(a))
                ax.fill_between(E, q1, q3, alpha=0.2, color=barve.get(a))
        ax.set_yscale("log")
        ax.set_xlabel("porabljena energija [J]")
        ax.set_ylabel("najboljša vrednost (mediana, IQR)")
        ax.set_title(sk)
        ax.legend()
        for r, (kljuc, naslov) in enumerate((("uJ_na_fe", "energija na evalvacijo [µJ/FE]"),
                                              ("E2_J", "energija zagona E2 [J]"))):
            ax = osi3[r][c]
            podatki = [[v[kljuc] for v in vr if v["alg"] == a
                        and not math.isinf(v[kljuc]) and not math.isnan(v[kljuc])]
                       for a in algoritmi]
            oznake = [f"{a}\n({len(d)})" for a, d in zip(algoritmi, podatki)]
            if any(podatki):
                ax.boxplot([d if d else [NAN] for d in podatki])
                ax.set_xticks(range(1, len(oznake) + 1), oznake)
            ax.set_title(f"{sk}: {naslov}", fontsize=9)
    for fig, ime in ((fig2, "graf_konvergenca_energija.png"), (fig3, "graf_energija.png")):
        fig.tight_layout()
        fig.savefig(os.path.join(mapa, ime), dpi=150)
        plt.close(fig)
    print("Grafi: graf_moc.png, graf_konvergenca_energija.png, graf_energija.png")


# ======================================================================
#  POVZETEK ZAPISOV ESP32 (brez sledi moči)
# ======================================================================
def povzetek_zapisov(args):
    """Izpiše, kaj je v esp32.txt, brez sledi RIGOL-a: stanje seje in za
    vsako celico (funkcija, D, način, proračun) in algoritem število
    zagonov, trajanje (mediana, najmanj, največ), evalvacije in število
    zagonov, ki so dosegli vsak cilj. Za celice v načinu FE izpiše še
    mediano trajanja VSEH neogrevalnih zagonov celice: to je predlog za T
    iste celice v kampanji (zaokroženo na celo sekundo)."""
    param, rez = preberi_esp(args.esp_txt)
    print(f"prevod = {param['prevod']}\nstanje = {param['stanje']}, zapisov {len(rez)} od "
          f"načrtovanih {param['zapisov_nacrt']}, resetov = {param['resetov']}, red = "
          f"{param['red']}, pokvarjenih zapisov (crc) = {sum(z['crc_ok'] != 1 for z in rez)}")
    if param["stanje"] != "koncan":
        print(f"SEJA NI KONČANA: stanje = {param['stanje']}, razlog ponovnega zagona = "
              f"{RAZLOGI_RESETA.get(int(param.get('razlog_prekinitve', 0) or 0), '?')}, vrsta "
              f"napake = {param.get('napaka_v', '?')}. (Razlog 'vklop napajanja' pomeni, da je "
              "bilo napajanje izklopljeno med sejo.)")
    celice = list(dict.fromkeys((z["funkcija"], z["D"], z["nacin"], z["proracun"]) for z in rez))
    predlogi = []
    for c in celice:
        vsi = [z for z in rez if (z["funkcija"], z["D"], z["nacin"], z["proracun"]) == c
               and not z["ogrev"]]
        print(f"\n{c[0]} D={c[1]} način {c[2]} proračun {c[3]}"
              + (" us" if c[2] == "CAS" else " FE"))
        for a in ALG_VRSTNI_RED:
            g = [z for z in vsi if z["alg"] == a]
            if not g:
                continue
            tr = sorted(z["cas_us"] / 1e6 for z in g)
            fe = sorted(z["fe"] for z in g)
            cilji = [sum(1 for z in g if z["cilji"][k][1] > 0) for k in range(len(g[0]["cilji"]))]
            print(f"  {a:7s} n={len(g):3d}  trajanje {tr[len(tr) // 2]:8.3f} s "
                  f"({tr[0]:.3f}-{tr[-1]:.3f})  FE {fe[len(fe) // 2]}  dosegli cilje "
                  + "/".join(map(str, cilji)))
        if c[2] == "FE" and vsi:
            tr = sorted(z["cas_us"] / 1e6 for z in vsi)
            med = tr[len(tr) // 2]
            predlogi.append((c, med))
            print(f"  mediana trajanja vseh zagonov celice: {med:.3f} s")
    if predlogi:
        import naprava
        print("\nPredlog T za kampanjo (mediana trajanja zagonov FE, zaokrožena na celo sekundo, "
              "najmanj 1 s); zapiše jih Mac_5_nastavi_T.py v ea_T.h:")
        for fun, d, med, t_us in naprava.predlagaj_T(rez):
            print(f"  #define T_{fun.upper()}_D{d}_US  {t_us}ULL   // {med:.3f} s")
    return predlogi


# ======================================================================
#  SAMOPREIZKUS MERILNE VERIGE (program z NACRT 2)
# ======================================================================
IME_OBREMENITVE = {1: "prazna zanka", 2: "celoštevilsko", 3: "float (Rastrigin D=10)",
                   4: "sprehod po pomnilniku"}
IME_OPERACIJE = {1: "branje ure", 2: "rnd()", 10: "evalvacija rastrigin D=10",
                 11: "evalvacija rastrigin D=20", 12: "evalvacija rosenbrock D=10",
                 13: "evalvacija rosenbrock D=20"}


def analiza_samopreizkusa(args):
    """Preveri merilno verigo z znanimi obremenitvami (zapisi SAMO).

    Časovno os sledi poravna z uro ESP32 z ENIM zamikom: začetek prvega
    zaznanega okna v sledi = začetek prve stalne obremenitve na ESP32. Vsa
    okna se nato vzamejo iz časov ESP32 (zaznavanje robov se pri delovnih
    ciklih ne uporablja, ker moč v njih niha).

    Poroča:
      stalne obremenitve: povprečna moč (trapez in notranja), E1, E2 in
        razlika med začetkom/koncem okna v sledi in po uri ESP32 (lezenje ure);
      delovni cikli: izmerjena povprečna moč proti pričakovani
        delež_dela * P(float) + (1 - delež_dela) * P(spanje), kjer sta
        deleža izmerjena na ESP32; razlika nad samopreizkus.toleranca_rel
        je označena;
      čas operacij: ns na operacijo in delež, ki ga v načinu CAS stane
        branje ure na evalvacijo (čas branja ure / PERIODA_URE_FE)."""
    pot_nast = getattr(args, "nastavitve", None) or PRIVZETE_NASTAVITVE
    nast = preberi_nastavitve(pot_nast)
    sled = preberi_sled(args.rigol_csv)
    t, p = sled["t"], sled["p"]
    param, _ = preberi_esp(args.esp_txt)
    samo = param["samo"]
    if not samo:
        raise NapakaAnalize("V esp32.txt ni vrstic SAMO (program ni bil preveden z NACRT 2).")
    if any(z["crc_ok"] != 1 for z in samo):
        raise NapakaAnalize("Zapis samopreizkusa ima napačno kontrolno vsoto.")
    stalne = [z for z in samo if z["vrsta"] == 1]
    cikli = [z for z in samo if z["vrsta"] == 2]
    casi = [z for z in samo if z["vrsta"] == 3]
    if len(stalne) != 4 or len(cikli) != 3:
        raise NapakaAnalize(f"Pričakovane 4 stalne obremenitve in 3 delovni cikli, najdeno "
                            f"{len(stalne)} in {len(cikli)}; samopreizkus se ni končal.")
    najdeno = najdi_okna(t, p, nast["okna"])
    if not najdeno["okna"]:
        raise NapakaAnalize("V sledi ni nobenega okna visoke moči.")
    zamik = najdeno["okna"][0][0] - stalne[0]["t_zacetek_us"] / 1e6
    spanje_s = float(param["spanje"])
    energ_n, bazna_n = nast["energija"], nast["bazna"]
    tol = nast["samopreizkus"]["toleranca_rel"]

    surova = os.path.dirname(os.path.abspath(args.rigol_csv))
    osnova = os.path.join(surova, time.strftime("samopreizkus_%Y%m%d_%H%M%S"))
    mapa, st = osnova, 1
    while True:
        try:
            os.makedirs(mapa, exist_ok=False)
            break
        except FileExistsError:
            st += 1
            mapa = f"{osnova}_{st}"
    import shutil
    shutil.copy(pot_nast, os.path.join(mapa, "analiza_nastavitve.json"))

    def okno(z):
        return z["t_zacetek_us"] / 1e6 + zamik, z["t_konec_us"] / 1e6 + zamik

    a0, _ = okno(stalne[0])
    P_spanje = povprecje(t, p, a0 - spanje_s + bazna_n["zacetek_po_s"],
                         a0 - bazna_n["konec_pred_s"])
    vrstice, P_stalna = [], {}
    for z in stalne:
        a, b = okno(z)
        trajanje = b - a
        E1, E2, P_notr = energija_okna(t, p, a, b, trajanje, energ_n,
                                       f"obremenitev {z['id']}")
        P_stalna[z["id"]] = P_notr
        zaznano = min(najdeno["okna"], key=lambda o: abs(o[0] - a))
        vrstice.append({"vrsta": "stalna", "id": z["id"], "opis": IME_OBREMENITVE[z["id"]],
                        "trajanje_esp_s": trajanje, "ponovitev": z["stevec"],
                        "P_trapez_mW": E1 / trajanje * 1000, "P_notranja_mW": P_notr * 1000,
                        "P_pricakovana_mW": "", "razlika_rel": (E1 - E2) / E2,
                        "oznaceno": int(abs((E1 - E2) / E2) > tol),
                        "E1_J": E1, "E2_J": E2,
                        "rob_zacetek_sled_minus_esp_s": zaznano[0] - a,
                        "rob_konec_sled_minus_esp_s": zaznano[1] - b,
                        "delez_dela_esp": ""})
    for z in cikli:
        a, b = okno(z)
        trajanje = b - a
        E1 = integriraj(t, p, a, b)
        delez = z["aktivno_us"] / (z["aktivno_us"] + z["spanje_us"])
        P_pric = delez * P_stalna[3] + (1 - delez) * P_spanje
        raz = (E1 / trajanje - P_pric) / P_pric
        vrstice.append({"vrsta": "delovni_cikel", "id": z["id"],
                        "opis": f"{z['id']} % dela, perioda {z['parameter']} ms",
                        "trajanje_esp_s": trajanje, "ponovitev": z["stevec"],
                        "P_trapez_mW": E1 / trajanje * 1000, "P_notranja_mW": "",
                        "P_pricakovana_mW": P_pric * 1000, "razlika_rel": raz,
                        "oznaceno": int(abs(raz) > tol), "E1_J": E1, "E2_J": "",
                        "rob_zacetek_sled_minus_esp_s": "", "rob_konec_sled_minus_esp_s": "",
                        "delez_dela_esp": delez})
    cas_vrstice = []
    ns = {z["id"]: (z["t_konec_us"] - z["t_zacetek_us"]) * 1000.0 / z["stevec"] for z in casi}
    perioda = int(param.get("perioda_ure_fe", 16))
    for z in casi:
        v = {"id": z["id"], "operacija": IME_OPERACIJE.get(z["id"], "?"),
             "ponovitev": z["stevec"], "ns_na_operacijo": ns[z["id"]],
             "delez_branja_ure_na_evalvacijo": ""}
        if z["id"] >= 10 and 1 in ns:
            v["delez_branja_ure_na_evalvacijo"] = ns[1] / perioda / ns[z["id"]]
        cas_vrstice.append(v)
    for ime, vsebina in (("samopreizkus.csv", vrstice), ("samopreizkus_casi.csv", cas_vrstice)):
        if vsebina:
            with open(os.path.join(mapa, ime), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(vsebina[0].keys()))
                w.writeheader()
                w.writerows(vsebina)
    with open(os.path.join(mapa, "porocilo.txt"), "x", encoding="utf-8") as dat:
        stari = sys.stdout
        sys.stdout = _Tee(stari, dat)
        try:
            fs = (len(t) - 1) / (t[-1] - t[0])
            print(f"SAMOPREIZKUS  prevod = {param['prevod']}\n"
                  f"Posnetek: {len(t)} vzorcev, {fs:.1f} Hz; zamik ure sled - ESP32 = {zamik:.3f} s; "
                  f"moč spanja {P_spanje * 1000:.2f} mW")
            print("Stalne obremenitve (P trapez | P notranja | E1 proti E2 | rob sled - ESP32):")
            for v in vrstice[:4]:
                print(f"  {v['opis']:26s} {v['P_trapez_mW']:8.2f} mW | {v['P_notranja_mW']:8.2f} mW"
                      f" | {100 * v['razlika_rel']:+6.2f} % | začetek "
                      f"{1000 * v['rob_zacetek_sled_minus_esp_s']:+5.0f} ms, konec "
                      f"{1000 * v['rob_konec_sled_minus_esp_s']:+5.0f} ms"
                      + ("   OZNAČENO" if v["oznaceno"] else ""))
            print(f"Delovni cikli (izmerjena | pričakovana povprečna moč; toleranca "
                  f"{100 * tol:.1f} %):")
            for v in vrstice[4:]:
                print(f"  {v['opis']:26s} {v['P_trapez_mW']:8.2f} mW | {v['P_pricakovana_mW']:8.2f} mW"
                      f" | {100 * v['razlika_rel']:+6.2f} %   delež dela na ESP32 "
                      f"{100 * v['delez_dela_esp']:.2f} %" + ("   OZNAČENO" if v["oznaceno"] else ""))
            print(f"Čas operacij (ura se v načinu CAS bere vsakih {perioda} evalvacij):")
            for v in cas_vrstice:
                d = v["delez_branja_ure_na_evalvacijo"]
                print(f"  {v['operacija']:28s} {v['ns_na_operacijo']:10.1f} ns"
                      + (f"   branje ure stane {100 * d:.3f} % evalvacije" if d != "" else ""))
            print(f"Shranjeno v {mapa}")
        finally:
            sys.stdout = stari
    return vrstice, cas_vrstice


# ======================================================================
#  CELOTEN POSKUS BREZ POSEGANJA
# ======================================================================
def poskus(args):
    """snemaj -> (če je esp32.txt že v mapi) analiza, vse v isti mapi."""
    if not os.path.exists(args.ino):
        print(f"Ne najdem {args.ino} (kopija programa se shrani k meritvam).")
        return False
    obstojece = [d for d in DATOTEKE_SNEMANJA + ("ea_energija.ino",)
                 if os.path.exists(os.path.join(args.mapa, d))]
    if obstojece:
        print(f"Mapa {args.mapa} že vsebuje meritev ({', '.join(obstojece)}). Surovih podatkov "
              "ne prepisujem: izberite novo mapo (--mapa).")
        return False
    # Kopija točno tega programa v mapo meritev (ponovljivost).
    os.makedirs(args.mapa, exist_ok=True)
    mapa_izvora = os.path.dirname(os.path.abspath(args.ino))
    for ime in izvor.izvorne_datoteke() + ["ea_prevod.h"]:
        vir_pot = os.path.join(mapa_izvora, ime)
        if os.path.exists(vir_pot):
            with open(vir_pot, "rb") as vir, open(os.path.join(args.mapa, ime), "xb") as c:
                c.write(vir.read())
    args._mapa_pripravljena = True
    ok = snemaj(args)
    esp = os.path.join(args.mapa, "esp32.txt")
    if not os.path.exists(esp):
        print("\nNASLEDNJI KORAK - rezultati z ESP32 prek USB (LAB_GUIDE.md):\n"
              "  1) odprite stikalo v + vodniku RIGOL-a (izhod je že izklopljen),\n"
              "  2) USB kabel priklopite na Mac in tam poženite Mac_4_preberi.py\n"
              f"     (ime seje: {os.path.basename(args.mapa)}),\n"
              "  3) mapo prenos/<seja> prenesite na ta računalnik,\n"
              "  4) poženite PC_3_analiza.py.")
    if os.path.exists(esp):
        a = argparse.Namespace(rigol_csv=os.path.join(args.mapa, "rigol.csv"), esp_txt=esp,
                               grafi=True, podrobno=False, nastavitve=PRIVZETE_NASTAVITVE)
        analiza(a)
    return ok


# ======================================================================
def main():
    ap = argparse.ArgumentParser(description="Meritev porabe ESP32 (DE/jDE/L-SHADE) z RIGOL-om")
    sub = ap.add_subparsers(dest="ukaz", required=True)

    privzeti_ino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ea_energija.ino")

    a = sub.add_parser("seznam", help="izpiše priklopljene VISA naprave")
    a.add_argument("--visa-backend", default=None)

    def snemanje_argumenti(a):
        a.add_argument("--rigol", default="", help="VISA naslov (privzeto: edina naprava RIGOL)")
        a.add_argument("--kanal", default="CH1", help="CH1/CH2/CH3, prazno za enokanalne")
        a.add_argument("--perioda", type=float, default=0.0,
                       help="premor med poizvedbami (s); 0 = najhitreje, kar zmore RIGOL")
        a.add_argument("--visa-backend", default=None,
                       help="privzeto sistemski VISA, nato '@py' (pyvisa-py)")
        a.add_argument("--mapa", default=time.strftime("meritve_%Y%m%d_%H%M%S"))
        a.add_argument("--ino", default=privzeti_ino,
                       help="ea_energija.ino; kopija (z ea_jedro.h) se shrani k meritvam")
        a.add_argument("--cas-zacetka-s", type=float, default=300.0,
                       help="če ESP32 v tem času ne začne računati, se snemanje ustavi (s)")
        a.add_argument("--najdlje-s", type=float, default=0.0,
                       help="najdaljši čas snemanja (s); 0 = brez omejitve")
        a.add_argument("--brez-nastavljanja", dest="nastavi", action="store_false",
                       help="ne spreminjaj nastavitev in ne vklapljaj izhoda (ročni način)")
        a.add_argument("--napetost", type=float, default=3.30)
        a.add_argument("--tok-omejitev", type=float, default=0.5,
                       help="A; odločitev projekta: najmanj 0,5")
        a.add_argument("--nacin-perioda", type=float, default=10.0,
                       help="razmik poizvedb :OUTP:MODE? (CV/CC/UR) v s; 0 = brez")
        a.add_argument("--premor-izklop", type=float, default=5.0,
                       help="koliko časa je izhod izklopljen pred začetkom (s)")
        a.add_argument("--pusti-vklopljeno", action="store_true",
                       help="po koncu ne izklopi izhoda")
        a.add_argument("--razlika-ma", type=float, default=10.0,
                       help="koliko mA nad tokom v spanju (tla) pomeni, da ESP32 računa")
        a.add_argument("--cas-konec-s", type=float, default=60.0,
                       help="koliko časa brez računanja pomeni konec poskusa (s)")
        a.add_argument("--pricakovano-oken", type=int, default=0,
                       help="samo za izpis napredka: načrtovano število merilnih oken")
        a.add_argument("--pricakovano-s", type=float, default=0.0,
                       help="samo za izpis napredka: približno trajanje seje (s)")

    a = sub.add_parser("snemaj", help="nastavi RIGOL, vklopi izhod, snema do konca poskusa")
    snemanje_argumenti(a)

    a = sub.add_parser("poskus", help="celoten poskus brez posega: snemaj (+ analiza)")
    snemanje_argumenti(a)

    a = sub.add_parser("preberi", help="prebere rezultate z ESP32 prek USB v esp32.txt")
    a.add_argument("--port", default="", help="serijska vrata, npr. COM5 ali /dev/cu.usbserial-0001 (privzeto: samodejno)")
    a.add_argument("--mapa", required=True, help="mapa poskusa (ista kot pri snemaj)")
    a.add_argument("--baud", type=int, default=115200)
    a.add_argument("--cas", type=float, default=600.0,
                   help="najdaljše čakanje (s); izpis polne kampanje traja okoli minute")

    a = sub.add_parser("analiza", help="izračun energije, statistika, testi, grafi")
    a.add_argument("rigol_csv", help="datoteka rigol.csv iz snemanja")
    a.add_argument("esp_txt", help="zapisi ESP32 (REZ, KONV), datoteka esp32.txt")
    a.add_argument("--grafi", action="store_true", help="nariše grafe (matplotlib)")
    a.add_argument("--nastavitve", default=PRIVZETE_NASTAVITVE,
                   help="datoteka s pragovi in tolerancami analize (kopira se k rezultatom)")
    a.add_argument("--podrobno", action="store_true", help="izpiši vsak zagon")

    a = sub.add_parser("zapisi", help="povzetek zapisov v esp32.txt (brez sledi); predlog T")
    a.add_argument("esp_txt", help="zapisi ESP32, datoteka esp32.txt")

    a = sub.add_parser("samopreizkus", help="preveri merilno verigo z znanimi obremenitvami "
                                            "(program z NACRT 2)")
    a.add_argument("rigol_csv", help="datoteka rigol.csv iz snemanja")
    a.add_argument("esp_txt", help="zapisi ESP32 (vrstice SAMO), datoteka esp32.txt")
    a.add_argument("--nastavitve", default=PRIVZETE_NASTAVITVE)

    args = ap.parse_args()
    if args.ukaz == "seznam":
        import pyvisa
        rm = pyvisa.ResourceManager(args.visa_backend) if args.visa_backend else pyvisa.ResourceManager()
        for r in rm.list_resources():
            print(r)
    elif args.ukaz == "snemaj":
        try:
            sys.exit(0 if snemaj(args) else 1)
        except NapakaRigol as e:
            print(f"\nNAPAKA RIGOL: {e}", file=sys.stderr)
            sys.exit(3)
    elif args.ukaz == "poskus":
        try:
            sys.exit(0 if poskus(args) else 1)
        except NapakaAnalize as e:
            print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
            sys.exit(2)
        except NapakaRigol as e:
            print(f"\nNAPAKA RIGOL: {e}", file=sys.stderr)
            sys.exit(3)
    elif args.ukaz == "preberi":
        sys.exit(0 if preberi(args) else 1)
    elif args.ukaz == "zapisi":
        try:
            povzetek_zapisov(args)
        except NapakaAnalize as e:
            print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
            sys.exit(2)
    elif args.ukaz == "samopreizkus":
        try:
            analiza_samopreizkusa(args)
        except NapakaAnalize as e:
            print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        try:
            analiza(args)
        except NapakaAnalize as e:
            print(f"\nNAPAKA ANALIZE: {e}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()
