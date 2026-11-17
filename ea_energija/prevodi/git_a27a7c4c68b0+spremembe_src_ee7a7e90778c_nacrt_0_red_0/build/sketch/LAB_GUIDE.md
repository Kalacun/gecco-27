#line 1 "/Users/aleks/gecco2027-electricity/ea_energija/LAB_GUIDE.md"
# Lab guide: running the experiments

This is the authoritative procedure after the 2026-11 audit. It replaces the workflow parts of
`GUIDE.md`, `SETUP_GUIDE.md`, `ea_energija/README.md` and the root `README.md` (those still
describe the hardware rig correctly, but their commands, settings and the WiFi path are out of date).

**Status of this code.** Everything here is tested on a computer (77 tests of the PC scripts
including the recovery tool, 31 tests of the algorithm core, firmware builds without warnings). **Nothing has yet run on an
ESP32 or against a real RIGOL.** Steps C and D below are therefore also the verification of the
firmware and of the acquisition script. Expect to fix small things there; do not start the
campaign (step F) until C and D pass.

All commands are run in the folder `ea_energija`. Replace `PORT` with the serial port of the
ESP32 (`COM5` on Windows, `/dev/cu.usbserial-0001` or `/dev/cu.SLAB_USBtoUART` on macOS,
`/dev/ttyUSB0` on Linux). On Windows write `python` instead of `python3`.

Order of work:

| Step | What | Time |
|---|---|---|
| 0 | Prepare the lab PC | 20 min, once |
| A | Rescue the data of previous runs (before anything is flashed) | 15 min |
| B | Wiring and supply check | 10 min |
| C | Self-test session (known loads) | 15 min |
| D | Chain test (all four cells, short) | 45 min |
| E | Fix the remaining settings (T, thresholds) and commit them | 15 min |
| F | Campaign | several hours, unattended |
| G | After the campaign | 30 min |

---

## 0. Prepare the lab PC (once)

1. **Get the code.** The work is on branch `audit/phase2` and has not been pushed. On the Mac:

   ```bash
   git push -u origin audit/phase2
   ```

   On the lab PC:

   ```bash
   git clone https://codeberg.org/firefly-cpp/gecco2027-electricity.git
   cd gecco2027-electricity
   git switch audit/phase2
   cd ea_energija
   ```

   (If you copy the folder instead, copy the hidden `.git` folder too; the build id needs it.)

2. **Python 3.9 or newer** and the packages:

   ```bash
   python3 -m pip install pyvisa pyvisa-py pyserial matplotlib
   ```

   On Windows also install NI-VISA or RIGOL UltraSigma so that the supply appears as a VISA device.

3. **Arduino IDE 2 with "esp32 by Espressif Systems" version 3.3.12.** The IDE contains
   `arduino-cli`, which `prevedi.py` finds by itself. Check:

   ```bash
   python3 prevedi.py --nacrt 2
   ```

   It must end with `Prevedeno: ... B, brez opozoril v izvornih datotekah.` If it cannot find
   `arduino-cli`, pass the path with `--cli`. If the installed core is not 3.3.12, install that
   version in the Boards Manager: the audit checked watchdog, timer and power settings for
   3.3.12 only.

4. **Run the tests.**

   ```bash
   python3 -m unittest test_zajem test_stari_zapisi
   ```

   Both must report `OK`. If the PC has a C++ compiler (`c++`), also run
   `python3 -m unittest gostitelj/test_gostitelj.py`; otherwise run that one on the Mac.

5. **Find the supply.**

   ```bash
   python3 zajem.py seznam
   python3 PC_1_preveri_rigol.py
   ```

   Expected: one device `USB0::0x1AB1::...::INSTR`, identity `RIGOL TECHNOLOGIES,DP821A,...`
   and one reading `V, A, W`. Neither command changes any setting.

---

## A. Rescue the data of previous runs — do this first

**Why first, and why this way.** Two things destroy the old records:

* flashing new firmware (a build with a different build id erases them), and
* the firmware that is on the board now: if its last session was interrupted, it deletes all
  records about 10 seconds after power-up — so merely plugging in USB can erase them.

A raw copy of the flash avoids both, because with BOOT held the old program never starts.

### A1. Archive what is on the lab PC

Copy every existing measurement folder (`meritve_*`, with `rigol.csv`, `meta.json`,
`esp32.txt`, ...) to an archive location and do not touch the originals. The new scripts never
write into an existing session folder, but keep a separate copy anyway.

### A2. Copy the whole flash of the ESP32

1. Open the switch in the RIGOL lead (or switch the output off). USB and RIGOL must never
   power the board together.
2. **Hold the BOOT button on the board, plug in the USB cable, keep BOOT pressed for two more
   seconds, release.** The chip is now in its boot loader and the old program is not running.
3. Read the flash (a read; nothing on the board changes):

   ```bash
   esptool --chip esp32 --port PORT --baud 460800 read-flash 0 0x400000 kopija_flash_2026-11-17.bin
   ```

   If `esptool` is not on the PATH, use the copy that comes with the Arduino core:

   * macOS: `~/Library/Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool`
   * Windows: `%LOCALAPPDATA%\Arduino15\packages\esp32\tools\esptool_py\5.3.1\esptool.exe`
   * or install it: `python3 -m pip install esptool`, then `python3 -m esptool ...`

   (esptool older than version 5 spells the command `read_flash`.) It takes about two minutes.
   The file must be exactly 4 194 304 bytes. Copy it to the archive as well.

### A3. Extract the old records from the copy

```bash
python3 stari_zapisi.py kopija_flash_2026-11-17.bin --izhod arhiv_esp32_2026-11-17
```

Result in the new folder: `stari_zapisi.csv` (one row per old run), the cut-out file-system
partition and the unpacked files. The script prints the build tags it finds and how many
records it converted.

* `Datoteke rez.bin ni` means the board holds no records (never run, already cleared, or
  already deleted by the old program).
* A warning that the size is not a multiple of 112 bytes means the board ran firmware older
  than the audited one; keep the image and tell me, the layout has to be worked out.
* This path was tested with a synthetic image only. If `mklittlefs` fails on the real image,
  keep the `.bin` file: the data are in it and can be extracted later.

### A4. Optional: the text dump of the old program

Only after A2. Unplug USB, plug it in again **without** BOOT, then:

```bash
python3 zajem.py preberi --port PORT --mapa arhiv_esp32_izpis_2026-11-17
```

This saves what the old program prints (`esp32.txt`) if its last session finished. If nothing
arrives within the timeout, the old session was not finished; you already have the data from A3.

### A5. About these old data

They were produced by the firmware the audit found defective (unshifted functions, so L-SHADE
lands on exactly 0; one target at 1e-6, below the accuracy of single precision; time budget
only; a short random generator). Keep them as an archive. They are **not** results for the
paper, and the new analysis refuses their format on purpose. If you want the old numbers for
the record, the old analysis script is in git:

```bash
git show 4d7c5cc:ea_energija/zajem.py > ../zajem_stari_4d7c5cc.py
python3 ../zajem_stari_4d7c5cc.py analiza <old folder>/rigol.csv <old folder>/esp32.txt --grafi
```

That script has the defects listed in the audit (it re-pairs windows and records silently and
averages time-to-target over successful runs only).

---

## B. Wiring and supply

Hardware is unchanged; `SETUP_GUIDE.md` section 1 describes the rig. The rules that matter:

* RIGOL **CH1** (the 60 V / 1 A channel of the DP821A) to the board's **3V3** and **GND** pins,
  through a switch in the + lead. Never 5V/VIN.
* **USB unplugged during every measurement.** USB is plugged in only with the switch open
  (flashing, reading out).
* Nothing else connected to the board. Same board, same wires, same channel for all sessions.

You do not set the supply by hand. The acquisition script sets 3.30 V, a 0.5 A current limit,
OVP 3.6 V and OCP 0.6 A, reads every setting back, compares, and starts only if they match.
It refuses a limit below 0.5 A.

---

## C. Self-test session (about 5 minutes of recording)

Purpose: check the supply read-out and the energy calculation against loads whose result is
known, and measure how long a clock read and an evaluation take on the chip.

1. **Build and flash** (switch open, USB in):

   ```bash
   python3 prevedi.py --nacrt 2 --nalozi --port PORT
   ```

   Then look at the serial output:

   ```bash
   arduino-cli monitor -p PORT -c baudrate=115200
   ```

   (or the Serial Monitor of the IDE at 115200). Press the EN button once if nothing is shown.
   Expected line: `#PRIPRAVLJEN prevod=git:... src:... nacrt:2 red:0`. Close the monitor.

2. **Unplug USB.** Close the switch.

3. **Record.** The folder must not exist yet.

   ```bash
   python3 zajem.py poskus --mapa meritve/2026-11-17_samopreizkus
   ```

   The script prints the settings it read back from the supply, switches the output on (the
   board starts), records, and stops by itself about a minute after the board went to deep
   sleep. Total about 5 minutes. At the end it prints the achieved sampling rate and jitter.

4. **Read out.** Open the switch, plug in USB:

   ```bash
   python3 zajem.py preberi --port PORT --mapa meritve/2026-11-17_samopreizkus
   ```

5. **Analyse.**

   ```bash
   python3 zajem.py samopreizkus meritve/2026-11-17_samopreizkus/rigol.csv meritve/2026-11-17_samopreizkus/esp32.txt
   ```

**What to check in the report** (`samopreizkus_<date>/porocilo.txt`):

* *Steady loads*: four different power levels; `E1 proti E2` within a fraction of a percent;
  the edge offsets (`rob sled - ESP32`) small and not growing from the first to the fourth
  load. A growing offset means the ESP32 timer and the PC clock drift apart.
* *Duty cycles*: measured mean power close to the expected one. A small positive difference is
  normal (waking from light sleep costs energy that the simple expectation ignores). Lines
  marked `OZNAČENO` exceed the tolerance (5 %) and need a look.
* *Čas operacij*: the last column says what share of one evaluation the TIME-mode clock read
  costs with the clock read every 16 evaluations. It should be well below 1 %. If it is not,
  tell me before the campaign; `PERIODA_URE_FE` would have to be raised (for all algorithms).
* In `meta_konec.json`: `napak_branja` 0, `vzorcev_nacina_ne_CV` 0, `OVP_sprozen` and
  `OCP_sprozen` `NO`, and the sampling period (`perioda`).
* In `okna.csv`: the durations of the rows `kratek_interval` (boot, flash writes). You need
  the longest one in step E.

If the acquisition stops with `NAPAKA RIGOL`, the message names the command or the setting
that did not match. The SCPI commands were checked against the DP800 Programming Guide of
March 2013; a DP821A with newer firmware may answer one of the read-back queries differently.
Send me the message.

---

## D. Chain test (about 25 to 40 minutes of recording)

Purpose: the complete protocol on all four cells with the campaign's FE budget, two blocks
each, plus one short TIME row. It verifies the firmware end to end and yields the durations
from which T is set.

1. **Build and flash** (switch open, USB in):

   ```bash
   python3 prevedi.py --nacrt 0 --nalozi --port PORT
   arduino-cli monitor -p PORT -c baudrate=115200
   ```

   Expected: `#PRIPRAVLJEN prevod=... nacrt:0 red:0`. Close the monitor, unplug USB, close the
   switch.

2. **Record.**

   ```bash
   python3 zajem.py poskus --mapa meritve/2026-11-17_veriga
   ```

   45 runs (5 rows × 3 algorithms × (2 blocks + 1 warm-up)), each 10 s rest plus the run.

3. **Read out** (switch open, USB in):

   ```bash
   python3 zajem.py preberi --port PORT --mapa meritve/2026-11-17_veriga
   ```

4. **Look at the records** (works without the power trace):

   ```bash
   python3 zajem.py zapisi meritve/2026-11-17_veriga/esp32.txt
   ```

   Expected: `stanje = koncan, zapisov 45 od načrtovanih 45, resetov = 1`, no corrupt records,
   every FE row with `FE` equal to its budget (100000 at D = 10, 200000 at D = 20). At the end
   it prints four ready-made lines `#define T_..._US ...` — keep them for step E.

5. **Analyse.**

   ```bash
   python3 zajem.py analiza meritve/2026-11-17_veriga/rigol.csv meritve/2026-11-17_veriga/esp32.txt --grafi --podrobno
   ```

6. **Compare the device with the host build** (needs a C++ compiler; run it on the Mac with the
   `esp32.txt` if the lab PC has none):

   ```bash
   python3 gostitelj/primerjaj_z_napravo.py meritve/2026-11-17_veriga/esp32.txt
   ```

**Acceptance.** All of these must hold before the campaign:

1. The analysis finishes without `NAPAKA ANALIZE`. 45 windows, 45 records.
2. `E1 proti E2`: no flagged run, or the flagged ones are understood.
3. `izlocitve.csv` lists exactly the 15 warm-up runs and nothing else.
4. In `energija.csv`: `cpu_mhz` 240 everywhere; `prosta_kopica_B` does not shrink from run to
   run; `sklad_min` stays well above zero (it is the smallest free stack; the task has 8192
   bytes); `pocitek_esp_s` close to 10.
5. Host comparison: seed equal 36/36 and evaluation count equal 36/36. Checkpoints agree at
   the start; later divergence is expected (different math libraries) and is not a failure.
   Medians of the final values on both sides should be of the same order.
6. `meta_konec.json` as in step C.

**If the analysis stops**, the message says why. The likely first-time cases:

| Message | Meaning and action |
|---|---|
| `V sledi moči je N merilnih oken, zapisov REZ pa je M` | Windows and records differ. Open `okna.csv` in the new `analiza_...` folder. If a boot or flash-write interval was counted as a window, or a short FE run was not, adjust `okna.min_trajanje_okna_s` (step E) and analyse again. |
| `znotraj robov (...) je samo N vzorcev` | A window is too short for the E2 margin at this sampling rate. See step E. |
| `premor pred oknom X s, pričakovan 11 s` | The pause between runs (1 s sleep, flash write, 10 s rest) deviates by more than `okna.toleranca_premora_s`. If X is stable (flash write simply takes longer), raise the tolerance in step E; if it jumps, look at the trace. |
| `vrzel_v_oknu` | The PC lost samples for more than 1 s inside a window (see `rigol_dogodki.csv`). Repeat the session. |
| `ni_CV_v_oknu` | The supply left constant-voltage mode or the voltage moved by more than 0.05 V. Check wiring and the limit. |
| `seja se ni končala redno: stanje = prekinjen` | The ESP32 reset during the session; the message gives the reason (for example brown-out). The records up to that point are kept but the session is not complete. |

Every analysis writes into a new sub-folder, so repeating it with other settings loses nothing.
The raw files are never modified.

---

## E. Fix the remaining settings, then freeze them

Do this **after** steps C and D and **before** the campaign. Nothing may be changed once
campaign data exist.

1. **T for the four cells.** Paste the four lines printed by `zajem.py zapisi` in step D4 over
   the four `#define T_..._US 0ULL` lines in `ea_energija.ino` (search for `T_RASTRIGIN_D10_US`).
   T is the median duration of the FE runs of that cell, so both budget modes cost similar energy.

2. **Thresholds of the analysis**, file `analiza_nastavitve.json`. The values in it are my
   defaults and need your decision. Use the self-test and chain-test outputs:

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

   **Short FE windows.** With FE_max = 10000 × D the D = 10 runs may last only a few seconds.
   At 5 to 10 samples per second that leaves few samples per window. If the chain test shows
   windows shorter than about 3 s, the energy of those runs rests on very few samples; consider
   a larger FE budget before the campaign rather than smaller margins. This is your decision;
   the chain-test numbers tell you which case you are in.

3. **Block order.** Default is the random order with 25 blocks (`--red 0`). The balanced order
   with 30 blocks is `--red 1`. Decide now; the choice is printed in every dump header.

4. **Commit** the changed files, so that the build id points at exactly this state:

   ```bash
   git add ea_energija.ino analiza_nastavitve.json
   git commit -m "Campaign settings: T per cell and analysis thresholds, fixed before the campaign"
   ```

---

## F. Campaign

Plan: Rastrigin and Rosenbrock, D = 10 and 20, FE and TIME budget = 8 rows; 3 algorithms;
25 blocks plus 1 warm-up → 624 runs. Duration ≈ 624 × 11.3 s (rest and writing, about 2 hours)
plus the sum of all windows; with the T values from step E you can compute it exactly.
Flash space is checked by the firmware before it starts (624 records × 488 bytes).

1. **Build and flash** (switch open, USB in):

   ```bash
   python3 prevedi.py --nacrt 1 --red 0 --nalozi --port PORT
   arduino-cli monitor -p PORT -c baudrate=115200
   ```

   The build output must **not** say `+spremembe` in the build id (that means uncommitted
   changes; commit first). Expected on the board: `#PRIPRAVLJEN prevod=git:... nacrt:1 red:0`.
   Close the monitor, unplug USB, close the switch.

2. **Record.** New folder; PC on mains power, updates paused.

   ```bash
   python3 zajem.py poskus --mapa meritve/kampanja_2026-11-18 --najdlje-s 86400
   ```

   `--najdlje-s` is a safety cap (here 24 h). The script keeps the PC awake, stops about a
   minute after the board went to deep sleep and switches the output off. Do not touch the
   supply or the board while it runs. If you must stop it, use Ctrl+C once and check that the
   output is off.

3. **Read out** (switch open, USB in). The dump of a full campaign takes one to two minutes:

   ```bash
   python3 zajem.py preberi --port PORT --mapa meritve/kampanja_2026-11-18
   python3 zajem.py zapisi meritve/kampanja_2026-11-18/esp32.txt
   ```

   Expected: `stanje = koncan, zapisov 624 od načrtovanih 624, resetov = 1`.

4. **Copy the build record** into the session folder (the folder name is printed by
   `prevedi.py`):

   ```bash
   cp prevodi/<build id>/prevod_info.json meritve/kampanja_2026-11-18/
   ```

5. **Analyse.**

   ```bash
   python3 zajem.py analiza meritve/kampanja_2026-11-18/rigol.csv meritve/kampanja_2026-11-18/esp32.txt --grafi
   python3 gostitelj/primerjaj_z_napravo.py meritve/kampanja_2026-11-18/esp32.txt
   ```

**Do not flash or send `n` to the board until the read-out is saved and checked.** The records
stay on the board until a build with another id is flashed or `n` is sent twice.

**If the session was interrupted** (`stanje = prekinjen`): the records written so far are kept
and can be read out as above. The analysis refuses an incomplete session by default. Do not
patch a second session onto it; find the cause (the reset reason is in the header and in the
error message), then repeat the whole session into a new folder.

**To run another session with the same firmware** (same build id): read out first, then open
the monitor, type `n` and Enter, and again `n` and Enter. The board answers that the records
are erased and waits for the next power-up.

---

## G. Files of one session

Raw, written once, never modified:

| File | Content |
|---|---|
| `meta.json` | Start time, instrument identity, requested and **read-back** settings, stop rules, hash of `zajem.py` |
| `rigol.csv` | `t_pred_s, t_po_s` (PC monotonic clock before and after the query), `U_V, I_A, P_W` exactly as the instrument returned them |
| `rigol_nacin.csv` | CV/CC/UR every 10 s |
| `rigol_dogodki.csv` | Query errors, unparseable replies and gaps with duration |
| `meta_konec.json` | End reason, counts, sampling period and jitter, final instrument state |
| `ea_energija.ino`, `ea_jedro.h` | Copy of the firmware source |
| `esp32.txt` | The board's records (`REZ`, `CILJ`, `TOCKA` lines) |
| `prevod_info.json` | Build id, git revision, hashes, board settings, tool versions (copy it in) |

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

Statistics, as implemented: Mann–Whitney U two-sided with normal approximation, mid-ranks for
ties, tie-corrected variance and continuity correction; Holm over the algorithm pairs within
one metric and one cell; A12 = P(first > second) + 0.5 P(equal), so below 0.5 means the first
algorithm has smaller values; ERT = total cost of all runs divided by the number of successful
runs, an unsuccessful run counting with its whole budget.

---

## H. What is still unverified

* Every firmware path on real hardware: session states, record checksum, reset reasons, light
  sleep timing, the pin configuration, the self-test loads.
* The acquisition script against a real DP821A (reply formats, error-queue text, query speed).
* Whether a 60 s busy window trips no watchdog (the configuration says no; the old 10 s chain
  test agrees; the campaign windows are the first long ones).
* Free heap at D = 20 and stack headroom: read them from `energija.csv` after the chain test.
* The read-back resolution and accuracy of the DP821A on the 60 V / 1 A channel: take them
  from the datasheet for the paper. They affect absolute joules, not the comparison.
* The exact wording of the three algorithm papers (selection rule in Storn and Price 1997,
  bound handling in jDE): check against the PDFs before submission.
