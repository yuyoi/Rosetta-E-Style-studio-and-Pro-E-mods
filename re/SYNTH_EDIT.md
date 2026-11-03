# SYNTH EDIT (Rosetta OS PRO-E v0.4d): tone editing on the PRO-E's own panel

Works on hardware. Needs the [pin-31 mod](../docs/PIN31_MOD.md): the code lives in the upper half of IC7.

## Using it

| Control | Does |
|---|---|
| **CURSOR** (main screen) | opens SYNTH EDIT. Inside the stock menus CURSOR still does its normal job |
| **TEMPO dial** | scrolls the list, or changes the value while editing |
| **CURSOR** | one level in: page list → parameter list → edit (`>` in front of the value) |
| **PARAMETER** | one level back, and out of SYNTH EDIT from the page list |
| **BANK 1-8** | jump straight to page 1-8 |

Line 1 = page and part (`FILTER      SOLO`), line 2 = parameter and value (`CUTOFF   >    64`).
On opening, it reads the part's tone back from the CK-34 (MT-32 RQ1), so the values are the real ones. If the CK-34
doesn't answer, line 1 says `NO REPLY` and you edit a built-in fallback tone.

## Pages (Juno-style macros, not raw LA parameters)

| BANK | Page | Parameters |
|---|---|---|
| 1 | PCM WAVE | WAVE (bank 1/2 + number, PCM partials) |
| 2 | SYNTH OSC | WAVE (SQUARE / SAW), PULSE W, PW VELO |
| 3 | PITCH | TUNE, FINE, KEY FOLLW, BENDER |
| 4 | FILTER | CUTOFF, RESO, ENV AMT, KEY TRACK, VELOCITY |
| 5 | ENVELOPE | ATTACK, DECAY, SUSTAIN, RELEASE: one envelope drives both TVA and TVF |
| 6 | AMP | LEVEL, VELOCITY |
| 7 | LFO | RATE, DEPTH, MOD WHEEL |
| 8 | LIVE FILTER | opens straight into editing CUTOFF / RESO |
| 9 | PART | SOLO / LOWER / MANUAL BASS (dial only) |

Each macro acts on all active partials of the tone. Most of them move every partial by the same step, so the tone's own
balance stays (and stops at the CK-34's limits). Wave choices and switches set one value on all of them. Every change goes
out as one MT-32 DT1 per changed byte, so you hear it right away.

## How it's built

| File | What |
|---|---|
| `build_v04b.py` | the menu as data (`PAGES`, `ITEMS`, `LISTS`), like the D-70 Rosetta OS. Builds IC7 + IC4 from your ROM Studio build |
| `synth_v04b.asm` | the menu engine, RQ1 readback, DT1 sender (68HC11, upper half bank 5 `$A000`) |
| `synth_v04b_ram.asm` | RAM trampoline at `$2DA6`: far call = bank 5 + PA6 high, back to PA6 low |
| `hc11asm.py` / `hc11sim.py` | assembler (opcode table from capstone) and a small simulator |
| `test_synth_v04b.py` | 130 simulator checks: boot copy, keys, readback, menus, every SysEx byte, banking |

Hooks in the stock code (each one checks the original bytes first): IC7 bank 0 `$4CF7`/`$4D01` key dispatch → RAMKEY,
IC4 `$FA7B` page-$0D tick → RAMTICK, IC4 `$E625` → BOOTCOPY at `$FFB1` (the trampoline copy + a "SYNTH READY" splash).
The CK-34 timbre clamp table is read from your IC28 dump at build time.

Next: a couple of save slots on the WRITE key, then a CK-34 firmware rewrite so the voice side fits the Juno-style controls.
