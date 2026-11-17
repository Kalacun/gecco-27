# Lab guide, IDE version: Arduino IDE on the Mac, PyCharm on the PC with the RIGOL

Two equivalent guides exist (see `LAB_GUIDE.md`): `LAB_GUIDE_CLI.md` does everything with
terminal commands on one computer; this one splits the work the way the lab is set up:

| Machine | Used for | Programs |
|---|---|---|
| **Mac** | Everything that touches the ESP32 over USB: rescue of old data, flashing, checking what is flashed, reading the records | Arduino IDE 2, scripts `Mac_*.py` (plain Python, no packages) |
| **PC** | Everything that touches the RIGOL: recording, analysis | PyCharm with the packages from `requirements.txt`, scripts `PC_*.py` |

The ESP32 is connected by **one USB cable to the Mac** and, through the **switch, to the RIGOL**.
The two are never connected at the same time: USB only with the switch open.

**Status of this code.** Everything here is tested on a computer: the analysis, the Mac helpers
(on synthetic data and on a real image built by `arduino-cli`), the recording script against a
fake instrument, and a rehearsal of the PC steps on a synthetic session. **Nothing has yet run on
an ESP32, on a real RIGOL, or with Arduino IDE itself.** The self-test and chain test below are
therefore also the first execution of those paths. Expect to fix small things there; do not start
the campaign (step F) until C and D pass.

---

## How the work flows

```
 Mac                                                PC (RIGOL)
 ────────────────────────────────────────           ───────────────────────────────────
 Mac_2_pripravi.py   (VRSTA, RED)
 Arduino IDE: Upload
 Mac_3_preveri_nalaganje.py  → "V redu"
 unplug USB                         ──► close the switch ──►
                                                    PC_2_snemaj.py  (VRSTA, DATUM)
                                                    records; output off at the end
 open the switch ◄──
 plug USB
 Mac_4_preberi.py   (SEJA)  → prenos/<SEJA>/
                      copy the folder  ─────────────────►  PC_3_analiza.py (SEJA, PRENOS)
```

**Session name.** One session = one name `DATUM_VRSTA`, for example `2026-11-18_kampanja`
(`VRSTA` is `samopreizkus`, `veriga` or `kampanja`). It is derived in `PC_2_snemaj.py` from `DATUM`
and `VRSTA` and typed as `SEJA` in `Mac_4_preberi.py` and `PC_3_analiza.py`.

**What has to be the same on both machines.** The folder `ea_energija` (source code: `ea_energija.ino`,
`ea_jedro.h`, `ea_premiki.h`, and `ea_T.h` once it exists). `PC_2_snemaj.py` and the analysis compare a
hash of these files with the one in the build id; a difference stops the recording or the analysis.
`analiza_nastavitve.json` is used on the PC only.

**What crosses over.** The folder `prenos/<SEJA>` from the Mac to the PC (USB stick, network
folder, cloud: the files are small), and `ea_T.h` from the Mac to the PC after step E.

**Scripts.** Wherever a step runs a script, the step shows the command in a box you can copy. Mac commands go
into Terminal, PC commands into the *Terminal* tab of PyCharm, both in the folder `ea_energija` (Mac: `python3`,
PC: `python`). The examples use the date `2026-11-18`; replace it with the date of your session. `Mac_2_pripravi.py`
prints the commands of the following steps with your date and source hash already filled in. Instead of a command
you can also edit the capital-letter settings at the top of the script and press Run in PyCharm (the options
of the command and the variables in the file are the same); the parameters can also be put into the run
configuration (*Run → Edit Configurations → Parameters*).

| Script | Machine | Step | What it does |
|---|---|---|---|
| `PC_0_testi.py` | PC | 0 | Runs all tests that need no hardware |
| `PC_1_preveri_rigol.py` | PC | B | Finds the RIGOL, prints identity and one reading (changes nothing) |
| `Mac_1_kopija_flash.py` | Mac | A | Copies the whole flash, extracts old records |
| `Mac_2_pripravi.py` | Mac | C, D, F | Creates the build id and settings file; prints the Tools settings |
| Arduino IDE | Mac | C, D, F | Upload |
| `Mac_3_preveri_nalaganje.py` | Mac | C, D, F | Reads the program back from the chip and checks it |
| `PC_2_snemaj.py` | PC | C, D, F | Records a session with the RIGOL |
| `Mac_4_preberi.py` | Mac | C, D, F | Reads the records into `prenos/<SEJA>`, prints a summary, host comparison |
| `PC_3_analiza.py` | PC | C, D, F | Copies the transfer folder into the session, analyses |
| `Mac_5_nastavi_T.py` | Mac | E | Writes `ea_T.h` from the chain test |
| `Mac_6_pobrisi_zapise.py` | Mac | repeat | Erases the records after explicit confirmation |

---

## 0. Prepare the machines (once)

### 0.1 The code

Copy the whole `gecco2027-electricity` folder **including the hidden `.git` folder** to both machines (the Mac
needs git for the build id; the PC does not). On the Mac check the branch (it must print `audit/phase2`):

```bash
cd gecco2027-electricity/ea_energija
git branch --show-current
```

**Commit on the Mac before you prepare a build.** `Mac_2_pripravi.py` warns with `+spremembe` if `ea_energija.ino`,
`ea_jedro.h`, `ea_premiki.h` or `ea_T.h` differ from the last commit, and the analysis refuses data from such a build.

### 0.2 Mac

1. **Arduino IDE 2** with **"esp32 by Espressif Systems" version 3.3.12** (Boards Manager). The audit checked
   watchdog, timer and power settings for that version only.
2. Python 3 (the system one is enough). Nothing to install: `esptool` comes with the esp32 core.
3. Optional: a C++ compiler (`c++`, from Xcode command line tools) for the host comparison.
4. Run the tests that need no hardware (Terminal, in `ea_energija`); they must end with `OK`:

   ```bash
   python3 -m unittest discover -s . -p "test_*.py"
   ```

### 0.3 PC (PyCharm)

1. Open the folder `ea_energija` as a project (File → Open).
2. Set an interpreter (Settings → Project → Python Interpreter) and install the packages (PyCharm offers it when
   you open `requirements.txt`, or in the *Terminal* tab):

   ```bash
   python -m pip install -r requirements.txt
   ```

3. On Windows install NI-VISA or RIGOL UltraSigma so that the supply appears as a VISA device.
4. Run all tests that need no hardware (they must end with `VSI TESTI V REDU`):

   ```bash
   python PC_0_testi.py
   ```

5. Check the RIGOL. Expected: one device `USB0::0x1AB1::...::INSTR`, identity `RIGOL TECHNOLOGIES,DP821A,...` and
   one reading `V, A, W`. It changes no setting.

   ```bash
   python PC_1_preveri_rigol.py
   ```

Running a script in PyCharm instead of in the Terminal: right-click in the editor → *Run 'name'*; output is in the
Run panel; the red square stops it. After stopping a recording by hand, check that the RIGOL output is off.

---

## A. Rescue the data of previous runs — do this first, on the Mac

**Why first, and why this way.** Two things destroy the old records:

* flashing a build with a different build id erases them (the first Upload does it), and
* the firmware that is on the board now: if its last session was interrupted, it deletes all records about 10
  seconds after power-up, so merely plugging in USB can erase them.

A raw copy of the flash avoids both, because with BOOT held the old program never starts.

1. **Archive** every existing measurement folder (`meritve_*` with `rigol.csv`, `meta.json`, `esp32.txt`, ...) from
   the PC to an archive location. Do not touch the originals.
2. **Switch open**, then on the board: **hold BOOT, plug the USB cable into the Mac, keep holding BOOT two more
   seconds, release.** The old program is not running.
3. **Mac, copy the flash** (about six minutes). It reads the whole 4 MB flash **without resetting the chip, before
   or after**, at 115200 baud (the most reliable speed), checks the size, stores `arhiv/<ime>/kopija_flash.bin` and
   its SHA-256, and extracts the old records into `arhiv/<ime>/zapisi/stari_zapisi.csv`:

   ```bash
   python3 Mac_1_kopija_flash.py --ime flash_2026-11-18
   ```

4. Copy `arhiv/flash_2026-11-18` to the archive. Unplug USB.

If the read fails, the script explains the error in Slovenian. For `No more data to read from the serial port` or
`Failed to connect`: unplug USB, hold BOOT again, plug in (directly into the Mac, no hub, a data cable), release
BOOT after two seconds and run the same command again; the same name is accepted until a copy is complete. Close
the Serial Monitor of Arduino IDE first. If it keeps failing on a board with a CH340 chip, install the WCH driver.

What the extraction may say:

* `Datoteke rez.bin ni`: the board holds no records (never run, already cleared, or already deleted by the old
  program).
* A warning that the size is not a multiple of 112 bytes: the board ran firmware older than the audited one. Keep
  the image and tell me; the layout has to be worked out.
* This path was tested with a synthetic image only. If the extraction fails on the real image, keep the `.bin` file:
  the data are in it.

**About these old data.** They come from the firmware the audit found defective (unshifted functions, so L-SHADE
lands on exactly 0; one target at 1e-6, below single-precision accuracy; time budget only; a short random
generator). Keep them as an archive. They are **not** results for the paper, and the new analysis refuses their
format on purpose. The old analysis script is in git (`git show 4d7c5cc:ea_energija/zajem.py`) if you want the old
numbers for the record; it has the defects listed in the audit.

---

## B. Wiring and supply

Hardware is unchanged; `SETUP_GUIDE.md` section 1 describes the rig. The rules that matter:

* RIGOL **CH1** (the 60 V / 1 A channel of the DP821A) to the board's **3V3** and **GND** pins, through a switch in
  the + lead. Never 5V/VIN.
* **USB unplugged during every measurement.** USB only with the switch open.
* Nothing else connected to the board. Same board, wires and channel for all sessions.

You do not set the supply by hand. `PC_2_snemaj.py` sets 3.30 V, a 0.5 A limit, OVP 3.6 V and OCP 0.6 A, reads every
setting back, compares, and starts only if they match.

---

## C. Self-test session (about 5 minutes of recording)

Purpose: check the supply read-out and the energy calculation against loads whose result is known, and measure how
long a clock read and an evaluation take on the chip.

**1. Mac, prepare.** It prints the Tools settings to check, the **ZGOSTITEV IZVORA** (12 characters) and the exact
commands for the next steps:

```bash
python3 Mac_2_pripravi.py --vrsta samopreizkus --datum 2026-11-18
```

**2. Mac, Arduino IDE, upload.** Open `ea_energija/ea_energija.ino`. Set *Tools* exactly as the script printed:

| Setting | Value |
|---|---|
| Board | ESP32 Dev Module |
| CPU Frequency | 240MHz (WiFi/BT) |
| Flash Mode / Frequency / Size | QIO / 80MHz / 4MB (32Mb) |
| Partition Scheme | Default 4MB with spiffs (1.2MB APP/1.5MB SPIFFS) |
| PSRAM | Disabled |
| Core Debug Level | None |
| Arduino Runs On / Events Run On | Core 1 / Core 1 |
| Erase All Flash Before Sketch Upload | Disabled |

Select the port, click **Upload**. The compiler itself refuses a wrong CPU frequency, debug level or PSRAM setting
with an `#error`; the other settings are checked from the FQBN the program records. Wait for "Done uploading". **Do
not open the Serial Monitor and do not press EN afterwards:** after a new build the first boot only prepares the
board, the next boot starts a session, and that must happen on the RIGOL's power.

**3. Mac, verify.** Close any Serial Monitor. **Unplug USB, hold BOOT, plug USB in, keep BOOT two more seconds,
release** (the script never resets the chip, so it must already be in its boot loader). It reads the program back
from the chip (about 45 s; the chip stays in its boot loader afterwards) and must end with `V redu`: exactly the
expected build id, and the required board settings. **Then unplug USB.**

```bash
python3 Mac_3_preveri_nalaganje.py
```

**4. PC, record.** Close the switch, then run the command printed in step 1 (replace `0123456789ab` with your
12 characters). The script refuses to start if the code on the PC differs from the Mac's. It prints the settings it
read back from the supply, switches the output on (the board starts), records, stops by itself about a minute after
the board went to deep sleep, and switches the output off. At the end it prints the achieved sampling rate and
jitter.

```bash
python PC_2_snemaj.py --vrsta samopreizkus --datum 2026-11-18 --src 0123456789ab
```

**5. Mac, read out.** Open the switch. Plug USB into the Mac. It saves `prenos/<seja>/esp32.txt` and prints that this
is a self-test dump and the board-settings check:

```bash
python3 Mac_4_preberi.py --seja 2026-11-18_samopreizkus
```

**6. PC, analyse.** Copy the folder `prenos/2026-11-18_samopreizkus` from the Mac to the PC (USB stick or network
folder), then give its path in `--prenos`. The report is in `meritve/<seja>/samopreizkus_<date>/porocilo.txt`:

```bash
python PC_3_analiza.py --seja 2026-11-18_samopreizkus --prenos "E:/prenos/2026-11-18_samopreizkus"
```

**What to check in the report:**

* *Steady loads*: four different power levels; `E1 proti E2` within a fraction of a percent; the edge offsets
  (`rob sled - ESP32`) small and not growing from the first to the fourth load. A growing offset means the ESP32
  timer and the PC clock drift apart.
* *Duty cycles*: measured mean power close to the expected one. A small positive difference is normal (waking from
  light sleep costs energy the simple expectation ignores). Lines marked `OZNAČENO` exceed the tolerance (5 %) and
  need a look.
* *Čas operacij*: the share of one evaluation that the TIME-mode clock read costs with the clock read every 16
  evaluations. It should be well below 1 %. If not, tell me before the campaign; `PERIODA_URE_FE` would have to be
  raised (for all algorithms).
* In `meta_konec.json` (session folder): `napak_branja` 0, `vzorcev_nacina_ne_CV` 0, `OVP_sprozen` and
  `OCP_sprozen` `NO`, and the sampling period (`perioda`).
* In `okna.csv` of a chain-test analysis: the durations of the rows `kratek_interval`. You need the longest one in
  step E.

If `PC_2_snemaj.py` stops with `NAPAKA RIGOL`, the message names the command or setting that did not match. The SCPI
commands were checked against the DP800 Programming Guide of March 2013; a DP821A with newer firmware may answer a
read-back query differently. Send me the message.

---

## D. Chain test (about 20 to 40 minutes of recording)

Purpose: the complete protocol on all four cells with the campaign's FE budget, two blocks each, plus one short TIME
row. It verifies the firmware end to end and yields the durations from which T is set. The steps are those of C with
`veriga` instead of `samopreizkus`. The recording is 45 runs (5 rows × 3 algorithms × (2 blocks + 1 warm-up)), each
10 s rest plus the run. In step 6 `PC_3_analiza.py` first prints the summary of the records (state of the session,
durations per cell and algorithm, targets reached) and then runs the full analysis into
`meritve/<seja>/analiza_<date>_<time>/`; in step 5 `Mac_4_preberi.py` also prints the board-settings check and, if
`c++` exists, the comparison with the host build of the same code.

1. Mac, prepare (random block order; add `--red 1` for the balanced one):

   ```bash
   python3 Mac_2_pripravi.py --vrsta veriga --datum 2026-11-18
   ```

2. Mac, Arduino IDE: check *Tools*, **Upload**. No Serial Monitor, no EN.
3. Mac, unplug USB, hold BOOT while plugging it in again, verify, then unplug USB:

   ```bash
   python3 Mac_3_preveri_nalaganje.py
   ```

4. PC, close the switch, record (your 12 characters in `--src`):

   ```bash
   python PC_2_snemaj.py --vrsta veriga --datum 2026-11-18 --src 0123456789ab
   ```

5. Mac, open the switch, plug USB, read out:

   ```bash
   python3 Mac_4_preberi.py --seja 2026-11-18_veriga
   ```

6. Copy `prenos/2026-11-18_veriga` to the PC, then PC, analyse:

   ```bash
   python PC_3_analiza.py --seja 2026-11-18_veriga --prenos "E:/prenos/2026-11-18_veriga"
   ```

**Acceptance.** All of these must hold before the campaign:

1. The summary shows `stanje = koncan, zapisov 45 od načrtovanih 45, resetov = 1` and no corrupt records, and every
   FE row has `FE` equal to its budget (100000 at D = 10, 200000 at D = 20).
2. The analysis finishes without `NAPAKA ANALIZE`: 45 windows, 45 records.
3. `E1 proti E2`: no flagged run, or the flagged ones are understood.
4. `izlocitve.csv` lists exactly the 15 warm-up runs and nothing else.
5. In `energija.csv`: `cpu_mhz` 240 everywhere; `prosta_kopica_B` does not shrink from run to run; `sklad_min` stays
   well above zero (the smallest free stack; the task has 8192 bytes); `pocitek_esp_s` close to 10.
6. Host comparison (printed by `Mac_4_preberi.py`): seed equal 36/36 and evaluation count equal 36/36. Checkpoints
   agree at the start; later divergence is expected (different math libraries) and is not a failure. Medians of the
   final values on both sides should be of the same order.
7. `meta_konec.json` as in step C.

**If the analysis stops**, the message says why. The likely first-time cases:

| Message | Meaning and action |
|---|---|
| `V sledi moči je N merilnih oken, zapisov REZ pa je M` | Windows and records differ. Open `okna.csv` in the new `analiza_...` folder. If a boot or flash-write interval was counted as a window, or a short FE run was not, adjust `okna.min_trajanje_okna_s` (step E) and analyse again. |
| `znotraj robov (...) je samo N vzorcev` | A window is too short for the E2 margin at this sampling rate. See step E. |
| `premor pred oknom X s, pričakovan 11 s` | The pause between runs (1 s sleep, flash write, 10 s rest) deviates by more than `okna.toleranca_premora_s`. If X is stable, raise the tolerance (step E); if it jumps, look at the trace. |
| `vrzel_v_oknu` | The PC lost samples for more than 1 s inside a window (see `rigol_dogodki.csv`). Repeat the session. |
| `ni_CV_v_oknu` | The supply left constant-voltage mode or the voltage moved by more than 0.05 V. Check wiring and the limit. |
| `Program ni sledljiv ali ni preveden z zahtevanimi nastavitvami` | The id says `rocno` (uploaded without `Mac_2_pripravi.py`) or `+spremembe` (uncommitted source), the source copies in the session folder have another hash than the id (the PC's `ea_energija` differs from the Mac's), or the board settings are wrong. Commit, prepare, upload, repeat the session. |
| `seja se ni končala redno: stanje = prekinjen` | The ESP32 reset during the session; the message gives the reason (for example brown-out). Records up to that point are kept but the session is not complete. |

Every analysis writes into a new sub-folder, so repeating it with other settings loses nothing. To analyse a session
again, run the PC command again without `--prenos`. The raw files are never modified.

---

## E. Fix the remaining settings, then freeze them

Do this **after** steps C and D and **before** the campaign. Nothing may be changed once campaign data exist.

1. **T for the four cells (Mac).** T is the median duration of the FE runs of that cell in the chain test, rounded to
   a whole second, so both budget modes cost similar energy. First look at the proposal:

   ```bash
   python3 Mac_5_nastavi_T.py --seja 2026-11-18_veriga
   ```

   If the values are acceptable, write `ea_T.h`:

   ```bash
   python3 Mac_5_nastavi_T.py --seja 2026-11-18_veriga --zapisi
   ```

   The script refuses an unfinished chain test, corrupt records and a missing cell, and does not overwrite an
   existing `ea_T.h` unless you add `--prepisi`. The campaign cannot be built without `ea_T.h`.

2. **Thresholds of the analysis (PC)**, file `analiza_nastavitve.json`. The values are my defaults and need your
   decision. Use the self-test and chain-test outputs:

   | Setting | Default | How to decide |
   |---|---|---|
   | `okna.min_trajanje_okna_s` | 1.5 | Between the longest `kratek_interval` and the shortest real window in `okna.csv`. |
   | `okna.toleranca_trajanja_s` | 0.5 | Largest allowed difference between a window's length in the trace and on the chip. |
   | `okna.toleranca_premora_s` | 1.5 | From the pauses seen in the chain test. |
   | `energija.rob_E2_s` | 0.5 | At least two sampling periods (see `perioda` in `meta_konec.json`). |
   | `energija.min_vzorcev_E2` | 5 | Fewer interior samples than this stop the analysis. |
   | `energija.toleranca_E1_E2_rel` | 0.02 | Runs beyond it are flagged, not excluded. |
   | `veljavnost.max_vrzel_s` | 1.0 | Longest allowed gap between samples inside a window. |
   | `veljavnost.U_toleranca_V` | 0.05 | Allowed deviation from 3.30 V. |
   | `samopreizkus.toleranca_rel` | 0.05 | Flag limit in the self-test. |

   **Short FE windows.** With FE_max = 10000 × D the D = 10 runs may last only a few seconds. At 5 to 10 samples per
   second that leaves few samples per window. If the chain test shows windows shorter than about 3 s, the energy of
   those runs rests on very few samples; consider a larger FE budget (`FE_D10`, `FE_D20` near the top of
   `ea_energija.ino`) before the campaign rather than smaller margins. This is your decision; the chain-test numbers
   tell you which case you are in. If you change the budget, repeat the chain test.

3. **Block order.** Default is the random order with 25 blocks; the balanced order with 30 blocks is `--red 1` in
   `Mac_2_pripravi.py`. Decide now; the choice is printed in every dump header.

4. **Commit on the Mac**, so that the build id points at exactly this state (run from the repository root, the folder
   `gecco2027-electricity`):

   ```bash
   git add ea_energija/ea_T.h ea_energija/ea_energija.ino ea_energija/analiza_nastavitve.json
   git commit -m "Campaign settings: T per cell and analysis thresholds, fixed before the campaign"
   ```

5. **Copy to the PC** the new `ea_T.h` (and `ea_energija.ino` if you changed it) and, if you edited the thresholds on
   the Mac, `analiza_nastavitve.json`. `PC_2_snemaj.py` will refuse to start if the code differs.

---

## F. Campaign

Plan: Rastrigin and Rosenbrock, D = 10 and 20, FE and TIME budget = 8 rows; 3 algorithms; 25 blocks plus 1 warm-up →
624 runs. Duration ≈ 624 × 11.3 s (rest and writing, about 2 hours) plus the sum of all windows; with the T values
from step E you can compute it exactly. Flash space is checked by the firmware before it starts (624 records × 488
bytes). The steps are those of C with `kampanja`.

* The id printed by `Mac_2_pripravi.py` must **not** contain `+spremembe`; the script refuses without `ea_T.h`.
* The PC must be on mains power with updates paused; do not touch the supply or the board while recording. If you must
  stop `PC_2_snemaj.py`, press the red square once and check that the RIGOL output is off. The recording has a safety
  cap of 24 h.
* Reading out takes one to two minutes of dump; if `Mac_4_preberi.py` times out, add `--cas 1800`.
* Expected summary: `stanje = koncan, zapisov 624 od načrtovanih 624, resetov = 1`.

1. Mac, prepare (`--red 1` for the balanced order, as decided in E):

   ```bash
   python3 Mac_2_pripravi.py --vrsta kampanja --datum 2026-11-18
   ```

2. Mac, Arduino IDE: check *Tools*, **Upload**. No Serial Monitor, no EN.
3. Mac, unplug USB, hold BOOT while plugging it in again, verify, then unplug USB:

   ```bash
   python3 Mac_3_preveri_nalaganje.py
   ```

4. PC, close the switch, record (your 12 characters in `--src`):

   ```bash
   python PC_2_snemaj.py --vrsta kampanja --datum 2026-11-18 --src 0123456789ab
   ```

5. Mac, open the switch, plug USB, read out:

   ```bash
   python3 Mac_4_preberi.py --seja 2026-11-18_kampanja
   ```

6. Copy `prenos/2026-11-18_kampanja` to the PC, then PC, analyse:

   ```bash
   python PC_3_analiza.py --seja 2026-11-18_kampanja --prenos "E:/prenos/2026-11-18_kampanja"
   ```

**Do not flash or erase the records until the read-out is saved, copied to the PC and checked.** The records stay on
the board until a build with another id is flashed or the erase is confirmed.

**If the session was interrupted** (`stanje = prekinjen`): the records written so far are kept and can be read out as
above. The analysis refuses an incomplete session by default. Do not patch a second session onto it; find the cause
(the reset reason is in the summary and in the error message), then repeat the whole session into a new folder.

**To run another session with the same firmware** (same build id; the same source, plan and order give the same id,
so flashing does not wipe the board): read out, transfer and check the records, then on the Mac with USB in and the
switch open erase them. The script waits for the end of the dump, sends `n` twice as the firmware requires and
reports the confirmation. The erase cannot be undone. The next session starts at the next power-up.

```bash
python3 Mac_6_pobrisi_zapise.py --potrjujem
```

---

## G. Files of one session

Raw, written once, never modified (in `meritve/<SEJA>` on the PC):

| File | Content |
|---|---|
| `meta.json` | Start time, instrument identity, requested and **read-back** settings, stop rules, hash of `zajem.py` |
| `rigol.csv` | `t_pred_s, t_po_s` (PC monotonic clock before and after the query), `U_V, I_A, P_W` exactly as the instrument returned them |
| `rigol_nacin.csv` | CV/CC/UR every 10 s |
| `rigol_dogodki.csv` | Query errors, unparseable replies and gaps with duration |
| `meta_konec.json` | End reason, counts, sampling period and jitter, final instrument state |
| `ea_energija.ino`, `ea_jedro.h`, `ea_premiki.h`, `ea_T.h`, `ea_prevod.h` | Copy of the firmware source; the analysis recomputes its hash and compares it with the build id |
| `esp32.txt` | The board's records (`REZ`, `CILJ`, `TOCKA` lines), copied from `prenos/<SEJA>` |
| `prevod_info.json` | Build id, git revision, hashes, requested board settings (copied from the Mac) |

Per analysis, in a new folder `analiza_<date>_<time>/`:

| File | Content |
|---|---|
| `porocilo.txt` | The printed report |
| `analiza_nastavitve.json` | Copy of the thresholds used |
| `okna.csv` | Every detected interval (windows and short intervals) |
| `energija.csv` | One row per run: **E2_J** (primary, gross), E1_J, their difference and flag, net energy, baseline power, FE, µJ per FE, best, seed, CPU MHz, heap, stack |
| `cilji.csv` | One row per run and target: reached, FE, seconds and E2 energy to the first hit |
| `ert.csv` | Expected running time per cell, algorithm and target in FE, J and s; flag for the Rastrigin 1e-4 target |
| `povzetek.csv`, `testi.csv` | Descriptive statistics; Mann–Whitney U, Holm, A12 |
| `kontrola.csv` | Position counts and position effect, baseline drift, outliers |
| `izlocitve.csv` | Every excluded run with its reason |
| `konvergenca_energija.csv` | Checkpoints: FE, time, best, energy to that point |

The data folders `meritve/`, `prenos/` and `arhiv/` are ignored by git: back them up separately.

Statistics, as implemented: Mann–Whitney U two-sided with normal approximation, mid-ranks for ties, tie-corrected
variance and continuity correction; Holm over the algorithm pairs within one metric and one cell; A12 = P(first >
second) + 0.5 P(equal), so below 0.5 means the first algorithm has smaller values; ERT = total cost of all runs divided
by the number of successful runs, an unsuccessful run counting with its whole budget.

---

## H. What is still unverified

* Every firmware path on real hardware: session states, record checksum, reset reasons, light sleep timing, the pin
  configuration, the self-test loads.
* `Mac_1`, `Mac_3`, `Mac_4` and `Mac_6` against a real ESP32 (they call `esptool` and the serial port), and
  `PC_2_snemaj.py` against a real DP821A (reply formats, error-queue text, query speed).
* That Arduino IDE 2 builds with exactly the settings the script prints and passes them in the FQBN in the same
  spelling (it uses `arduino-cli` and the same core files). The first IDE build in the lab shows it: the dump header
  contains `fqbn=...`, and `Mac_3` and the analysis check it.
* Whether a 60 s busy window trips no watchdog (the configuration says no; the old 10 s chain test agrees; the
  campaign windows are the first long ones).
* Free heap at D = 20 and stack headroom: read them from `energija.csv` after the chain test.
* The read-back resolution and accuracy of the DP821A on the 60 V / 1 A channel: take them from the datasheet for the
  paper. They affect absolute joules, not the comparison.
* The exact wording of the three algorithm papers (selection rule in Storn and Price 1997, bound handling in jDE):
  check against the PDFs before submission.
