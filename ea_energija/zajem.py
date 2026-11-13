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
    pip install scipy matplotlib        (neobvezno: točni testi in grafi)

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

# Kritične vrednosti t-porazdelitve (95 %, dvostransko) za df = 1..30
T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]

NAN = float("nan")
INF = float("inf")


# ======================================================================
#  NAČRT POSKUSA (prebran iz ea_energija.ino)
# ======================================================================
def nacrt_iz_ino(pot):
    """Iz ea_energija.ino prebere nastavitve poskusa in izračuna, koliko
    časa bo trajal. Uporablja se za samodejno ustavitev snemanja in za
    preverjanje, ali se posnetek ujema z načrtom."""
    if not pot or not os.path.exists(pot):
        return None
    src = open(pot, encoding="utf-8").read()
    src = re.sub(r"//[^\n]*", "", src)                 # brez komentarjev

    def define(ime, privzeto):
        m = re.search(rf"#define\s+{ime}\s+([0-9.]+)", src)
        return float(m.group(1)) if m else privzeto
    m = re.search(r"POSKUSI\[\]\s*=\s*\{(.*?)\};", src, re.S)
    poskusi = re.findall(r"\{\s*(\d+)\s*,\s*(\d+)\s*\}", m.group(1)) if m else []
    m = re.search(r"ALGORITMI\[\]\s*=\s*\{(.*?)\};", src, re.S)
    n_alg = len(re.findall(r"\d+", m.group(1))) if m else 3
    n = {"zagonov": int(define("ZAGONOV", 10)), "spanje": define("SPANJE_S", 10),
         "opt": define("OPT_S", 60), "ogrevanje": int(define("OGREVANJE", 0)),
         "zacetno": define("ZACETNO_SPANJE_S", 0), "n_alg": n_alg,
         "poskusi": [("rastrigin" if f == "0" else "rosenbrock", int(d)) for f, d in poskusi],
         "wifi": int(define("WIFI_POSILJANJE", 0))}
    n["n_poskusov"] = max(1, len(n["poskusi"]))
    n["zagonov_skupaj"] = n["n_poskusov"] * n_alg * (n["zagonov"] + n["ogrevanje"])
    # +1 s spanja po optimizaciji, ~0,3 s pisanja v flash, ~5 s za zagon
    n["trajanje_s"] = n["zacetno"] + 5 + n["zagonov_skupaj"] * (n["spanje"] + n["opt"] + 1.3)
    return n


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
def snemaj(args):
    """Samodejno: nastavi napajalnik, izklopi in vklopi izhod (ESP32 se
    zažene in začne poskus), snema napetost/tok/moč, prepozna konec
    poskusa in izhod izklopi. Človek med poskusom ne posega."""
    os.makedirs(args.mapa, exist_ok=True)
    pot = os.path.join(args.mapa, "rigol.csv")
    nacrt = nacrt_iz_ino(args.ino)
    inst, naslov = odpri_rigol(args.rigol, args.visa_backend)
    idn = inst.query("*IDN?").strip()
    print("RIGOL:", idn, "(", naslov, ")")
    k = args.kanal
    ukaz = f":MEAS:ALL? {k}".strip()

    if args.nastavi:
        # Varnostne meje: OVP malo nad 3,3 V, OCP nad pričakovanimi konicami.
        for c in (f":OUTP {k},OFF", f":APPL {k},{args.napetost},{args.tok_omejitev}",
                  f":OUTP:OVP:VAL {k},{args.napetost + 0.3:.2f}", f":OUTP:OVP {k},ON",
                  f":OUTP:OCP:VAL {k},{args.tok_omejitev + 0.1:.2f}", f":OUTP:OCP {k},ON"):
            try:
                inst.write(c)
            except Exception as e:  # noqa: BLE001
                print(f"  opozorilo: ukaz '{c}' ni uspel: {e}")
        time.sleep(args.premor_izklop)      # ESP32 brez napajanja -> čist zagon
        print(f"Nastavljeno: {inst.query(f':APPL? {k}').strip()}")

    meta = {"zacetek": time.strftime("%Y-%m-%d %H:%M:%S"), "rigol": idn, "naslov": naslov,
            "kanal": k, "napetost_V": args.napetost, "tok_omejitev_A": args.tok_omejitev,
            "nacrt": nacrt}
    if nacrt:
        print(f"Načrt: {nacrt['n_poskusov']} poskusov x {nacrt['n_alg']} algoritmov x "
              f"({nacrt['zagonov']} + {nacrt['ogrevanje']} ogrevalnih) = "
              f"{nacrt['zagonov_skupaj']} zagonov, ~{nacrt['trajanje_s']/3600:.2f} h")
    trajanje = nacrt["trajanje_s"] if nacrt else None

    prepreci_spanje_racunalnika()
    print(f"Snemam v {pot}.  Ctrl+C (PyCharm: rdeči gumb Stop) za ročno prekinitev.\n")
    t0 = time.monotonic()
    if args.nastavi:
        inst.write(f":OUTP {k},ON")
    zadnji_visok = None        # čas zadnjega vzorca z visokim tokom
    n, napak = 0, 0
    razlog = "?"
    with open(pot, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "U_V", "I_A", "P_W"])
        try:
            while True:
                try:
                    # Čas vzorca vzamemo na sredini poizvedbe.
                    ta = time.monotonic() - t0
                    odg = inst.query(ukaz)
                    tb = time.monotonic() - t0
                    u, i, p = (float(v) for v in odg.strip().split(",")[:3])
                except Exception as e:  # noqa: BLE001
                    napak += 1
                    print("\nNapaka RIGOL:", e, file=sys.stderr)
                    time.sleep(0.5)
                    continue
                t = 0.5 * (ta + tb)
                w.writerow([f"{t:.4f}", u, i, p])
                n += 1
                if n % 20 == 0:
                    f.flush()
                    preostalo = f"  ~{max(0, trajanje - t)/60:5.1f} min do konca" if trajanje else ""
                    print(f"\r  t = {t:8.1f} s   I = {i*1000:7.2f} mA   "
                          f"P = {p*1000:7.1f} mW   vzorcev: {n}{preostalo}   ", end="")
                if i * 1000 > args.prag_visok_ma:
                    zadnji_visok = t
                # Konec: po pričakovanem trajanju (če je znano) ni bilo
                # računanja ali WiFi vsaj cas_konec_s -> ESP32 je v deep sleepu.
                miruje = zadnji_visok is not None and t - zadnji_visok > args.cas_konec_s
                if miruje and (trajanje is None or t > 0.95 * trajanje):
                    razlog = "konec poskusa (deep sleep)"
                    break
                if trajanje and miruje and t - zadnji_visok > max(300, 3 * args.cas_konec_s):
                    razlog = "ESP32 predolgo ne računa (napaka?)"
                    break
                if trajanje and t > 1.3 * trajanje + 600:
                    razlog = "preseženo pričakovano trajanje"
                    break
                if args.perioda > 0:
                    time.sleep(args.perioda)
        except KeyboardInterrupt:
            razlog = "ročno prekinjeno"
    if args.nastavi and not args.pusti_vklopljeno:
        try:
            inst.write(f":OUTP {k},OFF")
        except Exception:  # noqa: BLE001
            pass
    inst.close()
    trajanje_snemanja = time.monotonic() - t0
    meta.update({"konec": time.strftime("%Y-%m-%d %H:%M:%S"), "razlog_konca": razlog,
                 "vzorcev": n, "napak_branja": napak, "trajanje_s": trajanje_snemanja,
                 "fs_Hz": n / trajanje_snemanja if trajanje_snemanja > 0 else 0})
    with open(os.path.join(args.mapa, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"\n{razlog}. Shranjeno: {pot}  ({n} vzorcev, {meta['fs_Hz']:.1f} Hz, "
          f"napak branja: {napak})")
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
    with open(pot, "w", encoding="utf-8") as f:
        f.write("\n".join(vrstice) + "\n")
    n_rez = sum(1 for v in vrstice if v.startswith("REZ,"))
    n_konv = sum(1 for v in vrstice if v.startswith("KONV,"))
    print(f"Shranjeno: {pot}  (REZ: {n_rez}, KONV: {n_konv})")
    if n_rez != n_konv:
        print("OPOZORILO: število vrstic REZ in KONV se ne ujema.")
    return True


# ======================================================================
#  REZULTATI S STREŽNIKA SUCCULENT (WIFI_POSILJANJE 1)
# ======================================================================
def iz_succulent(args):
    """Prebere rezultate, ki jih je ESP32 poslal na strežnik succulent
    (GET /export ali neposredno data/data.csv), in jih zapiše v
    <mapa>/esp32.txt v enaki obliki kot izpis ESP32 (#POSKUS, REZ, KONV).
    Strežnik lahko hrani več poskusov; privzeto vzame zadnjega."""
    import io
    import urllib.request
    if args.vir.startswith(("http://", "https://")):
        url = args.vir.rstrip("/")
        if not url.endswith("/export"):
            url += "/export"
        zahteva = urllib.request.Request(url, headers={"Authorization": f"Bearer {args.geslo}"})
        try:
            with urllib.request.urlopen(zahteva, timeout=10) as odg:
                besedilo = odg.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"Napaka pri branju {url}: {e}")
            return False
    else:
        with open(args.vir, encoding="utf-8") as f:
            besedilo = f.read()
    vrstice = list(csv.DictReader(io.StringIO(besedilo)))
    # Oznaka prevoda: novejši program jo pošlje kot "prevod" ("poskus" je
    # indeks poskusa), starejši kot "poskus".
    kljuc_poskusa = "prevod" if vrstice and vrstice[0].get("prevod") else "poskus"
    vrstice = [v for v in vrstice if v.get(kljuc_poskusa) and v.get("i") not in (None, "")]
    if not vrstice:
        print("Na strežniku ni rezultatov.")
        return False

    poskusi = list(dict.fromkeys(v[kljuc_poskusa] for v in vrstice))   # po vrstnem redu prejema
    print("Prevodi (zagoni programa) na strežniku:")
    for ps in poskusi:
        n = len({v["i"] for v in vrstice if v[kljuc_poskusa] == ps})
        print(f"  {ps}   zapisov: {n}")
    izbran = args.poskus or poskusi[-1]
    if izbran not in poskusi:
        print(f"Poskusa '{izbran}' ni na strežniku.")
        return False
    # ponovljeno pošiljanje: za vsak i velja zadnji prejeti zapis
    zapisi = {}
    for v in vrstice:
        if v[kljuc_poskusa] == izbran:
            zapisi[int(float(v["i"]))] = v
    v0 = next(iter(zapisi.values()))

    def cel(x):
        return int(float(x))

    glava = ["zagonov", "spanje", "opt", "ogrevanje", "tock", "cilj", "seme", "resetov"]
    deli = []
    for g in glava:
        if g in v0 and v0[g] != "":
            x = v0[g]
            deli.append(f"{g}={x}s" if g in ("spanje", "opt") else
                        f"{g}={float(x):.3e}" if g == "cilj" else f"{g}={cel(x)}")
    izhod = ["#POSKUS " + " ".join(deli) + f" prevod={izbran.replace(' ', '_')} vir=succulent"]
    stolpci = [c for c in ("i", "poskus", "funkcija", "D", "alg", "zagon", "poz", "ogrev",
                           "fe", "gen", "best", "cas_ms", "fe_cilj", "ms_cilj", "np_konec",
                           "LS_NP_INIT") if c in v0]
    izhod.append("#REZ," + ",".join(stolpci))
    for i in sorted(zapisi):
        v = zapisi[i]
        polja = []
        for c in stolpci:
            x = v[c]
            polja.append(str(i) if c == "i" else f"{float(x):.6e}" if c == "best" else
                         x if c in ("funkcija", "alg") else str(cel(x)))
        izhod.append("REZ," + ",".join(polja))
    izhod.append("#KONV,i,alg,zagon,best_1 ... best_TOCK")
    for i in sorted(zapisi):
        v = zapisi[i]
        izhod.append(f"KONV,{i},{v['alg']},{cel(v['zagon'])}," + v["konv"].replace(";", ","))
    izhod.append("#KONEC_IZPISA")

    manjka = sorted(set(range(max(zapisi) + 1)) - set(zapisi))
    os.makedirs(args.mapa, exist_ok=True)
    pot = os.path.join(args.mapa, "esp32.txt")
    with open(pot, "w", encoding="utf-8") as f:
        f.write("\n".join(izhod) + "\n")
    print(f"Shranjeno: {pot}  (poskus {izbran}, REZ: {len(zapisi)})")
    if manjka:
        print(f"OPOZORILO: manjkajo zapisi i = {manjka}. Preberite jih prek USB (zajem.py preberi).")
    return True


# ======================================================================
#  BRANJE PODATKOV
# ======================================================================
def preberi_rigol(pot):
    t, p = [], []
    with open(pot) as f:
        for vr in csv.DictReader(f):
            t.append(float(vr["t_s"]))
            p.append(float(vr["P_W"]))
    return t, p


STARI_REZ = ["i", "alg", "zagon", "fe", "gen", "best", "cas_ms", "fe_cilj", "ms_cilj",
             "np_konec"]
CELA = {"i", "poskus", "D", "zagon", "poz", "ogrev", "fe", "gen", "cas_ms", "fe_cilj",
        "ms_cilj", "np_konec", "LS_NP_INIT"}


def preberi_esp(pot):
    """Iz izpisa ESP32 (USB ali succulent) pobere glavo #POSKUS ter vrstice
    REZ in KONV. Stolpci REZ se preberejo iz vrstice "#REZ,..." (glava),
    zato deluje tudi s starejšim izpisom. Izpis se ponavlja vsakih 10 s,
    zato vsak zagon vzamemo enkrat. Časovne žige Serial Monitorja ignoriramo."""
    param, rez, konv = {}, {}, {}
    stolpci = ["REZ"] + STARI_REZ
    with open(pot, encoding="utf-8", errors="replace") as f:
        for vr in f:
            vr = vr.strip()
            k = vr.find("#POSKUS")
            if k >= 0:
                for kljuc, vred in re.findall(r"(\w+)=([^\s]+)", vr[k:]):
                    param[kljuc] = vred.rstrip("s") if kljuc in ("spanje", "opt") else vred
                continue
            k = vr.find("#REZ,")
            if k >= 0:
                stolpci = vr[k + 1:].split(",")
                continue
            for oznaka in ("REZ,", "KONV,"):
                k = vr.find(oznaka)
                if k < 0 or vr[k - 1:k] == "#":
                    continue
                d = vr[k:].split(",")
                try:
                    if oznaka == "REZ,":
                        if len(d) != len(stolpci):
                            raise ValueError
                        z = {}
                        for ime, v in zip(stolpci[1:], d[1:]):
                            z[ime] = int(v) if ime in CELA else (
                                float(v) if ime == "best" else v)
                        rez[z["i"]] = z
                    else:
                        konv[int(d[1])] = [float(v) for v in d[4:]]
                except (ValueError, IndexError):
                    pass   # nepopolna vrstica (npr. prekinjen izpis)
    for i, z in rez.items():
        z["konv"] = konv.get(i, [])
        z.setdefault("ogrev", 0)
        z.setdefault("poz", -1)
        z.setdefault("poskus", 0)
        z.setdefault("funkcija", param.get("funkcija", "?"))
        z.setdefault("D", int(param.get("D", 0) or 0))
    return param, [rez[i] for i in sorted(rez)]


# ======================================================================
#  ISKANJE ZAGONOV V TOKU IN INTEGRACIJA
# ======================================================================
def najdi_zagone(t, p, min_s, max_s):
    """Poišče intervale optimizacije (visoka moč). Prag je sredina med
    nizko (spanje) in visoko (računanje) ravnjo. Čase prehodov linearno
    interpoliramo med vzorci, da je meja natančnejša od periode vzorčenja.
    Intervali zunaj [min_s, max_s] (zagon ESP32, formatiranje flasha,
    pisanje rezultatov) se zavržejo."""
    s = sorted(p)
    nizka = s[int(0.03 * (len(s) - 1))]
    # Raven računanja = mediana vzorcev, ki so očitno nad spanjem. Tako
    # kratki skoki z večjo močjo (npr. pošiljanje prek WiFi po koncu
    # poskusa) ne premaknejo praga, tudi pri kratkih preizkusnih poskusih.
    vrh = s[int(0.99 * (len(s) - 1))]
    nad = s[next((k for k, v in enumerate(s) if v > nizka + 0.25 * (vrh - nizka)), len(s) - 1):]
    visoka = nad[len(nad) // 2]
    prag = 0.5 * (nizka + visoka)

    def presecisce(k):
        if p[k] == p[k - 1]:
            return t[k]
        a = (prag - p[k - 1]) / (p[k] - p[k - 1])
        return t[k - 1] + a * (t[k] - t[k - 1])

    zagoni, zavrzeni, zacetek = [], [], None
    for k in range(1, len(p)):
        if p[k - 1] <= prag < p[k]:
            zacetek = presecisce(k)
        elif p[k - 1] > prag >= p[k] and zacetek is not None:
            konec = presecisce(k)
            if min_s <= konec - zacetek <= max_s:
                zagoni.append((zacetek, konec))
            else:
                zavrzeni.append((zacetek, konec))
            zacetek = None
    # Interval s povprečno močjo, ki je bistveno nad ravnjo računanja, ni
    # zagon algoritma (npr. WiFi s prenosom rezultatov, ~2x večja moč).
    if zagoni:
        moci = sorted(povprecje(t, p, a, b) for a, b in zagoni)
        mediana = moci[len(moci) // 2]
        zavrzeni += [z for z in zagoni if povprecje(t, p, *z) > 1.5 * mediana]
        zagoni = [z for z in zagoni if povprecje(t, p, *z) <= 1.5 * mediana]
        zavrzeni.sort()
    return zagoni, zavrzeni, prag, nizka, visoka


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
    """Dvostranski Mann-Whitneyjev (Wilcoxonov rank-sum) test.
    Uporabi scipy, če je na voljo (točna porazdelitev za majhne vzorce),
    sicer normalno aproksimacijo s popravkom za vezi in zveznost."""
    a = [v for v in a if not math.isnan(v)]
    b = [v for v in b if not math.isnan(v)]
    if len(a) < 2 or len(b) < 2:
        return NAN
    if all(v == a[0] for v in a + b):
        return 1.0
    try:
        from scipy.stats import mannwhitneyu
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:  # noqa: BLE001  (ni scipy ali neskončne vrednosti)
        pass
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


def holm(pvred):
    """Holm-Bonferronijev popravek za več primerjav."""
    m = len(pvred)
    red = sorted(range(m), key=lambda i: (math.isnan(pvred[i]), pvred[i]))
    popr = [NAN] * m
    najvecja = 0.0
    for rang, i in enumerate(red):
        if math.isnan(pvred[i]):
            continue
        najvecja = max(najvecja, min(1.0, (m - rang) * pvred[i]))
        popr[i] = najvecja
    return popr


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
    mapa = os.path.dirname(os.path.abspath(args.rigol_csv))
    with open(os.path.join(mapa, "porocilo.txt"), "w", encoding="utf-8") as dat:
        stari = sys.stdout
        sys.stdout = _Tee(stari, dat)
        try:
            return _analiza(args, mapa)
        finally:
            sys.stdout = stari


def _analiza(args, mapa):
    t, p = preberi_rigol(args.rigol_csv)
    param, rez = preberi_esp(args.esp_txt) if args.esp_txt else ({}, [])

    opt_s = float(param.get("opt", args.opt or 0)) or None
    spanje_s = float(param.get("spanje", args.spanje))
    tock = int(param.get("tock", 0)) or (len(rez[0]["konv"]) if rez else 0)
    if opt_s:   # sprejmemo le intervale, ki trajajo približno OPT_S
        min_s, max_s = 0.8 * opt_s - 0.5, 1.2 * opt_s + 0.5
    else:
        min_s, max_s = args.min_trajanje, INF

    zagoni, zavrzeni, prag, nizka, visoka = najdi_zagone(t, p, min_s, max_s)
    print(f"Poskusi: {param.get('poskusi', param.get('funkcija', '?'))}, opt = {opt_s} s, "
          f"počitek = {spanje_s} s, ogrevanje = {param.get('ogrevanje', 0)}, "
          f"cilj = {param.get('cilj', '?')}, seme = {param.get('seme', '?')}")
    fs = (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 else 0
    print(f"Posnetek: {len(t)} vzorcev, {t[-1] - t[0]:.0f} s, {fs:.1f} Hz")
    print(f"Raven spanja ~{nizka*1000:.2f} mW, računanja ~{visoka*1000:.1f} mW, "
          f"prag {prag*1000:.1f} mW")
    print(f"Najdenih zagonov v toku: {len(zagoni)} (zavrženih kratkih/dolgih "
          f"intervalov: {len(zavrzeni)}),  zapisov REZ: {len(rez)}")
    if int(param.get("resetov", 1)) > 1:
        print(f"OPOZORILO: ESP32 je med poskusom začel znova ({param['resetov']}-krat zagnan),"
              " npr. zaradi padca napetosti. Zapisi so le od zadnjega začetka.")
    # Poravnava: zapisi v flashu so od ZADNJEGA začetka poskusa, zato
    # intervale in zapise poravnamo od konca (morebitni zagoni pred
    # resetom ali pred začetkom snemanja ostanejo brez para).
    if rez and len(zagoni) != len(rez):
        print("OPOZORILO: število zagonov v toku in zapisov REZ se ne ujema!\n"
              "  Poravnam od konca; preverite graf_moc.png in stolpec 'usklajenost_s'.")
        n = min(len(zagoni), len(rez))
        zavrzeni = sorted(zavrzeni + zagoni[:len(zagoni) - n])
        zagoni, rez = zagoni[len(zagoni) - n:], rez[len(rez) - n:]

    vrstice, konv_vrstice = [], []
    for k, (t0, t1) in enumerate(zagoni):
        T = t1 - t0
        E = integriraj(t, p, t0, t1)
        # Bazna poraba: zadnji del počitka pred zagonom (brez prvih 2 s
        # po pisanju v flash in zadnjih 0,5 s pred začetkom optimizacije).
        P_baza = povprecje(t, p, t0 - spanje_s + 2.0, t0 - 0.5)
        r = rez[k] if k < len(rez) else {}
        fe = r.get("fe", 0)
        ms_cilj = r.get("ms_cilj", 0)
        dosezen = ms_cilj > 0
        E_cilj = integriraj(t, p, t0, t0 + ms_cilj / 1000.0) if dosezen else INF
        cas_esp = r.get("cas_ms", NAN) / 1000.0
        vrstice.append({
            "zagon_i": r.get("i", k),
            "poskus": f"{r.get('funkcija', '?')}_D{r.get('D', '?')}",
            "funkcija": r.get("funkcija", "?"),
            "D": r.get("D", NAN),
            "alg": r.get("alg", "?"),
            "ponovitev": r.get("zagon", -1),
            "poz": r.get("poz", -1),
            "ogrev": r.get("ogrev", 0),
            "t_zacetek_s": t0,
            "trajanje_s": T,
            "cas_esp_s": cas_esp,
            "usklajenost_s": T - cas_esp,
            "E_J": E,
            "E_mWh": E / 3.6,                         # 1 mWh = 3,6 J
            "E_neto_J": E - P_baza * T,
            "P_povp_mW": E / T * 1000,
            "P_bazna_mW": P_baza * 1000,
            "fe": fe or NAN,
            "uJ_na_fe": E / fe * 1e6 if fe else NAN,
            "uJ_neto_na_fe": (E - P_baza * T) / fe * 1e6 if fe else NAN,
            "best": r.get("best", NAN),
            "cilj_dosezen": int(dosezen),
            "ms_do_cilja": ms_cilj if dosezen else NAN,
            "E_do_cilja_J": E_cilj,
            "E_neto_do_cilja_J": E_cilj - P_baza * ms_cilj / 1000.0 if dosezen else INF,
            "E_po_cilju_J": E - E_cilj if dosezen else NAN,   # "zapravljena" energija
            "np_konec": r.get("np_konec", NAN),
        })
        # Konvergenca po energiji: best ob t = T*j/TOCK
        for j, b in enumerate(r.get("konv", []), start=1):
            tj = t0 + T * j / tock
            konv_vrstice.append({"poskus": vrstice[-1]["poskus"], "alg": r["alg"],
                                 "ponovitev": r["zagon"], "ogrev": r.get("ogrev", 0),
                                 "tocka": j, "t_s": tj - t0,
                                 "E_J": integriraj(t, p, t0, tj), "best": b})

    if not vrstice:
        print("Ni najdenih zagonov. Preverite rigol.csv (graf z --grafi) in --min-trajanje.")
        return

    # Zagon je neveljaven, če se trajanje v toku ne ujema s časom, ki ga
    # je izmeril ESP32 (napačna poravnava ali motnja v posnetku).
    for v in vrstice:
        v["veljaven"] = int(not v["ogrev"] and not (abs(v["usklajenost_s"]) > args.toleranca_s))
    neusklajeni = [v for v in vrstice if not v["ogrev"] and not v["veljaven"]]
    if neusklajeni:
        print(f"OPOZORILO: {len(neusklajeni)} zagonov ima trajanje v toku, ki se od časa ESP32 "
              f"razlikuje za več kot {args.toleranca_s} s; izločeni so iz statistike "
              f"(zagon_i: {[v['zagon_i'] for v in neusklajeni]}).")

    pot = os.path.join(mapa, "energija.csv")
    with open(pot, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(vrstice[0].keys()))
        w.writeheader()
        w.writerows(vrstice)
    if konv_vrstice:
        with open(os.path.join(mapa, "konvergenca_energija.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(konv_vrstice[0].keys()))
            w.writeheader()
            w.writerows(konv_vrstice)
    n_ogrev = sum(v["ogrev"] for v in vrstice)
    print(f"Zagoni -> {pot}  (vseh {len(vrstice)}, ogrevalnih {n_ogrev}, "
          f"veljavnih za analizo {sum(v['veljaven'] for v in vrstice)})")
    if args.podrobno:
        for v in vrstice:
            oz = "ogrev" if v["ogrev"] else ("" if v["veljaven"] else "NEVELJ")
            print(f"  {v['zagon_i']:3d} {v['poskus']:15s} {v['alg']:7s} #{v['ponovitev']:<2d} "
                  f"poz {v['poz']}  {v['trajanje_s']:6.2f} s  E = {v['E_J']:7.3f} J  "
                  f"P = {v['P_povp_mW']:6.1f} mW  best = {v['best']:.3e} {oz}")

    # ------------- analiza po poskusih (funkcija, D) -------------
    analiz = [v for v in vrstice if v["veljaven"]]
    skupine = list(dict.fromkeys(v["poskus"] for v in analiz))
    povzetek, testi, kontrola = [], [], []
    for sk in skupine:
        vr = [v for v in analiz if v["poskus"] == sk]
        povzetek_poskusa(sk, vr, povzetek, testi)
        kontrola += kontrola_pravicnosti(sk, vr)

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
                         ("kontrola.csv", kontrola)):
        if vsebina:
            with open(os.path.join(mapa, ime), "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(vsebina[0].keys()))
                w.writeheader()
                w.writerows(vsebina)
    try:
        import scipy  # noqa: F401
    except ImportError:
        print("  (scipy ni nameščen: uporabljena normalna aproksimacija; "
              "za članek priporočam 'pip install scipy')")

    print(f"\nShranjeno v {mapa}: energija.csv, povzetek.csv, testi.csv, kontrola.csv, "
          "konvergenca_energija.csv, porocilo.txt")
    if args.grafi:
        grafi(mapa, t, p, zagoni, zavrzeni, prag, vrstice, konv_vrstice, skupine)


ALG_VRSTNI_RED = ("DE", "jDE", "LSHADE")


def povzetek_poskusa(sk, vr, povzetek, testi):
    """Opisna statistika in testi za en poskus (eno funkcijo in D)."""
    algoritmi = [a for a in ALG_VRSTNI_RED if any(v["alg"] == a for v in vr)]
    po_alg = {a: [v for v in vr if v["alg"] == a] for a in algoritmi}
    metrike = [("E_J", "J"), ("E_neto_J", "J"), ("P_povp_mW", "mW"), ("P_bazna_mW", "mW"),
               ("fe", "FE"), ("uJ_na_fe", "uJ/FE"), ("uJ_neto_na_fe", "uJ/FE"),
               ("best", ""), ("ms_do_cilja", "ms"), ("E_do_cilja_J", "J"),
               ("E_po_cilju_J", "J")]
    print(f"\n================ {sk} ================")
    print("Povzetek po algoritmih (povprečje ± 95 % IZ | mediana [Q1, Q3])")
    print("  (metrike 'do cilja' samo za zagone, ki so cilj dosegli)")
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
    for a in algoritmi:
        u = sum(v["cilj_dosezen"] for v in po_alg[a])
        print(f"  uspešnost {a:7s} {u}/{len(po_alg[a])} = {100*u/len(po_alg[a]):.0f} %")
        povzetek.append({"poskus": sk, "alg": a, "metrika": "uspesnost_%", "n": len(po_alg[a]),
                         "povp": 100 * u / len(po_alg[a])})

    # Neuspeli zagoni imajo energijo do cilja = neskončno, zato so pri
    # rangiranju najslabši (običajna obravnava pri testih "čas do cilja").
    pari = [(a, b) for i, a in enumerate(algoritmi) for b in algoritmi[i + 1:]]
    if not pari:
        return
    print("Primerjave (Mann-Whitney, dvostransko, Holmov popravek; "
          "A12 < 0,5 => prvi ima manjše vrednosti)")
    for kljuc in ("best", "E_J", "E_neto_J", "uJ_na_fe", "E_do_cilja_J"):
        pv = [mann_whitney([v[kljuc] for v in po_alg[a]],
                           [v[kljuc] for v in po_alg[b]]) for a, b in pari]
        ph = holm(pv)
        print(f"  {kljuc}")
        for (a, b), p0, p1 in zip(pari, pv, ph):
            ef = a12([v[kljuc] for v in po_alg[a]], [v[kljuc] for v in po_alg[b]])
            zn = "*" if p1 < 0.05 else " "
            print(f"     {a:7s} vs {b:7s}  p = {p0:.3g}  p_Holm = {p1:.3g} {zn}  A12 = {ef:.2f}")
            testi.append({"poskus": sk, "metrika": kljuc, "alg1": a, "alg2": b, "p": p0,
                          "p_holm": p1, "A12": ef})


def kontrola_pravicnosti(sk, vr):
    """Preveri pogoje za pravično primerjavo: uravnotežen vrstni red,
    vpliv položaja v bloku na moč, enak časovni proračun, osamelci."""
    vrstice = []
    algoritmi = [a for a in ALG_VRSTNI_RED if any(v["alg"] == a for v in vr)]
    print("Kontrola pravičnosti")
    # 1) uravnoteženost: kolikokrat je bil vsak algoritem na vsakem položaju
    pozicije = sorted({v["poz"] for v in vr if v["poz"] >= 0})
    if pozicije:
        print("  položaj v bloku (število zagonov / mediana P_povp [mW]):")
        for a in algoritmi:
            deli = []
            for z in pozicije:
                m = [v["P_povp_mW"] for v in vr if v["alg"] == a and v["poz"] == z]
                s = opisna(m)
                deli.append(f"poz{z}: {len(m):2d} / {s['med']:.2f}" if s else f"poz{z}: 0")
                vrstice.append({"poskus": sk, "kontrola": f"stevilo_na_poz{z}", "alg": a,
                                "vrednost": len(m), "opomba": ""})
            # razlika med položaji glede na raztros (Kruskal-Wallis, če je scipy)
            pv = NAN
            try:
                from scipy.stats import kruskal
                skupine = [[v["P_povp_mW"] for v in vr if v["alg"] == a and v["poz"] == z]
                           for z in pozicije]
                if all(len(g) > 1 for g in skupine) and len(skupine) > 1:
                    pv = float(kruskal(*skupine).pvalue)
            except Exception:  # noqa: BLE001
                pass
            print(f"     {a:7s} " + "   ".join(deli) +
                  (f"   (Kruskal-Wallis p = {pv:.3g})" if not math.isnan(pv) else ""))
            vrstice.append({"poskus": sk, "kontrola": "vpliv_polozaja_p", "alg": a,
                            "vrednost": pv, "opomba": "p < 0,05: moč je odvisna od položaja"})
    # 2) enak časovni proračun
    tr = opisna([v["trajanje_s"] for v in vr])
    if tr:
        print(f"  trajanje merilnih oken: {tr['min']:.2f} - {tr['max']:.2f} s "
              f"(mediana {tr['med']:.2f} s)")
    # 3) osamelci (|z| > 3, Cruz 2021) - samo poročamo, ne izločamo
    for a in algoritmi:
        e = [v["E_J"] for v in vr if v["alg"] == a]
        s = opisna(e)
        if s and s["std"] > 0:
            osam = [v["zagon_i"] for v in vr if v["alg"] == a
                    and abs(v["E_J"] - s["povp"]) > 3 * s["std"]]
            if osam:
                print(f"  osamelci E_J (|z| > 3) {a}: zagon_i {osam} (niso izločeni)")
            vrstice.append({"poskus": sk, "kontrola": "osamelci_E_J", "alg": a,
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
                e = opisna([k["E_J"] for k in g])
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
                                              ("E_do_cilja_J", "energija do cilja [J]"))):
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
#  CELOTEN POSKUS BREZ POSEGANJA
# ======================================================================
def poskus(args):
    """snemaj -> (succulent) -> analiza, vse v isti mapi."""
    if not os.path.exists(args.ino):
        print(f"Ne najdem {args.ino} (potreben za načrt poskusa).")
        return False
    nacrt = nacrt_iz_ino(args.ino)
    # Kopija točno tega programa v mapo meritev (ponovljivost).
    os.makedirs(args.mapa, exist_ok=True)
    import shutil
    shutil.copy(args.ino, os.path.join(args.mapa, "ea_energija.ino"))
    ok = snemaj(args)
    esp = os.path.join(args.mapa, "esp32.txt")
    if args.succulent:
        time.sleep(2)
        a = argparse.Namespace(vir=args.succulent, mapa=args.mapa, geslo=args.geslo, poskus="")
        if not iz_succulent(a):
            print("Rezultatov s strežnika ni. Preberite jih prek USB:\n"
                  f"  python zajem.py preberi --port <PORT> --mapa {args.mapa}")
    elif nacrt and not nacrt["wifi"] and not os.path.exists(esp):
        print("\nNASLEDNJI KORAK - rezultati z ESP32 prek USB:\n"
              "  1) odprite stikalo v + vodniku RIGOL-a (izhod je že izklopljen),\n"
              "  2) ESP32 priklopite z USB na računalnik (Mac) in tam poženite\n"
              f"       python3 zajem.py preberi --mapa {os.path.basename(args.mapa)}\n"
              f"  3) esp32.txt prenesite v mapo {args.mapa} na tem računalniku,\n"
              "  4) poženite PC_4_analiza.py (ali: zajem.py analiza ... --grafi).")
    if os.path.exists(esp):
        a = argparse.Namespace(rigol_csv=os.path.join(args.mapa, "rigol.csv"), esp_txt=esp,
                               grafi=True, spanje=10.0, opt=0.0, min_trajanje=5.0,
                               toleranca_s=0.5, podrobno=False)
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
                       help="ea_energija.ino, iz katerega se prebere načrt poskusa")
        a.add_argument("--brez-nastavljanja", dest="nastavi", action="store_false",
                       help="ne spreminjaj nastavitev in ne vklapljaj izhoda (ročni način)")
        a.add_argument("--napetost", type=float, default=3.30)
        a.add_argument("--tok-omejitev", type=float, default=0.3,
                       help="A; brez WiFi zadošča 0,3 (z WIFI_POSILJANJE 1: 0,5)")
        a.add_argument("--premor-izklop", type=float, default=5.0,
                       help="koliko časa je izhod izklopljen pred začetkom (s)")
        a.add_argument("--pusti-vklopljeno", action="store_true",
                       help="po koncu ne izklopi izhoda")
        a.add_argument("--prag-visok-ma", type=float, default=20.0,
                       help="tok, nad katerim velja, da ESP32 računa (mA)")
        a.add_argument("--cas-konec-s", type=float, default=60.0,
                       help="koliko časa brez računanja pomeni konec poskusa (s)")

    a = sub.add_parser("snemaj", help="nastavi RIGOL, vklopi izhod, snema do konca poskusa")
    snemanje_argumenti(a)

    a = sub.add_parser("poskus", help="celoten poskus brez posega: snemaj + succulent + analiza")
    snemanje_argumenti(a)
    a.add_argument("--succulent", default="", help="naslov strežnika, npr. http://localhost:8080")
    a.add_argument("--geslo", default="", help="password iz configuration.yml")

    a = sub.add_parser("preberi", help="prebere rezultate z ESP32 prek USB v esp32.txt")
    a.add_argument("--port", default="", help="serijska vrata, npr. COM5 ali /dev/cu.usbserial-0001 (privzeto: samodejno)")
    a.add_argument("--mapa", required=True, help="mapa poskusa (ista kot pri snemaj)")
    a.add_argument("--baud", type=int, default=115200)
    a.add_argument("--cas", type=float, default=60.0, help="najdaljše čakanje (s)")

    a = sub.add_parser("succulent", help="prenese rezultate s strežnika succulent v esp32.txt")
    a.add_argument("vir", help="naslov strežnika (npr. http://localhost:8080) "
                               "ali pot do succulent_streznik/data/data.csv")
    a.add_argument("--mapa", required=True, help="mapa poskusa (ista kot pri snemaj)")
    a.add_argument("--geslo", default="", help="password iz configuration.yml")
    a.add_argument("--poskus", default="", help="oznaka poskusa (privzeto zadnji)")

    a = sub.add_parser("analiza", help="izračun energije, statistika, testi, grafi")
    a.add_argument("rigol_csv", help="datoteka rigol.csv iz snemanja")
    a.add_argument("esp_txt", nargs="?", help="izpis Serial Monitorja (REZ, KONV)")
    a.add_argument("--grafi", action="store_true", help="nariše grafe (matplotlib)")
    a.add_argument("--spanje", type=float, default=10.0,
                   help="SPANJE_S, če ga ni v esp32.txt")
    a.add_argument("--opt", type=float, default=0.0,
                   help="OPT_S, če ga ni v esp32.txt")
    a.add_argument("--toleranca-s", type=float, default=0.5,
                   help="največja razlika med trajanjem v toku in časom ESP32 (s)")
    a.add_argument("--podrobno", action="store_true", help="izpiši vsak zagon")
    a.add_argument("--min-trajanje", type=float, default=5.0,
                   help="najkrajši interval, ki šteje kot zagon, če OPT_S ni znan (s)")

    args = ap.parse_args()
    if args.ukaz == "seznam":
        import pyvisa
        rm = pyvisa.ResourceManager(args.visa_backend) if args.visa_backend else pyvisa.ResourceManager()
        for r in rm.list_resources():
            print(r)
    elif args.ukaz == "snemaj":
        sys.exit(0 if snemaj(args) else 1)
    elif args.ukaz == "poskus":
        sys.exit(0 if poskus(args) else 1)
    elif args.ukaz == "preberi":
        sys.exit(0 if preberi(args) else 1)
    elif args.ukaz == "succulent":
        sys.exit(0 if iz_succulent(args) else 1)
    else:
        analiza(args)


if __name__ == "__main__":
    main()
