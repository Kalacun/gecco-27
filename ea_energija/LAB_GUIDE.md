# Lab guide: which version to use

All three versions run the same firmware, write the same records and apply the same checks. Pick one
per session; you can switch between them.

| | **Windows, one PC** — `LAB_GUIDE_WINDOWS.md` (slovensko) | **IDE version** — `LAB_GUIDE_IDE.md` | **Command-line version** — `LAB_GUIDE_CLI.md` |
|---|---|---|---|
| Machines | One Windows PC connected to the RIGOL and the ESP32 | Mac (ESP32 on USB) + PC (RIGOL); data cross in `prenos/<session>` | One computer connected to both |
| Firmware build and upload | PyCharm: `W2_pripravi_in_nalozi.py` (`arduino-cli`) | Arduino IDE on the Mac (Upload button) | `python3 prevedi.py ... --nalozi` |
| Recording and analysis | PyCharm: `W4`, `W5`, `W6` | PyCharm on the PC (`PC_*.py`) | `python3 zajem.py ...` |
| Session settings | One file, `seja_nastavitve.py`; the session name is kept automatically | Settings or options per script | Options per command |
| Helper steps | `W0` check, `W1` flash copy, `W3` verify, `W7` T, `W8` erase | `Mac_1`…`Mac_6` | `python3 naprava.py <command>` |

## What is common to all three

* The order of work: **A** rescue old data → **B** wiring → **C** self-test → **D** chain test → **E** fix T and
  thresholds, commit → **F** campaign.
* **Rescue the old data before anything is flashed.** Flashing a build with another id erases the records, and the
  firmware now on the board deletes them at power-up if its last session was interrupted.
* **USB and the RIGOL never power the board together.** USB only with the switch open.
* **After flashing, do not press EN and do not open a serial monitor.** The next boot starts the session, and that
  must happen on the RIGOL's power. Check what was flashed with `Mac_3_preveri_nalaganje.py` /
  `python3 naprava.py preveri-nalozeno`.
* **Commit before you build.** A build from uncommitted source is marked `+spremembe` and the analysis refuses it, as
  it does a build made without the prepare step (`rocno`), a recording computer whose source differs from what was
  flashed, and wrong board settings.
* Every session goes into a **new folder**; nothing raw is ever overwritten.
* The firmware's records, the build id, the source hash and the board settings are checked by the analysis, which
  stops with a reason rather than analysing doubtful data.

## State of the code

Tested on a computer only (analysis, Mac helpers, recording against a fake instrument, rehearsal of the PC steps on
a synthetic session, firmware builds without warnings). **Nothing has yet run on an ESP32 or a real RIGOL, and the IDE
route has not been run in Arduino IDE.** The self-test and chain test are the first execution. See
`AUDIT_PHASE2.md` for the status of every audit finding.

Older guides (`GUIDE.md`, `SETUP_GUIDE.md`, `README.md`, `ea_energija/README.md`) are marked superseded; their
hardware descriptions still apply.
