# Setup guide: hardware, Arduino IDE, and the full workflow

> **Superseded (2026-11-16).** The procedure, commands and settings in this file predate the
> audit. Use `ea_energija/LAB_GUIDE.md`. The hardware description here is still valid; the
> WiFi upload, the `test_veriga` sketch, the 300 mA limit and the old output files are not.

> **Decision: WiFi is not used.** `WIFI_POSILJANJE` stays `0`. The ESP32 is powered only by the RIGOL during the campaign. A separate PC (PyCharm, no terminal) controls and records the RIGOL; this Mac uploads the firmware and reads the ESP32's run records over USB once, after the campaign (Section 4). Sections 3, 5 and 6 (WiFi upload to succulent) are kept only for reference and can be skipped.

This guide covers the measurement rig for the paper *Joules, Not Evaluations*: an ESP32-WROOM-32 powered and measured by a RIGOL bench supply. A PC connected to the RIGOL records the power trace; the ESP32's run records are read over USB after the campaign.

The repository has three parts that work together:

| File | What it does |
|---|---|
| `ea_energija.ino` | DE, jDE and L-SHADE, the experiment schedule, results stored in flash. With `WIFI_POSILJANJE 1` the results are also uploaded after the last run |
| `wifi_nastavitve_primer.h` | template for the WiFi and server settings. Copy it to `wifi_nastavitve.h`, which git ignores |
| `succulent_streznik/` | `streznik.py` and `configuration.yml` for the succulent server on the PC |
| `zajem.py` | records the RIGOL, then `succulent` (new: converts server data into `esp32.txt`), `preberi` (USB), and `analiza` |
| `PC_1…PC_4_*.py` | one-click PyCharm scripts for the RIGOL PC (Section 4.1) |
| `test_veriga/test_veriga.ino` | short copy of the firmware for the chain test (Section 4.4) |

---

## 1. Hardware

### 1.1 Rules the measurement depends on

1. **One power path only.** During a measurement the board gets power only from the RIGOL, on the **3V3** pin. USB stays unplugged. If USB and RIGOL are connected at the same time, the board is fed from two sources: the measurement is wrong, and current can flow back into the supply or the PC's USB port.
2. **Use 3V3, never 5V/VIN.** Feeding 3V3 directly bypasses the on-board LDO, so the RIGOL measures the module plus whatever else sits on the 3.3 V rail, not regulator losses.
3. **Nothing else powered from the board.** Any sensor, LED or module on the 3.3 V rail adds to the measured energy.
4. **Stable, low-resistance connection.** Dupont jumper wires on header pins are the most common source of noisy voltage traces (M5 fails) and of resets when a wire is bumped. Solder the power path.

### 1.2 Recommended rig (minimum worth building)

```
 RIGOL CH1 (+) ──[SPST switch]──┬────────────── 3V3  ┐
                                │  100 µF + 100 nF   │ ESP32 DevKit
 RIGOL CH1 (−) ─────────────────┴────────────── GND  ┘
 RIGOL USB  ─────────────── PC (zajem.py snemaj)
 GPIO4 ──[1 kΩ]──► test point / scope / logger (optional marker)
 GND ─────────────► test point (scope ground)
```

| Part | Why | Notes |
|---|---|---|
| Perfboard or a **screw-terminal breakout** for your DevKit | gives the power leads a soldered or clamped joint | breakouts exist for both the 30-pin and 38-pin DevKit variants, so buy the one that matches your board width. A perfboard with two rows of female headers works just as well |
| 2 wires, 0.5 mm² (20–22 AWG), as short as practical (aim ≤ 15 cm; the Hubble guide uses < 10 cm), **twisted** together, with 4 mm banana plugs on the RIGOL end | low, constant resistance and less pickup | at ~50 mA, 15 cm of 22 AWG drops about 1–2 mV, which is negligible |
| **SPST toggle switch** in the + lead | lets you leave the RIGOL wired up permanently and open the switch whenever USB is plugged in (flashing, readout) | this is the cheapest protection against rule 1 |
| **Optional without WiFi:** 100 µF electrolytic or tantalum + 100 nF ceramic across 3V3–GND, at the board | smooths WiFi current peaks (up to ~300 mA) at the end of the experiment and the long-lead inductance | does not change the energy over a 60 s window. Its leakage (µA) is far below the baseline |
| Two **test points** (GPIO4 marker via 1 kΩ, and GND) | for a scope or a second logger (Section 1.4) | 1 kΩ protects GPIO4 if the instrument on the other side is unpowered |

**Where to solder on the DevKit.** Pin order differs between DevKitC V4 (38-pin) and the many 30-pin clones, so go by the silkscreen labels, not by position:

| Signal | Pin label | Use |
|---|---|---|
| Supply + | `3V3` | RIGOL + (through the switch) |
| Supply − | `GND` (any GND pin, the one nearest 3V3 is best) | RIGOL − |
| Marker | `IO4` / `D4` / `G4` | HIGH during each optimization window (already in the firmware) |
| Never | `5V` / `VIN` | do not connect the RIGOL here |

**Pins to avoid if you add anything later:** GPIO 6–11 (internal flash), the strapping pins GPIO 0, 2, 5, 12 and 15 (they affect boot; GPIO12 HIGH at boot breaks flash voltage selection), and GPIO 1 and 3 (UART). GPIO 34–39 are input-only. Safe general-purpose choices: GPIO 4, 13, 14, 16–19, 21, 22 (I²C defaults are SDA 21 and SCL 22), 23, 25–27, 32 and 33.

### 1.3 Lowering the board baseline (optional, recommended)

The analysis reports **gross** and **net** energy (net = gross − baseline × time), so the baseline does not bias results. A smaller and more stable baseline still makes the net numbers less noisy.

1. **Power LED.** If the red LED lights when the board runs from the RIGOL alone, it sits on the 3.3 V rail and costs roughly 1–3 mA. Desolder the LED or its series resistor. Measure the sleep baseline before and after, and note the modification in the paper.
2. **USB-UART chip (CP2102/CH340).** On many boards it is powered from the 3.3 V rail even with USB unplugged. The firmware already tri-states TX (GPIO1) so the ESP32 does not drive it through the data line. Removing the chip is not worth it, because you need it for flashing.
3. **Cleanest option: a bare module carrier.** Mount an ESP32-WROOM-32 module on a breakout with only decoupling capacitors (10 µF + 100 nF at 3V3), an EN pull-up (10 kΩ + 1 µF to GND), a BOOT button on GPIO0, and a 6-pin header (3V3 not connected, GND, TX0, RX0, EN, IO0) for an external 3.3 V USB-UART adapter. Then the RIGOL measures the module only. Do this only if you have time: the paper states "development board", and the baseline subtraction already handles the board.

Whatever you choose, **use the same board for all four experiments** and report it.

### 1.4 Higher time resolution (optional, for figures or future work)

Sampling the RIGOL over SCPI gives about 5–10 Hz. That is enough to integrate 60 s windows with nearly constant power, but it cannot resolve algorithm phases. Two upgrades, both using the GPIO4 marker that the firmware already drives:

* **Oscilloscope.** Put a 1 Ω 0.1 % shunt in the GND lead (1 mV per mA). Channel 1 goes across the shunt, channel 2 on GPIO4, and the scope triggers on GPIO4. The shunt drops ~50 mV, so the board then sees ~3.25 V. Use the RIGOL's remote-sense terminals, if your model has them, or report the lower voltage.
* **INA226 logger (also what the paper's "future work" needs).** Wire an INA226 breakout (0.1 Ω shunt, ~25 µA resolution) high-side: RIGOL + → `IN+`, `IN−` → ESP32 3V3, `VBUS` → `IN−`, GND common. Power the INA226 (`VS`) and read it over I²C from a **second** microcontroller, so its own current is not counted. Wire GPIO4 (through 1 kΩ) to an input of the logger, so every sample carries the exact run boundary. This cross-checks the RIGOL energy at ~1 kHz.

### 1.5 RIGOL settings

* 3.30 V, current limit **300 mA** (this is what `zajem.py` sets; 500 mA would only be needed with `WIFI_POSILJANJE 1`). Above 300 mA the supply would go into constant-current mode during WiFi transmit peaks, the voltage would dip, and the ESP32 would brown-out and reset.
* Always the same channel. Record the model, serial number and **readback resolution** from the datasheet: it differs between models (for example DP832 versus DP832A). A 1 mA readback resolution is coarse for a sleep baseline of a few mA. If yours is that coarse, say so in the paper or validate it with the INA226.
* Disable the supply's own over-current or "sense" features only if you know what they do. Otherwise leave them at default.

---

## 2. Arduino IDE

The sketch was compiled with **arduino-esp32 core 3.3.12**, which is what this Mac has installed. It builds with WiFi off (342 kB, 26 % of flash) and on (1,083 kB, 82 %). No extra libraries are needed: `WiFi`, `HTTPClient`, `LittleFS` and `Preferences` ship with the core.

1. *Boards Manager* → **esp32 by Espressif Systems** (already installed).
2. *Tools* settings. **Keep these identical for every experiment and record them**, because CPU and flash frequency directly change power:

| Setting | Value |
|---|---|
| Board | ESP32 Dev Module |
| CPU Frequency | 240 MHz (WiFi/BT) |
| Flash Frequency | 80 MHz |
| Flash Mode | QIO |
| Flash Size | 4 MB (32 Mb) |
| Partition Scheme | Default 4MB with spiffs (1.2MB APP / 1.5MB SPIFFS). The WiFi build fits |
| PSRAM | Disabled (WROOM-32 has none) |
| Core Debug Level | **None** (debug output costs energy and writes to UART) |
| Arduino Runs On / Events Run On | Core 1 |
| Erase All Flash Before Sketch Upload | Disabled |
| Upload Speed | 921600 (lower to 115200 if uploads fail) |

3. Port: on macOS `/dev/cu.usbserial-…` or `/dev/cu.SLAB_USBtoUART`. If nothing appears, install the Silicon Labs CP210x driver, or WCH CH34x for boards with a CH340, and try a data-capable USB cable.
4. For WiFi: copy `wifi_nastavitve_primer.h` to `wifi_nastavitve.h` in the same folder, fill it in (Section 3.3), and set `#define WIFI_POSILJANJE 1` at the top of the sketch. Arduino IDE shows both `.h` files as tabs. That is expected.

---

## 3. WiFi upload to succulent

### 3.1 How it works, and why only after the last run

Uploading after **each** run would contaminate the measurement in three ways:

* Initializing WiFi does RF calibration and leaves the driver resident, which changes the baseline (light-sleep power) of every following run.
* The WiFi stack needs ~50 kB of heap, which L-SHADE at D = 100 already uses.
* The paper states that WiFi is not active during measurement.

So the firmware keeps the original protocol untouched and adds one step at the very end:

```
… last run → 1 s sleep → flash write → state = DONE, "upload pending"
→ deep sleep 2 s (= clean reboot, all RAM free)
→ boot: connect WiFi (≤ 15 s) → POST one JSON record per run (≤ 30 s total)
→ WiFi off → deep sleep (end, current ~0)
```

* Failure (no network, server down, brown-out reset): it retries after 5 s, up to 3 times in total, then gives up. **The results always stay in flash**, so USB readout (`zajem.py preberi`) works exactly as before. In the Serial Monitor, sending `w` re-uploads over WiFi.
* The WiFi phase shows in the power trace as a short burst at roughly 2× compute power. `zajem.py analiza` now rejects it (shown hatched in `graf_moc.png`). The threshold level is also computed robustly, so the burst cannot shift it. A synthetic test with 10 s runs plus a WiFi burst finds all 6 runs; the old version found 1.
* Each record carries the build tag (`poskus` = compile date and time) and the board MAC, so one server can collect all four experiments. Duplicates from re-sends are removed when the data is converted.

**Cost of the switch.** With `WIFI_POSILJANJE 1`, the WiFi libraries are linked in. WiFi is not started during the runs, but the binary is larger and **~27 kB less RAM is free** (53 kB versus 26 kB of globals). Therefore:

* use the **same setting for all four experiments**,
* run the smoke test (Section 4.3) with WiFi on and confirm there is no `#NAPAKA` at D = 100,
* in the chain test (Section 4, step C), compare `P_bazna_mW` and `P_povp_mW` against a run with `WIFI_POSILJANJE 0`. They should agree within noise.

With `WIFI_POSILJANJE 0` the firmware is functionally the original: the build is 4 bytes larger and RAM is unchanged.

### 3.2 PC side: succulent server

succulent needs **Python 3.10–3.13**. The `python3` on this Mac is 3.15, and succulent requires `pandas < 3`, which may not install there. Use a conda environment:

```bash
conda create -n energija python=3.12
```

```bash
conda activate energija
```

```bash
pip install succulent pyvisa pyvisa-py pyserial scipy matplotlib
```

Start the server (leave this terminal open for the whole session):

```bash
cd ea_energija/succulent_streznik && python streznik.py
```

* It listens on port 8080 on all interfaces. Data is stored in `succulent_streznik/data/data.csv`, one row per run, and git ignores it.
* Change `password` in `configuration.yml`. It must match `SUCC_GESLO` in `wifi_nastavitve.h`.
* Browser: `http://localhost:8080/` shows the status page, and `http://localhost:8080/explore` shows the dashboard of received rows (handy to watch the upload arrive).
* Test from the PC before involving the ESP32:

```bash
curl -X POST http://localhost:8080/measure -H "Authorization: Bearer spremeni-me" -H "Content-Type: application/json" -d '{"poskus":"test","i":0,"alg":"DE"}'
```

  The test row ends up in `data.csv`. It does no harm, because `zajem.py succulent` selects the experiment by its tag.

### 3.3 Network

* **2.4 GHz, WPA2-Personal.** The ESP32 cannot join 5 GHz networks or **eduroam** (WPA2-Enterprise). Use a home router, a cheap travel router, or a phone hotspot (on iPhone enable *Maximize Compatibility* for 2.4 GHz). Join the Mac to the same network.
* **The PC's IP address** goes into `SUCC_URL`: `ipconfig getifaddr en0` on macOS. Reserve it in the router (DHCP reservation), because it is compiled into the firmware.
* **Device-to-device traffic must be allowed.** Guest networks and some hotspots isolate clients. Test by opening `http://<PC-IP>:8080/` from your phone on the same network.
* **macOS firewall**: if it is on, allow incoming connections for `python` when asked, or add it under System Settings → Network → Firewall → Options.

`wifi_nastavitve.h`:

```cpp
#define WIFI_SSID   "your-2.4GHz-network"
#define WIFI_GESLO  "network-password"
#define SUCC_URL    "http://192.168.1.50:8080/measure"   // your PC's IP
#define SUCC_GESLO  "same-as-configuration.yml"
#define WIFI_MOC_ODDAJANJA  WIFI_POWER_8_5dBm             // low TX power = smaller current peaks
```

### 3.4 Getting the data into the analysis

```bash
python zajem.py succulent http://localhost:8080 --geslo spremeni-me --mapa meritve_rastrigin50
```

It lists all experiments stored on the server, takes the **latest** (or the one given with `--poskus "<tag>"`), and writes `meritve_rastrigin50/esp32.txt` in the same format the USB readout produces. `analiza` is unchanged. It warns if any run index is missing. You can also pass the file path `succulent_streznik/data/data.csv` instead of the URL.

---

## 4. Complete experimental workflow (two computers)

| Computer | Used for | Software |
|---|---|---|
| **Mac** | uploading firmware to the ESP32, reading the results back over USB | Arduino IDE; the built-in `python3` (no extra packages: `zajem.py preberi` falls back to the standard library when `pyserial` is missing) |
| **RIGOL PC** | controls and records the RIGOL DP821A, runs the analysis | PyCharm with an interpreter that has `pyvisa`, `pyvisa-py`, `pyusb`, `pyserial`, `scipy`, `matplotlib`; NI-VISA (or UltraSigma) for USB |

The ESP32 is never connected to both at the same time: USB to the Mac only while the RIGOL switch is open, RIGOL only while USB is unplugged.

**Keep the two copies of the `ea_energija` folder identical.** The RIGOL PC reads the plan (number of runs, timing) from the `.ino` file, so after every change on the Mac copy the folder to the PC (USB stick, cloud folder or `git pull`).

### 4.1 PyCharm on the RIGOL PC (no terminal needed)

1. **Open the project:** *File → Open…* → choose the `ea_energija` folder.
2. **Interpreter:** bottom-right corner of the window → choose the environment that has `pyvisa`. If a package is missing: *Settings → Project → Python Interpreter → +* → search for it → *Install Package*.
3. **Run a script:** open one of the `PC_…` files and click the green ▶ next to the first line (or right-click in the file → *Run 'PC_…'*). Output appears in the *Run* panel at the bottom.
4. **Change a setting:** each `PC_…` script has its settings in capital letters at the top (`MAPA`, `PROGRAM`, `RIGOL`). Edit, save (Ctrl+S), run again.
5. **Stop:** the red ■ *Stop* button in the *Run* panel. After stopping by hand, **check the RIGOL front panel and switch the output off** if it is still on: a forced stop may not reach the script's own switch-off.
6. **Results:** the folder (e.g. `meritve_test_veriga`) appears in the *Project* panel on the left; double-click `porocilo.txt` or a `graf_*.png` to view it.

| Script | When | What it does |
|---|---|---|
| `PC_1_preveri_rigol.py` | once, and whenever the RIGOL is not found | lists VISA devices, prints `*IDN?`, the CH1 settings and one reading. Changes nothing |
| `PC_2_test_veriga.py` | chain test (4.4) | sets the RIGOL, power-cycles the ESP32, records ~7 min, switches off |
| `PC_3_kampanja.py` | the real campaign (4.5) | same for the whole night; refuses to overwrite an existing folder |
| `PC_4_analiza.py` | after `esp32.txt` is copied in | analysis, statistics, checks and graphs |

The scripts keep the PC awake while recording. Still: connect the PC to mains power, and on Windows pause *Windows Update* for the night (*Settings → Windows Update → Pause*), so it does not restart.

### 4.2 One-time preparation (≈ 2–3 h, including soldering)

1. Build the rig (Section 1.2). Optionally remove the power LED (1.3).
2. **Mac:** Arduino IDE settings (Section 2).
3. **RIGOL PC:** PyCharm as in 4.1; copy the `ea_energija` folder; run `PC_1_preveri_rigol.py`. Pass: it prints `RIGOL TECHNOLOGIES,DP821A,…` and a reading like `3.300,0.000,0.000`. Note the RIGOL's readback resolution from the DP821A datasheet.
4. Start a lab log (template at the end of `README.md` in the repository root): board, supply model and serial, core version 3.3.12, Tools settings, board modifications.

### 4.3 Smoke test on the Mac only (≈ 5 min, no RIGOL)

Checks that L-SHADE at D = 100 fits in RAM. On the Mac, temporarily set in `ea_energija.ino`: `ZAGONOV 1`, `SPANJE_S 2`, `OPT_S 5`, `OGREVANJE 0`, `IZPIS_MED_POSKUSOM 1`.

1. Upload. The Serial Monitor (115200 baud) shows `#PRIPRAVLJEN`.
2. Press **EN** on the board. Every experiment prints `#Poskus …` with the free RAM, then a line per run.
3. Pass: all four experiments print their runs and there is **no `#NAPAKA`**.
4. Set the values back (Section 9.2) and `IZPIS_MED_POSKUSOM 0`.

### 4.4 Chain test (≈ 20 min, once)

Uses the ready-made `test_veriga/test_veriga.ino` (Rastrigin D = 50, 6 blocks, 10 s runs, 21 runs in total).

**Mac**
1. RIGOL switch **open**. Connect the ESP32 by USB.
2. Arduino IDE: open `test_veriga/test_veriga.ino` → *Upload*. Serial Monitor: `#PRIPRAVLJEN`.
3. Close the Serial Monitor and **unplug USB** from the ESP32.

**Rig**
4. RIGOL CH1 + → switch → 3V3, CH1 − → GND. Close the switch. Nothing needs setting on the RIGOL; leave the output off.

**RIGOL PC (PyCharm)**
5. Run `PC_2_test_veriga.py`. It prints the plan (21 runs, ~0.10 h) and a live line with current and minutes left: ~10 mA in sleep, ~40–60 mA while computing.
6. After ~7 min it prints `konec poskusa (deep sleep)` and switches the output off. Don't touch the rig before that.

**Mac**
7. Open the RIGOL switch, connect the ESP32 by USB. In Terminal, in the `ea_energija` folder:

```bash
python3 zajem.py preberi --mapa meritve_test_veriga
```

   It finds the port by itself and writes `meritve_test_veriga/esp32.txt` (`REZ: 21, KONV: 21`). (Alternative without Terminal: Arduino IDE Serial Monitor → wait for `#KONEC_IZPISA` → select and copy the text into a file `esp32.txt`; timestamps are ignored.)
8. Copy `esp32.txt` into the `meritve_test_veriga` folder on the RIGOL PC.

**RIGOL PC**
9. Run `PC_4_analiza.py` (`MAPA = "meritve_test_veriga"`).
10. Pass (in `porocilo.txt`): 21 runs found = 21 REZ records; 3 warm-up + 18 valid, none excluded; 6 runs per algorithm per position; `graf_moc.png` shows 21 windows, the first 3 grey. Note the sampling rate (`meta.json`, `fs_Hz`) and the sleep and compute power.

### 4.5 The campaign (all four experiments, one upload, ≈ 8.5 h, unattended)

**Mac**
1. Final settings from Section 9.2 in `ea_energija.ino`, `IZPIS_MED_POSKUSOM 0`, `WIFI_POSILJANJE 0`. Don't change anything afterwards.
2. **Copy the `ea_energija` folder to the RIGOL PC** (the PC must have exactly this `.ino`).
3. RIGOL switch open → USB in → open `ea_energija.ino` → *Upload* → `#PRIPRAVLJEN` → close Serial Monitor → **unplug USB** → close the switch.

**RIGOL PC**
4. Write date, start time and room temperature in the lab log.
5. Run `PC_3_kampanja.py` (`MAPA = "meritve_kampanja1"`). Leave everything alone overnight.
6. Next morning the script has stopped by itself and switched the output off. The folder has `rigol.csv`, `meta.json` and a copy of `ea_energija.ino`.

**Mac**
7. Switch open, USB in:

```bash
python3 zajem.py preberi --mapa meritve_kampanja1
```

   Expect `REZ: 372`. **Do not upload any sketch before you have this file**: an upload erases the results.
8. Copy `esp32.txt` to `meritve_kampanja1` on the RIGOL PC.

**RIGOL PC**
9. `PC_4_analiza.py` with `MAPA = "meritve_kampanja1"`. Check Section 9.4, back up the folder, note the room temperature at the end.

### 4.6 After the campaign

`energija.csv` holds one row per run for all four experiments (column `poskus`); `povzetek.csv` and `testi.csv` hold the per-experiment statistics. The `gecco_paper/` scripts mentioned in the root `README.md` are not in this repository yet.

---

## 5. What to change in the paper if you use WiFi upload

* Hardware paragraph: "Wi-Fi and Bluetooth are never initialized" becomes something like *"Bluetooth is never initialized; Wi-Fi is started only after the last run, following a reset, to upload the records to a collection server [succulent], and is never active during a measurement window."*
* Protocol paragraph: "the records are read out over USB afterwards" becomes *"…uploaded over Wi-Fi (with the on-chip copy as fallback)"*.
* If you remove the power LED or use a bare module, say so, together with the baseline you measured.
* Fill in the RIGOL model, its readback resolution and the measured sampling rate (`fs`).
* Check the succulent repository for its preferred citation.

---

## 6. Troubleshooting (WiFi-specific)

| Symptom | Cause / fix |
|---|---|
| No rows at `/explore` after the experiment | wrong IP in `SUCC_URL`, firewall, client isolation, or 5 GHz/enterprise network. Test from your phone. Plug in USB and send `w` in the Serial Monitor: it prints `#WiFi …` lines with the HTTP code per record |
| HTTP 400 `Unauthorised access` | `SUCC_GESLO` ≠ `password` in `configuration.yml` |
| HTTP -1 / connection refused | server not running or wrong port |
| Board resets during the upload, RIGOL shows CC | current limit too low. Set 500 mA, add the 100 µF capacitor, keep `WIFI_POWER_8_5dBm` |
| `#NAPAKA` with `WIFI_POSILJANJE 1` at D = 100 | the WiFi libraries take ~27 kB RAM. Use `WIFI_POSILJANJE 0` (USB readout) for this experiment series |
| Analysis finds one run too many | look at `graf_moc.png`. If the WiFi burst was not rejected, its mean power was not > 1.5× compute power, so check `WiFi.setSleep(false)` was kept |
| `zajem.py succulent` warns about missing `i` | some records were not accepted. Read the rest over USB (`preberi`) |

---

## 7. How this design compares with published measurement guides

| Point | Espressif "Current Consumption Measurement of Modules" | Hubble "Profile ESP32 power accurately" | Lucidar FireBeetle | This design |
|---|---|---|---|---|
| Where power is fed | module 3V3 through the meter | bench 3.3 V through the meter into the module's 3V3 | whole board over USB | RIGOL 3.30 V into the 3V3 pin ✔ |
| Dev board or module | dev board **not recommended**: board circuits draw current | "measure at the module, not through your dev board"; cut the LED, bypass USB | dev board (works only because that board has no LED and a 2 µA LDO) | dev board, baseline measured and subtracted, LED removal optional. **Deviation: state it in the paper** |
| Instrument | Joulescope or PPK2 (wide dynamic range, low burden voltage) | PPK2, or a shunt + scope; multimeters at 2–3 Hz rejected | high-sensitivity multimeter (deep sleep only) | RIGOL readback at ~5–10 Hz. Adequate for **60 s windows of nearly constant power**, not for transients or sleep µA. **Validate once with a shunt + scope** (Section 1.4) |
| Leads | – | < 10 cm, solid connections | – | ≤ 15 cm, soldered or screw terminals |
| Things that bias results | ammeter burden voltage | power LED 2–5 mA; measure ≥ 5 s after boot; temperature changes current by ~10 % | LED, LDO quiescent current | 10 s sleep before every run; algorithms interleaved; log room temperature ✔ |
| Capacitors | not discussed | not discussed | not discussed | come from the Espressif hardware guidelines (10 µF + 0.1 µF at the module) and brownout reports (bulk capacitor for WiFi peaks). Only needed for the WiFi upload |

Reference numbers to sanity-check your own readings:
* WiFi TX peaks 150–350 mA, RX 80–100 mA (Hubble). Only relevant with WiFi upload, which is not used.
* Deep sleep: a bare module 5–10 µA, a dev board 20–50 µA or much more (Hubble). Espressif's low-power page gives ~5 µA. A DevKitC with its LED fitted will be in the mA range. The RIGOL cannot resolve this, and the analysis does not need it.
* Active current: the Lucidar board drew 42 mA while awake (no WiFi); Espressif measured 23.9 mA on an ESP32-S3 (a different chip). Expect roughly 40–70 mA at 240 MHz on the WROOM-32. The ESP32 datasheet's power table is the authoritative source to cite.

**Conclusion:** the approach matches the published practice on the essentials: feed 3.3 V straight into 3V3, keep USB out of the power path, deal with the LED, short solid leads, and wait after boot before measuring. The one real weakness is the instrument. A ~5–10 Hz supply readback is a coarse ammeter compared with a PPK2 or Joulescope. It is defensible for 60 s integrals, but quantify it with a one-off shunt + scope comparison (Section 1.4, done once during the chain test) and name it under Limitations. A Nordic Power Profiler Kit II (roughly 100 €; 200 nA–1 A per the Hubble guide) would remove the weakness entirely if your lab can buy one.

---

## 8. What to bring (besides the RIGOL, the ESP32, an oscilloscope and the USB cable)

**Must have**
1. Laptop with Arduino IDE (esp32 core 3.3.12), the `energija` conda env, and this repository. Plus its charger, because experiments run 90 min each.
2. **USB cable for the RIGOL** (USB-B type, for the rear port). This is separate from the ESP32's micro-USB cable. Make sure the ESP32 cable is a **data** cable, not a charge-only one.
3. Two **4 mm banana-plug leads**, red and black, or banana-to-bare-wire leads. Plus 0.5 mm² (20–22 AWG) stranded wire, red and black, about 1 m each.
4. **Small SPST toggle switch** for the + lead.
5. **Capacitors (optional without WiFi):** 100 µF / ≥ 6.3 V electrolytic and 100 nF ceramic.
6. **Mounting:** a screw-terminal breakout matching your board width (30- or 38-pin), *or* perfboard plus 2 × 19-pin (38-pin board) or 2 × 15-pin (30-pin board) female headers.
7. **Soldering kit:** iron, solder, flux, desoldering wick (for removing the LED), side cutters, wire stripper, heat-shrink tubing or electrical tape.
8. **Digital multimeter:** check polarity, check that 3V3 is not shorted to GND before switching on, and confirm 3.30 V at the board.
9. **No network needed** (WiFi is not used).
10. **Lab log** (template in the root `README.md`) and a pen. Also a **thermometer** for room temperature, which matters because temperature changes current by ~10 %.

**For the oscilloscope validation (recommended once)**
11. **Shunt resistor: 1 Ω, 0.1 % or 1 %, ≥ 0.25 W.** At ~50 mA this gives 50 mV per 50 mA, which a scope reads easily. Bring a 0.1 Ω one too, for the WiFi peaks.
12. **1 kΩ resistor** for the GPIO4 marker, and **two oscilloscope probes**: one across the shunt, one on the marker.
13. Two **test-point pins or hooks** (TP1 marker, TP2 GND) and a few **jumper wires with clips**.

**Optional**
14. **INA226 breakout (0.1 Ω shunt) plus a second microcontroller** as an independent logger (Section 1.4).
15. **A spare ESP32 board of the same model**, in case you damage one while soldering. Use only one board for all the experiments.
16. **A USB hub with a power switch per port**, which makes it easier to obey the "unplug USB" rule.

Sources for Section 7: [Espressif – Current Consumption Measurement of Modules](https://docs.espressif.com/projects/esp-idf/en/v5.3.4/esp32/api-guides/current-consumption-measurement-modules.html) · [Hubble – How to profile ESP32 power consumption accurately](https://hubble.com/community/guides/how-to-profile-esp32-power-consumption-accurately) · [Lucidar – FireBeetle DFR0478 consumption](https://lucidar.me/en/esp32/power-consumption-of-esp32-firebeetle-dfr0478/) · [Espressif low-power mode (zh)](https://docs.espressif.com/projects/esp-idf/zh_CN/v5.3.4/esp32/api-guides/low-power-mode.html) · [Espressif hardware design guidelines](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32/esp-hardware-design-guidelines-en-master-esp32.pdf) · [DevKitC V4 guide](https://docs.espressif.com/projects/esp-idf/en/v5.2.2/esp32/hw-reference/esp32/get-started-devkitc.html)

---

## 9. Experimental protocol

### 9.1 What the published methodology asks for, and how this protocol does it

| Recommendation | Source | Here |
|---|---|---|
| Automate the whole run, no human during measurement | Cruz 2021 | one upload, one command; the script switches the supply on and off and stops by itself; records are read over USB once, after the campaign |
| Warm up before measuring (e.g. ~5 min) and discard it, preferably by running the same tests | Cruz 2021 | `OGREVANJE 1`: at the start of **each** experiment every algorithm runs once (3 × 60 s ≈ 3 min at that D); recorded but flagged `ogrev=1` and excluded |
| Rest between measurements to avoid carry-over (≈ 1 min on PCs) | Cruz 2021 | `SPANJE_S 20` s light sleep before every run. A bare MCU has a far smaller thermal mass than a PC; the baseline-drift check (9.4) tells you whether 20 s is enough |
| Shuffle the execution order | Cruz 2021 | balanced randomised blocks: each block runs every algorithm once; all 6 orders occur equally often (5× with 30 blocks), their sequence is shuffled with a fixed, reported seed. Every algorithm is first, second and third exactly 10 times (verified on the firmware code) |
| ~30 repetitions | Cruz 2021 | `ZAGONOV 30` per algorithm per experiment |
| Subtract idle/sleep energy measured over the same period | Merelo et al. 2023 (JavaScript EA energy) | `P_bazna` measured in the last part of each rest, `E_neto = E − P_bazna·T` per run |
| Same conditions for every treatment | general | same board, supply, voltage, 240 MHz fixed, same time budget, same seed for all algorithms in a block (common random numbers), WiFi/BT never started |
| Report and investigate outliers (|z| > 3) rather than silently drop them | Cruz 2021 | reported in `kontrola.csv`, never removed automatically |
| Non-parametric tests with effect sizes, corrected for multiple comparisons | standard in EC (Vargha–Delaney A12, Holm) | Mann–Whitney U, Holm, A12 per experiment |

### 9.2 Final settings (in `ea_energija.ino`, decided before the campaign)

| Setting | Value | Why |
|---|---|---|
| `POSKUSI` | `{0,50},{0,100},{1,50},{1,100}` | the four experiments of the paper |
| `ZAGONOV` | 30 | Cruz's 30 repetitions; multiple of 6 keeps the order perfectly balanced |
| `OPT_S` | 60 | fixed time budget, identical for all algorithms |
| `SPANJE_S` | 20 | rest + baseline window |
| `OGREVANJE` | 1 | warm-up per experiment |
| `ZACETNO_SPANJE_S` | 10 | supply settles after power-on |
| `SEME` | 20270101 | report it; change it only for a replication |
| `PRAG_CILJA` | 1e-6 | decide before the campaign |
| `TOCK` | 20 | convergence points |

Duration: 4 × 3 × 31 runs × (20 + 60 + 1.3) s ≈ **8.4 h**, plus the upload.

### 9.3 Timeline of one campaign

```
power on (script) ─ 10 s sleep ─ flash format
for each experiment (Rastrigin/Rosenbrock × D=50/100):
    allocate memory for this D                (outside any measurement window)
    warm-up: DE, jDE, L-SHADE once each       (flagged ogrev=1, excluded)
    30 blocks, each a balanced random order of DE, jDE, L-SHADE:
        20 s light sleep   → baseline P_bazna (last 17.5 s)
        60 s optimisation  → energy E (GPIO4 high)
        1 s light sleep, write the record to flash
    free memory
deep sleep (current drops)
script: no compute for 60 s after the planned end → output off
you: switch open, USB in to the Mac → zajem.py preberi → copy esp32.txt to the RIGOL PC → PC_4_analiza.py
```

### 9.4 Acceptance checks (all printed in `porocilo.txt`, written to `kontrola.csv`)

Decide these before looking at results, and report them in the paper:

1. **Completeness:** runs found in the trace = REZ records = 372, and `resetov=1` (no brown-out restart). A restart is handled (records are aligned from the end), but report it.
2. **Alignment:** `|usklajenost_s|` < 0.5 s for every run (power-trace duration vs the ESP32's own timer). Runs outside are excluded and listed.
3. **Balance:** 10 runs per algorithm per position in every experiment.
4. **No position effect:** Kruskal–Wallis on power by position, per algorithm, p > 0.05. If it fails, the rest period is too short.
5. **Baseline drift:** slope of `P_bazna` over the night (mW/h). Report it; a large drift points to temperature changes, which the balanced order spreads evenly over the algorithms.
6. **Equal time budget:** measurement windows 60 s for all runs.
7. **Outliers:** report |z| > 3 runs; investigate if more than 5.

### 9.5 Data flow (readable output)

| File | Contents |
|---|---|
| `rigol.csv` | raw trace: time, U, I, P |
| `meta.json` | supply identity, settings, start/end, sampling rate, plan read from the `.ino` |
| `ea_energija.ino` | exact firmware used |
| `esp32.txt` | records from the ESP32 (header, one `REZ` and one `KONV` line per run) |
| `energija.csv` | **one row per run, all experiments**: experiment, algorithm, block, position, warm-up flag, start time, E, E_net, P, baseline, FE, µJ/FE, best, time and energy to target, validity |
| `povzetek.csv`, `testi.csv` | per experiment and algorithm: descriptive statistics; pairwise tests (p, Holm p, A12) |
| `kontrola.csv`, `porocilo.txt` | fairness checks and the full printed report |
| `graf_*.png` | power trace with segmentation, convergence over energy, energy box plots per experiment |

### 9.6 References for the protocol

* L. Cruz, *Green Software Engineering Done Right: a Scientific Guide to Set Up Energy Efficiency Experiments*, 2021. [link](https://luiscruz.github.io/2021/10/10/scientific-guide.html)
* J. J. Merelo-Guervós, M. García-Valdez, P. A. Castillo, *An Analysis of Energy Consumption of JavaScript Interpreters with Evolutionary Algorithm Workloads*, ICSOFT 2023. [link](https://www.scitepress.org/Documents/2023/121281) (15 repetitions, sleep energy over the same period subtracted, according to their slides)
* A. Abdelhafez, E. Alba, G. Luque, *A component-based study of energy consumption for sequential and parallel genetic algorithms*, J. Supercomputing 75, 2019. [dblp](https://dblp.dagstuhl.de/rec/journals/tjs/AbdelhafezAL19.html)
* J. Díaz-Álvarez et al., *Population size influence on the energy consumption of genetic programming*, 2022. [link](https://digibug.ugr.es/handle/10481/74815)
* R. Pereira et al., *Ranking programming languages by energy efficiency*, Sci. Comput. Program. 205, 2021. [PDF](https://web.fe.up.pt/~jacome/downloads/SCP21.pdf)
* Espressif, *Current Consumption Measurement of Modules*. [link](https://docs.espressif.com/projects/esp-idf/en/v5.3.4/esp32/api-guides/current-consumption-measurement-modules.html)
