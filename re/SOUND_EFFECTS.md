# PRO-E SOUND EFFECTS: how the pads make sound (traced 2026-11-03, `sfx_map.py`, full table in `sfx_map.txt`)

**Pad -> sequence -> rhythm part -> PCM wave.** The pads do not play one long sample: each one starts a little
**sequence** of rhythm notes, and the long effects are short PCM loops kept running by that sequence.

| Step | Where | What happens |
|---|---|---|
| 1. pad press | IC7 bank 0 `$7095` | pads a-l (key codes `$48-$4D`, `$50-$55`) = pad 0-11. Note = RAM `$240D[pad]` (battery RAM; hold a keyboard key + press a pad = store that key's note on the pad). Only when key mode SOUND EFFECTS (`$0E.2`) is lit |
| 2. voice | `$407A` | 4 SFX voices (`$3E+v` note, `$42+v` flags). Note >= 109 = stop all. Note 76-108 = one of **33 SFX sequences** |
| 3. sequence | table bank 0 `$BFA1` (pointer per note) + `$BFEB` (bank nibble) | all 33 live in **IC7 bank 4 `$52E1-$56D0`**, in the **same event format as the styles** (rosetta_style.decode_events). END loops back to the start, so an effect runs until it's released / stopped |
| 4. player | IC4 `$C612-$C719` (tick) | steps each voice; event field + 60 = rhythm key, velocity nibble via `$ED5A`; monophonic per voice |
| 5. send | IC4 `$EC7A` | note-on **`$99` = CK-34 channel 10, the rhythm part**, velocity scaled by the SOUND EFFECTS volume `$2405`. Copy to MIDI OUT on the EFFECT channel (`$2447`, `$EBEA`). Song recorder track 5 (`$D7F1`) |
| 6. CK-34 | IC28 rhythm setup `0x8580` (keys 24-108) -> R timbre map `0x8500` -> partial PCM wave -> table `0x8100` | e.g. key 76 Laughing, 84 Door, 87 Engine, 88 Car-stop, 91 Siren, 92 Train, 93 Jet, 94 Helicopter, 95 Starship, 96 Pistol (IC38), plus bongos/congas/timbales 60-68 (IC37) |

**Wave lengths:** the longest SFX waves are 16 K samples (0.51 s: Laughing one-shot; Train / Jet / Helicopter loops).
In the whole table the longest one-shot is 16 K samples, the longest loop 32 K (1.02 s). The table's length field goes up
to 0x800 << 7 = 256 K samples (8.2 s) and the CK-34 passes it straight to the LA32 (`0x0D01`), the same field the D-110
long-sample test bank (Rosetta v13) uses. So longer waves should work here too, but stock never uses them: not yet
heard on the PRO-E.

**For custom sounds:** an SFX pad can be retargeted three ways: a new sequence (IC7, style format: our encoder already
writes it), a new rhythm-key timbre (IC28), or a new wave in IC38 at the same slot (in-place swap, no IC28 change).
The 12 factory pad notes are battery RAM (`$240D`), not ROM; pressing a pad sends its note on MIDI OUT (EFFECT channel),
which is the easy way to read them.
