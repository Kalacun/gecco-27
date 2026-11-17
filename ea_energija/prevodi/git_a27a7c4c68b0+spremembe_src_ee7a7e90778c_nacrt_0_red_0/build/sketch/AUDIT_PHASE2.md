#line 1 "/Users/aleks/gecco2027-electricity/ea_energija/AUDIT_PHASE2.md"
# Audit, Phase 2: what was fixed, what was left, and why

Branch `audit/phase2`, baseline commit `4d7c5cc`. The Phase 1 report (findings C1–C5, M1–M19,
N1–N12) is the reference for the ids below. How to run everything: `LAB_GUIDE.md`.

**Verification status.** Every fix is verified by unit tests on a computer (74 tests of the PC
scripts, 3 of the recovery tool, 31 of the algorithm core compiled from the same header as the
firmware) and by firmware builds without warnings. **No fix has been run on an ESP32 or
against a real RIGOL DP821A.** The self-test and the chain test in the lab (LAB_GUIDE steps C
and D) are the first execution on hardware.

## Critical findings

| Id | Finding | Status | Commit | Remark |
|---|---|---|---|---|
| C1 | Unshifted objectives, optimum at the centre | Fixed | `a4daad6` | Seeded shift table in flash, 20–80 % of the half-range, generator script committed |
| C2 | Windows and records re-paired silently | Fixed | `685d11c`, `22e6e7e` | Any mismatch stops the analysis; pause between windows also checked |
| C3 | Budget check and checkpoints per generation | Fixed | `d3e40ea` | One compare per evaluation for all algorithms; clock every 16 evaluations in TIME mode. Its cost on the chip is measured by the self-test |
| C4 | Target below single-precision accuracy | Fixed, with a declared limitation | `d3e40ea`, `a4daad6`, `201de19` | Ladder 1e1…1e-4. Rastrigin error is 1.9e-5 (D = 10) and 5.8e-5 (D = 20); 1e-4 on Rastrigin is recorded, flagged and not tested (authors' decision) |
| C5 | Success-only means, no ERT | Fixed | `6543ea3`, `22e6e7e` | ERT per target in FE, J and s |

## Major findings

| Id | Finding | Status | Commit | Remark |
|---|---|---|---|---|
| M1 | Generator period shorter than a session; seed not stored | Fixed | `8306b25` | xoshiro128++; rule documented, seed in every record |
| M2 | Reset erased all records and restarted | Fixed | `201de19` | Session becomes "prekinjen"; records kept; reset reason stored |
| M3 | No FE mode | Fixed | `d3e40ea` | FE and TIME rows in one binary |
| M4 | No E2 estimator | Fixed | `9fa4997` | E2 primary, E1 cross-check, flag |
| M5 | Record without version, checksum, build id, CPU frequency, timers, reset reason | Fixed | `d3e40ea`, `201de19` | 488-byte record, CRC32 verified at dump |
| M6 | Build not reproducible, id was a timestamp, warnings off | Fixed | `fc72391` | `prevedi.py`; build id from git revision and source hash. Images of the same source differ only in the embedded ELF hash and image checksum |
| M7 | Flash writes unchecked, full behaviour undefined | Fixed | `201de19` | Space checked before the session; failed append stops with records kept |
| M8 | CPU frequency not read back; sleep unchecked | Fixed | `201de19` | Both stored per record and checked by the analysis |
| M9 | Limit 0.3 A; CV/CC not recorded | Fixed | `6963fae`, `27e57b2` | 0.5 A enforced; mode every 10 s plus per-sample voltage check |
| M10 | Raw files overwritten | Fixed | `6963fae`, `22e6e7e` | Exclusive creation everywhere |
| M11 | Settings not read back; errors swallowed | Fixed | `6963fae` | Read-back compared before output-on; error queue read |
| M12 | Gaps, timestamps, jitter | Fixed | `6963fae` | Both stamps stored; gaps logged; jitter reported |
| M13 | Thresholds hard-coded; exclusions without reason | Fixed | `aba0864`, `2ac4990` | One config file copied to results; `izlocitve.csv` |
| M14 | Statistics depended on installed packages | Fixed | `f820abb` | One procedure, standard library only |
| M15 | No tests | Mostly fixed | several | J9, K1 (tool), K3, K4 done. **K2 left**, see below |
| M16 | L-SHADE schedule one generation late | Fixed | `d3e40ea` | A mutation test proves the check detects the old behaviour |
| M17 | L-SHADE NP_init capped | Fixed | `b73058a` | 18 D; allocation failure stops |
| M18 | Plan parsed from a local sketch; duplicated firmware; stale code in README | Fixed, README appendix left | `71dd758`, `266e9a0` | The old README still contains the stale code appendix; it is marked superseded, not rewritten |
| M19 | Heap and stack headroom unknown | Fixed in code, value pending | `201de19` | Free heap and stack mark are in every record; read them after the chain test |

## Minor findings

| Id | Finding | Status | Remark |
|---|---|---|---|
| N1 | Cauchy edge case at rnd() = 0 (probability 2^-24 per draw) | Left | Changing it changes L-SHADE's random stream for no measurable effect; documented |
| N2 | 32-bit timer values | Fixed (`d3e40ea`) | 64-bit `esp_timer_get_time()`; start and end stored |
| N3 | DE path stores unused F and CR | Left | Report only; a change for one algorithm would itself be a bias |
| N4 | L-SHADE archive copy and linear worst search | Left | Report only, same reason |
| N5 | Float division and square root are library calls | Left | Inherent to L-SHADE; the self-test timings quantify evaluation cost |
| N6 | `disableCore1WDT()` without effect | Left, commented | Harmless; the comment states why |
| N7 | Unused pins undefined | Fixed (`201de19`) | Inputs with pull-down on general-purpose pins; effect on the baseline unverified |
| N8 | Block-order generator | Fixed (`502e2c1`) | Documented, tested, both orders |
| N9 | Readings re-serialised | Fixed (`6963fae`) | Strings stored as received |
| N10 | Stray files, stale guides | Partly | Guides marked superseded; `main.py`, `test_rigol.py`, `Read_Voltage.py` left in place (not mine to delete; they are not part of the pipeline) |
| N11 | Host and device cannot match bit for bit | Addressed | Stated in the comparison tool's acceptance rule |
| N12 | Analysis overwrote earlier results | Fixed (`aba0864`) | New folder per analysis |

## Left open, and why

* **K2, comparison with published results.** The host tests check that jDE and L-SHADE reach
  1e-2 on both shifted functions at D = 10 in 300000 evaluations, which is a sanity check, not
  a comparison with published numbers. A proper check needs reference results for these exact
  shifted functions or a trusted reference implementation run on them; neither is in the
  repository. Not done.
* **Paper wording.** The algorithm tables in the Phase 1 report were written without opening
  the three papers. The selection rule of Storn and Price (1997) and bound handling in jDE
  should be checked against the PDFs.
* **Instrument specifications.** Read-back resolution, accuracy and update rate of the DP821A
  on the 60 V / 1 A channel were not found in a source I could read. The SCPI syntax was checked
  against the DP800 Programming Guide of March 2013, which predates the DP821A.
* **Old root README.** Its 2000 lines include an obsolete copy of the code. It carries a
  "superseded" notice; rewriting it is left to the authors.

## Decisions taken by the authors during Phase 2 (2026-11-16)

Bring the code to the project decisions; xoshiro128++; bound handling stays per algorithm
(random re-initialisation for DE and jDE, midpoint for L-SHADE); no anchor algorithm and no cost
multiplier; warm-up runs kept and flagged; WiFi upload removed; shift vectors from a seeded
table (20–80 % of the half-range); FE_max = 10000 × D; T per cell from the chain test; block
order random with 25 blocks by default, balanced with 30 available; the 1e-4 target on
Rastrigin recorded and flagged but not tested.

## Still to be decided by the authors

* The four T values (after the chain test) and the analysis thresholds in
  `analiza_nastavitve.json` (my defaults are marked in LAB_GUIDE step E).
* Whether FE_max = 10000 × D gives windows long enough at D = 10 for the supply's sampling rate.
* The block order must be fixed before the campaign. Choosing between the two designs after
  seeing results would be a forking-paths problem a reviewer can raise.

## Deviations from the published algorithms that remain

* L-SHADE in TIME mode reduces the population on elapsed time (t/T) instead of evaluations.
* DE and jDE re-initialise out-of-bounds components at random (author choice; the papers leave
  it open as far as I know).
* Crossover uses `rnd() < CR` (strict); the difference from `<=` has probability 2^-24.

## Data produced before the audit

`meritve_test_veriga/esp32.txt` and anything still stored on the board come from the audited
firmware: unshifted functions, a 1e-6 target below evaluation accuracy, a capped L-SHADE
population at D = 50, and a session that was restarted six times. They are an archive, not
results. `stari_zapisi.py` recovers what is on the board (LAB_GUIDE step A).
