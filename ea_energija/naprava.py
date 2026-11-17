#!/usr/bin/env python3
"""Pomožne funkcije za Mac (Arduino IDE in ESP32 prek USB): kopija flasha,
preverjanje, kaj je naloženo, branje izpisa, izračun T. Skripte Mac_*.py
so tanke ovojnice okoli teh funkcij.

Nobena funkcija tu NE ponastavi ESP32: esptool se vedno kliče z
"--before no-reset" in "--after no-reset". ESP32 mora biti zato že v
nalagalniku: ob priklopu USB držite tipko BOOT. Razlog: samodejna
ponastavitev prek linij DTR/RTS (privzeta v esptool) na nekaterih ploščicah
in gonilnikih ne drži GPIO0 nizko, zato bi se zagnal program na ESP32. Stari
program lahko ob zagonu pobriše zapise, novi pa po nalaganju ob naslednjem
zagonu začne sejo na napajanju USB.
"""
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys

import izvor

FLASH_VELIKOST = 0x400000          # 4 MB
APP_ODMIK = 0x10000                # app0 v privzeti shemi (Default 4MB with spiffs)
APP_BRANJE = 0x70000               # 458 kB: preveden program je okoli 345 kB
# Hitrost serijske povezave. 115200 je hitrost, s katero se nalagalnik ESP32
# oglasi, zato esptool hitrosti ne spreminja; to je najzanesljiveje (višje hitrosti
# na macOS z vgrajenim gonilnikom za CH340 pogosto končajo z "No more data to
# read from the serial port"). Kopija celotnega flasha traja okoli 6 min.
PRIVZETA_HITROST = 115200


def najdi_esptool():
    """Vrne seznam, s katerim se začne ukaz esptool, ali None."""
    for ime in ("esptool", "esptool.py"):
        pot = shutil.which(ime)
        if pot:
            return [pot]
    koreni = [os.path.expanduser("~/Library/Arduino15"), os.path.expanduser("~/.arduino15"),
              os.path.expandvars(r"%LOCALAPPDATA%\Arduino15")]
    for koren in koreni:
        najdeni = sorted(glob.glob(os.path.join(koren, "packages", "esp32", "tools", "esptool_py",
                                                "*", "esptool*")))
        najdeni = [n for n in najdeni if os.path.isfile(n) and not n.endswith((".md", ".py"))
                   or n.endswith("esptool.exe")]
        if najdeni:
            return [najdeni[-1]]
    r = subprocess.run([sys.executable, "-m", "esptool", "version"], capture_output=True,
                       text=True, encoding='utf-8', errors='replace')
    if r.returncode == 0:
        return [sys.executable, "-m", "esptool"]
    return None


def esptool_argumenti(port, baud, odmik, velikost, izhod, nova=True, ponastavi=False):
    """Argumenti za branje flasha. Po branju ESP32 NIKOLI ne ponastavi (--after
    no-reset). Pred branjem ga ponastavi samo s ponastavi=True (--before
    default-reset: esptool z linijama DTR/RTS sproži ponastavitev v nalagalnik;
    to je varno samo, ko uporabnik drži tipko BOOT). nova = esptool 5, sicer 4."""
    uk, nr, dr = (("read-flash", "no-reset", "default-reset") if nova else
                  ("read_flash", "no_reset", "default_reset"))
    return ["--chip", "esp32", "--port", port, "--baud", str(baud), "--before",
            dr if ponastavi else nr, "--after", nr, uk, hex(odmik), hex(velikost), izhod]


def razlozi_napako(izpis):
    """Kratka razlaga pogostih napak esptool v slovenščini (ali "")."""
    if re.search(r"Failed to connect|Wrong boot mode|waiting for packet header|"
                 r"Invalid head of packet", izpis, re.I):
        return ("ESP32 ni odgovoril. Preverite po vrsti:\n"
                "  1. Arduino IDE in njegov Serial Monitor sta zaprta (zasedata vrata).\n"
                "  2. Vrata so res ESP32: W0_preveri_namestitev.py izpiše vsa vrata z opisom (CP210x\n"
                "     ali CH340). Če je napačna, vpišite pravo v PORT_ESP32 v seja_nastavitve.py.\n"
                "  3. Izvlecite USB kabel, počakajte 2 s, DRŽITE BOOT (ne EN/RST), priklopite kabel,\n"
                "     BOOT držite, poženite skripto in tipko spustite šele, ko se izpišejo odstotki.\n"
                "  4. Drug USB kabel (za prenos podatkov) in drug USB priključek, brez razdelilca.\n"
                "  5. Stikalo RIGOL-a je odprto (ploščico napaja samo USB).")
    if re.search(r"No more data to read|serial data stream stopped|Errno 6|"
                 r"device reports readiness|Device not configured", izpis, re.I):
        return ("Povezava se je prekinila. Odklopite USB, DRŽITE BOOT, priklopite USB (po "
                "možnosti neposredno v Mac, brez razdelilca, s kablom za prenos podatkov), "
                "spustite BOOT in poženite znova. Zaprite Serial Monitor v Arduino IDE. Če se "
                "ponavlja na ploščici s čipom CH340, namestite gonilnik WCH (wch-ic.com).")
    if re.search(r"could not open port|Resource busy|Permission denied", izpis, re.I):
        return ("Vrata so zasedena: zaprite Serial Monitor v Arduino IDE in druge programe, "
                "ki uporabljajo ESP32.")
    return ""


NI_ODGOVORA = re.compile(r"Failed to connect|No serial data received|Wrong boot mode|"
                         r"waiting for packet header", re.I)


def preberi_flash(port, odmik, velikost, izhod, baud=PRIVZETA_HITROST, esptool=None,
                  ponastavi_ob_neodzivu=False, izpis=None):
    """Prebere del flasha v datoteko. ESP32 mora biti v nalagalniku (BOOT ob
    priklopu); esptool ga ne ponastavi ne pred branjem ne po njem. Med branjem
    se piše v <izhod>.delno, ki se ob uspehu preimenuje v <izhod>, ob neuspehu
    pa izbriše. Vrne (ok, izpis); ob neuspehu je izpisu dodana razlaga."""
    esptool = esptool or najdi_esptool()
    if not esptool:
        return False, ("Ne najdem esptool. Namestite ga: python3 -m pip install esptool "
                       "(ali uporabite Arduino IDE z jedrom esp32).")
    delno = izhod + ".delno"
    besedilo = ""
    poskusi = [False] + ([True] if ponastavi_ob_neodzivu else [])
    for ponastavi in poskusi:
        if ponastavi:
            msg = ("ESP32 brez ponastavitve ni odgovoril. Ponastavljam ga v nalagalnik (DTR/RTS); "
                   "tipka BOOT mora biti še vedno pritisnjena ...")
            (izpis or print)(msg)
            besedilo += "\n" + msg + "\n"
        for nova in (True, False):
            if os.path.exists(delno):
                os.remove(delno)
            r = subprocess.run(esptool + esptool_argumenti(port, baud, odmik, velikost, delno, nova,
                                                           ponastavi),
                               capture_output=True, text=True, encoding='utf-8', errors='replace')
            zadnji = r.stdout + r.stderr
            if r.returncode == 0 and os.path.isfile(delno):
                os.replace(delno, izhod)
                return True, besedilo + zadnji
            if not re.search(r"invalid choice|No such command|Usage:|unrecognized|no such option",
                             zadnji, re.I):
                break                              # drug razlog (vrata, BOOT ...): ne ponavljaj
        besedilo += zadnji
        if not NI_ODGOVORA.search(zadnji):
            break                                  # ponastavitev ne bi pomagala
    if os.path.exists(delno):
        os.remove(delno)
    razlaga = razlozi_napako(besedilo)
    return False, besedilo + ("\n" + razlaga if razlaga else "")


def najdi_vrata(podana=""):
    """Serijska vrata ESP32. Brez podanih poišče edina primerna."""
    if podana:
        return podana
    import zajem
    vrata = zajem.najdi_serijska_vrata()
    if vrata:
        return vrata
    try:
        from serial.tools import list_ports
        kandidati = [p.device for p in list_ports.comports()
                     if any(k in (p.description + p.hwid).upper() for k in
                            ("CP210", "CH340", "CH910", "USB SERIAL", "FTDI", "SILICON LABS"))]
        if len(kandidati) == 1:
            return kandidati[0]
    except ImportError:
        pass
    return ""


def esp32_priklopljen(nastavljena_vrata=""):
    """Ali je ESP32 trenutno priklopljen prek USB (njegova serijska vrata obstajajo)."""
    try:
        from serial.tools import list_ports
        prisotna = [p.device for p in list_ports.comports()]
    except ImportError:
        prisotna = None
    if nastavljena_vrata:
        return nastavljena_vrata in prisotna if prisotna is not None else os.path.exists(
            nastavljena_vrata)
    return bool(najdi_vrata(""))


def sha256_datoteke(pot):
    h = hashlib.sha256()
    with open(pot, "rb") as f:
        for kos in iter(lambda: f.read(1 << 20), b""):
            h.update(kos)
    return h.hexdigest()


OZNAKA_RE = re.compile(rb"(?:git:[0-9a-f]{12}(?:\+spremembe)? src:[0-9a-f]{12} nacrt:\d red:\d"
                       rb"|rocno [A-Z][a-z]{2} [ \d]\d \d{4} \d\d:\d\d:\d\d)")
FQBN_RE = re.compile(rb"esp32:esp32:esp32:[A-Za-z0-9=,_.+-]+")


def poisci_v_sliki(slika):
    """Oznake prevoda in FQBN-ji, najdeni v binarni sliki programa."""
    return (sorted({m.decode() for m in OZNAKA_RE.findall(slika)}),
            sorted({m.decode() for m in FQBN_RE.findall(slika)}))


def preveri_sliko(slika, pricakovana_oznaka):
    """Primerja sliko programa na ESP32 s pričakovano oznako (iz ea_prevod.h).
    Vrne (ok, sporocila)."""
    oznake, fqbni = poisci_v_sliki(slika)
    sp = [f"Oznake prevoda v sliki: {oznake or 'nobene'}", f"FQBN v sliki: {fqbni or 'noben'}"]
    ok = True
    if pricakovana_oznaka not in oznake:
        ok = False
        sp.append(f"NAPAKA: v sliki ni pričakovane oznake '{pricakovana_oznaka}'. Naložen je "
                  "drug program (ali ste po pripravi spremenili kodo / pozabili Upload).")
    elif len(oznake) > 1:
        ok = False
        sp.append("NAPAKA: v sliki je več oznak prevoda (ostanek starega programa?).")
    if not fqbni:
        ok = False
        sp.append("NAPAKA: v sliki ni FQBN (program ni preveden z jedrom esp32 3.x?).")
    for f in fqbni:
        for n in izvor.napake_plosce(f):
            ok = False
            sp.append(f"NAPAKA nastavitve plošče: {n}. Popravite meni Tools in ponovno Upload.")
    if ok:
        sp.append("V redu: naložen je program, ki ga je pripravil pripravi.py, z zahtevanimi "
                  "nastavitvami plošče.")
    return ok, sp


def predlagaj_T(rez):
    """Iz zapisov preizkusa verige: za vsako celico (funkcija, D) v načinu FE
    mediana trajanja neogrevalnih zagonov in iz nje T (celo število sekund,
    najmanj 1 s). Vrne seznam (funkcija, D, mediana_s, T_us) v vrstnem redu
    pojavljanja."""
    celice = list(dict.fromkeys((z["funkcija"], z["D"]) for z in rez if z["nacin"] == "FE"))
    izhod = []
    for fun, d in celice:
        tr = sorted(z["cas_us"] / 1e6 for z in rez if z["nacin"] == "FE" and not z["ogrev"]
                    and (z["funkcija"], z["D"]) == (fun, d))
        if not tr:
            continue
        med = tr[len(tr) // 2]
        izhod.append((fun, d, med, max(1, int(med + 0.5)) * 1000000))   # .5 navzgor
    return izhod


def besedilo_ea_T(predlogi, vir_sha256, vir_prevod, datum):
    """Vsebina ea_T.h. predlogi iz predlagaj_T; zahtevane so vse štiri celice."""
    zahtevane = [("rastrigin", 10), ("rastrigin", 20), ("rosenbrock", 10), ("rosenbrock", 20)]
    slovar = {(f, d): (m, t) for f, d, m, t in predlogi}
    manjka = [c for c in zahtevane if c not in slovar]
    if manjka:
        raise ValueError(f"V preizkusu verige manjkajo celice v načinu FE: {manjka}")
    v = ["// ====================================================================",
         "//  ea_T.h - USTVARJENO z Mac_5_nastavi_T.py; v git, ne urejajte ročno.",
         "//  T (v mikrosekundah) za kampanjo: mediana trajanja neogrevalnih zagonov",
         "//  FE te celice v preizkusu verige, zaokrožena na celo sekundo.",
         f"//  Datum: {datum}",
         f"//  Vir: esp32.txt, SHA-256 {vir_sha256}",
         f"//  Prevod preizkusa verige: {vir_prevod}",
         "// ===================================================================="]
    for f, d in zahtevane:
        m, t = slovar[(f, d)]
        v.append(f"#define T_{f.upper()}_D{d}_US  {t}ULL   // mediana {m:.3f} s")
    return "\n".join(v) + "\n"


def odpri_serijska(port, baud=115200):
    """Serijska vrata brez ponastavitve ESP32 (DTR in RTS ostaneta izklopljena,
    da se ESP32 ob odprtju ne zažene znova). pyserial, če je nameščen, sicer
    termios (macOS, Linux)."""
    import zajem
    try:
        import serial
        ser = serial.serial_for_url(port, do_not_open=True)
        ser.baudrate = baud
        ser.timeout = 1.0
        ser.dtr = False
        ser.rts = False
        ser.open()
        return ser
    except ImportError:
        return zajem._PosixSerijska(port, baud)


def izbrisi_zapise(ser, najdlje_s=600, ura=None, izpis=print):
    """Pobriše zapise na ESP32 po protokolu programa: počaka konec izpisa
    (#KONEC_IZPISA), pošlje 'n', počaka na poziv za potrditev in pošlje 'n'
    še enkrat v istem oknu 10 s. Vrne True, ko program potrdi brisanje.
    Zapisov NE pobriše, če potrditve ni; pošlje se največ en par ukazov."""
    import time
    ura = ura or time.monotonic
    konec = ura() + najdlje_s
    faza = 0
    while ura() < konec:
        vr = ser.readline().decode("utf-8", errors="replace").strip()
        if not vr:
            continue
        izpis("  < " + vr[:100])
        if faza == 0 and vr.startswith("#KONEC_IZPISA"):
            ser.write(b"n")
            faza = 1
        elif faza == 1 and "pošljite 'n' še enkrat" in vr:
            ser.write(b"n")
            faza = 2
        elif faza == 2 and "Zapisi pobrisani" in vr:
            return True
    return False


# ======================================================================
#  KORAKI (uporabljajo jih skripte Mac_*.py in ukazna vrstica:
#  python3 naprava.py <ukaz> ...). Vrnejo izhodno kodo, nič ne kličejo sys.exit.
# ======================================================================
def kopija_flash(mapa, port="", izpis=print, baud=PRIVZETA_HITROST):
    """Cel flash (4 MB) v <mapa>/kopija_flash.bin (brez ponastavitve ESP32) in
    izvleček starih zapisov v <mapa>/zapisi. Mapa z že dokončano kopijo se ne
    prepiše; mapo prejšnjega neuspelega poskusa (brez kopije) se lahko uporabi."""
    kopija = os.path.join(mapa, "kopija_flash.bin")
    if os.path.exists(os.path.join(mapa, "kopija_flash.sha256")) or os.path.exists(kopija):
        izpis(f"V mapi {mapa} je že kopija flasha. Ne prepisujem: izberite drugo ime.")
        return 1
    port = najdi_vrata(port)
    if not port:
        izpis("Ne najdem serijskih vrat ESP32. Priklopite USB (z BOOT) ali podajte vrata.")
        return 1
    os.makedirs(mapa, exist_ok=True)
    trajanje = "okoli 6 min" if baud <= 115200 else "okoli 2 min"
    izpis(f"Vrata: {port}, hitrost {baud}. Berem {FLASH_VELIKOST} B flasha v {kopija} "
          f"({trajanje}; ESP32 se ne ponastavi) ...")
    ok, tekst = preberi_flash(port, 0, FLASH_VELIKOST, kopija, baud=baud)
    izpis(tekst[-1500:])
    if not ok:
        izpis("Branje ni uspelo (razlaga zgoraj). Kopije ni; mapo lahko uporabite znova.")
        return 1
    if os.path.getsize(kopija) != FLASH_VELIKOST:
        izpis(f"Kopija ima {os.path.getsize(kopija)} B namesto {FLASH_VELIKOST} B; ni popolna.")
        return 1
    sha = sha256_datoteke(kopija)
    with open(os.path.join(mapa, "kopija_flash.sha256"), "x", encoding="utf-8") as f:
        f.write(f"{sha}  kopija_flash.bin\n")
    izpis(f"Kopija je popolna, SHA-256 {sha}.\nIzvlečem stare zapise ...")
    r = subprocess.run([sys.executable, os.path.join(izvor.MAPA, "stari_zapisi.py"), kopija,
                        "--izhod", os.path.join(mapa, "zapisi")])
    izpis("Končano." if r.returncode == 0 else
          "Kopija flasha je shranjena, izvleček zapisov pa ni uspel. Podatki so v kopiji; "
          "shranite jo.")
    izpis(f"Shranite celo mapo {mapa}. Nato odklopite USB.")
    return 0


NVS_ODMIK, NVS_VELIKOST = 0x9000, 0x5000
IMENA_STANJ = {1: "seja teče", 2: "seja končana", 3: "napaka", 4: "pripravljen",
               5: "seja prekinjena"}


def stanje_iz_nvs(nvs):
    """Zadnje veljavne vrednosti programa v NVS: {'prevod', 'stanje', 'resetov'} (ali None)."""
    import stari_zapisi
    zadnje = {"prevod": None, "stanje": None, "resetov": None}
    for veljavnost, kljuc, vred in stari_zapisi.zgodovina_nvs(nvs):
        if veljavnost == "veljaven" and kljuc in zadnje:
            zadnje[kljuc] = vred
    for k in ("stanje", "resetov"):
        if zadnje[k] is not None:
            zadnje[k] = int(zadnje[k])
    return zadnje


def oceni_stanje(st, pricakovana_oznaka, slika_ok=True):
    """Ali je ESP32 pripravljen za sejo. Vrne (ok, sporocila). Navodilo za
    zagon brez BOOT se da samo, če je v flashu res novi program (slika_ok)."""
    sp = [f"Stanje programa v NVS: oznaka '{st['prevod']}', stanje "
          f"{st['stanje']} ({IMENA_STANJ.get(st['stanje'], 'neznano')}), resetov {st['resetov']}"]
    if st["prevod"] != pricakovana_oznaka and not slika_ok:
        sp.append("NAPAKA: na ESP32 ni pričakovanega programa (glejte zgoraj). Ponovite Upload v "
                  "Arduino IDE in počakajte na 'Done uploading'. Do takrat ESP32 ne priklapljajte "
                  "brez tipke BOOT.")
        return False, sp
    if st["prevod"] != pricakovana_oznaka:
        sp.append("NAPAKA: novi program se po nalaganju še ni zagnal (v NVS je oznaka prejšnjega "
                  "programa). To je varno popraviti: odklopite USB, priklopite ga BREZ tipke BOOT, "
                  "počakajte 10 s (prvi zagon novega programa samo pripravi ploščico in zaspi), "
                  "odklopite, nato znova z BOOT in ponovite to preverjanje. Če Upload v Arduino IDE ni "
                  "končal z 'Done uploading', ga najprej ponovite.")
        return False, sp
    if st["stanje"] == 4:
        sp.append("V redu: program je pripravljen; seja se začne ob naslednjem vklopu (RIGOL).")
        return True, sp
    if st["stanje"] in (1, 5):
        sp.append("NAPAKA: seja se je že začela (ESP32 je bil vklopljen BREZ tipke BOOT po nalaganju, "
                  "npr. ob priklopu USB ali s tipko EN). Popravek: odklopite USB, priklopite ga "
                  "BREZ BOOT in počakajte 15 s (program sejo označi kot prekinjeno in začne izpisovati), "
                  "poženite Mac_6_pobrisi_zapise.py --potrjujem, odklopite, nato znova z BOOT in "
                  "ponovite to preverjanje.")
        return False, sp
    if st["stanje"] == 2:
        sp.append("NAPAKA: ta program je že izvedel celotno sejo. Če njenih zapisov še niste prebrali, "
                  "najprej Mac_4_preberi.py; nato Mac_6_pobrisi_zapise.py --potrjujem.")
        return False, sp
    sp.append("NAPAKA: program je v stanju napake ali neznanem stanju. Preberite izpis z "
              "Mac_4_preberi.py (priklop brez BOOT) in mi ga pošljite.")
    return False, sp


def preveri_nalozeno(port="", izpis=print, baud=PRIVZETA_HITROST):
    """Prebere NVS in program iz flasha (en klic esptool) in preveri oznako iz
    ea_prevod.h, nastavitve plošče in da je program pripravljen za sejo."""
    import tempfile
    pricakovano = izvor.preberi_prevod_h()
    if pricakovano is None:
        izpis("Ni ea_prevod.h. Najprej priprava (Mac_2_pripravi.py ali prevedi.py).")
        return 1
    port = najdi_vrata(port)
    if not port:
        izpis("Ne najdem serijskih vrat ESP32 (USB priklopljen? Zaprt Serial Monitor v IDE?).")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        pot = os.path.join(tmp, "app.bin")
        izpis(f"Vrata {port}, hitrost {baud}. Berem NVS in program iz flasha (okoli 50 s). "
              "Tipko BOOT držite, dokler se ne izpišejo odstotki ...")
        dolzina = APP_ODMIK + APP_BRANJE - NVS_ODMIK
        ok, tekst = preberi_flash(port, NVS_ODMIK, dolzina, pot, baud=baud,
                                  ponastavi_ob_neodzivu=True, izpis=izpis)
        if not ok:
            izpis(tekst[-1500:])
            izpis("Branje ni uspelo (razlaga zgoraj).")
            return 1
        with open(pot, "rb") as f:
            podatki = f.read()
    nvs = podatki[:NVS_VELIKOST]
    slika = podatki[APP_ODMIK - NVS_ODMIK:]
    ok, sporocila = preveri_sliko(slika, pricakovano[0])
    izpis(f"Pričakovana oznaka: {pricakovano[0]}")
    izpis("\n".join(sporocila))
    ok_st, sp_st = oceni_stanje(stanje_iz_nvs(nvs), pricakovano[0], slika_ok=ok)
    izpis("\n".join(sp_st))
    ok = ok and ok_st
    izpis("\nVSE V REDU. Odklopite USB. Seja se začne ob vklopu z RIGOL-om (stikalo zaprto)." if ok
          else "\nNe nadaljujte s snemanjem, dokler to preverjanje ne javi VSE V REDU.")
    return 0 if ok else 1


def nastavi_T(esp_pot, zapisi=False, prepisi=False, izpis=print):
    """T za kampanjo iz preizkusa verige: predlog, nato (zapisi=True) ea_T.h."""
    import time
    import zajem
    if not os.path.isfile(esp_pot):
        izpis(f"Ni {esp_pot}.")
        return 1
    try:
        param, rez = zajem.preberi_esp(esp_pot)
    except zajem.NapakaAnalize as e:
        izpis(f"NAPAKA: {e}")
        return 1
    if param["nacrt"] != "0" or param["stanje"] != "koncan":
        izpis(f"To ni končan preizkus verige (nacrt={param['nacrt']}, stanje={param['stanje']}).")
        return 1
    if any(z["crc_ok"] != 1 for z in rez) or len(rez) != int(param["zapisov_nacrt"]):
        izpis("Zapisi preizkusa verige niso popolni ali so pokvarjeni; T iz njih ne določam.")
        return 1
    predlogi = predlagaj_T(rez)
    izpis(f"Preizkus verige: {param['prevod']}")
    for fun, d, med, t_us in predlogi:
        n = sum(1 for z in rez if z["nacin"] == "FE" and not z["ogrev"]
                and (z["funkcija"], z["D"]) == (fun, d))
        izpis(f"  {fun:10s} D={d:2d}   {n} zagonov FE, mediana trajanja {med:7.3f} s  ->  "
              f"T = {t_us // 1000000} s ({t_us} us)")
    kratke = [(f, d) for f, d, m, _ in predlogi if m < 3.0]
    if kratke:
        izpis(f"OPOZORILO: celice {kratke} imajo zagone, krajše od 3 s. Pri vzorčenju 5-10 Hz je "
              "to malo vzorcev na okno; razmislite o večjem FE_max (LAB_GUIDE, korak E).")
    if not zapisi:
        izpis("Zapisal nisem nič. Če so vrednosti sprejemljive, ponovite z zapisi (--zapisi / "
              "ZAPISI = True).")
        return 0
    pot_T = os.path.join(izvor.MAPA, "ea_T.h")
    if os.path.exists(pot_T) and not prepisi:
        izpis("ea_T.h že obstaja; za prepis uporabite prepisi (--prepisi / PREPISI = True).")
        return 1
    try:
        besedilo = besedilo_ea_T(predlogi, sha256_datoteke(esp_pot), param["prevod"],
                                 time.strftime("%Y-%m-%d"))
    except ValueError as e:
        izpis(f"NAPAKA: {e}")
        return 1
    with open(pot_T, "w", encoding="utf-8", newline="\n") as f:
        f.write(besedilo)
    izpis("Zapisano: ea_T.h\n" + besedilo)
    izpis("Naslednje: git add ea_energija/ea_T.h && git commit; kopirajte ea_T.h na PC z RIGOL-om.")
    return 0


def pobrisi(port="", potrjujem=False, izpis=print):
    """Pobriše zapise na ESP32 (nepovratno) po izrecni potrditvi."""
    if not potrjujem:
        izpis("Zapisal nisem nič. Zapisi bodo nepovratno pobrisani: ko so prebrani, preneseni in "
              "preverjeni, potrdite (POTRJUJEM = True / --potrjujem).")
        return 1
    port = najdi_vrata(port)
    if not port:
        izpis("Ne najdem serijskih vrat ESP32.")
        return 1
    ser = odpri_serijska(port)
    try:
        ok = izbrisi_zapise(ser, izpis=izpis)
    finally:
        ser.close()
    izpis("Zapisi pobrisani." if ok else
          "ESP32 brisanja ni potrdil. Zapisi niso pobrisani (ali pa so; preberite jih z zajem.py preberi).")
    return 0 if ok else 1


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Koraki z ESP32 na USB (ukazna vrstica; enako počnejo skripte Mac_*.py)")
    sub = ap.add_subparsers(dest="ukaz", required=True)
    a = sub.add_parser("kopija-flash", help="cel flash + stari zapisi (držite BOOT ob priklopu USB)")
    a.add_argument("--izhod", required=True, help="NOVA mapa, npr. arhiv/flash_2026-11-17")
    a.add_argument("--port", default="")
    a.add_argument("--baud", type=int, default=PRIVZETA_HITROST)
    a = sub.add_parser("preveri-nalozeno", help="ali je na ESP32 program iz ea_prevod.h "
                                                "(držite BOOT ob priklopu USB)")
    a.add_argument("--port", default="")
    a.add_argument("--baud", type=int, default=PRIVZETA_HITROST)
    a = sub.add_parser("nastavi-T", help="T za kampanjo iz esp32.txt preizkusa verige")
    a.add_argument("esp_txt")
    a.add_argument("--zapisi", action="store_true", help="zapiši ea_T.h")
    a.add_argument("--prepisi", action="store_true", help="prepiši obstoječi ea_T.h")
    a = sub.add_parser("pobrisi", help="pobriši zapise na ESP32 (nepovratno)")
    a.add_argument("--port", default="")
    a.add_argument("--potrjujem", action="store_true",
                   help="zapisi so prebrani, preneseni in preverjeni")
    args = ap.parse_args(argv)
    if args.ukaz == "kopija-flash":
        return kopija_flash(args.izhod, args.port, baud=args.baud)
    if args.ukaz == "preveri-nalozeno":
        return preveri_nalozeno(args.port, baud=args.baud)
    if args.ukaz == "nastavi-T":
        return nastavi_T(args.esp_txt, args.zapisi, args.prepisi)
    return pobrisi(args.port, args.potrjujem)


if __name__ == "__main__":
    sys.exit(main())
