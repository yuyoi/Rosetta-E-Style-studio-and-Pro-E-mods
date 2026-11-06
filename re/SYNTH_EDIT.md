# SYNTH EDIT (Rosetta OS PRO-E v0.7 "JUNO FX"): Juno mode and effects on the PRO-E's own panel

Works on hardware. Needs the [pin-31 mod](../docs/PIN31_MOD.md): the code lives in the upper half of IC7.
The voice-board side (live filter, moving chorus) needs the IC28 build, the effects need the IC13 build: see
[REVERB_CHIP.md](REVERB_CHIP.md).

## Using it

| Control | Does |
|---|---|
| **CURSOR** (main screen) | opens SYNTH EDIT. Inside the stock menus CURSOR still does its normal job |
| **TEMPO dial** | scrolls the page list, or changes the value while editing (lists move one entry per click) |
| **CURSOR** | one level in: page list → parameter list → edit (`>` in front of the value) |
| **PARAMETER** | one level back, and out of SYNTH EDIT from the page list |
| **BANK 1-8** | jump straight to page 1-8 |

Line 1 = page and part (`FILTER      SOLO`), line 2 = parameter and value (`CUTOFF   >    64`).
On opening, it reads the part's tone back from the voice board (MT-32 RQ1), so the values are the real ones. If the
board doesn't answer, line 1 says `NO REPLY` and you edit a built-in fallback tone.

## Pages (19)

| # | Page | Parameters |
|---|---|---|
| 1 | **JUNO** | MAKE JUNO, SAW, PULSE, PULSE W, SUB OSC, DETUNE, RANGE |
| 2 | FILTER | CUTOFF, RESO, ENV AMT, KEY TRACK, VELOCITY |
| 3 | ENVELOPE | ATTACK, DECAY, SUSTAIN, RELEASE (one envelope on amp + filter) |
| 4 | PITCH ENV | AMOUNT, TIME, DEPTH, VELOCITY |
| 5 | LFO | RATE, DEPTH, MOD WHEEL |
| 6 | VOICE | STRUCT 1-2 / 3-4, RING 1-2 / 3-4, LEVEL P1-P4 |
| 7 | PCM WAVE | WAVE |
| 8 | LIVE FILTER | CUTOFF, RESO (acts on held notes with the IC28 build) |
| 9 | SYNTH OSC | WAVE, PULSE W, PW VELO |
| 10 | PITCH | TUNE, FINE, KEY FOLLOW, BENDER |
| 11 | AMP | LEVEL, VELOCITY |
| 12 | PART | SOLO / LOWER / MANUAL BASS |
| 13 | REVERB | TIME, LEVEL (Roland's plate) |
| 14 | JUNO CHORUS | RATE, DEPTH |
| 15 | DELAY | TIME (40-495 ms), FEEDBACK |
| 16 | LO-FI | CRUSH (16 bit … 8 bit, with or without drive), TONE |
| 17 | FLANGER | RATE, DEPTH |
| 18 | DRIVE | GAIN, TONE |
| 19 | FX ROUTING | PART FX (DRY / DRY+FX) for the part, or ALL PARTS |

### JUNO mode
**MAKE JUNO** turns the tone into a Juno-style voice: partial 1 = saw, 2 = pulse, 3 = sub oscillator (square, one octave
down), 4 = a second saw detuned 8 cents, all synth partials through one filter and one envelope. It starts with only the
saw on; dial the others up. Then the page works like a Juno panel:
SAW / PULSE / SUB OSC levels, PULSE W (square or a fixed duty in %), DETUNE (spread in cents) and RANGE (16' … 2').
The LA chip always had these parts; Roland's interface just never put them on a front panel.

### Effects
The effect pages pick and edit what the voice board's effects chip plays (one effect for the whole synth, like stock).
Any edit sends the effect setting, so the effect you edit is the one you hear. FX ROUTING sets which parts go into it:
keep the drums DRY and put the synth on DRY+FX. The PRO-E's own reverb type list is renamed to match:
Plate 1/2, Juno I/II, Delay 1/2, Lo-Fi 1/2. (FXONLY / TEST 3 in the routing list are experiments: wet-only does not work
this way, see REVERB_CHIP.md.)

## Remote control over MIDI (v0.7)

`tools/proe_link.py` drives her from a PC through any MIDI interface: press panel keys, turn the dial, read the LCD and
LEDs, peek/poke RAM, send raw SysEx to the voice board, record her through an audio interface.
Protocol: `F0 7D 52 00 00 cmd args F7` (7D = non-commercial ID). The `00` guard byte keeps her own Roland SysEx parser
from reading our commands as data requests/writes. Replies come back on MIDI OUT.

| cmd | does |
|---|---|
| 01 kk / 02 kk | press / release panel key kk |
| 03 dd | dial dd - 64 steps |
| 10 / 11 | screen (32 chars) / LED bytes |
| 12 aaaa n / 13 aaaa vv | peek n bytes / poke one byte (below $4000) |
| 20 bytes | raw bytes to the voice board |
| 7F | ping, answers "RO07" |

## How it's built

| File | What |
|---|---|
| `build_v07.py` | the menu as data (`PAGES`, `ITEMS`, `LISTS`). Builds IC7 + IC4 from your ROM Studio build |
| `synth_v07.asm`, `synth_v07_fx.asm`, `synth_v07_ram.asm` | menu engine, JUNO page, FX pages, remote control (68HC11) |
| `test_synth_v07.py` | 505 simulator checks (`test_synth_v06.py` 308, `v05` 204 still pass) |
| `hc11asm.py` / `hc11sim.py` | assembler (opcode table from capstone) and a small simulator |

Hooks in the stock code (each one checks the original bytes first): IC7 bank 0 `$4CF7`/`$4D01` key dispatch → RAMKEY,
IC4 `$FA7B` page-$0D tick → RAMTICK, IC4 `$E625` → BOOTCOPY, MIDI IN `$9703`/`$9745` → the remote parser.
The voice-board clamp table is read from your IC28 dump at build time.

Older builds (v0.4b … v0.6) stay in the repo; each later one keeps the earlier tests passing.
