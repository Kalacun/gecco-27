# Protokol testiranja: poraba energije DE, jDE in L-SHADE na ESP32

> **Zastarelo (2026-11-16).** Postopek, ukazi in nastavitve v tej datoteki so izpred revizije.
> Veljavna navodila so v `ea_energija/LAB_GUIDE.md`. Opis strojne opreme še velja; pošiljanje
> prek WiFi, program `test_veriga`, omejitev 300 mA, priložena stara koda in stare izhodne
> datoteke ne veljajo več.

**Namen:** izmeriti električno energijo, ki jo algoritmi klasični DE, jDE in L-SHADE porabijo na mikrokontrolerju ESP32, in iz meritev dobiti številke za članek *"Joules, Not Evaluations: Energy as a Stopping Criterion for Differential Evolution on a Microcontroller"* (GECCO 2027, poster-only paper, rok 25. 1. 2027).

**Obseg:** štirje poskusi (dve funkciji × dve dimenziji). V vsakem poskusu se vsak algoritem izvede 25-krat po 60 s. Algoritmi se v vsaki ponovitvi izmenjujejo.

**Trajanje:** priprava okoli 1 ura (koraki 0–2), vsak poskus okoli 1,5 ure, analiza okoli 15 minut. Skupaj približno 8 ur, ki jih lahko razdelite na več dni.

Celotna koda je v **prilogi** na koncu tega dokumenta in v mapah `ea_energija/` in `gecco_paper/`.

---

## Kazalo

1. [Oprema in programska oprema](#1-oprema-in-programska-oprema)
2. [Fiksni pogoji meritve](#2-fiksni-pogoji-meritve)
3. [Načrt poskusov](#3-načrt-poskusov)
4. [Korak 0: priprava računalnika](#korak-0-priprava-računalnika)
5. [Korak 1: preizkus programa prek USB](#korak-1-preizkus-programa-prek-usb)
6. [Korak 2: preizkus celotne verige z RIGOL-om](#korak-2-preizkus-celotne-verige-z-rigol-om)
7. [Korak 3: izvedba enega poskusa](#korak-3-izvedba-enega-poskusa)
8. [Korak 4: merila sprejemljivosti](#korak-4-merila-sprejemljivosti)
9. [Korak 5: rezultati za članek](#korak-5-rezultati-za-članek)
10. [Organizacija in arhiviranje podatkov](#organizacija-in-arhiviranje-podatkov)
11. [Odpravljanje težav](#odpravljanje-težav)
12. [Dnevnik meritev (obrazec)](#dnevnik-meritev-obrazec)
13. [Priloga: celotna koda](#priloga-celotna-koda)

---

## 1. Oprema in programska oprema

### Strojna oprema

| Kos | Opomba |
|---|---|
| ESP32-WROOM-32 razvojna ploščica (npr. DevKitC) | **ves čas ista ploščica**, zapišite model in oznako |
| Programabilni napajalnik RIGOL z USB vmesnikom | skripta uporablja SCPI ukaz `:MEAS:ALL?` (serija DP800). Zapišite model, potrebuje ga članek |
| USB kabel za ESP32 (s prenosom podatkov) | ne samo za polnjenje |
| USB kabel za RIGOL | |
| 2 žici (ženska–banana ali ženska–krokodilček) | 3V3 in GND |
| Računalnik (Windows, Linux ali macOS) | |
| *(neobvezno)* osciloskop in sonda na GPIO4 | marker optimizacije, za lepe slike na posterju |
| *(neobvezno)* termometer | sobna temperatura v dnevnik |

### Programska oprema

| Program | Namestitev |
|---|---|
| Arduino IDE 2.x | arduino.cc |
| Paket **esp32** (Espressif Systems) | Arduino IDE → *Boards Manager* → "esp32" |
| Python 3.8 ali novejši | python.org |
| Knjižnice Python | `pip install pyvisa pyvisa-py pyserial scipy matplotlib` |
| *(Windows, če RIGOL ni viden)* NI-VISA ali RIGOL UltraSigma | z uporabo `--visa-backend ""` |

### Datoteke

```
projekt/
├── PROTOKOL.md              ta dokument
├── ea_energija/
│   ├── ea_energija.ino      program za ESP32 (DE, jDE, L-SHADE)
│   ├── zajem.py             snemanje, branje rezultatov, analiza
│   └── README.md            podroben opis programa in skripte
└── gecco_paper/
    ├── main.tex             članek
    ├── references.bib       reference
    ├── results_placeholder.tex
    ├── make_results.py      številke in slike za članek iz meritev
    ├── NAVODILA.md          navodila za članek
    └── main.pdf             predogled z ograbami
```

Arduino IDE zahteva, da je `ea_energija.ino` v mapi z enakim imenom `ea_energija/`, kar je že res.

---

## 2. Fiksni pogoji meritve

Ti pogoji morajo biti **enaki za vse štiri poskuse**. Vsako odstopanje zapišite v dnevnik.

| Pogoj | Vrednost |
|---|---|
| Napetost napajalnika | **3,30 V** |
| Tokovna omejitev | **300 mA** |
| Kanal napajalnika | CH1 (ali drug, a vedno isti) |
| Priklop | RIGOL (+) → pin **3V3**, RIGOL (−) → pin **GND** |
| USB kabel med meritvijo | **odklopljen** |
| Druge naprave na ploščici | nobene (razen sonde na GPIO4, če jo uporabljate) |
| Ploščica | vedno ista |
| Prostor | sobna temperatura, brez neposrednega sonca ali ventilatorja na ploščico |
| `SPANJE_S` | 10 |
| `OPT_S` | 60 |
| `ZAGONOV` | 25 |
| `PRAG_CILJA` | `1e-6f` |
| `TOCK` | 20 |
| `IZPIS_MED_POSKUSOM` | **0** |
| Parametri algoritmov | privzeti (ne spreminjajte) |

> **Varnost:** RIGOL in USB kabel nikoli ne smeta biti hkrati priklopljena na ESP32. Ploščica bi se napajala iz dveh virov, meritev bi bila napačna, v najslabšem primeru bi tok tekel v USB vrata računalnika. Pred vsakim priklopom preverite, da je drugi vir odklopljen.

---

## 3. Načrt poskusov

| Poskus | Mapa | `FUNKCIJA` | `DIM` | Trajanje |
|---|---|---|---|---|
| P1 | `meritve_rastrigin50` | 0 | 50 | ~90 min |
| P2 | `meritve_rastrigin100` | 0 | 100 | ~90 min |
| P3 | `meritve_rosenbrock50` | 1 | 50 | ~90 min |
| P4 | `meritve_rosenbrock100` | 1 | 100 | ~90 min |

Trajanje: (10 + 60 + 1) s × 3 algoritmi × 25 ponovitev = 5325 s ≈ 89 min, plus nekaj sekund za zagon.

Če vam zmanjka časa, lahko `ZAGONOV` znižate na 10 (~36 min na poskus), a enako za vse štiri poskuse. Za GECCO je 25 ponovitev bolj prepričljivo.

---

## Korak 0: priprava računalnika

Naredite enkrat.

1. Namestite Arduino IDE in paket **esp32**. Nato *Tools → Board → ESP32 Dev Module* in *Tools → Partition Scheme → Default 4MB with spiffs*.
2. Namestite knjižnice Python:
   ```bash
   pip install pyvisa pyvisa-py pyserial scipy matplotlib
   ```
3. Priklopite RIGOL prek USB in poiščite njegov naslov:
   ```bash
   cd projekt/ea_energija
   python zajem.py seznam
   ```
   Izpiše se nekaj takega kot `USB0::0x1AB1::0x0E11::DP8C2xxxxxxxx::INSTR`. Zapišite ga v dnevnik. Če se ne izpiše nič, glejte [Odpravljanje težav](#odpravljanje-težav).
4. Priklopite ESP32 prek USB in poiščite njegova serijska vrata:
   - Windows: *Upravitelj naprav → Vrata (COM in LPT)*, npr. `COM5`
   - Linux: `/dev/ttyUSB0` ali `/dev/ttyACM0`
   - macOS: `/dev/cu.usbserial-…`

   Zapišite jih v dnevnik.

**V redu, ko:** imate zapisan naslov RIGOL-a in serijska vrata ESP32.

---

## Korak 1: preizkus programa prek USB

Cilj je preveriti, da se program prevede, da so vsi trije algoritmi dovolj veliki za pomnilnik in da ESP32 izpisuje rezultate. RIGOL za ta korak ni potreben.

1. V `ea_energija.ino` začasno nastavite:
   ```cpp
   #define ZAGONOV    1
   #define SPANJE_S   5
   #define OPT_S      10
   #define DIM        100      // največja dimenzija, ki jo boste uporabili
   #define IZPIS_MED_POSKUSOM 1
   ```
2. Naložite program (*Upload*). Če se ustavi pri "Connecting...", držite tipko **BOOT**.
3. Odprite *Serial Monitor* (115200 baud) in pritisnite **EN**.
4. Po približno 50 s se izpišejo tri vrstice `REZ` (DE, jDE, LSHADE).
5. Po zadnjem algoritmu gre ESP32 v deep sleep in utihne. Pritisnite **EN**: ker je poskus končan, ESP32 zdaj vsakih 10 s izpiše vse rezultate. Preverite, da se izpiše blok od `#POSKUS` do `#KONEC_IZPISA`.

**V redu, ko:**
- se izpišejo tri vrstice `REZ`, ena za vsak algoritem,
- `fe` je pri vseh treh večji od 0 in `cas_ms` je ~10000,
- **ne** pojavi se `#NAPAKA: premalo pomnilnika`.

Če se pojavi `#NAPAKA`, zmanjšajte `DIM`, a potem tudi spremenite načrt poskusov in članek.

---

## Korak 2: preizkus celotne verige z RIGOL-om

Cilj je preizkusiti vezavo, snemanje, branje rezultatov in analizo na kratkem poskusu, preden porabite ure za pravega.

1. V `ea_energija.ino` nastavite:
   ```cpp
   #define ZAGONOV    2
   #define SPANJE_S   10
   #define OPT_S      10
   #define DIM        50
   #define FUNKCIJA   0
   #define IZPIS_MED_POSKUSOM 0      // pomembno: tiho!
   ```
2. Naložite program, nato izvedite **celoten Korak 3** z mapo `test_veriga`.
3. V `test_veriga/` preglejte `graf_moc.png` in izpis analize po merilih iz Koraka 4. Pri tem kratkem poskusu se zagoni dolžine 10 s pravilno prepoznajo, ker skripta dolžino vzame iz izpisa ESP32.

**V redu, ko:** analiza najde 6 zagonov (3 algoritmi × 2) in so izpolnjena vsa merila iz Koraka 4.

Iz tega koraka si zapišite tudi:
- **bazno porabo** (`P_bazna_mW`) in **moč med računanjem** (`P_povp_mW`),
- **tok v deep sleepu** po koncu poskusa (zadnja vrednost, ki jo kaže `snemaj`).

Če je tok v deep sleepu večji od 1 mA (zaradi LED na ploščici), pri pravih poskusih uporabite `--prag-konec-ma` z vrednostjo malo nad izmerjenim tokom, npr. `--prag-konec-ma 5`.

---

## Korak 3: izvedba enega poskusa

Ponovite za P1, P2, P3 in P4. Spodaj je primer za P1.

### 3.1 Nastavitev in nalaganje programa

1. V `ea_energija.ino` nastavite vrednosti iz [razdelka 2](#2-fiksni-pogoji-meritve) ter `FUNKCIJA` in `DIM` iz [načrta](#3-načrt-poskusov):
   ```cpp
   #define ZAGONOV    25
   #define SPANJE_S   10
   #define OPT_S      60
   #define DIM        50
   #define FUNKCIJA   0
   #define PRAG_CILJA 1e-6f
   #define IZPIS_MED_POSKUSOM 0
   ```
2. ESP32 priklopite prek USB in naložite program.
3. **Takoj odklopite USB kabel** (v pol minute po koncu nalaganja).

> Program se po nalaganju takoj zažene na USB napajanju. To ni problem: ker poskus ni bil zaključen, se ob vklopu z RIGOL-om začne znova od začetka. Če pa bi pustili USB priklopljen tako dolgo, da se poskus konča (pri kratkem testu iz Koraka 2 je to že po nekaj minutah), bi ESP32 ob vklopu z RIGOL-om samo izpisoval rezultate in ne bi računal. V tem primeru program preprosto znova naložite. Vsako novo nalaganje samodejno pobriše stare rezultate.

### 3.2 Priklop na RIGOL

1. Na RIGOL-u **izklopite izhod**, nastavite 3,30 V in 300 mA.
2. RIGOL (+) priklopite na pin **3V3**, RIGOL (−) na pin **GND**.
3. Preverite, da USB kabel ESP32 **ni** priklopljen.
4. Zapišite v dnevnik: datum, uro začetka, sobno temperaturo, poskus.

### 3.3 Snemanje

1. V terminalu v mapi `ea_energija`:
   ```bash
   python zajem.py snemaj --rigol "USB0::0x1AB1::...::INSTR" --mapa meritve_rastrigin50
   ```
   Če je potrebno, dodajte še `--prag-konec-ma 5` (glej Korak 2).
2. Ko skripta izpiše "Vklopite izhod RIGOL-a", **vklopite izhod**.
3. V prvih minutah preverite izpis skripte:
   - med spanjem je tok nizek (nekaj mA),
   - med optimizacijo je tok bistveno višji, nekaj deset mA (natančno vrednost ste izmerili v Koraku 2),
   - ni sporočil `Napaka RIGOL`.
4. Počakajte okoli 90 minut. **Med snemanjem ne premikajte žic in ne uporabljajte RIGOL-a.** Računalnik lahko uporabljate, a naj ne gre v spanje.
5. Skripta se ustavi sama, ko je ESP32 60 s v deep sleepu, in izpiše "poskus je končan". Če se ne ustavi (tok v deep sleepu je nad pragom), jo ustavite s **Ctrl+C**, ko tok pade in ostane nizek vsaj minuto.

### 3.4 Branje rezultatov z ESP32

1. Na RIGOL-u **izklopite izhod**, nato odklopite obe žici.
2. Priklopite USB kabel ESP32.
3. Preverite, da je *Serial Monitor* v Arduino IDE **zaprt**.
4. V terminalu:
   ```bash
   python zajem.py preberi --port COM5 --mapa meritve_rastrigin50
   ```
   Skripta v nekaj sekundah izpiše `Shranjeno: …/esp32.txt (REZ: 75, KONV: 75)`.

Število vrstic `REZ` mora biti 3 × `ZAGONOV` = 75. Če skripta ne deluje, odprite *Serial Monitor* in celoten blok od `#POSKUS` do `#KONEC_IZPISA` ročno skopirajte v `meritve_rastrigin50/esp32.txt`.

> **Rezultatov ne brišite pred analizo.** Ne pritiskajte tipke BOOT in ne nalagajte novega programa, dokler `esp32.txt` ni preverjen. Do takrat ostanejo rezultati varno v flashu ESP32.

### 3.5 Analiza

```bash
python zajem.py analiza meritve_rastrigin50/rigol.csv meritve_rastrigin50/esp32.txt --grafi
```

Izpis analize shranite v datoteko, npr. tako, da `> meritve_rastrigin50/analiza.txt` dodate na konec ukaza, ali pa izpis skopirate. Nato preverite merila iz Koraka 4.

### 3.6 Zaključek poskusa

- Izpolnite vrstico v [dnevniku](#dnevnik-meritev-obrazec).
- Mapo `meritve_rastrigin50/` kopirajte na varno mesto (npr. na disk v oblaku).
- Nadaljujte s naslednjim poskusom pri koraku 3.1.

---

## Korak 4: merila sprejemljivosti

Poskus je veljaven, če so izpolnjena **vsa** merila. Če katero ni izpolnjeno, poskus ponovite in v dnevnik zapišite razlog.

| # | Merilo | Kje preveriti | Pogoj |
|---|---|---|---|
| M1 | Število zagonov v toku | izpis analize, "Najdenih zagonov v toku" | = 3 × `ZAGONOV` |
| M2 | Število rezultatov z ESP32 | izpis analize, "vrstic REZ" | = M1, brez opozorila "se ne ujema" |
| M3 | Ujemanje trajanja | `energija.csv`: `trajanje_s` in `cas_esp_s` | razlika < 0,3 s pri vseh zagonih |
| M4 | Pravilna segmentacija | `graf_moc.png` | vsa obarvana okna so na platojih računanja, barve si sledijo DE, jDE, L-SHADE |
| M5 | Stabilna napetost | `rigol.csv`, stolpec `U_V` | vse vrednosti 3,29–3,31 V |
| M6 | Stabilna bazna poraba | `energija.csv`, `P_bazna_mW` | vse vrednosti znotraj ±10 % mediane |
| M7 | Hitrost vzorčenja | `t_s` v `rigol.csv`, ali vrstica `fs` v izpisu `make_results.py` | ≥ 5 Hz |
| M8 | Brez napak med snemanjem | izpis `snemaj` | ni vrstic `Napaka RIGOL` |
| M9 | Brez izpada | izpis analize | ni opozoril, ESP32 se ni resetiral med poskusom |

Za hitro preverjanje M3, M5 in M6 lahko poženete:

```bash
python - <<'EOF'
import csv, statistics as st
m = "meritve_rastrigin50"
e = list(csv.DictReader(open(f"{m}/energija.csv")))
r = list(csv.DictReader(open(f"{m}/rigol.csv")))
d = max(abs(float(v["trajanje_s"]) - float(v["cas_esp_s"])) for v in e)
u = [float(v["U_V"]) for v in r]
b = [float(v["P_bazna_mW"]) for v in e]
t = [float(v["t_s"]) for v in r]
print(f"M3 največja razlika trajanja: {d:.3f} s   {'OK' if d < 0.3 else 'NI OK'}")
print(f"M5 napetost: {min(u):.3f}-{max(u):.3f} V   {'OK' if min(u) >= 3.29 and max(u) <= 3.31 else 'NI OK'}")
med = st.median(b); od = max(abs(x - med) / med for x in b)
print(f"M6 bazna poraba: mediana {med:.2f} mW, največje odstopanje {100*od:.1f} %   {'OK' if od < 0.1 else 'NI OK'}")
fs = (len(t) - 1) / (t[-1] - t[0])
print(f"M7 vzorčenje: {fs:.1f} Hz   {'OK' if fs >= 5 else 'NI OK'}")
EOF
```

(Na Windows namesto `python - <<'EOF'` shranite vsebino v datoteko `preveri.py` in poženite `python preveri.py`.)

---

## Korak 5: rezultati za članek

Ko so vsi štirje poskusi veljavni:

1. V mapi `gecco_paper`:
   ```bash
   python make_results.py ../ea_energija/meritve_rastrigin50 ../ea_energija/meritve_rastrigin100 \
                          ../ea_energija/meritve_rosenbrock50 ../ea_energija/meritve_rosenbrock100
   ```
   Ustvari `results.tex`, `fig_convergence.pdf` in `fig_trace.pdf` ter izpiše vse številke, ki gredo v besedilo.
2. Preverite izpis: `fs` pri vseh poskusih ≥ 5 Hz, enako število zagonov za vse algoritme, brez opozorila o različnih nastavitvah.
3. Prevedite članek (Overleaf ali `latexmk -pdf main.tex`).
4. Dopolnite rdeče označena mesta: model RIGOL-a, interpretacijo rezultatov in zaključni stavek. Podrobnosti so v `gecco_paper/NAVODILA.md`.
5. Preverite seznam pred oddajo v `NAVODILA.md`: 4 strani, anonimnost, brez rdečih oznak.

---

## Organizacija in arhiviranje podatkov

Po vseh poskusih mora biti struktura taka:

```
ea_energija/
├── meritve_rastrigin50/
│   ├── rigol.csv                   surovi podatki napajalnika   (NE BRIŠI)
│   ├── esp32.txt                   surovi rezultati ESP32       (NE BRIŠI)
│   ├── analiza.txt                 izpis analize
│   ├── energija.csv                energija po zagonih
│   ├── povzetek.csv, testi.csv     statistika
│   ├── konvergenca_energija.csv
│   └── graf_moc.png, graf_konvergenca_energija.png, graf_energija.png
├── meritve_rastrigin100/  …
├── meritve_rosenbrock50/  …
└── meritve_rosenbrock100/ …
```

- `rigol.csv` in `esp32.txt` sta **surova podatka**. Vse ostalo se da iz njiju vedno znova izračunati.
- Vrstica `#POSKUS` v `esp32.txt` vsebuje oznako prevoda (`prevod=…`), ki pove, s katero različico programa je bil poskus narejen.
- Shranite tudi točno tisto `ea_energija.ino`, s katero so bile narejene meritve, npr. kot kopijo v vsaki mapi meritev.
- Po sprejemu članka objavite kodo in surove podatke (članek to obljublja).

---

## Odpravljanje težav

| Težava | Vzrok in rešitev |
|---|---|
| Nalaganje obstane pri "Connecting..." | med nalaganjem držite tipko BOOT |
| `#NAPAKA: premalo pomnilnika` | prevelik `DIM`. Zmanjšajte ga (in posodobite načrt) |
| `zajem.py seznam` ne najde RIGOL-a | preverite USB kabel. Na RIGOL-u izberite USB kot vmesnik. Na Windows namestite NI-VISA ali UltraSigma in dodajte `--visa-backend ""` |
| `Napaka RIGOL` pri vsaki poizvedbi | drug model: pri enokanalnih `--kanal ""`, sicer preverite ukaz `:MEAS:ALL?` v priročniku |
| Med optimizacijo je tok skoraj 0 | ESP32 se ne zažene. Preverite, ali je žica na pinu 3V3 (ne 5V/VIN) in ali je izhod vklopljen |
| RIGOL preklopi v CC (tokovna omejitev) | omejitev je prenizka ali je kratek stik. Izklopite in preverite vezavo |
| `snemaj` se ne ustavi sam | tok v deep sleepu je nad pragom. Ctrl+C ali `--prag-konec-ma` |
| `preberi` javi "Ni celotnega izpisa" | poskus ni bil zaključen (izklop pred koncem). Ponovite poskus |
| `preberi` ne odpre vrat | Serial Monitor je odprt ali so vrata napačna. Zaprite ga |
| Analiza: "število zagonov … se ne ujema" | snemanje se je začelo po vklopu izhoda, ali pa se je ESP32 vmes resetiral (preverite tokovno omejitev). Poskus ponovite |
| Ob vklopu z RIGOL-om ESP32 samo izpisuje in ne računa | v flashu je končan poskus. Za nov poskus pritisnite BOOT (na USB) ali znova naložite program |

---

## Dnevnik meritev (obrazec)

Skopirajte v ločeno datoteko ali natisnite.

**Splošno**

| Polje | Vrednost |
|---|---|
| Ploščica (model, oznaka) | |
| Napajalnik (model, serijska št.) | |
| VISA naslov | |
| Serijska vrata ESP32 | |
| Različica Arduino ESP32 paketa | |
| Bazna poraba iz Koraka 2 [mW] | |
| Tok v deep sleepu iz Koraka 2 [mA] | |

**Poskusi**

| Poskus | Datum | Začetek | Konec | Temp. [°C] | M1–M9 OK? | Ponovljeno? | Opombe |
|---|---|---|---|---|---|---|---|
| test_veriga | | | | | | | |
| P1 Rastrigin 50 | | | | | | | |
| P2 Rastrigin 100 | | | | | | | |
| P3 Rosenbrock 50 | | | | | | | |
| P4 Rosenbrock 100 | | | | | | | |

---

## Priloga: celotna koda

Spodaj je celotna koda vseh treh programov, enaka datotekam v mapah `ea_energija/` in `gecco_paper/`. Članek (`main.tex`, `references.bib`, `results_placeholder.tex`) je samo v mapi `gecco_paper/`.

### Priloga A: Program za ESP32 (`ea_energija/ea_energija.ino`, 637 vrstic)

Arduino IDE, plošča ESP32 Dev Module. Nastavitve poskusa so na vrhu datoteke.

```cpp
// ====================================================================
//  DE, jDE in L-SHADE na ESP32 - meritev porabe energije
//  Arduino IDE, plošča: "ESP32 Dev Module"
//
//  V vsakem "zagonu" se zaporedoma izvedejo vsi izbrani algoritmi
//  (DE, jDE, L-SHADE, DE, jDE, L-SHADE, ...). Izmenjevanje zagotovi,
//  da vse algoritme enako prizadenejo morebitne spremembe temperature
//  ali napajanja med dolgim poskusom.
//
//  En korak poskusa:
//    SPANJE_S light sleep  (bazna poraba)
//    OPT_S optimizacija    (tu merimo energijo; GPIO4 = 1)
//    1 s light sleep       (loči optimizacijo od pisanja v flash)
//    zapis rezultata v flash
//
//  POTEK DELA (podrobno v README.md):
//   1) Naložite program prek USB, nato USB ODKLOPITE.
//   2) ESP32 priklopite na RIGOL (3,3 V na pin 3V3, GND na GND),
//      na PC-ju poženite "python zajem.py snemaj ..." in vklopite izhod.
//   3) Ko je vse končano, gre ESP32 v deep sleep (tok pade skoraj na 0).
//   4) Izklopite RIGOL, priklopite USB, odprite Serial Monitor (115200).
//      ESP32 vsakih 10 s izpiše shranjene rezultate.
//   5) Nov poskus: tipka BOOT ali ukaz "n" v Serial Monitorju.
//      Nov poskus se začne tudi, če naložite nov program.
// ====================================================================
#include "esp_sleep.h"
#include <Preferences.h>
#include <LittleFS.h>

// ======================= NASTAVITVE POSKUSA =========================
#define ZAGONOV    10     // ponovitev VSAKEGA algoritma
#define SPANJE_S   10     // spanje pred vsako optimizacijo (s)
#define OPT_S      60     // trajanje ene optimizacije (s)
#define DIM        50     // dimenzija problema (do 100)
#define FUNKCIJA   0      // 0 = Rastrigin, 1 = Rosenbrock

// Kateri algoritmi se izvajajo in v kakšnem vrstnem redu:
// 0 = klasični DE, 1 = jDE, 2 = L-SHADE
const uint8_t ALGORITMI[] = {0, 1, 2};

// Cilj za "energijo do cilja": prvi trenutek, ko je best <= PRAG_CILJA.
// Pri D = 50 Rastrigina v 60 s verjetno ne bo rešen do 1e-6, zato je
// smiselno nastaviti tudi bolj dosegljiv cilj (npr. 1e0 ali 1e1).
#define PRAG_CILJA 1e-6f

// Število točk konvergenčne krivulje (best ob t = OPT_S*k/TOCK, k=1..TOCK)
#define TOCK       20

// ---- parametri klasičnega DE (DE/rand/1/bin) ----
#define DE_NP      100
#define DE_F       0.5f
#define DE_CR      0.9f

// ---- parametri jDE (Brest in sod., 2006) ----
#define JDE_NP     100
#define JDE_TAU1   0.1f
#define JDE_TAU2   0.1f
#define JDE_FL     0.1f
#define JDE_FU     0.9f

// ---- parametri L-SHADE (Tanabe in Fukunaga, 2014) ----
// Originalno je NP_init = 18*D. To pri D = 50 pomeni 900 posameznikov
// in s 2,6-kratnim arhivom ~830 kB RAM, česar ESP32 nima (~300 kB).
// Zato NP_init omejimo tako, da pomnilnik ostane pod ~170 kB.
// To odstopanje od originala navedite v članku!
#define LS_NP_INIT  ((18 * DIM < 9200 / DIM) ? 18 * DIM : 9200 / DIM)
#define LS_NP_MIN   4
#define LS_H        6       // velikost zgodovinskega spomina
#define LS_P        0.11f   // delež najboljših za current-to-pbest
#define LS_RARC     2.6f    // velikost arhiva = LS_RARC * NP

// ---- strojna oprema ----
#define MARKER     4      // GPIO, ki je 1 med optimizacijo (za osciloskop)
#define TIPKA_BOOT 0      // tipka BOOT na ploščici (GPIO0)

// 1 = med poskusom izpisuj napredek na UART (samo za preizkus prek USB!)
// 0 = med poskusom popolnoma tiho (za pravo meritev z RIGOL-om)
#define IZPIS_MED_POSKUSOM 0
// ====================================================================

#define N_ALG   (sizeof(ALGORITMI) / sizeof(ALGORITMI[0]))
#define N_REZ   (ZAGONOV * N_ALG)
#define PI_F    3.14159265f
const char *IME_ALG[] = {"DE", "jDE", "LSHADE"};

// Največja velikost populacije, ki jo potrebuje katerikoli algoritem
#define MAX3(a, b, c) ((a) > (b) ? ((a) > (c) ? (a) : (c)) : ((b) > (c) ? (b) : (c)))
#define NP_MAX   MAX3(DE_NP, JDE_NP, LS_NP_INIT)
#define ARH_MAX  ((int)(LS_RARC * LS_NP_INIT) + 1)

// ======================= SHRANJEVANJE V FLASH =======================
// Stanje poskusa hranimo v NVS (Preferences), rezultate pa v datoteki
// /rez.bin na LittleFS (privzeta particija ~1,4 MB). Oboje preživi
// izklop napajanja.
#define DATOTEKA "/rez.bin"
#define STANJE_TECE    1   // poskus se izvaja (ali je bil prekinjen)
#define STANJE_KONCAN  2   // vsi zagoni so končani
#define STANJE_NAPAKA  3   // premalo pomnilnika

struct Rezultat {          // en zagon enega algoritma (108 bajtov)
  uint8_t  alg;            // 0 = DE, 1 = jDE, 2 = L-SHADE
  uint8_t  zagon;          // številka ponovitve
  uint16_t np_konec;       // velikost populacije ob koncu (L-SHADE jo manjša)
  uint32_t fe;             // število evalvacij
  uint32_t gen;            // število generacij
  uint32_t cas_ms;         // dejanski čas optimizacije
  uint32_t fe_cilj;        // evalvacij do best <= PRAG_CILJA (0 = ni doseženo)
  uint32_t ms_cilj;        // milisekund do cilja (0 = ni doseženo)
  float    best;           // najboljša najdena vrednost
  float    konv[TOCK];     // best ob t = OPT_S*k/TOCK
};
Rezultat rezultati[N_REZ];
Preferences flash;

// Oznaka prevoda: ob vsakem novem nalaganju je drugačna,
// zato se stari rezultati samodejno pobrišejo.
const char *OZNAKA_PREVODA = __DATE__ " " __TIME__;

// ======================= POMNILNIK ALGORITMOV =======================
// Populacijo hranimo kot polje kazalcev na vrstice. Prednosti:
//  - ob selekciji samo zamenjamo kazalca (brez kopiranja D števil),
//  - vrstice so majhne, zato ESP32 ne potrebuje velikega
//    neprekinjenega bloka pomnilnika.
// Vse alociramo ENKRAT ob zagonu, da malloc ne vpliva na meritve.
float **X;        // trenutna populacija
float **U;        // poskusni vektorji
float **A;        // arhiv (samo L-SHADE)
float *fx, *fu;   // vrednosti kriterijske funkcije
float *Fpar, *CRpar;   // F in CR posameznikov (jDE)
float *Ftr, *CRtr;     // F in CR, uporabljena za poskusni vektor
int   *idx;            // indeksi, urejeni po kakovosti (L-SHADE)
float *SF, *SCR, *Sdf; // uspešni F, CR in izboljšave (L-SHADE)

bool alociraj() {
  X = (float **)malloc(NP_MAX * sizeof(float *));
  U = (float **)malloc(NP_MAX * sizeof(float *));
  A = (float **)malloc(ARH_MAX * sizeof(float *));
  if (!X || !U || !A) return false;
  for (int i = 0; i < NP_MAX; i++) {
    X[i] = (float *)malloc(DIM * sizeof(float));
    U[i] = (float *)malloc(DIM * sizeof(float));
    if (!X[i] || !U[i]) return false;
  }
  for (int i = 0; i < ARH_MAX; i++) {
    A[i] = (float *)malloc(DIM * sizeof(float));
    if (!A[i]) return false;
  }
  fx = (float *)malloc(NP_MAX * sizeof(float));
  fu = (float *)malloc(NP_MAX * sizeof(float));
  Fpar = (float *)malloc(NP_MAX * sizeof(float));
  CRpar = (float *)malloc(NP_MAX * sizeof(float));
  Ftr = (float *)malloc(NP_MAX * sizeof(float));
  CRtr = (float *)malloc(NP_MAX * sizeof(float));
  idx = (int *)malloc(NP_MAX * sizeof(int));
  SF = (float *)malloc(NP_MAX * sizeof(float));
  SCR = (float *)malloc(NP_MAX * sizeof(float));
  Sdf = (float *)malloc(NP_MAX * sizeof(float));
  return fx && fu && Fpar && CRpar && Ftr && CRtr && idx && SF && SCR && Sdf;
}

// ======================= NAKLJUČNA ŠTEVILA ==========================
// xorshift32: preprost, hiter, isto seme = isti rezultat.
uint32_t rng;
inline float rnd() {                   // enakomerno v [0, 1)
  rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
  return (rng >> 8) * (1.0f / 16777216.0f);
}
inline int rndi(int n) { return (int)(rnd() * n); }   // celo v [0, n)

// Normalna porazdelitev N(m, s) - Box-Mullerjeva transformacija
float rnd_normal(float m, float s) {
  float u1 = rnd();
  if (u1 < 1e-7f) u1 = 1e-7f;          // log(0) ni definiran
  return m + s * sqrtf(-2.0f * logf(u1)) * cosf(2.0f * PI_F * rnd());
}

// Cauchyjeva porazdelitev C(m, s)
float rnd_cauchy(float m, float s) {
  return m + s * tanf(PI_F * (rnd() - 0.5f));
}

// ======================= TESTNI FUNKCIJI ============================
// Obe imata globalni minimum 0. Vse v float (ESP32 ima FPU samo za float).
float kriterij(const float *x) {
  float s = 0.0f;
  if (FUNKCIJA == 0) {                 // Rastrigin, meje [-5.12, 5.12]
    s = 10.0f * DIM;
    for (int j = 0; j < DIM; j++)
      s += x[j] * x[j] - 10.0f * cosf(2.0f * PI_F * x[j]);
  } else {                             // Rosenbrock, meje [-30, 30]
    for (int j = 0; j < DIM - 1; j++) {
      float a = x[j + 1] - x[j] * x[j];
      float b = 1.0f - x[j];
      s += 100.0f * a * a + b * b;
    }
  }
  return s;
}
const float SPOD = (FUNKCIJA == 0) ? -5.12f : -30.0f;   // spodnja meja
const float ZGOR = (FUNKCIJA == 0) ?  5.12f :  30.0f;   // zgornja meja

// ======================= SPREMLJANJE ZAGONA =========================
// Skupno za vse algoritme: štetje evalvacij, najboljša vrednost,
// trenutek dosega cilja in točke konvergenčne krivulje.
struct Sledenje {
  uint32_t t0, fe, fe_cilj, us_cilj;
  float best;
  int k;                               // naslednja točka konvergence
} sl;
Rezultat *trenutni;

inline float oceni(const float *x) {
  float f = kriterij(x);
  sl.fe++;
  if (f < sl.best) {
    sl.best = f;
    // Prvi doseg cilja si zapomnimo (micros kličemo le enkrat).
    if (sl.fe_cilj == 0 && f <= PRAG_CILJA) {
      sl.fe_cilj = sl.fe;
      sl.us_cilj = micros() - sl.t0;
    }
  }
  return f;
}

// Pokliče se enkrat na generacijo. Zabeleži točke konvergence in
// vrne true, ko je čas potekel. Vrne tudi pretečeni delež časa.
bool konec_casa(float *delez) {
  uint32_t t = micros() - sl.t0;
  while (sl.k < TOCK && t >= (uint64_t)OPT_S * 1000000ULL * (sl.k + 1) / TOCK) {
    trenutni->konv[sl.k++] = sl.best;
  }
  if (delez) *delez = t / (OPT_S * 1e6f);
  return t >= OPT_S * 1000000UL;
}

inline void zamenjaj(float **a, float **b) { float *t = *a; *a = *b; *b = t; }

// Inicializacija populacije velikosti n (enakomerno v mejah)
void inicializiraj(int n) {
  for (int i = 0; i < n; i++) {
    for (int j = 0; j < DIM; j++) X[i][j] = SPOD + rnd() * (ZGOR - SPOD);
    fx[i] = oceni(X[i]);
  }
}

// ======================= DE in jDE ==================================
// Klasični DE/rand/1/bin s fiksnima F in CR. jDE je enak, le da ima
// vsak posameznik svoja F in CR, ki se samoprilagajata.
// Obravnava mej: komponenta izven mej -> naključna vrednost v mejah.
// Sinhrona različica: vsi poskusni vektorji generacije g se tvorijo
// iz populacije g, šele nato sledi selekcija.
int de_jde(bool jde) {
  const int NP = jde ? JDE_NP : DE_NP;
  inicializiraj(NP);
  for (int i = 0; i < NP; i++) { Fpar[i] = 0.5f; CRpar[i] = 0.9f; }

  uint32_t gen = 0;
  while (!konec_casa(NULL)) {
    for (int i = 0; i < NP; i++) {
      float F, CR;
      if (jde) {
        // jDE: z verjetnostjo tau1 nov F v [FL, FL+FU], z verjetnostjo
        // tau2 nov CR v [0, 1), sicer podedovana vrednost.
        F  = (rnd() < JDE_TAU1) ? JDE_FL + JDE_FU * rnd() : Fpar[i];
        CR = (rnd() < JDE_TAU2) ? rnd() : CRpar[i];
      } else {
        F = DE_F; CR = DE_CR;
      }
      Ftr[i] = F; CRtr[i] = CR;

      // trije različni naključni posamezniki, različni od i
      int r1, r2, r3;
      do r1 = rndi(NP); while (r1 == i);
      do r2 = rndi(NP); while (r2 == i || r2 == r1);
      do r3 = rndi(NP); while (r3 == i || r3 == r1 || r3 == r2);

      // mutacija DE/rand/1 + binomsko križanje
      int jr = rndi(DIM);              // vsaj ena komponenta iz mutanta
      float *u = U[i], *xi = X[i], *a = X[r1], *b = X[r2], *c = X[r3];
      for (int j = 0; j < DIM; j++) {
        if (j == jr || rnd() < CR) {
          float v = a[j] + F * (b[j] - c[j]);
          if (v < SPOD || v > ZGOR) v = SPOD + rnd() * (ZGOR - SPOD);
          u[j] = v;
        } else {
          u[j] = xi[j];
        }
      }
      fu[i] = oceni(u);
    }
    // selekcija: boljši ali enak poskusni vektor zamenja starša
    for (int i = 0; i < NP; i++) {
      if (fu[i] <= fx[i]) {
        zamenjaj(&X[i], &U[i]);
        fx[i] = fu[i];
        if (jde) { Fpar[i] = Ftr[i]; CRpar[i] = CRtr[i]; }   // parametra preživita
      }
    }
    gen++;
  }
  trenutni->gen = gen;
  return NP;
}

// ======================= L-SHADE ====================================
// Tanabe & Fukunaga, "Improving the search performance of SHADE using
// linear population size reduction", IEEE CEC 2014.
//  - mutacija current-to-pbest/1 z arhivom,
//  - zgodovinski spomin M_F, M_CR velikosti H,
//  - F ~ Cauchy(M_F, 0.1), CR ~ N(M_CR, 0.1),
//  - posodobitev spomina z uteženo Lehmerjevo sredino,
//  - linearno zmanjševanje populacije (LPSR) od NP_init do NP_min.
// RAZLIKA OD ORIGINALA: LPSR je vezan na pretečeni ČAS namesto na
// število evalvacij, ker je zaustavitveni pogoj čas (in ne MAX_NFE).
float *fx_sort;   // za primerjalno funkcijo qsort
int primerjaj(const void *a, const void *b) {
  float fa = fx_sort[*(const int *)a], fb = fx_sort[*(const int *)b];
  return (fa > fb) - (fa < fb);
}

int lshade() {
  int NP = LS_NP_INIT;
  inicializiraj(NP);

  float MF[LS_H], MCR[LS_H];           // MCR < 0 pomeni "terminalno" vrednost
  for (int h = 0; h < LS_H; h++) { MF[h] = 0.5f; MCR[h] = 0.5f; }
  int k = 0, nA = 0;
  uint32_t gen = 0;
  float delez;

  while (!konec_casa(&delez)) {
    // --- uredimo populacijo po kakovosti (za izbiro pbest) ---
    for (int i = 0; i < NP; i++) idx[i] = i;
    fx_sort = fx;
    qsort(idx, NP, sizeof(int), primerjaj);
    int pnum = (int)lroundf(LS_P * NP);
    if (pnum < 2) pnum = 2;

    // --- generiranje poskusnih vektorjev ---
    for (int i = 0; i < NP; i++) {
      int r = rndi(LS_H);
      float CR = (MCR[r] < 0) ? 0.0f : rnd_normal(MCR[r], 0.1f);
      if (CR < 0) CR = 0; else if (CR > 1) CR = 1;
      float F;
      do F = rnd_cauchy(MF[r], 0.1f); while (F <= 0);   // ponavljamo, dokler F <= 0
      if (F > 1) F = 1;
      Ftr[i] = F; CRtr[i] = CR;

      int pb = idx[rndi(pnum)];                          // eden izmed p% najboljših
      int r1; do r1 = rndi(NP); while (r1 == i);
      int r2; do r2 = rndi(NP + nA); while (r2 == i || r2 == r1);
      const float *xr2 = (r2 < NP) ? X[r2] : A[r2 - NP]; // iz populacije ali arhiva

      int jr = rndi(DIM);
      float *u = U[i], *xi = X[i], *xp = X[pb], *x1 = X[r1];
      for (int j = 0; j < DIM; j++) {
        if (j == jr || rnd() < CR) {
          float v = xi[j] + F * (xp[j] - xi[j]) + F * (x1[j] - xr2[j]);
          // obravnava mej kot v L-SHADE: polovica poti do meje
          if (v < SPOD) v = 0.5f * (SPOD + xi[j]);
          else if (v > ZGOR) v = 0.5f * (ZGOR + xi[j]);
          u[j] = v;
        } else {
          u[j] = xi[j];
        }
      }
      fu[i] = oceni(u);
    }

    // --- selekcija, arhiv in zbiranje uspešnih parametrov ---
    int Amax = (int)lroundf(LS_RARC * NP);
    int nS = 0;
    for (int i = 0; i < NP; i++) {
      if (fu[i] < fx[i]) {
        // starša shranimo v arhiv (če je poln, zamenjamo naključnega)
        float *cilj = (nA < Amax) ? A[nA++] : A[rndi(nA)];
        memcpy(cilj, X[i], DIM * sizeof(float));
        SF[nS] = Ftr[i]; SCR[nS] = CRtr[i]; Sdf[nS] = fx[i] - fu[i]; nS++;
      }
      if (fu[i] <= fx[i]) { zamenjaj(&X[i], &U[i]); fx[i] = fu[i]; }
    }

    // --- posodobitev zgodovinskega spomina (utežena Lehmerjeva sredina) ---
    if (nS > 0) {
      float vs = 0; for (int s = 0; s < nS; s++) vs += Sdf[s];
      float sF = 0, sF2 = 0, sC = 0, sC2 = 0, maxCR = 0;
      for (int s = 0; s < nS; s++) {
        float w = (vs > 0) ? Sdf[s] / vs : 1.0f / nS;
        sF += w * SF[s];  sF2 += w * SF[s] * SF[s];
        sC += w * SCR[s]; sC2 += w * SCR[s] * SCR[s];
        if (SCR[s] > maxCR) maxCR = SCR[s];
      }
      MF[k] = (sF > 0) ? sF2 / sF : MF[k];
      if (MCR[k] < 0 || maxCR == 0) MCR[k] = -1.0f;      // terminalna vrednost
      else MCR[k] = (sC > 0) ? sC2 / sC : MCR[k];
      k = (k + 1) % LS_H;
    }

    // --- linearno zmanjševanje populacije (glede na pretečeni čas) ---
    int NPnov = (int)lroundf((LS_NP_MIN - LS_NP_INIT) * delez + LS_NP_INIT);
    if (NPnov < LS_NP_MIN) NPnov = LS_NP_MIN;
    while (NP > NPnov) {               // odstranimo najslabšega
      int w = 0;
      for (int i = 1; i < NP; i++) if (fx[i] > fx[w]) w = i;
      zamenjaj(&X[w], &X[NP - 1]);
      fx[w] = fx[NP - 1];
      NP--;
    }
    Amax = (int)lroundf(LS_RARC * NP);
    while (nA > Amax) {                // arhiv zmanjšamo z naključnim brisanjem
      int w = rndi(nA);
      zamenjaj(&A[w], &A[nA - 1]);
      nA--;
    }
    gen++;
  }
  trenutni->gen = gen;
  return NP;
}

// ======================= EN ZAGON ===================================
void pozeni(uint8_t alg, int zagon, Rezultat *r) {
  memset(r, 0, sizeof(*r));
  r->alg = alg; r->zagon = zagon;
  trenutni = r;
  rng = 2463534242u + 7919u * zagon;   // isto seme za vse algoritme v zagonu
  for (int i = 0; i < 20; i++) rnd();  // "ogrevanje" generatorja

  sl.fe = 0; sl.fe_cilj = 0; sl.us_cilj = 0; sl.best = 1e30f; sl.k = 0;
  sl.t0 = micros();

  int np;
  if (alg == 2) np = lshade();
  else          np = de_jde(alg == 1);

  uint32_t t = micros() - sl.t0;
  while (sl.k < TOCK) r->konv[sl.k++] = sl.best;   // za vsak slučaj
  r->np_konec = np;
  r->fe = sl.fe;
  r->cas_ms = t / 1000;
  r->best = sl.best;
  r->fe_cilj = sl.fe_cilj;
  r->ms_cilj = sl.fe_cilj ? (sl.us_cilj + 500) / 1000 : 0;
  if (r->fe_cilj && r->ms_cilj == 0) r->ms_cilj = 1;   // 0 pomeni "ni doseženo"
}

// ======================= STATISTIKA =================================
// Kritične vrednosti t-porazdelitve (95 %, dvostransko) za df = 1..30
const double T95[30] = {12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365,
  2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110,
  2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052,
  2.048, 2.045, 2.042};

double kvantil(const double *s, int n, double p) {
  double h = p * (n - 1);
  int k = (int)h;
  if (k >= n - 1) return s[n - 1];
  return s[k] + (h - k) * (s[k + 1] - s[k]);
}

// Izpiše: povprečje, std, 95 % IZ povprečja, mediano, Q1, Q3, min, max
void statistika(const char *alg, const char *ime, const double *x, int n) {
  if (n == 0) return;
  double s[ZAGONOV];
  memcpy(s, x, n * sizeof(double));
  for (int i = 1; i < n; i++) {        // urejanje z vstavljanjem
    double v = s[i]; int j = i - 1;
    while (j >= 0 && s[j] > v) { s[j + 1] = s[j]; j--; }
    s[j + 1] = v;
  }
  double povp = 0; for (int i = 0; i < n; i++) povp += s[i];
  povp /= n;
  double var = 0; for (int i = 0; i < n; i++) var += (s[i] - povp) * (s[i] - povp);
  double sd = (n > 1) ? sqrt(var / (n - 1)) : 0;
  double t = (n > 31) ? 1.96 : (n > 1 ? T95[n - 2] : 0);
  Serial.printf("STAT,%s,%s,%d,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e,%.6e\n",
                alg, ime, n, povp, sd, t * sd / sqrt((double)n), kvantil(s, n, 0.5),
                kvantil(s, n, 0.25), kvantil(s, n, 0.75), s[0], s[n - 1]);
}

void izpisi_vse(int n) {
  Serial.printf("\n#POSKUS funkcija=%s D=%d zagonov=%d spanje=%ds opt=%ds tock=%d "
                "cilj=%.3e DE_NP=%d JDE_NP=%d LS_NP_INIT=%d prevod=%s\n",
                FUNKCIJA == 0 ? "rastrigin" : "rosenbrock", DIM, ZAGONOV, SPANJE_S,
                OPT_S, TOCK, (double)PRAG_CILJA, DE_NP, JDE_NP, LS_NP_INIT, OZNAKA_PREVODA);
  Serial.println("#REZ,i,alg,zagon,fe,gen,best,cas_ms,fe_cilj,ms_cilj,np_konec");
  for (int i = 0; i < n; i++) {
    Rezultat &r = rezultati[i];
    Serial.printf("REZ,%d,%s,%d,%lu,%lu,%.6e,%lu,%lu,%lu,%u\n", i, IME_ALG[r.alg],
                  r.zagon, (unsigned long)r.fe, (unsigned long)r.gen, (double)r.best,
                  (unsigned long)r.cas_ms, (unsigned long)r.fe_cilj,
                  (unsigned long)r.ms_cilj, r.np_konec);
  }
  Serial.println("#KONV,i,alg,zagon,best_1 ... best_TOCK");
  for (int i = 0; i < n; i++) {
    Rezultat &r = rezultati[i];
    Serial.printf("KONV,%d,%s,%d", i, IME_ALG[r.alg], r.zagon);
    for (int k = 0; k < TOCK; k++) Serial.printf(",%.4e", (double)r.konv[k]);
    Serial.println();
  }
  Serial.println("#STAT,alg,kolicina,n,povprecje,std,iz95,mediana,q1,q3,min,max");
  for (int a = 0; a < 3; a++) {
    double b[ZAGONOV], fe[ZAGONOV], fs[ZAGONOV], mc[ZAGONOV];
    int m = 0, usp = 0;
    for (int i = 0; i < n; i++) {
      Rezultat &r = rezultati[i];
      if (r.alg != a) continue;
      b[m] = r.best; fe[m] = r.fe; fs[m] = r.fe / (r.cas_ms / 1000.0);
      if (r.fe_cilj) mc[usp++] = r.ms_cilj;
      m++;
    }
    if (m == 0) continue;
    statistika(IME_ALG[a], "best", b, m);
    statistika(IME_ALG[a], "fe", fe, m);
    statistika(IME_ALG[a], "fe_na_s", fs, m);
    statistika(IME_ALG[a], "ms_do_cilja", mc, usp);
    Serial.printf("USPEH,%s,%d,%d,%.1f%%\n", IME_ALG[a], usp, m, 100.0 * usp / m);
  }
  Serial.println("#KONEC_IZPISA   (BOOT ali 'n' = pobriši in začni nov poskus)");
}

// ======================= POSKUS (napajanje z RIGOL-a) ===============
void spi(uint64_t us) {
  esp_sleep_enable_timer_wakeup(us);
  esp_light_sleep_start();
}

void izvedi_poskus() {
  flash.putUChar("stanje", STANJE_TECE);
  // Ob prvem zagonu po nalaganju se LittleFS formatira (lahko traja
  // nekaj sekund), zato je to tu, pred prvim spanjem.
  LittleFS.begin(true);
  LittleFS.remove(DATOTEKA);           // stari rezultati se pobrišejo

  if (!alociraj()) {                   // premalo pomnilnika (prevelik DIM)
    flash.putUChar("stanje", STANJE_NAPAKA);
    flash.end();
    esp_deep_sleep_start();
  }

#if IZPIS_MED_POSKUSOM
  Serial.begin(115200);
  delay(500);
  Serial.printf("#Poskus se začenja, prosti RAM: %u B\n", ESP.getFreeHeap());
#else
  // TX pin v visoko impedanco, da ESP32 ne napaja USB-UART čipa
  // na ploščici prek podatkovne linije.
  pinMode(1, INPUT);
#endif

  int i = 0;
  for (int z = 0; z < ZAGONOV; z++) {
    for (int a = 0; a < (int)N_ALG; a++, i++) {
      spi((uint64_t)SPANJE_S * 1000000ULL);   // bazna poraba

      digitalWrite(MARKER, HIGH);             // ---- merilno okno ----
      pozeni(ALGORITMI[a], z, &rezultati[i]);
      digitalWrite(MARKER, LOW);              // ---------------------

      spi(1000000ULL);                        // loči optimizacijo od pisanja
      File f = LittleFS.open(DATOTEKA, FILE_APPEND);   // dodamo na konec
      f.write((const uint8_t *)&rezultati[i], sizeof(Rezultat));
      f.close();
#if IZPIS_MED_POSKUSOM
      Rezultat &r = rezultati[i];
      Serial.printf("REZ,%d,%s,%d,%lu,%lu,%.6e,%lu,%lu,%lu,%u\n", i, IME_ALG[r.alg],
                    r.zagon, (unsigned long)r.fe, (unsigned long)r.gen, (double)r.best,
                    (unsigned long)r.cas_ms, (unsigned long)r.fe_cilj,
                    (unsigned long)r.ms_cilj, r.np_konec);
      Serial.flush();
#endif
    }
  }
  flash.putUChar("stanje", STANJE_KONCAN);
  flash.end();
  esp_deep_sleep_start();              // konec: tok pade skoraj na nič
}

// ======================= IZPIS (napajanje prek USB) =================
void izpisuj_rezultate(bool napaka) {
  Serial.begin(115200);
  int n = 0;
  LittleFS.begin(true);
  File f = LittleFS.open(DATOTEKA, FILE_READ);
  if (f) {
    n = f.size() / sizeof(Rezultat);
    if (n > (int)N_REZ) n = N_REZ;
    f.read((uint8_t *)rezultati, n * sizeof(Rezultat));
    f.close();
  }
  pinMode(TIPKA_BOOT, INPUT_PULLUP);

  while (true) {
    if (napaka) {
      Serial.printf("\n#NAPAKA: premalo pomnilnika za DIM=%d (potrebno ~%u B, "
                    "prosto %u B). Zmanjšajte DIM ali NP.\n",
                    DIM, (unsigned)((2 * NP_MAX + ARH_MAX) * DIM * 4), ESP.getFreeHeap());
    } else {
      izpisi_vse(n);
    }
    for (int k = 0; k < 1000; k++) {   // 10 s čakamo na BOOT ali "n"
      bool tipka = digitalRead(TIPKA_BOOT) == LOW;
      bool ukaz  = Serial.available() && (Serial.read() == 'n');
      if (tipka || ukaz) {
        Serial.println("#Rezultati pobrisani, začenjam nov poskus ...");
        Serial.flush();
        LittleFS.remove(DATOTEKA);
        flash.putUChar("stanje", 0);
        flash.end();
        delay(200);
        ESP.restart();
      }
      delay(10);
    }
  }
}

// ======================= GLAVNI PROGRAM =============================
void setup() {
  pinMode(MARKER, OUTPUT);
  digitalWrite(MARKER, LOW);
  disableCore1WDT();                   // watchdog ne sme motiti računanja

  flash.begin("ea", false);
  if (flash.getString("prevod", "") != String(OZNAKA_PREVODA)) {
    flash.clear();                     // nov program -> stari rezultati neveljavni
    flash.putString("prevod", OZNAKA_PREVODA);
  }

  uint8_t stanje = flash.getUChar("stanje", 0);
  if (stanje == STANJE_KONCAN) izpisuj_rezultate(false);
  else if (stanje == STANJE_NAPAKA) izpisuj_rezultate(true);
  else izvedi_poskus();
}

void loop() {}                         // ne uporabljamo
```

### Priloga B: Snemanje, branje rezultatov in analiza (`ea_energija/zajem.py`, 643 vrstic)

Ukazi: `seznam`, `snemaj`, `preberi`, `analiza`.

```python
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
#  SNEMANJE z RIGOL-a
# ======================================================================
def snemaj(args):
    import pyvisa
    os.makedirs(args.mapa, exist_ok=True)
    pot = os.path.join(args.mapa, "rigol.csv")
    rm = pyvisa.ResourceManager(args.visa_backend)
    inst = rm.open_resource(args.rigol)
    inst.timeout = 2000
    print("RIGOL:", inst.query("*IDN?").strip())
    # DP800 (več kanalov): ":MEAS:ALL? CH1" vrne "napetost,tok,moč".
    # Enokanalni modeli (npr. DP711): brez kanala -> --kanal ""
    ukaz = f":MEAS:ALL? {args.kanal}".strip()

    print(f"Snemam v {pot}")
    print("Vklopite izhod RIGOL-a. Ctrl+C za ročno prekinitev.\n")
    t0 = time.monotonic()
    bil_visok = False          # ali smo že videli vsaj eno optimizacijo
    nizek_od = None            # od kdaj je tok zelo nizek (deep sleep)
    n = 0
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
                    print("\nNapaka RIGOL:", e, file=sys.stderr)
                    time.sleep(0.5)
                    continue
                t = 0.5 * (ta + tb)
                w.writerow([f"{t:.4f}", u, i, p])
                n += 1
                if n % 20 == 0:
                    f.flush()
                    print(f"\r  t = {t:8.1f} s   I = {i*1000:7.2f} mA   "
                          f"P = {p*1000:7.1f} mW   vzorcev: {n}   ", end="")

                # Samodejna ustavitev: po vsaj eni optimizaciji je tok
                # dlje časa pod pragom deep sleepa -> ESP32 je končal.
                if i * 1000 > args.prag_visok_ma:
                    bil_visok = True
                if bil_visok and i * 1000 < args.prag_konec_ma:
                    nizek_od = nizek_od or t
                    if t - nizek_od > args.cas_konec_s:
                        print("\nESP32 je v deep sleepu, poskus je končan.")
                        break
                else:
                    nizek_od = None
                time.sleep(args.perioda)
        except KeyboardInterrupt:
            print("\nPrekinjeno.")
    inst.close()
    print(f"Shranjeno: {pot}  ({n} vzorcev)")
    print("Zdaj priklopite ESP32 na USB in shranite izpis Serial Monitorja v esp32.txt.")


# ======================================================================
#  BRANJE REZULTATOV Z ESP32 (namesto ročnega kopiranja iz Serial Monitorja)
# ======================================================================
def preberi(args, odpri=None):
    """Prebere en celoten izpis rezultatov (od #POSKUS do #KONEC_IZPISA)
    in ga shrani v <mapa>/esp32.txt. ESP32 izpis ponavlja vsakih 10 s.

    Linij DTR in RTS ne vklopimo, da se ESP32 ob odprtju vrat ne resetira
    ali ne preide v način za nalaganje programa (samodejni reset na
    razvojnih ploščicah). Tudi če se resetira, se rezultati ne izgubijo:
    končan poskus ob vklopu samo izpisuje."""
    import serial
    if odpri is None:
        ser = serial.serial_for_url(args.port, do_not_open=True)
        ser.baudrate = args.baud
        ser.timeout = 1.0
        ser.dtr = False
        ser.rts = False
        ser.open()
    else:
        ser = odpri                      # za preizkus brez strojne opreme
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
#  BRANJE PODATKOV
# ======================================================================
def preberi_rigol(pot):
    t, p = [], []
    with open(pot) as f:
        for vr in csv.DictReader(f):
            t.append(float(vr["t_s"]))
            p.append(float(vr["P_W"]))
    return t, p


def preberi_esp(pot):
    """Iz izpisa Serial Monitorja pobere glavo #POSKUS ter vrstice REZ in
    KONV. ESP32 izpis ponavlja vsakih 10 s, zato vsak zagon vzamemo enkrat.
    Časovne žige, ki jih doda Serial Monitor ("14:01:02.123 -> "), ignoriramo."""
    param, rez, konv = {}, {}, {}
    with open(pot, encoding="utf-8", errors="replace") as f:
        for vr in f:
            vr = vr.strip()
            k = vr.find("#POSKUS")
            if k >= 0:
                for kljuc, vred in re.findall(r"(\w+)=([^\s]+)", vr[k:]):
                    param[kljuc] = vred.rstrip("s") if kljuc in ("spanje", "opt") else vred
                continue
            for oznaka in ("REZ,", "KONV,"):
                k = vr.find(oznaka)
                if k < 0 or vr[k - 1:k] == "#":
                    continue
                d = vr[k:].split(",")
                try:
                    i = int(d[1])
                    if oznaka == "REZ,":
                        rez[i] = {"alg": d[2], "zagon": int(d[3]), "fe": int(d[4]),
                                  "gen": int(d[5]), "best": float(d[6]),
                                  "cas_ms": int(d[7]), "fe_cilj": int(d[8]),
                                  "ms_cilj": int(d[9]), "np_konec": int(d[10])}
                    else:
                        konv[i] = [float(v) for v in d[4:]]
                except (ValueError, IndexError):
                    pass   # nepopolna vrstica (npr. prekinjen izpis)
    for i in rez:
        rez[i]["konv"] = konv.get(i, [])
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
    visoka = s[int(0.97 * (len(s) - 1))]
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
def analiza(args):
    t, p = preberi_rigol(args.rigol_csv)
    param, rez = preberi_esp(args.esp_txt) if args.esp_txt else ({}, [])
    mapa = os.path.dirname(os.path.abspath(args.rigol_csv))

    opt_s = float(param.get("opt", args.opt or 0)) or None
    spanje_s = float(param.get("spanje", args.spanje))
    tock = int(param.get("tock", 0)) or (len(rez[0]["konv"]) if rez else 0)
    if opt_s:   # sprejmemo le intervale, ki trajajo približno OPT_S
        min_s, max_s = 0.8 * opt_s - 0.5, 1.2 * opt_s + 0.5
    else:
        min_s, max_s = args.min_trajanje, INF

    zagoni, zavrzeni, prag, nizka, visoka = najdi_zagone(t, p, min_s, max_s)
    print(f"Poskus: {param.get('funkcija', '?')}, D = {param.get('D', '?')}, "
          f"opt = {opt_s} s, spanje = {spanje_s} s, cilj = {param.get('cilj', '?')}")
    print(f"Raven spanja ~{nizka*1000:.2f} mW, računanja ~{visoka*1000:.1f} mW, "
          f"prag {prag*1000:.1f} mW")
    print(f"Najdenih zagonov v toku: {len(zagoni)} (zavrženih kratkih/dolgih "
          f"intervalov: {len(zavrzeni)}),  vrstic REZ: {len(rez)}")
    if rez and len(rez) != len(zagoni):
        print("OPOZORILO: število zagonov v toku in vrstic REZ se ne ujema!\n"
              "  Morda se je snemanje začelo prepozno ali se je ESP32 vmes resetiral.\n"
              "  Zagoni se povezujejo po vrstnem redu, zato preverite rezultate.")

    vrstice, konv_vrstice = [], []
    for k, (t0, t1) in enumerate(zagoni):
        T = t1 - t0
        E = integriraj(t, p, t0, t1)
        # Bazna poraba: zadnji del spanja pred zagonom (brez prvih 2 s
        # po pisanju v flash in zadnjih 0,5 s pred začetkom optimizacije).
        P_baza = povprecje(t, p, t0 - spanje_s + 2.0, t0 - 0.5)
        r = rez[k] if k < len(rez) else {}
        fe = r.get("fe", 0)
        ms_cilj = r.get("ms_cilj", 0)
        dosezen = ms_cilj > 0
        E_cilj = integriraj(t, p, t0, t0 + ms_cilj / 1000.0) if dosezen else INF
        vrstice.append({
            "zagon_i": k,
            "alg": r.get("alg", "?"),
            "ponovitev": r.get("zagon", -1),
            "trajanje_s": T,
            "cas_esp_s": r.get("cas_ms", NAN) / 1000.0,
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
            konv_vrstice.append({"alg": r["alg"], "ponovitev": r["zagon"], "tocka": j,
                                 "t_s": tj - t0, "E_J": integriraj(t, p, t0, tj),
                                 "best": b})

    if not vrstice:
        print("Ni najdenih zagonov. Preverite rigol.csv (graf z --grafi) in --min-trajanje.")
        return

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

    # ---------------- izpis po zagonih ----------------
    print(f"\nEnergija po zagonih -> {pot}")
    for v in vrstice:
        cilj = (f"cilj po {v['ms_do_cilja']/1000:6.2f} s / {v['E_do_cilja_J']:6.3f} J"
                if v["cilj_dosezen"] else "cilj ni dosežen")
        print(f"  {v['zagon_i']:3d} {v['alg']:7s} #{v['ponovitev']:<2d} {v['trajanje_s']:6.2f} s  "
              f"E = {v['E_J']:7.3f} J  P = {v['P_povp_mW']:6.1f} mW  "
              f"{v['uJ_na_fe']:8.3f} uJ/FE  best = {v['best']:.3e}  {cilj}")

    # ---------------- povzetek po algoritmih ----------------
    algoritmi = [a for a in ("DE", "jDE", "LSHADE") if any(v["alg"] == a for v in vrstice)]
    po_alg = {a: [v for v in vrstice if v["alg"] == a] for a in algoritmi}
    metrike = [("E_J", "J"), ("E_neto_J", "J"), ("P_povp_mW", "mW"), ("P_bazna_mW", "mW"),
               ("fe", "FE"), ("uJ_na_fe", "uJ/FE"), ("uJ_neto_na_fe", "uJ/FE"),
               ("best", ""), ("ms_do_cilja", "ms"), ("E_do_cilja_J", "J"),
               ("E_po_cilju_J", "J")]
    povzetek = []
    print("\nPovzetek po algoritmih (povprečje ± 95 % IZ | mediana [Q1, Q3])")
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
            povzetek.append({"alg": a, "metrika": kljuc, **s})
    for a in algoritmi:
        u = sum(v["cilj_dosezen"] for v in po_alg[a])
        print(f"  uspešnost {a:7s} {u}/{len(po_alg[a])} = {100*u/len(po_alg[a]):.0f} %")
    with open(os.path.join(mapa, "povzetek.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(povzetek[0].keys()))
        w.writeheader()
        w.writerows(povzetek)

    # ---------------- statistični testi ----------------
    # Neuspeli zagoni imajo energijo do cilja = neskončno, zato so pri
    # rangiranju najslabši (običajna obravnava pri testih "čas do cilja").
    pari = [(a, b) for i, a in enumerate(algoritmi) for b in algoritmi[i + 1:]]
    testi = []
    if pari:
        print("\nPrimerjave (Mann-Whitney, dvostransko, Holmov popravek; "
              "A12 < 0,5 => prvi ima manjše vrednosti)")
        for kljuc in ("best", "uJ_na_fe", "E_J", "E_do_cilja_J"):
            pv = [mann_whitney([v[kljuc] for v in po_alg[a]],
                               [v[kljuc] for v in po_alg[b]]) for a, b in pari]
            ph = holm(pv)
            print(f"  {kljuc}")
            for (a, b), p0, p1 in zip(pari, pv, ph):
                ef = a12([v[kljuc] for v in po_alg[a]], [v[kljuc] for v in po_alg[b]])
                zn = "*" if p1 < 0.05 else " "
                print(f"     {a:7s} vs {b:7s}  p = {p0:.3g}  p_Holm = {p1:.3g} {zn}  A12 = {ef:.2f}")
                testi.append({"metrika": kljuc, "alg1": a, "alg2": b, "p": p0,
                              "p_holm": p1, "A12": ef})
        with open(os.path.join(mapa, "testi.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(testi[0].keys()))
            w.writeheader()
            w.writerows(testi)
        try:
            import scipy  # noqa: F401
        except ImportError:
            print("  (scipy ni nameščen: uporabljena normalna aproksimacija; "
                  "za članek priporočam 'pip install scipy')")

    print(f"\nShranjeno v {mapa}: energija.csv, povzetek.csv, testi.csv, konvergenca_energija.csv")
    if args.grafi:
        grafi(mapa, t, p, zagoni, zavrzeni, prag, vrstice, konv_vrstice, algoritmi)


# ======================================================================
#  GRAFI (neobvezno, potrebuje matplotlib)
# ======================================================================
def grafi(mapa, t, p, zagoni, zavrzeni, prag, vrstice, konv, algoritmi):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Za grafe namestite matplotlib: pip install matplotlib")
        return
    barve = {"DE": "#1f77b4", "jDE": "#2ca02c", "LSHADE": "#d62728"}

    # 1) potek moči s prepoznanimi zagoni (kontrola segmentacije)
    fig, ax = plt.subplots(figsize=(12, 3.5))
    ax.plot(t, [x * 1000 for x in p], lw=0.6, color="k")
    for (a, b), v in zip(zagoni, vrstice):
        ax.axvspan(a, b, color=barve.get(v["alg"], "gray"), alpha=0.25, lw=0)
    for a, b in zavrzeni:
        ax.axvspan(a, b, color="gray", alpha=0.3, hatch="//", lw=0)
    ax.axhline(prag * 1000, ls="--", lw=0.8, color="gray")
    ax.set_xlabel("čas [s]")
    ax.set_ylabel("moč [mW]")
    ax.set_title("Moč ESP32 in prepoznani zagoni")
    fig.tight_layout()
    fig.savefig(os.path.join(mapa, "graf_moc.png"), dpi=150)
    plt.close(fig)

    # 2) konvergenca: mediana best glede na porabljeno energijo
    if konv:
        fig, ax = plt.subplots(figsize=(6, 4))
        for a in algoritmi:
            tocke = sorted({k["tocka"] for k in konv if k["alg"] == a})
            E, med, q1, q3 = [], [], [], []
            for j in tocke:
                vr = [k for k in konv if k["alg"] == a and k["tocka"] == j]
                s = opisna([max(k["best"], 1e-12) for k in vr])
                e = opisna([k["E_J"] for k in vr])
                E.append(e["med"]); med.append(s["med"]); q1.append(s["q1"]); q3.append(s["q3"])
            ax.plot(E, med, marker="o", ms=3, label=a, color=barve.get(a))
            ax.fill_between(E, q1, q3, alpha=0.2, color=barve.get(a))
        ax.set_yscale("log")
        ax.set_xlabel("porabljena energija [J]")
        ax.set_ylabel("najboljša vrednost (mediana, IQR)")
        ax.set_title("Konvergenca glede na energijo")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(mapa, "graf_konvergenca_energija.png"), dpi=150)
        plt.close(fig)

    # 3) energija na evalvacijo in energija do cilja
    fig, osi = plt.subplots(1, 2, figsize=(9, 3.5))
    for ax, kljuc, naslov in ((osi[0], "uJ_na_fe", "energija na evalvacijo [µJ/FE]"),
                              (osi[1], "E_do_cilja_J", "energija do cilja [J]")):
        podatki = [[v[kljuc] for v in vrstice if v["alg"] == a
                    and not math.isinf(v[kljuc]) and not math.isnan(v[kljuc])]
                   for a in algoritmi]
        oznake = [f"{a}\n({len(d)})" if kljuc == "E_do_cilja_J" else a
                  for a, d in zip(algoritmi, podatki)]
        if any(podatki):
            ax.boxplot([d if d else [NAN] for d in podatki])
            ax.set_xticks(range(1, len(oznake) + 1), oznake)
        ax.set_title(naslov, fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(mapa, "graf_energija.png"), dpi=150)
    plt.close(fig)
    print("Grafi: graf_moc.png, graf_konvergenca_energija.png, graf_energija.png")


# ======================================================================
def main():
    ap = argparse.ArgumentParser(description="Meritev porabe ESP32 (DE/jDE/L-SHADE) z RIGOL-om")
    sub = ap.add_subparsers(dest="ukaz", required=True)

    a = sub.add_parser("seznam", help="izpiše priklopljene VISA naprave")
    a.add_argument("--visa-backend", default="@py")

    a = sub.add_parser("snemaj", help="snemanje toka z RIGOL-a")
    a.add_argument("--rigol", required=True, help="VISA naslov napajalnika")
    a.add_argument("--kanal", default="CH1", help="CH1/CH2/CH3, prazno za enokanalne")
    a.add_argument("--perioda", type=float, default=0.05, help="premor med poizvedbami (s)")
    a.add_argument("--visa-backend", default="@py",
                   help="'@py' (pyvisa-py) ali '' za NI-VISA / UltraSigma")
    a.add_argument("--mapa", default=time.strftime("meritve_%Y%m%d_%H%M%S"))
    a.add_argument("--prag-visok-ma", type=float, default=20.0,
                   help="tok, nad katerim velja, da ESP32 računa (mA)")
    a.add_argument("--prag-konec-ma", type=float, default=1.0,
                   help="tok deep sleepa, ki pomeni konec poskusa (mA)")
    a.add_argument("--cas-konec-s", type=float, default=60.0,
                   help="koliko časa mora biti tok pod pragom za konec (s)")

    a = sub.add_parser("preberi", help="prebere rezultate z ESP32 prek USB v esp32.txt")
    a.add_argument("--port", required=True, help="serijska vrata, npr. COM5 ali /dev/ttyUSB0")
    a.add_argument("--mapa", required=True, help="mapa poskusa (ista kot pri snemaj)")
    a.add_argument("--baud", type=int, default=115200)
    a.add_argument("--cas", type=float, default=60.0, help="najdaljše čakanje (s)")

    a = sub.add_parser("analiza", help="izračun energije, statistika, testi, grafi")
    a.add_argument("rigol_csv", help="datoteka rigol.csv iz snemanja")
    a.add_argument("esp_txt", nargs="?", help="izpis Serial Monitorja (REZ, KONV)")
    a.add_argument("--grafi", action="store_true", help="nariše grafe (matplotlib)")
    a.add_argument("--spanje", type=float, default=10.0,
                   help="SPANJE_S, če ga ni v esp32.txt")
    a.add_argument("--opt", type=float, default=0.0,
                   help="OPT_S, če ga ni v esp32.txt")
    a.add_argument("--min-trajanje", type=float, default=5.0,
                   help="najkrajši interval, ki šteje kot zagon, če OPT_S ni znan (s)")

    args = ap.parse_args()
    if args.ukaz == "seznam":
        import pyvisa
        for r in pyvisa.ResourceManager(args.visa_backend).list_resources():
            print(r)
    elif args.ukaz == "snemaj":
        snemaj(args)
    elif args.ukaz == "preberi":
        sys.exit(0 if preberi(args) else 1)
    else:
        analiza(args)


if __name__ == "__main__":
    main()
```

### Priloga C: Številke in slike za članek (`gecco_paper/make_results.py`, 413 vrstic)

Potrebuje `zajem.py` (išče ga v `../ea_energija`).

```python
#!/usr/bin/env python3
"""
make_results.py - iz map z meritvami zgenerira številke, tabelo in sliki
                  za članek (results.tex, fig_convergence.pdf, fig_trace.pdf).

Vsaka mapa je en poskus (ena funkcija in dimenzija) in mora vsebovati
datoteke, ki jih ustvarita "zajem.py snemaj" in "zajem.py analiza":
    rigol.csv, esp32.txt, energija.csv, konvergenca_energija.csv

Uporaba (iz mape gecco_paper):
    python3 make_results.py ../meritve_rastrigin50 ../meritve_rastrigin100 \
                            ../meritve_rosenbrock50 ../meritve_rosenbrock100
    latexmk -pdf main.tex

Skripta potrebuje zajem.py (išče ga v tej mapi, v ../ea_energija ali
na poti, podani z --zajem) ter matplotlib in scipy:
    pip install matplotlib scipy
"""
import argparse
import csv
import math
import os
import sys

INF = float("inf")
NAN = float("nan")
ALGS = ["DE", "jDE", "LSHADE"]
IME = {"DE": "DE", "jDE": "jDE", "LSHADE": "L-SHADE"}
# Kategorična paleta (preverjena za barvno slepoto) + različni markerji,
# da identiteta ni odvisna samo od barve.
BARVA = {"DE": "#2a78d6", "jDE": "#eb6834", "LSHADE": "#1baf7a"}
MARKER = {"DE": "o", "jDE": "s", "LSHADE": "^"}
SPODNJA_MEJA = 1e-8   # vrednosti pod to mejo na log. osi narišemo na meji


def uvozi_zajem(pot):
    kandidati = [pot] if pot else []
    tu = os.path.dirname(os.path.abspath(__file__))
    kandidati += [tu, os.path.join(tu, "..", "ea_energija")]
    for k in kandidati:
        if k and os.path.isfile(os.path.join(k, "zajem.py")):
            sys.path.insert(0, os.path.abspath(k))
            import zajem  # noqa: E402
            return zajem
    sys.exit("Ne najdem zajem.py. Podajte pot z --zajem.")


def v_stevilo(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return NAN


def preberi_csv(pot):
    with open(pot, newline="") as f:
        return list(csv.DictReader(f))


def mediana(x):
    x = sorted(x)
    n = len(x)
    if n == 0:
        return NAN
    return x[n // 2] if n % 2 else 0.5 * (x[n // 2 - 1] + x[n // 2])


def povp(x):
    x = [v for v in x if not math.isnan(v)]
    return sum(x) / len(x) if x else NAN


def cv(x):
    """Koeficient variacije v %."""
    x = [v for v in x if not math.isnan(v)]
    if len(x) < 2:
        return 0.0
    m = sum(x) / len(x)
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))
    return 100 * s / m if m else NAN


# ======================================================================
#  Branje enega poskusa
# ======================================================================
def preberi_poskus(mapa, zajem):
    param, rez = zajem.preberi_esp(os.path.join(mapa, "esp32.txt"))
    energija = preberi_csv(os.path.join(mapa, "energija.csv"))
    konv = preberi_csv(os.path.join(mapa, "konvergenca_energija.csv"))
    t, p = zajem.preberi_rigol(os.path.join(mapa, "rigol.csv"))
    fs = (len(t) - 1) / (t[-1] - t[0]) if len(t) > 1 else NAN

    zagoni = []
    for v in energija:
        k = int(v["zagon_i"])
        r = rez[k] if k < len(rez) else {}
        fe_cilj = r.get("fe_cilj", 0)
        zagoni.append({
            "alg": v["alg"],
            "P": v_stevilo(v["P_povp_mW"]),
            "Pbaza": v_stevilo(v["P_bazna_mW"]),
            "E": v_stevilo(v["E_J"]),
            "fe": v_stevilo(v["fe"]),
            "e": v_stevilo(v["uJ_na_fe"]),
            "best": v_stevilo(v["best"]),
            "uspeh": int(v["cilj_dosezen"]) == 1,
            "ETT": v_stevilo(v["E_do_cilja_J"]),          # inf, če ni uspel
            "FEtT": fe_cilj if fe_cilj > 0 else INF,
            "Ew": v_stevilo(v["E_po_cilju_J"]),
        })
    return {
        "mapa": mapa,
        "funkcija": param.get("funkcija", "?"),
        "D": int(param.get("D", 0) or 0),
        "opt": float(param.get("opt", NAN)),
        "spanje": float(param.get("spanje", NAN)),
        "cilj": float(param.get("cilj", "nan")),
        "zagoni": zagoni,
        "konv": konv,
        "fs": fs,
        "t": t, "p": p,
    }


# ======================================================================
#  Oblikovanje števil za LaTeX
# ======================================================================
def f_sci(x):
    """Vrednost kriterijske funkcije: 0, navadno ali znanstveno."""
    if math.isnan(x):
        return "--"
    if x == 0:
        return "0"
    if 0.01 <= abs(x) < 1e4:
        return f"{x:.3g}"
    m, e = f"{x:.1e}".split("e")
    return f"${m}{{\\times}}10^{{{int(e)}}}$"


def f_num(x, dec=2):
    if math.isinf(x):
        return "$\\infty$"
    if math.isnan(x):
        return "--"
    return f"{x:.{dec}f}"


def f_cilj(x):
    if math.isnan(x):
        return "\\varepsilon"
    m, e = f"{x:.0e}".split("e")
    return f"10^{{{int(e)}}}" if m == "1" else f"{m}\\times10^{{{int(e)}}}"


# ======================================================================
#  Statistika: najboljši in značilno boljši od obeh drugih
# ======================================================================
def oznake(zajem, po_alg, kljuc, agregat, cilj_min=True):
    """Vrne {alg: (krepko, bodalo)}. Krepko = najboljši agregat (vezi vse),
    bodalo = Holm p < 0,05 proti obema drugima IN manjše vrednosti (A12 < 0,5)."""
    algi = [a for a in ALGS if po_alg.get(a)]
    vred = {a: agregat([z[kljuc] for z in po_alg[a]]) for a in algi}
    koncne = [v for v in vred.values() if not math.isnan(v) and not math.isinf(v)]
    naj = min(koncne) if koncne else None
    pari = [(a, b) for i, a in enumerate(algi) for b in algi[i + 1:]]
    pv = [zajem.mann_whitney([z[kljuc] for z in po_alg[a]],
                             [z[kljuc] for z in po_alg[b]]) for a, b in pari]
    ph = dict(zip(pari, zajem.holm(pv)))
    rez = {}
    for a in algi:
        krepko = naj is not None and vred[a] == naj
        boljsi = 0
        for b in algi:
            if b == a:
                continue
            p = ph.get((a, b), ph.get((b, a), NAN))
            a12 = zajem.a12([z[kljuc] for z in po_alg[a]], [z[kljuc] for z in po_alg[b]])
            if p < 0.05 and a12 < 0.5:
                boljsi += 1
        rez[a] = (krepko, boljsi == len(algi) - 1 and len(algi) > 1)
    return rez


def okrasi(besedilo, oznaka):
    krepko, bodalo = oznaka
    if krepko:
        besedilo = f"\\textbf{{{besedilo}}}"
    if bodalo:
        besedilo += "$^\\dagger$"
    return besedilo


def rang(vrednosti):
    """Vrstni red algoritmov po vrednosti (manjše je boljše)."""
    return tuple(sorted(vrednosti, key=lambda a: (vrednosti[a], a)))


# ======================================================================
#  results.tex
# ======================================================================
def results_tex(poskusi, zajem, pot):
    vrstice, preobrati = [], 0
    vsi = [z for po in poskusi for z in po["zagoni"]]
    efe_razpon = 0.0
    cvP, cvE = [], []
    for k, po in enumerate(poskusi):
        po_alg = {a: [z for z in po["zagoni"] if z["alg"] == a] for a in ALGS}
        po_alg = {a: v for a, v in po_alg.items() if v}
        o_e = oznake(zajem, po_alg, "e", povp)
        o_b = oznake(zajem, po_alg, "best", mediana)
        o_ett = oznake(zajem, po_alg, "ETT", mediana)
        o_fet = oznake(zajem, po_alg, "FEtT", mediana)

        e_vred = [povp([z["e"] for z in v]) for v in po_alg.values()]
        if len(e_vred) > 1 and min(e_vred) > 0:
            efe_razpon = max(efe_razpon, 100 * (max(e_vred) / min(e_vred) - 1))
        for v in po_alg.values():
            cvP.append(cv([z["P"] for z in v]))
            cvE.append(cv([z["E"] for z in v]))

        # Ali se razvrstitev po energiji do cilja razlikuje od razvrstitve
        # po evalvacijah do cilja? (primerjamo le, če je vsaj en algoritem uspel)
        m_ett = {a: mediana([z["ETT"] for z in v]) for a, v in po_alg.items()}
        m_fet = {a: mediana([z["FEtT"] for z in v]) for a, v in po_alg.items()}
        if any(not math.isinf(x) for x in m_ett.values()) and rang(m_ett) != rang(m_fet):
            preobrati += 1

        ime = f"{po['funkcija'].capitalize()}, $D{{=}}{po['D']}$"
        for j, (a, v) in enumerate(po_alg.items()):
            n = len(v)
            usp = [z for z in v if z["uspeh"]]
            celice = [
                ime if j == 0 else "",
                IME[a],
                f_num(povp([z["P"] for z in v]), 1),
                f_num(povp([z["fe"] for z in v]) / 1e6, 2),
                okrasi(f_num(povp([z["e"] for z in v]), 2), o_e[a]),
                okrasi(f_sci(mediana([z["best"] for z in v])), o_b[a]),
                f"{len(usp)}/{n}",
                okrasi(f_num(m_fet[a] / 1e6, 2), o_fet[a]),
                okrasi(f_num(m_ett[a], 2), o_ett[a]),
                f_num(mediana([z["Ew"] for z in usp]), 2) if usp else "--",
            ]
            vrstice.append("  " + " & ".join(celice) + " \\\\")
        if k < len(poskusi) - 1:
            vrstice.append("  \\midrule")

    def p_alg(a):
        return f_num(povp([z["P"] for z in vsi if z["alg"] == a]), 1)

    n_runs = min(sum(1 for z in po["zagoni"] if z["alg"] == a)
                 for po in poskusi for a in ALGS
                 if any(z["alg"] == a for z in po["zagoni"]))
    ew_delez = [z["Ew"] / z["E"] * 100 for z in vsi if z["uspeh"] and z["E"] > 0]
    po0 = poskusi[0]
    makri = {
        "NRUNS": str(n_runs),
        "TOPT": f"{po0['opt']:.0f}",
        "TIDLE": f"{po0['spanje']:.0f}",
        "TARGET": f_cilj(po0["cilj"]),
        "FS": f_num(mediana([po["fs"] for po in poskusi]), 1),
        "PIDLE": f_num(mediana([z["Pbaza"] for z in vsi]), 1),
        "PDE": p_alg("DE"), "PJDE": p_alg("jDE"), "PLSHADE": p_alg("LSHADE"),
        "CVPmax": f_num(max(cvP), 2),
        "CVEmax": f_num(max(cvE), 2),
        "EFEspread": f_num(efe_razpon, 0),
        "RankFlips": str(preobrati),
        "NPROBLEMS": str(len(poskusi)),
        "WastedMedian": f_num(mediana(ew_delez), 0) if ew_delez else "--",
    }
    # Stavka o razvrstitvi: besedilo je odvisno od tega, ali se razvrstitev obrne.
    M = len(poskusi)
    if preobrati > 0:
        makri["RankAbstract"] = (f"in {preobrati} of {M} problems the ranking by energy-to-target "
                                 "differs from the ranking by evaluations-to-target")
        makri["RankSentence"] = (f"In {preobrati} of {M} problems, the ranking of the algorithms by "
                                 "median energy-to-target differs from their ranking by median "
                                 "evaluations-to-target, i.e., an FE budget would have declared a "
                                 "different winner than an energy budget.")
    else:
        makri["RankAbstract"] = ("the ranking by energy-to-target nevertheless coincides with the "
                                 "ranking by evaluations-to-target on all problems")
        makri["RankSentence"] = (f"In all {M} problems, the ranking of the algorithms by median "
                                 "energy-to-target coincides with their ranking by median "
                                 "evaluations-to-target; here the energy budget changes the margins "
                                 "between the algorithms rather than the winner.")
    with open(pot, "w") as f:
        f.write("%% Generirano z make_results.py - ne urejajte ročno.\n")
        f.write("%% Viri: " + ", ".join(po["mapa"] for po in poskusi) + "\n")
        for k, v in makri.items():
            f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
        f.write("\\newcommand{\\ResultsRows}{%\n" + "\n".join(vrstice) + "\n}\n")
    return makri


# ======================================================================
#  Sliki
# ======================================================================
def nastavi_mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    global LogLocator
    from matplotlib.ticker import LogLocator
    plt.rcParams.update({
        "font.family": "serif", "font.size": 7, "axes.titlesize": 7.5,
        "axes.labelsize": 7, "legend.fontsize": 6.5, "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5, "axes.linewidth": 0.5, "lines.linewidth": 1.2,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42,
    })
    return plt


def slika_konvergenca(poskusi, pot):
    plt = nastavi_mpl()
    n = len(poskusi)
    fig, osi = plt.subplots(1, n, figsize=(7.0, 1.9), squeeze=False)
    for ax, po in zip(osi[0], poskusi):
        for a in ALGS:
            vr = [k for k in po["konv"] if k["alg"] == a]
            if not vr:
                continue
            tocke = sorted({int(k["tocka"]) for k in vr})
            E, med, q1, q3 = [], [], [], []
            for j in tocke:
                tj = [k for k in vr if int(k["tocka"]) == j]
                b = sorted(max(float(k["best"]), SPODNJA_MEJA) for k in tj)
                E.append(mediana([float(k["E_J"]) for k in tj]))
                med.append(mediana(b))
                q1.append(b[int(0.25 * (len(b) - 1))])
                q3.append(b[int(math.ceil(0.75 * (len(b) - 1)))])
            ax.fill_between(E, q1, q3, color=BARVA[a], alpha=0.18, lw=0)
            ax.plot(E, med, color=BARVA[a], marker=MARKER[a], ms=2.8,
                    markevery=2, label=IME[a])
        ax.set_yscale("log")
        ax.set_ylim(bottom=SPODNJA_MEJA * 0.5)
        ax.yaxis.set_major_locator(LogLocator(base=10, numticks=5))
        ax.set_title(f"{po['funkcija'].capitalize()}, D = {po['D']}")
        ax.set_xlabel("energy [J]")
        ax.grid(True, which="major", lw=0.3, color="#d9d9d6")
    osi[0][0].set_ylabel(r"$f_{\mathrm{best}}$")
    # Ena skupna legenda nad panoji, da ne prekriva krivulj.
    rocaji, oznake_ = osi[0][0].get_legend_handles_labels()
    fig.legend(rocaji, oznake_, loc="upper center", ncol=len(rocaji), frameon=False,
               bbox_to_anchor=(0.5, 1.0), handlelength=2.0, columnspacing=1.5)
    fig.tight_layout(pad=0.3, w_pad=0.6, rect=(0, 0, 1, 0.9))
    fig.savefig(pot)
    plt.close(fig)


def slika_potek(po, zajem, pot):
    """Potek moči ene ponovitve (DE, jDE, L-SHADE) s prepoznanimi okni."""
    plt = nastavi_mpl()
    t, p = po["t"], po["p"]
    opt = po["opt"]
    zagoni, _, _, _, _ = zajem.najdi_zagone(t, p, 0.8 * opt - 0.5, 1.2 * opt + 0.5)
    if len(zagoni) < 3:
        return False
    algi = [z["alg"] for z in po["zagoni"]]
    t_od = zagoni[0][0] - po["spanje"] - 2
    t_do = zagoni[2][1] + 4
    tt = [x for x in t if t_od <= x <= t_do]
    pp = [y * 1000 for x, y in zip(t, p) if t_od <= x <= t_do]
    fig, ax = plt.subplots(figsize=(3.33, 1.35))
    ymax = max(pp) * 1.18
    for (a, b), alg in zip(zagoni[:3], algi[:3]):
        ax.axvspan(a - t_od, b - t_od, color=BARVA[alg], alpha=0.15, lw=0)
        ax.text(0.5 * (a + b) - t_od, ymax * 0.97, IME[alg], ha="center",
                va="top", fontsize=6.5, color="#333333")
    ax.plot([x - t_od for x in tt], pp, color="#222222", lw=0.6)
    ax.set_ylim(0, ymax)
    ax.set_xlim(0, t_do - t_od)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("power [mW]")
    fig.tight_layout(pad=0.3)
    fig.savefig(pot)
    plt.close(fig)
    return True


# ======================================================================
def main():
    ap = argparse.ArgumentParser(description="Številke in slike za članek iz meritev")
    ap.add_argument("mape", nargs="+", help="mape z meritvami (ena na problem)")
    ap.add_argument("--zajem", help="mapa z zajem.py")
    ap.add_argument("--izhod", default=os.path.dirname(os.path.abspath(__file__)),
                    help="kam zapisati results.tex in sliki (privzeto mapa članka)")
    args = ap.parse_args()
    zajem = uvozi_zajem(args.zajem)

    poskusi = [preberi_poskus(m, zajem) for m in args.mape]
    poskusi.sort(key=lambda po: (po["funkcija"], po["D"]))
    for po in poskusi:
        n = {a: sum(1 for z in po["zagoni"] if z["alg"] == a) for a in ALGS}
        print(f"{po['mapa']}: {po['funkcija']} D={po['D']}  zagonov {n}  fs={po['fs']:.1f} Hz")
    if len({(po['opt'], po['spanje'], po['cilj']) for po in poskusi}) > 1:
        print("OPOZORILO: poskusi imajo različne OPT_S, SPANJE_S ali PRAG_CILJA; "
              "v članek gre vrednost prvega.")

    makri = results_tex(poskusi, zajem, os.path.join(args.izhod, "results.tex"))
    slika_konvergenca(poskusi, os.path.join(args.izhod, "fig_convergence.pdf"))
    ok = slika_potek(poskusi[0], zajem, os.path.join(args.izhod, "fig_trace.pdf"))
    print("\nMakri za besedilo:")
    for k, v in makri.items():
        print(f"  \\{k} = {v}")
    print("\nZapisano: results.tex, fig_convergence.pdf" + (", fig_trace.pdf" if ok else ""))
    print("Zdaj prevedite članek in dopolnite rdeče [opombe] v besedilu.")


if __name__ == "__main__":
    main()
```
