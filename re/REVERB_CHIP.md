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
| 0 | **RESONANT FILTER**: Chamberlin state-variable filter, 2 passes per sample (64 kHz), adds only | TIME = cutoff 110 Hz-7 kHz (16 steps), LEVEL = LP / LP RES / BP / BP RES (Q 1.9 / 10.7) |
| 1 | HALL = Roland's own programs (copied from your IC13 dump at build time), output +6 dB | stock |
| 2 | DELAY: mono, 2-tap-average feedback, R 7 ms later | 16 times 40-495 ms, feedback 0 / 38 / 63 / 75 % |
| 3 | LO-FI (levels 0-3): tone filter + bit crush; DRIVE (levels 4-7): gain into the clamp | TONE = time & 3 |
| 4 | FLANGER: comb 0.25-4 ms, feedback 0.75, smoothed | moved by IC28 |
| 5 | **JUNO + REVERB** (D-50 style): Juno chorus into a reverb | moved by IC28 |
| 6 + 7 | **JUNO CHORUS B**: 2-pole low-pass line, 128 positions (1.7-5.3 ms), L and R sweep opposite, 2-pole smoothing after the taps | moved by IC28 |

All new outputs are ×1.25 (+2 dB), the same on both sides.

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
- **Full Juno depth:** the panel's Juno I and II (LEVEL 4-7) sweep the whole Juno-60 range, 1.7-5.3 ms, at
  0.513 / 0.863 Hz (Juno-60 figures from pendragon-andyh's Juno60 analysis).
- **Fizz = ticks, not clipping (measured):** same notes at velocity 30-127, chorus frozen vs moving. Frozen is as
  clean as dry even at 127; moving makes a short tick at each position step, a fixed share of the signal, so it
  shows when you play loud. Two gentle low-pass poles *after* the taps (`gen_fx.pole_chain`) smooth each step:
  a loud chord went from 42 ticks to none. Loud high single notes still tick a little (next: 256 positions).
- Also in this build: reverb mode clamp 3 → 7 (all 8 slots), part reverb switch clamp 1 → 7, and the live filter
  (cutoff/resonance changes reach held notes). `test_ck34_lab.py` (34 checks) and `test_ck34_live.py` run it in an
  8096 simulator.

## Resonant filter (mode 0, `gen_filter.py`)

- hp = x − lp − q·bp, bp += f·hp, lp += f·bp, run twice per sample. The chip has no subtract, so −(lp + q·bp) is
  one add chain followed by the invert (the hardware rule above), then + x.
- **Every program in the block has the same step layout**, only the coefficients differ. The voice CPU switches
  programs mid-frame when you turn the cutoff; with different layouts half a frame of one program met half of
  another and spiked. `block()` asserts it.
- It filters whatever goes into the effect, so PCM samples get a resonant filter too: something the LA chip's own
  filter never does (it only works on the synth partials).
- IC7: LIVE FILTER page has FX CUTOFF / FX RESO, and **BENDER** = PITCH / CUTOFF / RESO. In CUTOFF mode the
  bender moves the cutoff ±8 steps around the knob (dead zone in the middle); in RESO mode up = more resonance,
  down = less. The bender's pitch is muted while it drives the filter.

## Wet-only mod (R27 + R31)

The CK-34 (service notes p.16) mixes three demux slots into each jack: SYN1 (dry of parts with the effect on), SYN2
(dry of parts with it off) and REV. Software can't give wet-only (above). Cutting **R27** (SYN1 → L) and **R31**
(SYN1 → R) removes the dry copy of every part that has the effect on: those parts are heard only through the effect.
Found with `tools/routing_scan.py` (no scope). Don't cut R29/R30: that silences the parts with the effect off.

- IC28 v7 (`DRYOFF`): with REVERB OFF (time 0 + level 0) every part is routed to SYN2, so turning the effect off
  plays everything dry, as before the mod.
- The cut SYN1 dry signal is still on IC18 pin 1 / IC2 pin 7: a pair of free outputs (`tools/outs_test.py`, being tested).

## IC28: PWM LFO (v8)

LIVECUT (called for each partial) now ends in `PWMLFO`: for a pulse partial whose PCM-number byte is $71-$7A
(set by the IC7 PWM knob, depth 1-10) it runs a triangle LFO on a 32-bit phase from timer1, speed = the tone's LFO
RATE, and writes the LA chip's pulse-width register (0x0C40 + 2p) between the tone's own width and 255. v8.1 keeps
the phase fraction (v8 dropped it and ran slower than the rate said). `test_ck34_lab.py` checks the sweep, the
clamp, the off cases and the exact phase sum.

## Tools

| File | What |
|---|---|
| `gen_fx.py` | builds IC13 (needs your stock IC13 dump for the hall), checks OFF is silent, renders previews |
| `gen_filter.py` | the resonant filter programs (mode 0) |
| `gen_chorus.py` | chorus delays, snake order, test signals |
| `boss_reverb.py` | the chip in Python (hardware-corrected invert rule) |
| `build_ck34_lab.py` | builds IC28 from your dump: live filter, stepper, clamps, DRYOFF, PWM LFO |
| `../tools/routing_scan.py` | which routing entry gives wet / dry (found the R27/R31 mod) |
| `../tools/juno_patch.py` | loads Juno patches over MIDI (`brass`, `pad`, `pwm`, `strings`) |
| `../tools/proe_link.py` | MIDI remote + Focusrite recording: `lab`, `lab3`, `flip` (A/B two choruses while you play) |
| `../tools/rec_session.py` | record a jam to `build/lab/sessions/` |

Next: LFO → filter and delayed vibrato in IC28, the mod wheel as a second filter axis.
