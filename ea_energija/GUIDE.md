# Measurement guide: two computers, no WiFi

> **Superseded (2026-11-16).** The procedure, commands and settings in this file predate the
> audit. Use `ea_energija/LAB_GUIDE.md`. The hardware description here is still valid; the
> WiFi upload, the `test_veriga` sketch, the 300 mA limit and the old output files are not.

| Computer | Role | Software |
|---|---|---|
| **Mac** | uploads firmware to the ESP32; reads results back over USB | Arduino IDE (esp32 core 3.3.12); built-in `python3` (no packages needed) |
| **PC** | controls and records the RIGOL DP821A; runs the analysis | PyCharm with an interpreter that has `pyvisa`, `pyvisa-py`, `pyusb`, `pyserial`, `scipy`, `matplotlib`; NI-VISA or RIGOL UltraSigma |

Both computers have the `ea_energija` folder. **Rule:** whenever you change an `.ino` on the Mac, copy it to the PC too. The PC reads the plan (number of runs, timing) from that file.

**Power rule:** the ESP32 is never powered from USB and the RIGOL at the same time. USB in → RIGOL switch open. RIGOL connected → USB out.

---

## 1. Wiring (once)

```
RIGOL CH1 (+) ──[switch]──── 3V3  ┐
RIGOL CH1 (−) ────────────── GND  ┘ ESP32 DevKit
RIGOL rear USB ───────────── PC
ESP32 micro-USB ──────────── Mac   (only while the switch is open)
```

* Use the pins labelled **3V3** and **GND**, never 5V/VIN. See `wiring_diagram.png`.
* Short (≤ 15 cm), twisted, soldered or screw-terminal wires. No dupont jumpers in the power path.
* Nothing else connected to the board.
* Optional: GPIO4 → 1 kΩ → test point, for an oscilloscope (HIGH during each run).

---

## 2. Mac: Arduino IDE settings (once)

*Tools* menu, identical for every upload:

| Setting | Value |
|---|---|
| Board | ESP32 Dev Module |
| CPU Frequency | 240 MHz (WiFi/BT) |
| Flash Frequency / Mode / Size | 80 MHz / QIO / 4 MB |
| Partition Scheme | Default 4MB with spiffs |
| Core Debug Level | None |
| Erase All Flash Before Sketch Upload | Disabled |
| Port | `/dev/cu.usbserial-…` or `/dev/cu.SLAB_USBtoUART` |

Serial Monitor: 115200 baud.

---

## 3. PC: PyCharm (once)

1. *File → Open…* → the `ea_energija` folder.
2. Bottom-right: choose the interpreter that has `pyvisa`. Missing package: *Settings → Project → Python Interpreter → + → install*.
3. **Run a script:** open it, click the green ▶ next to line 1 (or right-click → *Run*). Output appears in the *Run* panel.
4. **Settings** of each script are the CAPITAL variables at the top (`MAPA`, `PROGRAM`, `RIGOL`). Edit, Ctrl+S, run.
5. **Stop:** red ■ in the *Run* panel. After a manual stop, **check the RIGOL and switch the output off** by hand if needed.
6. Results appear as a folder in the *Project* panel; double-click `porocilo.txt` or `graf_*.png`.
7. Connect the PC to mains power, pause Windows Update for the night. The scripts keep the PC awake while recording.

| Script | What it does |
|---|---|
| `PC_1_preveri_rigol.py` | finds the RIGOL, prints its identity and one reading. Changes nothing |
| `PC_2_test_veriga.py` | chain test: sets the RIGOL, power-cycles the ESP32, records ~7 min, switches off |
| `PC_3_kampanja.py` | the full campaign, ~8.5 h; refuses to overwrite an existing folder |
| `PC_4_analiza.py` | analysis once `esp32.txt` is in the folder |

**Check:** run `PC_1_preveri_rigol.py`. Pass: `RIGOL TECHNOLOGIES,DP821A,…` and a reading `V, A, W`. If nothing is found, check the RIGOL USB cable and NI-VISA.

---

## 4. Smoke test (Mac only, ~5 min, no RIGOL)

Checks that all four experiments fit in RAM (L-SHADE at D = 100).

1. In `ea_energija.ino` temporarily set: `ZAGONOV 1`, `SPANJE_S 2`, `OPT_S 5`, `OGREVANJE 0`, `IZPIS_MED_POSKUSOM 1`.
2. USB in → *Upload* → Serial Monitor shows `#PRIPRAVLJEN` (the board waits instead of starting).
3. Press **EN** on the board. Each experiment prints `#Poskus … prosti RAM: …`, then one line per run.
4. **Pass:** four experiments, no `#NAPAKA`.
5. Set the values back (Section 7) and `IZPIS_MED_POSKUSOM 0`. Save.

---

## 5. Chain test (both computers, ~20 min)

Uses `test_veriga/test_veriga.ino` (Rastrigin D = 50, 1 warm-up round + 6 blocks, 10 s runs = 21 runs).

**Mac**
1. Switch **open**, USB in.
2. Open `test_veriga/test_veriga.ino` → *Upload* → Serial Monitor: `#PRIPRAVLJEN`.
3. Close the Serial Monitor, **unplug USB**.

**Rig**
4. Close the switch. Leave the RIGOL output off; the script handles it.

**PC**
5. Run `PC_2_test_veriga.py`. It sets 3.30 V / 0.3 A (OVP 3.6 V, OCP 0.4 A), output off for 5 s, then on, and prints a live line: ~10 mA sleeping, ~40–60 mA computing.
6. After ~7 min: `konec poskusa (deep sleep)`, output off. Don't touch the rig before this.

**Mac**
7. Open the switch, USB in. Terminal, in the `ea_energija` folder:

```bash
python3 zajem.py preberi --mapa meritve_test_veriga
```

   Expect `REZ: 21, KONV: 21`. (Without Terminal: Serial Monitor → wait for `#KONEC_IZPISA` → copy all text into `esp32.txt`.)
8. Copy `meritve_test_veriga/esp32.txt` to the same folder on the PC.

**PC**
9. `PC_4_analiza.py` with `MAPA = "meritve_test_veriga"`.
10. **Pass** (`porocilo.txt`):
    * `Najdenih zagonov v toku: 21 … zapisov REZ: 21`, no reset warning;
    * 3 warm-up + 18 valid runs, none excluded;
    * 6 runs per algorithm per position;
    * `graf_moc.png`: 21 windows, the first 3 grey.
    Note sampling rate (`meta.json` → `fs_Hz`), sleep and compute power.

If it fails, stop here and fix it before the campaign.

---

## 6. Campaign (all four experiments, ~8.5 h, unattended)

**Mac**
1. `ea_energija.ino` with the final settings (Section 7), `IZPIS_MED_POSKUSOM 0`, `WIFI_POSILJANJE 0`. Save.
2. **Copy `ea_energija.ino` to the PC.**
3. Switch open, USB in → *Upload* → `#PRIPRAVLJEN` → close Serial Monitor → **unplug USB** → close the switch.

**PC**
4. Lab log: date, start time, room temperature.
5. Run `PC_3_kampanja.py` (`MAPA = "meritve_kampanja1"`). Leave everything alone.
6. Next morning: stopped by itself, output off. Folder has `rigol.csv`, `meta.json`, copy of the `.ino`.

**Mac**
7. Switch open, USB in:

```bash
python3 zajem.py preberi --mapa meritve_kampanja1
```

   Expect `REZ: 372`. **Do not upload any sketch before this succeeds**: an upload erases the results.
8. Copy `esp32.txt` to `meritve_kampanja1` on the PC.

**PC**
9. `PC_4_analiza.py` with `MAPA = "meritve_kampanja1"`.
10. Check Section 8, back up the folder, note room temperature at the end.

For a repeat campaign: new `MAPA` name, upload again (that starts a fresh run).

---

## 7. Final settings (`ea_energija.ino`)

| Setting | Value | Why |
|---|---|---|
| `POSKUSI` | `{0,50},{0,100},{1,50},{1,100}` | Rastrigin and Rosenbrock, D = 50 and 100 |
| `ZAGONOV` | 30 | 30 repetitions (Cruz 2021); multiple of 6 keeps the order balanced |
| `OPT_S` | 60 | same time budget for every algorithm |
| `SPANJE_S` | 20 | rest before each run, also the baseline window |
| `OGREVANJE` | 1 | one warm-up run per algorithm per experiment, discarded |
| `ZACETNO_SPANJE_S` | 10 | supply settles after power-on |
| `SEME` | 20270101 | report it; change only for a replication |
| `PRAG_CILJA` | 1e-6 | target for energy-to-target |
| `TOCK` | 20 | convergence points |
| `WIFI_POSILJANJE`, `IZPIS_MED_POSKUSOM` | 0, 0 | nothing radio or UART during measurement |

Duration: 4 × 3 × 31 × (20 + 60 + 1.3) s ≈ 8.4 h.

---

## 8. Protocol and acceptance checks

What happens on the board:

```
power on (PC script) → 10 s sleep
for each experiment (Rastrigin/Rosenbrock × D=50/100):
    allocate memory for this D
    warm-up: DE, jDE, L-SHADE once each (flagged, excluded)
    30 blocks, each a balanced random order of DE, jDE, L-SHADE:
        20 s light sleep  → baseline power
        60 s optimisation → energy (GPIO4 high)
        1 s sleep, write record to flash
deep sleep → PC: 60 s without computing after the planned end → output off
```

Fairness: same time budget, same random seed for all algorithms within a block, every algorithm is first/second/third exactly 10 times, the same rest before every run, fixed 240 MHz, one board, one supply, no WiFi/BT.

Checks in `porocilo.txt` / `kontrola.csv` (decide before looking at results):

1. 372 runs in the trace = 372 records, `resetov=1`.
2. Every run's trace duration matches the ESP32 timer within 0.5 s (otherwise excluded and listed).
3. 10 runs per algorithm per position, per experiment.
4. No position effect (Kruskal–Wallis p > 0.05). If it fails, increase `SPANJE_S`.
5. Baseline drift over the night (mW/h): report it.
6. All windows 60 s.
7. Outliers |z| > 3: reported, not removed; investigate if more than 5.

Output files (on the PC, in `MAPA`): `rigol.csv` raw trace · `meta.json` supply and settings · `ea_energija.ino` exact firmware · `esp32.txt` ESP32 records · `energija.csv` one row per run · `povzetek.csv`, `testi.csv` statistics per experiment · `kontrola.csv`, `porocilo.txt` checks and report · `graf_*.png`.

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `PC_1` finds no device | RIGOL USB cable; install NI-VISA or UltraSigma; restart PyCharm |
| Board does nothing after the PC script switches on | was `#PRIPRAVLJEN` shown after upload? Is the switch closed? Wiring on 3V3/GND? |
| Recording never stops | the script stops at 1.3 × planned time + 10 min at the latest; check that the `.ino` on the PC is the uploaded one |
| `preberi` finds no port | close the Arduino Serial Monitor; check the cable is a data cable; give `--port /dev/cu.usbserial-XXXX` |
| `preberi` times out | the board may still be running or got reset: open Serial Monitor and look at what it prints |
| Runs found ≠ records | look at `graf_moc.png`; a reset makes the script align from the end and warn |
| `#NAPAKA` | not enough RAM for that D; smoke test (Section 4) catches this |

More background (hardware choices, sources, packing list): `SETUP_GUIDE.md`.
