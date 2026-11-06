# ROSETTA FX: new effects on the PRO-E's reverb chip (IC13 + IC28)

The PRO-E voice board (CK-34, MT-32 / CM-32L hardware) has a Boss reverb DSP, **HG61H20R36F**, that runs a program
from the IC13 ROM. Rosetta FX replaces those programs: Juno chorus, delay, lo-fi, drive and flanger, next to Roland's
plate. IC28 (the voice CPU's firmware) moves the chorus and unlocks all 8 effect slots. Everything here is
**measured on a real PRO-E** through an audio interface (`tools/proe_link.py`), not only in the emulator.

## The chip

- Fixed-sequence DSP: every sample (32 kHz) it runs one 256-byte program = 64 steps × 4 bytes, with 16K words of delay
  RAM. Program = mode × 16 + level × 2 + (time >> 2); `time & 3` gates the adds, so one program holds 4 coefficient sets.
- Format from Sergey V. Mikayev's interpreter (LGPL-2.1+, via gearmulator). Ported to `boss_reverb.py` (LGPL-2.1+).
- **No LFO and no delay modulation.** A delay only moves when the voice CPU switches programs.

### What the real chip does differently (measured 2026-11-06, 12 single-operation tests)

| | Emulator said | Her chip does |
|---|---|---|
| invert bit (b1/b3 bit 3) on its own | inverts the accumulator | **nothing**, in either half-step |
| invert bit in a half-step whose add fires | add, then invert | add, then invert ✓ |
| plain adds, doubling, same-frame write-then-read | ✓ | ✓ |

So every filter built on the "invert alone" trick squealed (full-scale 16 kHz) or got stuck. `boss_reverb.py` now
follows the hardware and reproduces every test. Rule for new programs: **write filters with adds only**,
z = (1 − a)·z + a·x (`gen_fx.tone_pole`). Other measured facts:
- The effect output is in phase with the dry sound and arrives **one sample later**.
- On the PRO-E, the chip's "R" output (latched before step 47) comes out of the **L** jack.
- The effect send is on/off per part (MT-32 reverb switch). Clearing routing bit 4 does not give wet-only: it turns the
  whole part down about 26 dB. Wet-only by phase cancelling gets −20 dB below 1 kHz only, so it isn't used.

## IC13 layout (`gen_fx.py`)

| Mode | Effect | TIME / LEVEL |
|---|---|---|
| 0 | REVERB = Roland's plate programs (copied from your own IC13 dump at build time) | stock |
| 1 | Juno chorus, 64 positions (fallback; IC28 plays mode 6/7 instead) | |
| 2 | DELAY: mono, 2-tap-average feedback, R 7 ms later | 16 times 40-495 ms, feedback 0 / 38 / 63 / 75 % |
| 3 | LO-FI: tone filter + bit crush (+ drive into the clamp) | 16 crush steps, TONE open … dull |
| 4 | FLANGER: comb 0.25-4 ms, feedback 0.75 | moved by IC28 |
| 5 | DRIVE: tone filter + gain into the clamp, back down to about the dry level | 16 gain steps |
| 6 + 7 | **JUNO CHORUS B**: 2-pole low-pass line, 128 positions (1.7-5.3 ms), L and R sweep opposite | moved by IC28 |

Time 0 + level 0 (REVERB OFF) is silent in every mode. IC13 is a 27C256-pinout socket; burn a W27C512 with the 32 KB
image twice (`IC13_fx_W27C512.bin`), so the extra address pin doesn't matter.

## IC28: moving chorus (`build_ck34_lab.py`)

- The voice CPU's idle loop runs a **stepper** every ≥ 1 ms: a triangle LFO (TIME = rate 0.25-6 Hz, LEVEL = depth)
  picks the chorus position and writes it to the effect latches.
- **Snake order:** positions are laid out so every step changes **one latch byte only**. With plain binary order the
  two writes left the chip on a wrong position for an instant at every 16-step boundary = clicks.
- **128 positions:** chorus B uses mode bit 0 as a third row bit (the same latch byte), so its steps are half the
  size of the 64-position chorus: 5.4 dB less zipper on her (5.6 dB in the emulator). The panel's JUNO CHORUS
  (mode 1) plays chorus B; leaving the chorus gives the stock settings back.
- Also in this build: reverb mode clamp 3 → 7 (all 8 slots), part reverb switch clamp 1 → 7, and the live filter
  (cutoff/resonance changes reach held notes). `test_ck34_lab.py` (34 checks) and `test_ck34_live.py` run it in an
  8096 simulator.

## Tools

| File | What |
|---|---|
| `gen_fx.py` | builds IC13 (needs your stock IC13 dump for the plate), checks OFF is silent, renders previews |
| `gen_chorus.py` | chorus delays, snake order, test signals |
| `boss_reverb.py` | the chip in Python (hardware-corrected invert rule) |
| `build_ck34_lab.py` | builds IC28 from your dump: live filter + stepper + clamps |
| `../tools/proe_link.py` | MIDI remote + Focusrite recording: `lab`, `lab3`, `flip` (A/B two choruses while you play) |
| `../tools/rec_session.py` | record a jam to `build/lab/sessions/` |

Next: an LFO block in IC28 (PWM, LFO → filter, delayed vibrato), then a D-50 style chorus + reverb program.
