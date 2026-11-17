# Navodila za laboratorij: en Windows PC za RIGOL in ESP32, vse v PyCharmu

En računalnik z Windows je povezan z napajalnikom RIGOL **in** z ESP32. Vse korake poganjate kot
skripte v PyCharmu (`W0` … `W8`); Arduino IDE potrebujete samo enkrat, za namestitev jedra esp32.
Program za ESP32 prevede in naloži skripta `W2` (prek `arduino-cli`, ki je del Arduino IDE).

Enakovredni navodili za druge postavitve: `LAB_GUIDE_IDE.md` (Arduino IDE na Macu, PyCharm na PC-ju)
in `LAB_GUIDE_CLI.md` (ukazna vrstica). Vse tri uporabljajo isti program, iste zapise in iste preverbe.

**Stanje kode.** Vse je preizkušeno na računalniku (131 testov, poskusni zagoni skript na sintetičnih
podatkih, prevod programa brez opozoril). **Na Windows, z ESP32 in z RIGOL-om še ni bilo nič pognano.**
Samopreizkus (C) in preizkus verige (D) sta zato tudi prvi preizkus skript na pravi opremi. Ko kaj ne
dela, mi pošljite celoten izpis iz PyCharma. Kampanje (F) ne začnite, dokler C in D nista v redu.

---

## Pet pravil, ki varujejo meritev

1. **USB kabel ESP32 in RIGOL nikoli ne napajata ploščice hkrati.** USB kabel ESP32 je priklopljen samo,
   ko je stikalo v + vodniku RIGOL-a **odprto**. Med snemanjem je USB kabel ESP32 **izklopljen** (`W4` to
   preveri in brez tega ne začne).
2. **Tipke EN (RST) nikoli ne pritiskajte.** Po nalaganju novega programa bi z njo začeli sejo na
   napajanju USB.
3. **Z BOOT ali brez BOOT** (razdelek »Priklop ESP32«): z držano tipko BOOT za `W1`, `W2`, `W3`; brez nje
   za `W5`, `W8`.
4. **Pred `W2` shranite kodo v git** (PyCharm: *Git → Commit*), sicer ima prevod oznako `+spremembe` in
   analiza njegove seje zavrne.
5. **Vsaka seja ima svojo mapo** `meritve/<seja>`; nič surovega se nikoli ne prepiše. Mape `meritve/` in
   `arhiv/` redno kopirajte na varno mesto (v git ne gredo).

---

## 0. Namestitev (enkrat)

### 0.1 Programi

1. **Python 3.11 ali novejši** s [python.org](https://www.python.org/downloads/windows/). Pri namestitvi
   označite *Add python.exe to PATH*.
2. **PyCharm** (Community zadošča).
3. **Git for Windows** (git-scm.com). Potreben je za oznako prevoda, ki poveže zapise s kodo.
4. **Arduino IDE 2.** Odprite *Tools → Board → Boards Manager*, poiščite **esp32 by Espressif Systems** in
   namestite različico **3.3.12** (iz seznama različic; ne najnovejše, če je drugačna). Če esp32 na seznamu
   ni, v *File → Preferences → Additional boards manager URLs* dodajte
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json` in poskusite znova. Po tem Arduino
   IDE ne potrebujete več; zaprite ga (zaseda serijska vrata).
5. **NI-VISA** (ali RIGOL UltraSigma), da Windows vidi napajalnik kot napravo VISA.
6. **Gonilnik za USB pretvornik na ploščici ESP32:** priklopite ESP32 (stikalo RIGOL-a odprto) in v
   *Upravitelju naprav → Vrata (COM in LPT)* poglejte, ali se pojavi npr. *Silicon Labs CP210x … (COM5)*
   ali *USB-SERIAL CH340 (COM3)*. Če se pojavi z rumenim klicajem ali ga ni, namestite gonilnik Silicon
   Labs CP210x oziroma WCH CH340.

### 0.2 Windows: računalnik ne sme zaspati in ne sme izklopiti USB

Med kampanjo (več ur) računalnik ne sme zaspati in ne sme izklopiti napajanja USB:

* *Nastavitve → Sistem → Napajanje*: zaslon in spanje **Nikoli** (ko je priklopljen na omrežje).
* *Nadzorna plošča → Možnosti porabe energije → Spremeni nastavitve načrta → Spremeni dodatne nastavitve
  porabe energije → Nastavitve USB → Začasna ustavitev izbirnega USB*: **Onemogočeno**.
* Posodobitve Windows začasno ustavite za čas kampanje.

### 0.3 Projekt v PyCharmu

1. Kopirajte celotno mapo `gecco2027-electricity` **skupaj s skrito mapo `.git`** na računalnik (npr. v
   `C:\Users\<ime>\gecco2027-electricity`).
2. PyCharm: *File → Open* → izberite mapo **`gecco2027-electricity\ea_energija`**.
3. *File → Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter →
   Virtualenv Environment → New* (osnova: Python 3.11+) → OK.
4. Odprite datoteko `requirements.txt`; PyCharm ponudi *Install requirements* → kliknite. Ali v zavihku
   *Terminal* (spodaj) prilepite:

   ```bash
   python -m pip install -r requirements.txt
   ```

5. Preverite veje (zavihek *Terminal*); izpisati mora `audit/phase2`:

   ```bash
   git branch --show-current
   ```

### 0.4 Kako poganjate skripte v PyCharmu

* Dvokliknite datoteko (npr. `W0_preveri_namestitev.py`), z desnim klikom v urejevalnik → **Run '…'**
  (ali zeleni trikotnik zgoraj desno).
* Izpis je v oknu *Run* spodaj. **Rdeči kvadrat** skripto ustavi.
* Nastavitve skripte so VELIKE ČRKE na vrhu datoteke. Spremenite → **Ctrl+S** → Run.
* Nastavitve seje so v **eni datoteki, `seja_nastavitve.py`**. Pred vsako sejo spremenite samo njo.

### 0.5 Preverjanje namestitve

Priklopite RIGOL (USB na PC, vklopljen; izhod ostane izklopljen). Poženite **`W0_preveri_namestitev.py`**.
Preveri Python in pakete, `arduino-cli` z jedrom esp32 3.3.12, git, kodo, serijska vrata, napajalnik RIGOL
(prebere identiteto, nič ne nastavlja) in požene vse teste. Na koncu mora pisati **`VSE V REDU`**. Pri
vsaki vrstici `NAPAKA` je napisano, kaj namestiti. (Opomba »ESP32 ni priklopljen« je v redu, če USB
kabel ESP32 ni priklopljen.)

---

## Priklop ESP32: z BOOT ali brez BOOT

Ob USB priključku ploščice sta dve tipki: **EN** (ali RST) in **BOOT** (ali IO0). EN nikoli ne
pritiskajte. Ali tipko BOOT držite, ko ploščica dobi napajanje, odloči, kaj ESP32 naredi:

| Kako ploščica dobi napajanje | Kaj naredi ESP32 | Kdaj |
|---|---|---|
| USB priklopljen **ob držani BOOT** | Ostane v nalagalniku; program se **ne** zažene. Varno. | `W1`, `W2`, `W3` |
| Samodejno takoj po nalaganju (`W2`) | Prvi zagon novega programa: ploščico pripravi in zaspi. Varno. | Po vsakem `W2` |
| USB priklopljen **brez** BOOT po nalaganju in pred sejo | **Začne sejo na napajanju USB. Napačno.** `W3` to zazna in pove, kako popraviti. | Nikoli |
| Izhod RIGOL-a vklopljen (stikalo zaprto, USB izklopljen) | Začne sejo. Pravilno. | `W4` |
| USB priklopljen **brez** BOOT po seji | Izpisuje zapise. | `W5`, `W8` |

**Postopek »z BOOT«:**

1. Stikalo RIGOL-a je odprto. Arduino IDE in njegov Serial Monitor sta zaprta.
2. Izklopite USB kabel ESP32 in počakajte 2 s.
3. Pritisnite in **držite BOOT**.
4. Medtem ko držite BOOT, priklopite USB kabel ESP32 (neposredno v računalnik, brez razdelilca).
5. **BOOT držite naprej**, poženite skripto in tipko spustite, ko skripta izpiše odstotke (`Reading …`)
   ali, pri `W2`, `Connecting…`/`Writing at …`.

Če skripta izpiše `Failed to connect … No serial data received`, ESP32 ni bil v nalagalniku: ponovite
korake 2–5.

---

## A. Stari podatki

**Že narejeno na Macu:** kopija flasha in obnovljeni zapisi so v `ea_energija/arhiv/flash_2026-11-18/` na
Macu. Mapo kopirajte v isto mesto na PC-ju in v arhiv. Tega koraka na Windows ne ponavljajte: odkar je bila
kopija narejena, se je stari program lahko zagnal in prepisal bloke, iz katerih so bili zapisi obnovljeni.

Samo za drugo ploščico, ki je še ni kopiral nihče: priklopite jo **z BOOT** (postopek zgoraj) in poženite
**`W1_kopija_flash.py`** (okoli 6 min). Rezultat je v `arhiv/flash_<datum>/`, obnovljeni zapisi v
`arhiv/flash_<datum>/zapisi/obnovljeno/`.

---

## B. Vezava in napajalnik

Strojna oprema je nespremenjena (`SETUP_GUIDE.md`, razdelek 1):

* RIGOL **CH1** (kanal 60 V / 1 A) na pin **3V3** in **GND** ploščice, prek stikala v + vodniku. Nikoli 5V/VIN.
* RIGOL z USB kablom na PC. ESP32 z USB kablom na PC, **samo ko je stikalo odprto**.
* Nič drugega na ploščici. Ista ploščica, žice in kanal za vse seje.

Napajalnika ne nastavljate ročno. `W4` nastavi 3,30 V, omejitev 0,5 A, OVP 3,6 V in OCP 0,6 A, vsako
nastavitev prebere nazaj, primerja in začne samo, če se ujemajo.

---

## C. Samopreizkus (okoli 5 minut snemanja)

Namen: preveriti meritev RIGOL-a in izračun energije z znanimi obremenitvami ter izmeriti, koliko časa na
čipu trajata branje ure in ena evalvacija.

**C1. Nastavitev seje.** Odprite `seja_nastavitve.py` in nastavite (ostale vrstice pustite):

```python
VRSTA = "samopreizkus"
RED = 0
```

Ctrl+S.

**C2. Prevod in nalaganje.** Stikalo odprto. ESP32 priklopite **z BOOT** (postopek zgoraj). Poženite
**`W2_pripravi_in_nalozi.py`**. Prevod traja 1–3 min, nalaganje okoli 30 s. Konča z `NALOŽENO. Aktivna
seja: <datum>_samopreizkus` in navodilom za naslednji korak.

* Če piše `OPOZORILO: … '+spremembe'`: *Git → Commit*, nato `W2` znova.
* Če nalaganje ne uspe s `Failed to connect`: ponovite priklop z BOOT in `W2`.

**C3. Preverjanje.** Izklopite USB kabel ESP32, **držite BOOT, priklopite, BOOT držite**, poženite
**`W3_preveri_nalaganje.py`**, BOOT spustite, ko se izpišejo odstotki (okoli 50 s). Preveri, da je na čipu
pravi program, da so nastavitve plošče prave in da se seja še ni začela. Mora končati z **`VSE V REDU`**.
Nato **izklopite USB kabel ESP32**.

Če javi težavo, pove, kaj storiti:

* `novi program se po nalaganju še ni zagnal`: USB priklopite **brez** BOOT, počakajte 10 s, izklopite,
  ponovite C3.
* `seja se je že začela`: USB priklopite brez BOOT, počakajte 15 s, v `W8_pobrisi_zapise.py` nastavite
  `POTRJUJEM = True`, poženite, izklopite USB, ponovite C3 (in `POTRJUJEM` vrnite na `False`).

**C4. Snemanje.** USB kabel ESP32 izklopljen, **zaprite stikalo**, poženite **`W4_snemaj.py`**. Izpiše
nastavitve, prebrane z RIGOL-a, vklopi izhod (ESP32 se zažene), snema in se sam ustavi približno minuto po
tem, ko ESP32 konča in zaspi; nato izklopi izhod. Na koncu izpiše doseženo frekvenco vzorčenja in tresenje.
Med snemanjem se ničesar ne dotikajte.

**C5. Branje zapisov.** **Odprite stikalo.** USB kabel ESP32 priklopite **brez** BOOT. Poženite
**`W5_preberi.py`**. Shrani `meritve/<seja>/esp32.txt` in izpiše preverjanje nastavitev plošče.

**C6. Analiza.** Poženite **`W6_analiza.py`**. Poročilo je v `meritve/<seja>/samopreizkus_<datum>/porocilo.txt`.

**Kaj preveriti v poročilu:**

* *Stalne obremenitve*: štiri različne ravni moči; `E1 proti E2` pod pol odstotka; odmiki robov
  (`rob sled - ESP32`) majhni in ne naraščajo od prve do četrte obremenitve (naraščanje pomeni, da ura ESP32
  in ura PC-ja lezeta narazen).
* *Delovni cikli*: izmerjena povprečna moč blizu pričakovane. Majhna pozitivna razlika je normalna (bujenje
  iz spanja porabi nekaj energije). Vrstice z `OZNAČENO` presegajo 5 % in jih pošljite meni.
* *Čas operacij*: delež evalvacije, ki ga stane branje ure v načinu CAS. Mora biti precej pod 1 %; sicer mi
  sporočite pred kampanjo.
* `meritve/<seja>/meta_konec.json`: `napak_branja` 0, `vzorcev_nacina_ne_CV` 0, `OVP_sprozen` in
  `OCP_sprozen` `NO`, perioda vzorčenja (`perioda`).

Če `W4` konča z `NAPAKA RIGOL`, sporočilo pove, kateri ukaz ali nastavitev se ni ujemala. Pošljite mi ga.

---

## D. Preizkus verige (20–40 minut snemanja)

Namen: celoten protokol na vseh štirih celicah s proračunom kampanje, po dva bloka, in ena kratka vrstica v
načinu CAS. Preveri program od začetka do konca in da trajanja, iz katerih se določi T.

`seja_nastavitve.py`:

```python
VRSTA = "veriga"
RED = 0
```

Nato natanko koraki **C2 → C6**: `W2` (z BOOT) → `W3` (z BOOT, `VSE V REDU`, USB izklop) → stikalo zaprto,
`W4` → stikalo odprto, USB brez BOOT, `W5` → `W6`. Snemanje ima 45 zagonov (5 vrstic × 3 algoritmi × (2 bloka
+ 1 ogrevalni)). `W5` in `W6` izpišeta povzetek zapisov (stanje seje, trajanja po celicah in algoritmih,
doseženi cilji); `W6` naredi celotno analizo v `meritve/<seja>/analiza_<datum>_<ura>/`.

**Sprejemni pogoji** (vsi morajo veljati pred kampanjo):

1. Povzetek: `stanje = koncan, zapisov 45 od načrtovanih 45, resetov = 1`, ni pokvarjenih zapisov, vsaka
   vrstica FE ima `FE` enak proračunu (100000 pri D = 10, 200000 pri D = 20).
2. Analiza konča brez `NAPAKA ANALIZE`: 45 oken, 45 zapisov.
3. `E1 proti E2`: noben zagon ni označen ali pa razumete, zakaj.
4. `izlocitve.csv` navaja natanko 15 ogrevalnih zagonov in nič drugega.
5. `energija.csv`: `cpu_mhz` povsod 240; `prosta_kopica_B` se iz zagona v zagon ne manjša; `sklad_min`
   ostaja precej nad nič; `pocitek_esp_s` blizu 10.
6. `meta_konec.json` kot pri C.

(Primerjavo z gostiteljskim prevodom, `gostitelj/primerjaj_z_napravo.py`, lahko po želji poženete na Macu z
datoteko `esp32.txt`; na Windows potrebuje prevajalnik C++.)

**Če se analiza ustavi**, sporočilo pove zakaj. Najverjetnejši primeri ob prvem zagonu:

| Sporočilo | Pomen in ukrep |
|---|---|
| `V sledi moči je N merilnih oken, zapisov REZ pa je M` | Okna in zapisi se ne ujemajo. Odprite `okna.csv` v novi mapi `analiza_…`. Če je zagon ESP32 ali pisanje v flash štelo kot okno, ali kratek zagon FE ni, popravite `okna.min_trajanje_okna_s` (korak E) in ponovno poženite `W6`. |
| `znotraj robov (...) je samo N vzorcev` | Okno je za rob E2 pri tej frekvenci vzorčenja prekratko. Glejte korak E. |
| `premor pred oknom X s, pričakovan 11 s` | Premor med zagoni odstopa več kot `okna.toleranca_premora_s`. Če je X stalen, povečajte toleranco (E); če skače, poglejte sled. |
| `vrzel_v_oknu` | Računalnik je v oknu izgubil vzorce za več kot 1 s (`rigol_dogodki.csv`). Ponovite sejo; preverite nastavitev USB iz 0.2. |
| `ni_CV_v_oknu` | Napajalnik je zapustil način CV ali se je napetost premaknila za več kot 0,05 V. Preverite vezavo. |
| `Program ni sledljiv ali ni preveden z zahtevanimi nastavitvami` | Prevod `rocno` ali `+spremembe`, ali se koda v mapi seje razlikuje od kode, ki je bila prevedena. Git → Commit, `W2`, ponovite sejo. |
| `seja se ni končala redno: stanje = prekinjen` | ESP32 se je med sejo ponovno zagnal; sporočilo pove razlog (npr. padec napetosti). |

Vsaka analiza piše v novo podmapo; ponovna analiza z drugimi nastavitvami nič ne izgubi. Surove datoteke se
nikoli ne spreminjajo.

---

## E. Nastavitve za kampanjo (po C in D, pred F)

Ko so kampanjski podatki enkrat posneti, se nič od tega ne sme več spreminjati.

**E1. T za štiri celice.** T je mediana trajanja zagonov FE te celice v preizkusu verige, zaokrožena na celo
sekundo. Poženite **`W7_nastavi_T.py`** (aktivna seja je preizkus verige) in preglejte predlog. Če je
sprejemljiv, na vrhu datoteke nastavite in poženite znova (nato vrnite na `False`):

```python
ZAPISI = True
```

Skripta zavrne nedokončan preizkus, pokvarjene zapise in manjkajočo celico ter ne prepiše obstoječega
`ea_T.h` brez `PREPISI = True`. Brez `ea_T.h` se kampanja ne prevede.

**E2. Pragovi analize**, datoteka `analiza_nastavitve.json` (odprite jo v PyCharmu). Vrednosti so moje
privzete in potrebujejo vašo odločitev:

| Nastavitev | Privzeto | Kako določiti |
|---|---|---|
| `okna.min_trajanje_okna_s` | 1.5 | Med najdaljšim `kratek_interval` in najkrajšim pravim oknom v `okna.csv`. |
| `okna.toleranca_trajanja_s` | 0.5 | Največja dovoljena razlika med dolžino okna v sledi in na čipu. |
| `okna.toleranca_premora_s` | 1.5 | Iz premorov v preizkusu verige. |
| `energija.rob_E2_s` | 0.5 | Vsaj dve periodi vzorčenja (`perioda` v `meta_konec.json`). |
| `energija.min_vzorcev_E2` | 5 | Manj notranjih vzorcev ustavi analizo. |
| `energija.toleranca_E1_E2_rel` | 0.02 | Zagoni nad njo so označeni, ne izločeni. |
| `veljavnost.max_vrzel_s` | 1.0 | Najdaljša dovoljena vrzel med vzorci v oknu. |
| `veljavnost.U_toleranca_V` | 0.05 | Dovoljeno odstopanje od 3,30 V. |
| `samopreizkus.toleranca_rel` | 0.05 | Meja označevanja v samopreizkusu. |

**Kratka okna FE.** Pri FE_max = 10000 × D lahko zagoni pri D = 10 trajajo le nekaj sekund; pri 5–10 vzorcih
na sekundo je to malo vzorcev. Če preizkus verige pokaže okna, krajša od približno 3 s (`W7` na to opozori),
razmislite o večjem proračunu FE (`FE_D10`, `FE_D20` na vrhu `ea_energija.ino`) in ponovite D.

**E3. Vrstni red blokov.** `RED = 0`: naključen, 25 blokov (privzeto). `RED = 1`: uravnotežen, 30 blokov.
Odločite zdaj; izbira je zapisana v vsakem izpisu.

**E4. Shranite v git.** PyCharm: *Git → Commit*, označite `ea_T.h` (in `analiza_nastavitve.json`,
`ea_energija.ino`, če ste ju spremenili), sporočilo npr. *Nastavitve kampanje: T in pragovi* → **Commit**.

---

## F. Kampanja

Načrt: Rastrigin in Rosenbrock, D = 10 in 20, proračun FE in CAS = 8 vrstic; 3 algoritmi; 25 blokov + 1
ogrevalni → 624 zagonov. Trajanje ≈ 624 × 11,3 s (počitek in pisanje, okoli 2 uri) plus vsota vseh oken
(iz T v `ea_T.h`). Prostor v flashu program preveri pred začetkom.

`seja_nastavitve.py`:

```python
VRSTA = "kampanja"
RED = 0
```

Nato koraki **C2 → C6** (`W2` z BOOT → `W3` z BOOT, `VSE V REDU` → USB izklop, stikalo zaprto, `W4` →
stikalo odprto, USB brez BOOT, `W5` → `W6`). Posebej:

* `W2` ne sme izpisati `+spremembe`.
* Med snemanjem: računalnik na omrežju, nič se ne dotikajte. Če morate `W4` ustaviti (rdeči kvadrat),
  preverite, da je izhod RIGOL-a izklopljen. Varovalka ustavi snemanje po 24 h.
* Izpis zapisov v `W5` traja 1–2 min; če poteče čas, povečajte `CAS_BRANJA_S` v `W5_preberi.py`.
* Pričakovani povzetek: `stanje = koncan, zapisov 624 od načrtovanih 624, resetov = 1`.

**Če je bila seja prekinjena** (`stanje = prekinjen`): dotedanji zapisi ostanejo in jih preberete z `W5`.
Analiza nepopolno sejo zavrne. Ne lepite druge seje nanjo; poiščite vzrok (razlog ponovnega zagona je v
povzetku in sporočilu napake) in sejo ponovite.

---

## G. Ponovitev seje z istim programom

Isti program (ista koda, VRSTA in RED) ima isto oznako, zato nalaganje zapisov ne pobriše. Ko so zapisi
prebrani (`W5`), analizirani (`W6`) in mapa `meritve/` shranjena:

1. stikalo odprto, USB kabel ESP32 priklopite **brez** BOOT,
2. v `W8_pobrisi_zapise.py` nastavite `POTRJUJEM = True`, poženite (počaka konec izpisa, pošlje ukaz za
   brisanje in počaka potrditev), nato `POTRJUJEM` vrnite na `False`,
3. za novo ime seje poženite `W2` znova (z BOOT; prevede in naloži isti program, ustvari novo sejo), nato
   `W3` → `W4` → `W5` → `W6`.

Brisanja ni mogoče razveljaviti.

---

## H. Datoteke ene seje (`meritve/<seja>/`)

Surove, zapisane enkrat, nikoli spremenjene:

| Datoteka | Vsebina |
|---|---|
| `meta.json` | Začetek, identiteta instrumenta, zahtevane in **prebrane** nastavitve, pravila konca, zgostitev `zajem.py` |
| `rigol.csv` | `t_pred_s, t_po_s` (ura PC-ja pred poizvedbo in po njej), `U_V, I_A, P_W` natanko kot jih vrne instrument |
| `rigol_nacin.csv` | CV/CC/UR vsakih 10 s |
| `rigol_dogodki.csv` | Napake poizvedb in vrzeli s trajanjem |
| `meta_konec.json` | Razlog konca, število vzorcev, perioda in tresenje, končno stanje instrumenta |
| `ea_energija.ino`, `ea_jedro.h`, `ea_premiki.h`, `ea_T.h`, `ea_prevod.h` | Kopija kode; analiza preveri njeno zgostitev z oznako prevoda |
| `esp32.txt` | Zapisi ESP32 (`W5`) |
| `prevod_info.json` | Oznaka prevoda, revizija git, zgostitve, nastavitve plošče, različice orodij |

Za vsako analizo nova mapa `analiza_<datum>_<ura>/`: `porocilo.txt`, kopija `analiza_nastavitve.json`,
`okna.csv`, `energija.csv` (E2_J primarna, E1_J kontrolna, neto, µJ/FE, best, seme, CPU, kopica, sklad),
`cilji.csv`, `ert.csv`, `povzetek.csv`, `testi.csv`, `kontrola.csv`, `izlocitve.csv`,
`konvergenca_energija.csv` in grafi.

---

## I. Odpravljanje težav

| Težava | Ukrep |
|---|---|
| `W0`: `NAPAKA pyvisa/serial/esptool` | V PyCharmu ni izbran pravi interpreter ali paketi niso nameščeni (0.3, točka 3–4). |
| `W0`: `arduino-cli` ni najden | Arduino IDE 2 ni nameščen na običajno mesto. Ponovno namestite ali mi pošljite pot do `arduino-cli.exe`. |
| `W0`: jedro esp32 ni 3.3.12 | Arduino IDE → Boards Manager → esp32 → različica 3.3.12 → Install. |
| `W0`: RIGOL ni najden | USB kabel RIGOL-a, vklop, NI-VISA; preverite v *NI MAX*. |
| `Ne najdem ESP32` | Upravitelj naprav → Vrata (COM in LPT): katera vrata so ESP32? Vpišite jih v `PORT_ESP32` v `seja_nastavitve.py` (npr. `"COM5"`). Gonilnik CP210x/CH340. |
| `Failed to connect … No serial data received` | ESP32 ni v nalagalniku: postopek »z BOOT«. Zaprite Arduino IDE. |
| `No more data to read from the serial port` | Kabel ali razdelilec: drug kabel (za prenos podatkov), neposredno v računalnik; postopek »z BOOT«. |
| `could not open port … Access is denied` | Vrata uporablja drug program (Arduino IDE, Serial Monitor, druga skripta). Zaprite ga. |
| `W4`: `USB kabel ESP32 je PRIKLOPLJEN` | Izklopite USB kabel ESP32 (ali ga izvlecite iz ploščice). |
| `W4`: `Seja … je že posneta` | Za novo sejo `W2` (po potrebi prej `W8`). |
| `W3`: `seja se je že začela` | Glejte C3. |
| Snemanje se ustavi sredi kampanje | Spanje ali USB izklop v Windows (0.2). |

---

## J. Kaj še ni preverjeno

* Vse poti programa na pravi strojni opremi: stanja seje, kontrolna vsota zapisov, razlogi ponovnega zagona,
  časi lahkega spanja, nastavitev pinov, obremenitve samopreizkusa.
* Skripte na Windows: nalaganje z `arduino-cli`, samodejno iskanje vrat COM, `esptool`, branje izpisa.
* Skripta za snemanje z resničnim DP821A (oblika odgovorov, vrsta napak, hitrost poizvedb).
* Ali 60-sekundno računanje ne sproži nadzornika (nastavitve pravijo, da ne; kampanja ima prva dolga okna).
* Prosta kopica pri D = 20 in rezerva sklada: preberite ju iz `energija.csv` po preizkusu verige.
* Ločljivost in natančnost DP821A na kanalu 60 V / 1 A: iz podatkovnega lista za članek.
