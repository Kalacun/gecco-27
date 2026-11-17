#line 1 "/Users/aleks/gecco2027-electricity/ea_energija/README.md"
# Energija kot zaustavitveni pogoj: DE, jDE in L-SHADE na ESP32

Merilni poskus porabe električne energije evolucijskih algoritmov na mikrokontrolerju ESP32-WROOM. ESP32 izvaja klasični DE, jDE in L-SHADE na Rastriginovi ali Rosenbrockovi funkciji, napajalnik RIGOL pa meri moč. Python skripta iz posnetka toka izračuna energijo vsakega zagona, energijo do cilja, energijo na evalvacijo in konvergenco glede na porabljeno energijo ter izvede statistične primerjave.

---

## 1. Datoteke

| Datoteka | Kje teče | Namen |
|---|---|---|
| `ea_energija.ino` | ESP32 (Arduino IDE) | DE, jDE, L-SHADE, testni funkciji, potek poskusa, shranjevanje v flash, izpis rezultatov in statistike |
| `zajem.py` | PC (Python 3.8+) | snemanje moči z RIGOL-a, iskanje zagonov v toku, izračun energije, statistika, testi, grafi |
| `README.md` | | ta dokument |

---

## 2. Kako poskus deluje

ESP32 med meritvijo **ni povezan z računalnikom**. Napaja ga samo RIGOL, zato ni drugega vira toka, ki bi popačil meritev. Rezultate algoritmov shranjuje v flash in jih izpiše šele po koncu, ko ga priklopite na USB.

Za vsak zagon vsakega algoritma se izvede:

```
  ┌──────────────┬────────────────────────┬──────┬───┐
  │ light sleep  │     optimizacija       │ sleep│ F │   F = zapis v flash
  │  SPANJE_S    │  OPT_S, GPIO4 = 1      │ 1 s  │   │
  └──────────────┴────────────────────────┴──────┴───┘
   bazna poraba    ← tu merimo energijo →
```

Algoritmi se v vsaki ponovitvi izmenjujejo (DE, jDE, L-SHADE, DE, jDE, L-SHADE, ...). Tako vse tri enako prizadenejo morebitne spremembe temperature, napajanja ali staranja meritev. Vsi trije v isti ponovitvi začnejo z istim semenom generatorja naključnih števil.

Ker ESP32 med poskusom ne pošilja oznak po UART, skripta zagone poišče **v samem toku**. Med spanjem je moč nekaj mW, med računanjem okoli 150 mW, in prehodi so jasno vidni. Kratko spanje (1 s) po optimizaciji loči pisanje v flash od merilnega okna, tako da se zapis ne prišteje k energiji algoritma.

Po zadnjem zagonu gre ESP32 v deep sleep in tok pade skoraj na 0. Po tem skripta prepozna, da je poskus končan.

---

## 3. Strojna oprema in vezava

Potrebujete ESP32-WROOM razvojno ploščico (npr. DevKitC), napajalnik RIGOL z daljinskim upravljanjem (preizkušeni ukazi so za serijo DP800) in USB kabel za ESP32.

**Med meritvijo:**

```
   RIGOL CH1 (+) ───────────── 3V3   ESP32
   RIGOL CH1 (−) ───────────── GND   ESP32
   RIGOL USB ───────────────── PC (zajem.py snemaj)
   (neobvezno) GPIO4 ───────── osciloskop, kanal 2 (marker optimizacije)
```

**Med nalaganjem programa in branjem rezultatov:** samo USB kabel med ESP32 in PC, brez RIGOL-a.

> **RIGOL in USB nikoli ne smeta biti priklopljena hkrati.** Ploščica bi se napajala iz dveh virov. Meritev bi bila napačna, v najslabšem primeru pa bi tok tekel v napajalnik ali v USB vrata.

Nastavitve RIGOL-a: **3,30 V**, tokovna omejitev okoli **300 mA**. Napajanje prek pina 3V3 obide LDO regulator na ploščici. Na ploščici sta še vedno priklopljena LED dioda in USB-UART čip, ki trošita nekaj mA. To je **bazna poraba**, ki jo skripta izmeri med spanjem in jo odšteje, ko računa neto vrednosti.

Program ob začetku poskusa preklopi pin TX (GPIO1) v visoko impedanco, da ESP32 prek podatkovne linije ne napaja nenapajanega USB-UART čipa.

---

## 4. Programska oprema

**Arduino IDE:**
1. *Tools → Board → Boards Manager*, poiščite **esp32** (Espressif Systems) in ga namestite. Program je preveden in preizkušen z jedrom 2.0.9, uporablja pa le funkcije, ki so enake tudi v 3.x.
2. *Tools → Board*: **ESP32 Dev Module**.
3. *Tools → Partition Scheme*: privzeta (**Default 4MB with spiffs**), ki vsebuje particijo za LittleFS.

**Python:**
```bash
pip install pyvisa pyvisa-py pyserial  # obvezno za snemanje in branje
pip install scipy matplotlib           # priporočeno: točni testi in grafi
```
Če RIGOL-a `python zajem.py seznam` ne najde, na Windows namestite **NI-VISA** ali RIGOL **UltraSigma** in skripti dodajte `--visa-backend ""`.

---

## 5. Nastavitve programa (`ea_energija.ino`)

Vse nastavitve so na vrhu datoteke.

| Nastavitev | Privzeto | Pomen |
|---|---|---|
| `ZAGONOV` | 10 | ponovitev **vsakega** algoritma (za članek priporočam 25) |
| `SPANJE_S` | 10 | spanje pred vsako optimizacijo, iz njega se meri bazna poraba |
| `OPT_S` | 60 | trajanje ene optimizacije (časovni zaustavitveni pogoj) |
| `DIM` | 50 | dimenzija problema (10–100) |
| `FUNKCIJA` | 0 | 0 = Rastrigin [−5,12; 5,12], 1 = Rosenbrock [−30; 30] |
| `ALGORITMI[]` | {0, 1, 2} | kateri algoritmi in v katerem vrstnem redu (0 = DE, 1 = jDE, 2 = L-SHADE) |
| `PRAG_CILJA` | 1e-6 | cilj za energijo do cilja: prvi trenutek, ko je `best ≤ PRAG_CILJA` |
| `TOCK` | 20 | točke konvergenčne krivulje (best ob t = OPT_S·k/TOCK) |
| `DE_NP`, `DE_F`, `DE_CR` | 100, 0,5, 0,9 | klasični DE |
| `JDE_NP`, `JDE_TAU1/2`, `JDE_FL/FU` | 100, 0,1, 0,1/0,9 | jDE (kot v originalnem članku) |
| `LS_NP_INIT`, `LS_NP_MIN`, `LS_H`, `LS_P`, `LS_RARC` | glej 6.3, 4, 6, 0,11, 2,6 | L-SHADE |
| `IZPIS_MED_POSKUSOM` | 0 | 1 = izpis napredka na UART, samo za preizkus prek USB |

**Trajanje poskusa:** en korak traja približno `SPANJE_S + OPT_S + 1` s. Skupaj je to

```
čas ≈ (SPANJE_S + OPT_S + 1) × število algoritmov × ZAGONOV
    = 71 s × 3 × 10 ≈ 36 min     (ZAGONOV = 25: ≈ 89 min)
```

Za vsako funkcijo in dimenzijo potrebujete ločen poskus.

---

## 6. Algoritmi

Vsi algoritmi računajo izključno v `float`, ker ima jedro Xtensa LX6 strojno enoto za plavajočo vejico le za enojno natančnost. `double` bi se računal programsko in bil večkrat počasnejši. Generator naključnih števil je xorshift32 s semenom, ki je odvisno od številke ponovitve, zato so zagoni ponovljivi. Vsa populacija in arhiv se alocirata **enkrat** ob zagonu programa, tako da dinamična alokacija ne vpliva na meritev. Selekcija ne kopira vektorjev, ampak samo zamenja kazalca.

### 6.1 Klasični DE (DE/rand/1/bin)
- Mutacija: v = x_r1 + F · (x_r2 − x_r3), kjer so r1, r2, r3 med seboj različni in različni od i.
- Binomsko križanje s CR, z zagotovljeno vsaj eno komponento iz mutanta (j_rand).
- Fiksna F = 0,5, CR = 0,9, NP = 100.
- Komponenta izven mej se nadomesti z naključno vrednostjo znotraj mej.
- Sinhrona generacija: vsi poskusni vektorji se tvorijo iz populacije g, nato sledi selekcija (u ≤ x).

### 6.2 jDE (Brest in sod., 2006)
- Enako kot DE, le da ima vsak posameznik svoja F in CR.
- Pred tvorbo poskusnega vektorja: z verjetnostjo τ₁ = 0,1 dobi nov F ∈ [0,1; 1,0], z verjetnostjo τ₂ = 0,1 dobi nov CR ∈ [0; 1).
- Nova parametra preživita le, če je poskusni vektor uspešen.
- Začetni F = 0,5, CR = 0,9, NP = 100.

### 6.3 L-SHADE (Tanabe in Fukunaga, 2014)
- Mutacija current-to-pbest/1 z arhivom: v = x_i + F(x_pbest − x_i) + F(x_r1 − x̃_r2), kjer je x̃_r2 iz populacije ∪ arhiva, pbest pa iz najboljših p = 11 %.
- Zgodovinski spomin velikosti H = 6. CR ~ N(M_CR, 0,1), odrezan na [0, 1]. F ~ Cauchy(M_F, 0,1), ponavljanje dokler F ≤ 0, rezanje na 1.
- Posodobitev spomina z uteženo Lehmerjevo sredino, uteži so sorazmerne izboljšavi |Δf|. Vključuje terminalno vrednost M_CR (⊥ → CR = 0).
- Arhiv velikosti r_arc · NP = 2,6 · NP, polni se s poraženimi starši, ob prepolnitvi se briše naključno.
- Obravnava mej: polovica poti do kršene meje, (meja + x_i)/2.
- Linearno zmanjševanje populacije (LPSR) od NP_init do NP_min = 4, odstranjujejo se najslabši.

**Odstopanja od originala, ki jih je treba navesti v članku:**

1. **NP_init je omejen zaradi pomnilnika.** Original predpisuje NP_init = 18·D. Pri D = 50 je to 900 posameznikov, kar bi z arhivom zahtevalo približno 830 kB RAM, ESP32 pa ima ~300 kB. Zato je NP_init = min(18·D, ⌊9200/D⌋):

   | D | NP_init (original) | NP_init (tu) | RAM za populacijo in arhiv |
   |---|---|---|---|
   | 10 | 180 | 180 | ~45 kB |
   | 30 | 540 | 306 | ~187 kB |
   | 50 | 900 | 184 | ~179 kB |
   | 100 | 1800 | 92 | ~179 kB |

2. **LPSR je vezan na čas, ne na število evalvacij.** Original zmanjšuje populacijo glede na delež porabljenih evalvacij (NFE/MAX_NFE). Ker je tu zaustavitveni pogoj čas, se uporablja delež pretečenega časa: NP = round((NP_min − NP_init) · t/T + NP_init). Enak princip bi se dalo uporabiti z deležem porabljene energije. To je naravna razširitev vaše ideje o energiji kot zaustavitvenem pogoju.

Če program ob zagonu ne dobi dovolj pomnilnika (npr. ob prevelikem `DIM`), poskusa ne izvede. Ob priklopu na USB izpiše `#NAPAKA: premalo pomnilnika ...`.

---

## 7. Shranjevanje rezultatov

- **Stanje poskusa** (teče / končan / napaka) in **oznaka prevoda** se hranita v NVS (knjižnica Preferences).
- **Rezultati** se po vsakem zagonu dodajo v datoteko `/rez.bin` na LittleFS. En zapis ima 108 bajtov, zato je prostora za tisoče zagonov.
- Ob vsakem **novem nalaganju programa** se oznaka prevoda spremeni in stari rezultati se samodejno zavržejo.
- Ob vklopu ESP32 velja:
  - če je poskus **končan**, samo izpisuje rezultate in nič ne briše,
  - sicer (prvi zagon ali prekinjen poskus) **začne poskus od začetka**.
- Nov poskus brez ponovnega nalaganja: med izpisom pritisnite tipko **BOOT** ali v Serial Monitor pošljite **`n`**.

---

## 8. Postopek meritve, korak za korakom

1. **Nastavite** parametre na vrhu `ea_energija.ino`.
2. **Naložite** program prek USB (*Upload*). Če se nalaganje ustavi pri "Connecting...", držite tipko BOOT. Program se po nalaganju takoj zažene na USB napajanju, kar ni problem.
3. **Odklopite USB.** Ker poskus na USB ni bil zaključen, se bo ob naslednjem vklopu začel znova.
4. **Priklopite RIGOL** na 3V3 in GND z izklopljenim izhodom.
5. **Zaženite snemanje** na PC-ju:
   ```bash
   python zajem.py seznam                    # naslov RIGOL-a, npr. USB0::0x1AB1::...
   python zajem.py snemaj --rigol "USB0::0x1AB1::0x0E11::DP8XXXXXXXXX::INSTR" --mapa meritve_rastrigin50
   ```
6. **Vklopite izhod** RIGOL-a. Skripta sproti izpisuje tok in moč.
7. **Počakajte.** Skripta se ustavi sama, ko je ESP32 po zadnjem zagonu 60 s v deep sleepu. Lahko pa jo ustavite s **Ctrl+C**, ko vidite, da je tok padel in ostal nizek.
8. **Izklopite izhod in odklopite RIGOL.**
9. **Priklopite USB** in rezultate preberite s skripto (Serial Monitor mora biti zaprt):
   ```bash
   python zajem.py preberi --port COM5 --mapa meritve_rastrigin50
   ```
   Skripta počaka na celoten izpis in ga shrani v `esp32.txt`. Lahko pa izpis iz *Serial Monitorja* (115200 baud) ročno skopirate v `esp32.txt` v isti mapi. Večkratno kopiranje istega izpisa in časovni žigi Serial Monitorja ne motijo.
10. **Analiza:**
    ```bash
    python zajem.py analiza meritve_rastrigin50/rigol.csv meritve_rastrigin50/esp32.txt --grafi
    ```
11. **Naslednji poskus** (npr. Rosenbrock): spremenite `FUNKCIJA`, naložite program in ponovite od točke 3.

**Hiter preizkus pred pravo meritvijo:** `ZAGONOV 2`, `SPANJE_S 5`, `OPT_S 10` in `IZPIS_MED_POSKUSOM 1`, na USB brez RIGOL-a. Po približno 1,5 minute so v Serial Monitorju vrstice REZ. Nato vrnite `IZPIS_MED_POSKUSOM 0`.

---

## 9. Izpis ESP32

```
#POSKUS funkcija=rastrigin D=50 zagonov=10 spanje=10s opt=60s tock=20 cilj=1.000e-06 ...
#REZ,i,alg,zagon,fe,gen,best,cas_ms,fe_cilj,ms_cilj,np_konec
REZ,0,DE,0,1111600,11115,1.790931e+01,60000,0,0,100
REZ,1,jDE,0,1235300,12352,0.000000e+00,60000,166749,9360,100
...
#KONV,i,alg,zagon,best_1 ... best_TOCK
KONV,0,DE,0,4.2527e+02,3.7166e+02,...
#STAT,alg,kolicina,n,povprecje,std,iz95,mediana,q1,q3,min,max
STAT,DE,best,10,...
USPEH,jDE,10,10,100.0%
#KONEC_IZPISA
```

| Polje | Pomen |
|---|---|
| `i` | zaporedna številka zagona v poskusu (vrstni red v toku) |
| `alg`, `zagon` | algoritem in številka ponovitve |
| `fe`, `gen` | število evalvacij in generacij v OPT_S sekundah |
| `best` | najboljša najdena vrednost |
| `cas_ms` | dejanski čas optimizacije, izmerjen na ESP32 |
| `fe_cilj`, `ms_cilj` | evalvacije in milisekunde do `best ≤ PRAG_CILJA` (0 = ni doseženo) |
| `np_konec` | velikost populacije ob koncu (L-SHADE: 4) |
| `KONV` | best ob t = OPT_S·k/TOCK, k = 1…TOCK |
| `STAT` | opisna statistika po algoritmih: best, fe, fe_na_s, ms_do_cilja |
| `USPEH` | delež zagonov, ki so dosegli cilj |

---

## 10. Python skripta (`zajem.py`)

### 10.1 Ukazi

| Ukaz | Pomen |
|---|---|
| `seznam` | izpiše priklopljene VISA naprave |
| `snemaj --rigol NASLOV [--mapa M]` | snema napetost, tok in moč v `M/rigol.csv` (privzeto `meritve_DATUM_CAS/`) |
| `preberi --port COM5 --mapa M` | prebere rezultate z ESP32 prek USB v `M/esp32.txt` |
| `analiza rigol.csv esp32.txt [--grafi]` | izračun energije, statistika, testi, grafi |

**Možnosti za `snemaj`:**

| Možnost | Privzeto | Pomen |
|---|---|---|
| `--kanal` | `CH1` | kanal napajalnika. Pri enokanalnih modelih (npr. DP711) `--kanal ""` |
| `--perioda` | 0,05 s | premor med poizvedbami. Dejanska frekvenca je ~5–10 Hz zaradi trajanja poizvedbe |
| `--prag-visok-ma` | 20 mA | nad tem tokom velja, da ESP32 računa |
| `--prag-konec-ma` | 1 mA | pod tem tokom velja, da je ESP32 v deep sleepu |
| `--cas-konec-s` | 60 s | koliko časa mora biti tok pod pragom za samodejno ustavitev |
| `--visa-backend` | `@py` | `""` za NI-VISA / UltraSigma |

Če LED in USB čip na vaši ploščici tudi v deep sleepu porabita več kot 1 mA, se snemanje ne ustavi samo. Takrat ga ustavite s Ctrl+C ali povečajte `--prag-konec-ma`. Na analizo to ne vpliva.

### 10.2 Metoda analize

1. **Iskanje zagonov.** Prag je sredina med nizko ravnjo moči (3. percentil, spanje) in visoko (97. percentil, računanje). Interval nad pragom šteje kot zagon, če traja 0,8–1,2 × OPT_S. Kratki skoki (zagon ESP32, formatiranje flasha, pisanje rezultatov) se zavržejo. Čas prečkanja praga se linearno interpolira med vzorci, zato je meja natančnejša od periode vzorčenja.
2. **Povezava z rezultati.** Zagoni v toku se z vrsticami REZ povežejo po vrstnem redu. Če se število ne ujema, skripta izpiše opozorilo.
3. **Energija zagona** E: trapezna integracija moči P(t) med začetkom in koncem intervala.
4. **Bazna poraba** P_baza: povprečna moč v spanju pred zagonom, od t₀ − SPANJE_S + 2 s do t₀ − 0,5 s. **Neto energija** je E − P_baza · T.
5. **Energija na evalvacijo**: E / FE v µJ.
6. **Energija do cilja**: integral moči od začetka zagona do trenutka `ms_cilj`, ki ga je zabeležil ESP32. **Energija po cilju** (E − E_do_cilja) je energija, ki jo je algoritem porabil, potem ko je cilj že dosegel. To je energija, ki bi jo prihranil energijsko ozaveščen zaustavitveni pogoj.
7. **Konvergenca po energiji**: za vsako točko KONV se izračuna energija od začetka zagona do tega trenutka.
8. **Statistični testi**: dvostranski Mann-Whitneyjev test (Wilcoxonov rank-sum) za vse pare algoritmov, s Holm-Bonferronijevim popravkom znotraj vsake metrike, in velikost učinka Vargha-Delaney A12. Pri energiji do cilja dobijo neuspeli zagoni vrednost +∞, torej so pri rangiranju najslabši. To je običajna obravnava pri metrikah "čas do cilja". Če je nameščen scipy, se uporabi točna porazdelitev testne statistike, sicer normalna aproksimacija s popravkom za vezi.

### 10.3 Izhodne datoteke (v mapi z meritvami)

| Datoteka | Vsebina |
|---|---|
| `rigol.csv` | `t_s, U_V, I_A, P_W`, vsi vzorci napajalnika |
| `energija.csv` | ena vrstica na zagon: `alg, ponovitev, trajanje_s, cas_esp_s, E_J, E_mWh, E_neto_J, P_povp_mW, P_bazna_mW, fe, uJ_na_fe, uJ_neto_na_fe, best, cilj_dosezen, ms_do_cilja, E_do_cilja_J, E_neto_do_cilja_J, E_po_cilju_J, np_konec` |
| `povzetek.csv` | opisna statistika vsake metrike po algoritmih (n, povprečje, std, 95 % IZ, mediana, Q1, Q3, min, max) |
| `testi.csv` | p, p_Holm in A12 za vse pare algoritmov za `best`, `uJ_na_fe`, `E_J` in `E_do_cilja_J` |
| `konvergenca_energija.csv` | `alg, ponovitev, tocka, t_s, E_J, best` za graf konvergence po energiji |
| `graf_moc.png` | potek moči s pobarvanimi prepoznanimi zagoni. **Vedno preverite**, ali je segmentacija pravilna |
| `graf_konvergenca_energija.png` | mediana in IQR najboljše vrednosti glede na porabljeno energijo (vrednosti 0 so na logaritemski osi prikazane kot 10⁻¹²) |
| `graf_energija.png` | škatlasta diagrama µJ/FE in energije do cilja (v oklepaju število uspešnih zagonov) |

**Preverjanje meritve:** `trajanje_s` iz toka in `cas_esp_s` z ESP32 se morata ujemati na nekaj desetink sekunde natančno. `P_bazna_mW` mora biti podobna pri vseh zagonih.

---

## 11. Pričakovani rezultati

Na ESP32 pri D = 10 in NP = 50 jDE naredi ~82 500 evalvacij na sekundo. Razlika v številu evalvacij med zagoni je ~0,01 %, kar pomeni zelo majhno varianco energije.

Simulacija na PC-ju, kjer 1 s ustreza približno 60–80 s na ESP32, nakazuje naslednje (3 ponovitve, cilj 10⁻⁶):

| Problem | DE | jDE | L-SHADE |
|---|---|---|---|
| Rastrigin D = 50 | best ~10–30, cilj ni dosežen | cilj v ~6–13 s | cilj v ~13–26 s |
| Rastrigin D = 100 | best ~550–670, cilj ni dosežen | cilj v ~35–45 s | cilj v ~20–30 s |
| Rosenbrock D = 50 | cilj v 2 od 3 zagonov, ~25–45 s | cilj v ~25–45 s | cilj v ~11–15 s |
| Rosenbrock D = 100 | best ~70–190, cilj ni dosežen | best ~70–110, cilj ni dosežen | cilj v 2 od 3 zagonov, ~30–40 s |

Pri D = 50 in D = 100 se algoritmi torej jasno ločijo tako po kakovosti kot po energiji do cilja. Ti časi so le ocena, prave vrednosti dobite z meritvijo.

Če cilj 10⁻⁶ pri kakem algoritmu ni nikoli dosežen, nastavite bolj dosegljiv `PRAG_CILJA` (npr. 1e-2 ali 1e0), da dobite smiselno primerjavo energije do cilja.

---

## 12. Pogoste težave

| Težava | Rešitev |
|---|---|
| Nalaganje obstane pri "Connecting..." | med nalaganjem držite tipko BOOT |
| `#NAPAKA: premalo pomnilnika` | zmanjšajte `DIM` ali `DE_NP`/`JDE_NP` |
| Serial Monitor ne izpisuje ničesar | 115200 baud, pritisnite EN. Če poskus še ni končan, ESP32 izvaja poskus in ne izpisuje |
| `python zajem.py seznam` ne najde RIGOL-a | NI-VISA ali UltraSigma in `--visa-backend ""`. Preverite USB kabel in na RIGOL-u izbiro USB vmesnika |
| Napaka pri poizvedbi `:MEAS:ALL?` | drug model RIGOL-a. Pri enokanalnih `--kanal ""`, sicer preverite ukaz v priročniku modela |
| Snemanje se ne ustavi samo | tok v deep sleepu je nad 1 mA (LED). Ctrl+C ali `--prag-konec-ma 10` |
| "število zagonov v toku in vrstic REZ se ne ujema" | snemanje se je začelo po vklopu izhoda ali se je ESP32 vmes resetiral (prenizka tokovna omejitev). Preverite `graf_moc.png` |
| Poskus se začne znova, ko želite le brati | ESP32 je bil izklopljen pred koncem poskusa, zato rezultati niso bili označeni kot končani |

---

## 13. Za članek: kaj navesti v metodologiji

- Naprava: ESP32-WROOM-32 (Xtensa LX6, 240 MHz), razvojna ploščica (model), napajanje 3,30 V neposredno na 3V3 (mimo LDO), WiFi in Bluetooth nista inicializirana.
- Algoritem teče na enem jedru, drugo jedro je nedejavno. Vsi izračuni v enojni natančnosti (strojni FPU).
- Merilnik: model RIGOL, frekvenca vzorčenja (iz `rigol.csv`), ločljivost toka. Integracija s trapezno metodo.
- Bazna poraba ploščice v light sleepu, poročane bruto in neto vrednosti.
- Parametri algoritmov (razdelek 6) in obe odstopanji L-SHADE od originala.
- Izmenjevanje algoritmov med ponovitvami in skupna semena.
- Število ponovitev, zaustavitveni pogoj (čas OPT_S), cilj za energijo do cilja.
- Statistika: Mann-Whitney, Holm, A12. Neuspeli zagoni pri energiji do cilja = +∞.
- **Omejitev:** frekvenca vzorčenja napajalnika (~5–10 Hz) zadošča za energijo v oknu 60 s, kjer je moč skoraj konstantna. Za časovni potek toka v milisekundah (npr. prikaz posameznih faz algoritma) je potreben osciloskop z merilnim uporom. GPIO4 je pripravljen kot sinhronizacijski signal.

---

## 14. Literatura

- R. Storn, K. Price, "Differential Evolution – A Simple and Efficient Heuristic for Global Optimization over Continuous Spaces", *Journal of Global Optimization* 11, 341–359, 1997.
- J. Brest, S. Greiner, B. Bošković, M. Mernik, V. Žumer, "Self-Adapting Control Parameters in Differential Evolution: A Comparative Study on Numerical Benchmark Problems", *IEEE Transactions on Evolutionary Computation* 10(6), 646–657, 2006.
- R. Tanabe, A. Fukunaga, "Improving the Search Performance of SHADE Using Linear Population Size Reduction", *IEEE Congress on Evolutionary Computation (CEC)*, 1658–1665, 2014.
- A. Vargha, H. D. Delaney, "A Critique and Improvement of the CL Common Language Effect Size Statistics of McGraw and Wong", *Journal of Educational and Behavioral Statistics* 25(2), 101–132, 2000.
- S. Holm, "A Simple Sequentially Rejective Multiple Test Procedure", *Scandinavian Journal of Statistics* 6(2), 65–70, 1979.
