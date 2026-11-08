# Rosetta Wave PRO-E

The D-110 Rosetta ROM Studio, ported to the PRO-E's CK-34 voice board (CM-32L hardware). Same codec, same table format.

| | D-110 | PRO-E |
|---|---|---|
| wave chips | IC8 (lower) + IC7 (upper) | **IC37** R15449121 (lower, MT-32 set) + **IC38** R15179945 (upper, CM-32L effects) |
| wave table | IC12 0x900 | **IC28** 0x8100 (256 x 4, same struct) |
| tones | IC12 | IC28: 128 presets (A 0x8000 / B 0x8080) = the PRO-E tone list (IC7 bank 0 0x24D9), rhythm 0x8500 / 0x8580 |
| wave names | IC12 0x100 | none in ROM: named after the first PRO-E tone / rhythm sound that plays it (project only) |

- `run_wave_studio.bat` or `pythonw rosetta_wave_proe.pyw`. Reads `../dumps/` (IC37, IC38, IC28, and IC7 for the tone names).
- Same-slot swap = new IC37 / IC38 only (W27C040 drop-ins). Root note, loop, bigger slots = IC28 table edits too; `report.txt` says which.
- `rosetta_wave_proe.pyw` is generated: `python -I port_from_d110.py rosetta_studio.pyw rosetta_wave_proe.pyw` (rosetta_studio.pyw = copy of the D-110 studio v0.4).
  `proe_profile.py` = the PRO-E specifics (table, tone usage, names). `test_proe_wave.py` = 18 checks on the real dumps.
- The stock CK-34 table has 4 entries not aligned to their own length (#252-255), so alignment is only required of entries the studio moves.
- Hardware-untested. IC28 burning needs a check of its socket pinout first (28-pin, pin 20 = enable, pin 22 ignored on read).
