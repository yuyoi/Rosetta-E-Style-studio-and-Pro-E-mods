# B3: CK-34 sound engine and data tables (IC28 "CK-34 v2.06 89-02-28", 8098 + LA32)

Source: `dumps/ck34_ic28_control_R15179974_CK-34_v2.06.bin` (SHA1 D80449D4...6551). Listing: `re/fw_map/ck34_ic28.lst`
(`mcs96_dis.py`, D-110 labels: `REV_LATCH_A` = 0x0400, `REV_LATCH_B` = 0x0800, `BTN_SC0` = 0x021A). Addresses are CPU addresses.
File offset = CPU address for 0x1000-0x7FFF; window 0x8000-0xBFFF shows file `page*0x4000` (page 2 = file 0x8000, page 3 = file 0xC000).
**C** = seen in code/data, **I** = inferred. Munt = mt32emu sources (Tables/TVA/TVF/TVP/Partial/PartialManager.cpp, read 2026-11-03).
Core, interrupts, monitor: see B1. MIDI parser and SysEx: see B2. This file: what happens from note-on to the LA32 pins.

## TL;DR
- **The CK-34 runs the CM-32L/LAPC-I sound engine**, unchanged in structure. Every ROM table I checked matches Munt's
  formulas or Munt's CM-32L map byte for byte. Munt can be used as the reference for this code. **C**
- **The data layout of the upper 32 KB is the CM-32L one:** timbre A map 0x8000, B map 0x8080, PCM table 0x8100 (256 x 4),
  rhythm timbre map 0x8500, rhythm setup 0x8580. **C**
- **PCM table:** entries 0-127 are **byte-identical to the MT-32 1.07 table** (128/128, compared with the owner's
  ic26/ic27 dumps). Entries 128-255 are the CM-32L extra set, mostly in IC38. **C**
- **Correction to WAVE_FORMAT.md:** len bit 0 = 1 means the wave **ignores** master tune (0x2CB4). **C**
- **128 preset timbres:** 122/128 are identical to the MT-32 1.07 presets. The other 6 differ only in small level/velocity
  tweaks. The order is the Pro-E tone list (IC7 0x24D9, 12-byte names, 118/128 names match). **C** (order match: I)
- **LA32 = 0x0C00-0x0DFF, 32 partials, register = base + 2*partial.** **C**
  - 0x0C00/01 = ramp A: TVF cutoff for synth, **TVA amplitude for PCM**.
  - 0x0C40 = pulse width. 0x0C41 = TVF base cutoff (synth) or PCM start page (PCM).
  - 0x0C80/81 = ramp B: TVA amplitude for synth.
  - 0x0CC0 = pitch word, 4096 per octave, 0xB000 = 1 kHz; writing it = key-on, 0xFFxx = off.
  - 0x0D00 = control byte (PCM, SAW, ring mod, reverb-off, 3-bit pan). 0x0D01 = resonance, or PCM length/loop byte.
- **EXTINT (0x2F2D)** reads the status at 0x0C00 and steps the TVA/TVF envelope phases. It frees partials at the end of
  the release and when a PCM one-shot ends. **C**
- **Pitch envelope, LFO, bend and master tune are done in software.** The idle loop (0x2AE2) handles one partial per
  pass and writes 0x0CC0. **C**
- **Reverb control:** **C**
  - mode bit 0 -> latch 0x0800 bit 2; mode bits 1-3 -> system latch bits 1-3 (shadow `rc8`, written to 0x021A)
  - time 0-7 -> 0x0400 bits 0-2
  - level 0-7 -> 0x0400 bit 3 + 0x0800 bits 0-1
  - per partial: LA32 control bit 3 = 1 means no reverb send
- **Master volume = 8098 PWM** (table 0x3D13 -> PWM_CONTROL), plus only a 0-8 digital trim (LAPC-I table 0x3CAE). **C**
- **Master tune:** `(mt-64)*171>>6` -> 0xF4A0. As in Munt, the boot code leaves it at 0, so 440 Hz even though mt = 0x4A. **C**

---

## 1. Where the sound data lives in IC28

### 1a. Upper half (banked, read with bank 2/3 at 0x0100)
| CPU/file | Size | What | Reader (code) | Status |
|---|---|---|---|---|
| 0x8000 | 64 x LE word | timbre **A** map: ptr -> bank `2+(ptr>>14)`, CPU `0x8000+(ptr&0x3FFF)` (= file 0x8000+ptr) | 0x4E84 + sub_4EEA 0x4EEA | C |
| 0x8080 | 64 x word | timbre **B** map, same format (timbres 64-127) | 0x4E6E-0x4E84 (index 0x40\|n) | C |
| 0x8100 | 256 x 4 | **PCM wave table** (sec. 2) | 0x34DF, 0x363B | C |
| 0x8500 | 64 x word | rhythm timbre map **R00-R63**: CPU address in bank 2, bit 14 = bank 3 | 0x26A3, 0x4E14 | C |
| 0x8580 | 85 x 4 | rhythm setup, keys 24-108: timbre (0x40+n = Rn), level, pan, reverb switch. Copied to RAM 0xE090 at boot | sub_50FD 0x50FD | C |
| 0x86D4-0x89FF | 812 B | FF. Contains the **0x8700 "group 5" map** (16 words) and the **0x8800 demo patch table** (8 B x 64). Both are empty in the CK-34 | 0x262A, 0x4DE5, 0x5DEB | C |
| 0x8A00-0xA8AF | | 64 rhythm timbres (Acou BD ... Babble, R63 "OFF") | via 0x8500 | C |
| 0xB000-0xFE29 | | 128 preset timbres (AcouPiano1 0xB000 ... JungleTune 0xFD34), compressed | via 0x8000/0x8080 | C |

- **Timbre format** (copier sub_4EBF/sub_4ECD, 0x4E89-0x4EB9) = Munt `initCompressedTimbre`. **C**
  - A 14-byte common block comes first. Then a 58-byte block follows only for partials whose mute bit is set; a muted
    partial re-reads the previous block (`sub r78, #0x3a`).
  - Every byte is clamped against the max tables at 0x4873 (common) and 0x4881 (partial) while it is copied into the
    part's timbre temp.
- **Timbre fetch by group** (sub_4D9C 0x4D9C, jump table 0x4DBE, index = patchTemp timbreGroup 0xE000[part]): **C**

  | Group | Handler | Source |
  |---|---|---|
  | 0 | 0x4E69 | A |
  | 1 | 0x4E6E | B |
  | 2 | 0x4E48 | memory: RAM bank 0x11, `0x8000 + n*256` |
  | 3 | 0x4DFB | R |
  | 4 | 0x4DF4 | forces the group back to 0 |
  | 5 | 0x4DCA | ROM map 0x8700, n & 0x0F; empty here |

  The patch max table only allows groups 0-3 (0x4843 = 03). **C**

### 1b. Code-half tables (fixed, 0x1000-0x7FFF)

**Munt CM-32L map fields:**

| CK-34 | Munt cm32l_1_02 | What | Status |
|---|---|---|---|
| 0x4F03 (9) | 0x4F93 | partial reserve 3,10,6,4,3,0,0,0,6 | C |
| 0x4F0C (9) | 0x4F9C | default programs. Bit 6 = group. 68,48,95,78,41,3,110,122 = Slap Bass1, Str Sect 1, Brs Sect 1, Sax 1, Ice Rain, ElecPiano1, BottleBlow, Orche Hit | C |
| 0x4F1E (9) | 0x4FAE | default pans 7,8,7,8,4,10,0,14 | C |
| 0x483F (4) | 0x48CB | rhythm max: 7F 64 0E **07** (the reverb switch may be 0-7) | C |
| 0x4843 (16) | 0x48CF | patch max: group 3, num 63, key 48, fine 100, bend 24, assign 3, reverb **1** | C |
| 0x4853 (31) | - | max for the 0xC000 "performance" records (B2) | C |
| 0x485C (23+) | 0x48E8 | system max: tune 7F, mode 3, time 7, level 7, reserve 0x20 x 9, channel 0x10 x 9, vol 100 | C |
| 0x4873 / 0x4881 | 0x48FF | timbre max: common (14) / partial (58) | C |
| 0x597E / 0x59FE | 0x5A96 | sound-group index (128 B) / 19 groups x 14 B ("Piano  \|"...) | C |
| 0x1EF0 / 0x4013 | 0x1EE7 / 0x4047 | " \*\* Roland MT-32 \*\* " / "Exc. Checksum error" | C |

**Engine tables (each checked against the Munt equivalent):**

| CK-34 | What | Munt equivalent | Check | Status |
|---|---|---|---|---|
| 0x1100 (97 w) | coarse pitch, -12288..+20480 (341.33 per semitone) | coarseToPitchTable | values | C |
| 0x11C2 (101 w) | fine pitch -170..+170, also used for the part fine tune | fineToPitchTable | values | C |
| 0x128C (101) | pulse width 0-100 -> 0-255 | pulseWidth100To255 | | C |
| 0x12F1 (128) | MIDI 0-127 -> 0-100 (CC7, CC11) | `vol*100/127` | | C |
| 0x1371 (256) | ramp rate from level delta | envLogarithmicTime | **256/256 identical** | C |
| 0x1471 (101) | level -> amp subtraction | levelToAmpSubtraction | **101/101 identical** | C |
| 0x16D6 (17 w) | pitch keyfollow: -8192 ... 16384, 8198, 8226 | pitchKeyfollowMult | | C |
| 0x16F8 (17) | TVF keyfollow: -21,-10,-5,0,2,5,8,10,13,16,18,21,26,32,42,21,21 | keyfollowMult21 | | C |
| 0x1709 (15) | TVF bias: 85..-85 | biasLevelToBiasMult | | C |
| 0x1718 (13) | TVA bias coefficient: 255,187,137,100,74,54,40,29,21,15,10,5,0 | biasLevelToAmpSubtractionCoeff | | C |
| 0x17AE (8 w) | pitch-envelope divisors 34078..62499 | TVP lowerDurationToDivisor | | C |
| 0x17BE (15 w) | pan -> 3-bit LA32 pan, 4 nibble variants (sec. 4) | | | C |
| 0x17DC (13 w) | structure 1-13 -> per-partial flags (sec. 4) | PartialStruct/PartialMixStruct | | C |
| 0x17F6 (16) | popcount of partial mute = partials per note | | | C |
| 0x39C2 (8) | reverb switch -> LA32 control bits (sec. 6) | | | C |
| 0x3C78 / 0x3C96 | 15 pointers, all to 0x3C96 / 12 semitone pitches 0..0xEAB | keyToPitch (equal temperament) | | C |
| 0x3CAE (101) | master volume -> amp subtraction, 8 ... 0 | LAPC-I masterVolToAmpSubtraction | **identical** | C |
| 0x3D13 (101) | master volume -> PWM: 0xFF,0xF8,... reaches 0 at vol 69 | | | C |
| 0x4F27 (11) | reverb presets, packed `mode<<6 \| level<<3 \| time`; used by the panel "Reverb mode" UI 0x54C4; preset 5 = Room/6/4 = boot default | | | C |

**Munt map line for this ROM (I, untested):**
`{"ctrl_ck34_2_06", NEW_MT32_COMPATIBLE, 0x8100, 256, 0x8000, 0x8000, true, 0x8080, 0x8000, true, 0x8500, 64, 0x8580, 85, 0x4F03, 0x4F1E, 0x4F0C, 0x483F, 0x4843, 0x485C, 0x4873, 0x59FE, 19, 0x1EF0, 0x4013}`.
With this line and the CM-32L PCM ROM, Munt should be able to load the CK-34 ROM.

---

## 2. PCM wave table (0x8100, 256 entries) — `dump_pcm_table.py`

### Entry format (Munt ControlROMPCMStruct)
`pos, len, pitchLSB, pitchMSB`. **C**
- start sample = pos x 0x800
- length = 0x800 << ((len>>4)&7)
- len bit 7 = loop
- pitch word is added to the base pitch (0x363B)

### Entry index
Built at 0x34C3-0x34DF: `idx = ((waveform>>1)&1)*128 + pcmWave`. **C**
- Waveform 0/1 (SQU/1, SAW/1) = entries 0-127 (MT-32 set).
- Waveform 2/3 = entries 128-255. Same rule as Munt for CM-32L ("waveform > 1 -> pcm += 128").

### How the bytes go to the LA32 (0x34E4-0x34FB)
- pos -> **0x0C41+2p** (shadow 0xF1C0) = the 2K-sample page, 0..255 = the whole 1 MB. **C**
- len | 0x08 -> **0x0D01+2p** (shadow 0xEF81): the LA32 gets the length exponent and the loop bit directly. Bit 3 is
  forced to 1. **C**
- The loop region is the whole wave. No loop points exist anywhere in the ROM. **C** (no other fields)

### Master-tune bit
In the idle loop at 0x2CB4-0x2CC4, master tune 0xF4A0 is added to synth partials, and to PCM partials only if
**0xEF81 bit 0 = 0**. So **len bit 0 = 1 means fixed pitch**. **C**
- This agrees with Munt `TVP::updatePitch` (`(len & 1) == 0` adds master tune).
- It is the opposite of the note in WAVE_FORMAT.md.

### Contents (full list: `B3_pcm_table.txt`)

| Entries | What |
|---|---|
| 0-53 | MT-32 one-shots (drums and attacks), pitch mostly 0x5000 |
| 54-73 | the same waves with bit 0 = 1 (fixed pitch, for rhythm) |
| 74-127 | looped versions, including 119-127 = long 32K-sample loops over whole regions |
| 128-156 | CM-32L effect one-shots in IC38 (pos 0x80-0xFF), fixed pitch |
| 157-185 | the same waves looped |
| 186-255 | new loop/one-shot variants that point **back into IC37** waves (e.g. 189 = pos 0x10 len 16K loop) |

- Totals: 135 looped, 78 fixed-pitch; no entry runs past 1 MB; 236 distinct (pos, len) regions. **C**
- **MT-32 match:** entries 0-127 equal the MT-32 1.07 table at 0x3000 of the merged ic27/ic26 image (ic27 = even bytes,
  as in MAME `ROM_SKIP`), 128/128. **C**
  - The CM-32L control ROM is not on disk, so entries 128-255 could not be byte-compared. They are internally consistent
    with the CM-32L 1 MB set: every IC38 entry start decodes (Munt unscramble) to non-silent log samples (`--ic38`). **I/C**
- Pitch: 4096 units per octave, so 0x5000 vs 0x4000 = one octave. The table pitch is the wave's root offset. **C**

Script usage:
`python -I dump_pcm_table.py [IC28] [--csv] [--mt32 IC26 IC27] [--ic38 IC38]`. With no arguments it reads `../../dumps/` IC28.

---

## 3. Timbres, rhythm, defaults — `dump_timbres.py` (full list: `B3_timbres.txt`)

### Presets
- 0-63 (A) live at 0xB000-0xD751 (bank 2 up to 0xBFFF, then bank 3). 64-127 (B) at 0xD752-0xFE29 (bank 3). **C**
- **122/128 are identical** to the MT-32 1.0.7 presets: common block plus every unmuted partial, compared with the
  merged MT-32 ROM, A map 0x8000 / B map 0xC000+0x4000. **C** The six that differ:

  | # | Name | Difference (MT-32 -> CK-34) |
  |---|---|---|
  | 7 | HonkyTonk | name case ("Honkytonk") |
  | 13 | Pipe Org 2 | P1 level 46->38, velo 60->65 |
  | 34 | Chorale | P3 level 30->27, velo 75->80 |
  | 72 | Flute 1 | P4 level 23->21, velo 70->75 |
  | 110 | BottleBlow | P2 level 37->32, sustain 73->70 |
  | 121 | Triangle | P1 level 41->52, P2 level 30->40 |

  **I:** these are the CM-32L / new-generation revisions.
- The Pro-E tone list in IC7 (bank 0 file 0x24D9, 12-byte records "ACOU PIANO1"...) has the same order: 118/128 names
  match on the first 6 letters. So Pro-E tone n = CK-34 timbre n. **I**

### Rhythm
- R map: R00 Acou BD, R01 Acou SD, R02-04 toms, R05 Elec SD, **R06 Clsd HiHat, R07 OpenHiHat1**, R08 Crash ... R29 OpenHiHat2,
  R30-R62 CM-32L effects (Laughing ... Babble), R63 "OFF". **C**
- Rhythm setup: keys 24-34 off (0x7F). Keys 35-108 use the standard CM-32L map (35/36 BD, 38 SD, 42 closed HH, 46 open HH,
  ... 76-108 effects). Level 100 everywhere, reverb switch 1 everywhere. **C**
- **Hi-hat choke**, note-on 0x2659-0x2690: **C**
  - R07 (open HH) notes are stored as key 0. R06 (closed HH) are stored as key 1, after a note-off of key 0.
  - So closed kills open. With Overflow Assign on, the CK-34 sends `9n 00 00` on TX.
- **Rhythm timbres are played straight from ROM.** `0xF310[part 8]` = window pointer; bank in 0xF317 -> 0xF201[p]. Only
  melodic parts copy their timbre into a timbre temp. **C**
- Memory timbres (rhythm timbre byte < 0x40) come from RAM bank 0x11, `0x8000 + n*256`. In demo mode (`rb1` bit 1) they
  come from the empty ROM map 0x8700 instead. **C**

### Boot defaults (sub_502A, sub_5154, sub_5121)
**C** unless marked.

| Setting | Value / source |
|---|---|
| patch temp | from 0x4F0C (program) and 0x4F1E (pan), plus key 24, fine 50, bend 12, assign 0, reverb 1, level 80 |
| 128 patches | group = i/64, num = i%64, then 6 bytes from 0x4F32 (18 32 0C 00 01 00) |
| memory timbres | cleared |
| master tune | 0x4A |
| reverb | preset 5 (0x4F27[5] = 0x1D) |

These equal Munt's `Synth::open` defaults.

---

## 4. RAM model and the note-on path

### RAM model
**RAM layout = Munt MemParams minus the timbre bank**, from the bounds in sub_472E 0x472E-0x47AD and the init pointers 0x4F5C-0x4F64. **C**

| Address | Contents |
|---|---|
| 0xE000 | patchTemp[9] x 16: +0 group, +1 num, +2 key shift, +3 fine, +4 bend range, +5 assign mode, +6 reverb switch, +8 output level (CC7), +9 pan (CC10) |
| 0xE090 | rhythmTemp[85] x 4 |
| 0xE1E4 | timbreTemp[8] x 0xF6 |
| 0xE994 | patches[128] x 8 |
| 0xED94 | system: +0 master tune, +1 reverb mode, +2 time, +3 level, +4 reserve x 9, +0xD channel x 9, +0x16 **master volume 0xEDAA**, +0x17.. CK-34 extra (B2) |
| 0xF280+16*part | part runtime state (B2). Engine use, **C**: +0 bend scale (`range*0x2AB`), +2 partials per note, +3 active (unreleased) partials, +4 used partials, +5 first poly, +6 hold (bit 6), +7 mod wheel, +8 = 100 constant (I: unused level slot), +9 expression, +0xB channel, +0xC reserve, +0xF noSustain |
| 0xF310.. | +0 timbre ptr, +2 bend offset, +7 bank, **+8 key-pitch table ptr (0x3C96), +0xA key offset, +0xB semitone add** (all three only set by sub_4CCF = equal temperament) |
| polys (32), index r52 | 0xF3A0 part, 0xF3C0/0xF3E0 next/prev, 0xF400 key (bit 7 = held by pedal), 0xF420 velocity, 0xF440 first partial, 0xF460 state (bit 6 = released), 0xF480 noSustain |
| partials (32), index p2 = 2*partial | see below |
| lists | `r48` = free poly list. `r49` = free partial list (linked by 0xEE40; **bit 7 tags a free adjacent LA32 pair**). `r4a` = free partial count (32 at boot, 0x4F4A-0x4F56) |

Partial arrays (index p2): **C**

| Address | Contents |
|---|---|
| 0xEDC0 | state: 0x80 free, 0x20 playing, 0x40 released |
| 0xEDC1 | TVA bias subtraction |
| 0xEE00 | part |
| 0xEE01 | poly |
| 0xEE40/41 | next/prev partial |
| 0xEE80 | partial param ptr |
| 0xEEC0/C1 | TVA phase / target |
| 0xEF00/01 | TVF phase / target |
| 0xEF40 | base pitch |
| 0xEF80/81 | shadows of 0x0D00/0x0D01 |
| 0xEFC0 | pitch-envelope + LFO offset |
| 0xF000/F040/F080/F0C0/F100 | pitch-envelope value / phase / rate / end time / LFO |
| 0xF140/F141 | key-follow time subtraction (pitch / TVA) |
| 0xF180 | velocity amp subtraction |
| 0xF1C0/C1 | cutoff shadow / TVF time key-follow |
| 0xF200 | TVF depth |
| 0xF201 | bank |
| 0xF240 | rhythm key*4 |

### Note-on: main loop 0x22C9 -> jump table 0x2466[1] -> L25C7
**C** for every step.
1. **Key folding:** key + key shift (0xE002) is folded by octaves into 36..132, then -24 (0x25CE-0x25F5). The rhythm part
   checks the range 24..108 and looks up rhythmTemp (0x2600-0x2610).
2. **Partials needed** = popcount(partial mute) via 0x17F6, kept in 0xF282 (0x26BE-0x26CA). 0 -> ignore the note.
3. **POLY1/2 (assign mode bit 1 = 0):** an old poly on the same key is aborted, sub_2AA3 (0x26D8-0x26FF).
4. **Free partials** `r4a` < needed (0x2702) -> the steal logic, which is **Munt `PartialManager::freePartials`**:
   - With Overflow Assign on, the note is forwarded to TX instead (0x270E-0x272C).
   - Parts are scanned in the order 7..0 then rhythm (0x272D-0x2758). In each part that is over its reserve
     (0xF28C < 0xF284), the first **released** poly is aborted, and the scan starts again.
   - If needed + active would exceed this part's reserve: **assign mode bit 0 -> give up** (0x276C-0x2771). Otherwise
     polys in over-reserve parts are aborted, preferring the ones held by the pedal (0x2774-0x2801).
   - Abort = sub_2AA3: both ramps get `inc=FF, target=0`, phase 6, then a busy-wait until EXTINT has freed the poly's
     partials (0x2AD6).
5. **Allocation** (L2804): a poly comes from the free list `r48`. The two pairs of the timbre are done one after the other
   (0x280A-0x283D): `ra8:ra9 = 0x17DC[structure]`, then sub_2935 with mute bits &3, and again for partials 3/4.
   - Mute 1 -> partial 1 only. Mute 2 -> partial 2 only: its ring bit is cleared, and +0x40 if PCM (0x295B).
   - Mute 3 with no ring mod -> two partials from the free list, L2993. Mute 3 with ring mod -> **must get a tagged
     adjacent LA32 pair**, L2A38.
   - If no such pair is free: ring+mix plays partial 1 alone; ring-only plays neither (0x2A2E).
   - `r4a` -= 1 or 2.
6. **sub_3416** (partial start, sec. 5) runs for each partial: p2 in r54, params in r56, flags in ra8.
7. **Key-on** (0x28D7-0x2933): interrupts off, and **the pitch words are written to 0x0CC0 last**.
   - For an adjacent pair, the code waits for a rising edge of **P0.4**, then a delay of `(p2>>4)+3` loops, then writes
     both pitches back to back. This starts the pair phase-locked.
   - P0.4 = the LA32 sample clock: MAME toggles port0 bit 4 at 64 kHz = 32 kHz frames. **C** code, **I** meaning.

**0x17DC flags** (low byte = partial 1, high byte = partial 2). Bit 7 = PCM, bit 6 = PCM and not a ring slave, bit 5 = ring,
bit 0 = PCM (used by software), bits 2-3 = pan nibble select. The values decode exactly to Munt's
PartialStruct/PartialMixStruct (structure 8 `S/S` = 0x08/0x0C, 9 `P/P` = 0xC9/0xCD, stereo pair). **C**

**Pan** (0x3460-0x3489): the LA32 pan nibble = `0x17BE[pan] >> (ra8 & 0x0C)`. **C**
- nibble 0/1 = `(pan+1)>>1` (normal)
- nibble 2 = `max(0, pan-7)`, nibble 3 = `min(7, pan)`: the stereo-structure pair, = Munt PAN_NUMERATOR_MASTER/SLAVE

**Note-off** (L251B -> sub_2561): **C**
- Find the poly by key. With the pedal held -> set key bit 7 (held).
- Otherwise sub_2E33 for each partial, = Munt TVA/TVF `startDecay`: phase 6, ramp to 0 at `-envTime[4]`. Pitch envelope
  phase 5, 0xEDC0 = 0x40, active-1.

---

## 5. LA32 register map (0x0C00-0x0DFF) and how sub_3416 fills it

### Per-partial registers
Register = base + 2*partial, partial 0-31; pairs are (2k, 2k+1).

| Reg | Synth partial | PCM partial | Written at | Status |
|---|---|---|---|---|
| 0x0C00 (read, no index) | IRQ status (sec. 6) | | 0x2F33 | C |
| 0x0C00/0x0C01 | **ramp A = TVF** (cutoff modifier): inc, target | **ramp A = TVA** (amp) | 0x37D2, 0x327D, 0x2DC3, 0x2E6B, 0x3921 | C |
| 0x0C40 | pulse width = 0x128C[PW] + (vel-64)*(PWvelo-7), clamped | not written by the engine | 0x36A7 | C |
| 0x0C41 | **TVF base cutoff**, 8 bit = Munt calcBaseCutoff incl. `-800`, the `0xE00 - pitch/16` limit, `+2056 >>4` | **PCM start page** = pos byte | 0x3735 / 0x34FB | C |
| 0x0C80/0x0C81 | **ramp B = TVA**: inc, target | zeroed (unused) | 0x3928, 0x3289, 0x2DCF / 0x3742 | C |
| 0x0CC0 (word) | pitch: 4096/oct, clamped 0..0xE800. Writing it starts the partial. 0xFFFF / 0xFFxx = off (boot 0x2126, stop 0x2F5F, free 0x32C9) | same | 0x28F1, 0x2924, 0x2CF5 | C |
| 0x0D00 | control: b6 = SAW (waveform bit 0, 0x3570), b5 = ring, b4/b3 = routing (b3 = 1 no reverb), b2-0 = pan (7 = L, 0 = R) | b7 = 1 PCM, b6, b5 from flags, b4/b3/pan the same | 0x3578 / 0x34BE | C |
| 0x0D01 | resonance r = res+1 (1-31), byte = `r \| ((r<<3)&0xE0)` | PCM len byte \| 0x08 | 0x3594 / 0x34F1 | C |

- **Ramp registers = Munt LA32Ramp.** Byte 0 = increment: bit 7 = down; bits 0-6 = rate, `exp2((inc&0x7F+24)/8)`;
  0 = hold, with no IRQ. Byte 1 = target 0-255. The ramp interrupts when it reaches the target. **C** (code writes inc
  then target; semantics from Munt **I**)
- `inc = 0xFF` = jump now: used to set the start level (0x3916-0x3928).
- **Write order:** 0x0D00 then 0x0D01. The EXTINT handler writes the word twice (0x2F70/0x2F75). **C**
- **Pitch scale, from the factory test strings** (0x722C-0x73BD, synth partial, pan L/R/C via 0x0D00 = 0x1F/0x18/0x1C):

  | Pitch | Test string |
  |---|---|
  | 0x7AD9 | 100 Hz |
  | 0x8AD9 | 200 Hz |
  | 0x9D09 | 440 Hz |
  | 0xB000 | 1 kHz |
  | 0xC000 | 2 kHz |
  | 0xC95C | 3 kHz |
  | 0xD000 | 4 kHz |

  -> **f = 1000 Hz x 2^((P-0xB000)/4096)** for SQU. **C**
  - Cross-check with Munt's square constant 37133 (0x910D, code 0x364E): middle C = 261.6 Hz and A4 = 440.0 Hz. SAW adds
    0x810D, one octave lower, because a saw sounds an octave up (0x3654). **C**
- Global registers: **C** (writes); meaning **I**, unknown.
  - Boot (sub_2DEC) writes 0x0DC2 = 0x0000 and 0x0DC0 = 0xC000 (words), and **0x0D40/0x0D42/0x0D44 = 0x0000/0x8000/0xFFFF
    for 4 groups at stride 0x10**.
  - Test mode (sub_73E8) writes the same values with stride 0x20.
  - **I:** the 4 groups match Munt's "partials grouped in quarters" mixing note.

### Partial start, sub_3416
Mirrors Munt Partial/TVP/TVF/TVA reset. **C**
- **Pitch** (0x3599-0x3671), clamped to 0..0xE800, stored in 0xEF40:
  - key -> `0xF318` table (0x3C96, semitones) + octave<<12 - 0x6000
  - x keyfollow (0x16D6) >> 13
  - + coarse (0x1100) + fine (0x11C2) + part fine (0xE003, 0x11C2)
  - + PCM pitch (0x8102), or 0x910D/0x810D
  - = Munt `calcBasePitch`
- **TVF:**
  - depth = envDepth x velocity / key-follow -> 0xF200 (0x3756-0x378D)
  - start ramp to `depth*envLevel[0]>>8` at `0x1371[target] - (time[0] - keyfollow)`, phase 1 (0x37AF-0x37DF)
  - PCM: ramp B = 0, TVF phase 6 (0x3742)
- **TVA** = Munt `calcBasicAmp` (0x387D-0x38F9):
  - 155 - 0x3CAE[master vol] - 0x1471[part level 0xE008] - 0x1471[0xF288] - 0x1471[expression 0xF289]
    - 0x1471[rhythm level 0xE091]
  - The volume terms are skipped for a ring slave (odd partial with b5).
  - Then - bias (0xEDC1, from 0x1718) - 0x1471[TVA level] - velocity term (0xF180), clamp 155, - resonance/2.
  - Then + envLevel[0] with phase 1 if time[0] == 0, else phase 0. Jump-set the ramp (inc 0xFF).
- **Pitch envelope / LFO init:** velocity multiplier 0x5555 (= Munt calcVeloMult 21845), level offsets -> 0xEFC0/0xF000
  (0x394F-0x39BC).

---

## 6. EXTINT = LA32 interrupt (0x2F2D-0x3415)

**Entry:** only if P2.2 is high. Read the status at 0x0C00 into r64. `int_mask` = 0x40, ei: MIDI RX may nest. Bank shadow
`rb8` = 0xF201[p]; the exit restores `rb7`. **C**

### Status byte r64

| bit 7 | bit 5 | Partial | Path | What happens |
|---|---|---|---|---|
| 1 | 1 | bits 0-4 | L30B7 | **ramp B done** -> TVA step (synth) |
| 1 | 0 | bits 0-4 | L2F96 | **ramp A done** -> TVF step (synth) or TVA step (PCM, 0xEF80 b7 -> L30EA) |
| 0 | - | **(bits 0-4) - 1** | 0x2F3F-0x2F82 | partial stop: pitch 0xFFFF, set 0x0D01 b7, TVA phase 6 -> next step = dead. **I: a PCM one-shot reached its end** (Munt: a non-looped PCM deactivates the partial) |

All three paths are **C** in code. If 0xEDC0[p] = 0x80 (free), the handler only writes 0xFF80 to the pitch and returns. **C**

### TVA step, L30D1/L30EA
= Munt `TVA::nextPhase`. **C**
- phase = 0xEEC0 + 1.
- Phase 7 -> both ramps 0, then free the partial (sub_32C9, plus the ring partner via 0x32A4-0x32BD).
- Phases whose remaining levels are 0 are skipped to "dead" (0x30FF-0x3124).
- Target = basic amp (same chain as above) + envLevel[phase-1].
- Time = envTime - TVA key-follow; phase 1 instead uses velocity: `(vel-64)>>(6-veloTimeSens)` (0x31C5-0x31D4).
- inc = `0x1371[|delta|] - time` (minimum 1, bit 7 if going down). delta 0 -> target-1 trick (0x3252).
- Phase 5 (sustain):
  - noSustain (0xF480 b0) -> release at `-envTime[4]` (0x3203-0x321E).
  - Otherwise target += sustain level, inc 0 (hold).
- Writes ramp A (PCM) or ramp B (synth) (0x3275-0x328E).

### TVF step, L2FD3
= Munt `TVF::nextPhase`. **C**
- phase 0xEF00; target = depth 0xF200 x envLevel (0x25+phase); time 0x20+phase - 0xF1C1.
- Phase 5/6: sustain with inc 0, or noSustain -> release.
- Phase 7: ramp A := 0.

### Free, sub_32C9
**C**
- Pitch := 0xFFxx; 0xEDC0 = 0x80; `r4a`++; the part's +3/+4 counters decrement.
- The partial goes back into the free list **next to its pair partner, with the bit-7 pair tag** if the partner is free
  (0x3305-0x33C9).
- Unlink from the poly. If the poly is empty -> back to the free poly list `r48` and out of the part's list (0x33E0-0x3410).

### Idle partial service (L2AE2-0x2DE9)
One partial per main-loop pass, only when no MIDI event is waiting, round-robin `r40` = 0..0x3E, then the UI at 0x529C. **C**
- **Pitch envelope:** software ramps. Time = timer1 with `r4b` as the high byte (timer-overflow ISR 0x22B7). Divisors at
  0x17AE. Phases 0xF040 1-5. **C**
- **LFO:** depth = `mod wheel 0xF287 * modSens >>7 + LFO depth`, sign flip each half period (0x2B90-0x2BAD). **C**
- **Pitch out:** `0xEFC0 + [0xF4A0 master tune unless PCM with fixed bit] + [0xF312 bend if bender on] + 0xEF40`, clamped
  0..0xE800 -> 0x0CC0 (0x2CAD-0x2CF5). **C**
- **TVA sustain refresh:** in phase 5 (with sustain level != 0), recompute the target. inc = `0x1371[|d|] - 2`, phase 4.
  = Munt `TVA::recalcSustain`, so CC7/CC11 changes reach sustaining notes (0x2D07-0x2DE6). **C**

---

## 7. Reverb control

| System param (RAM) | Goes to | Code | Status |
|---|---|---|---|
| reverbMode 0xED95 | bits 1-3 -> **`rc8` bits 1-3, written to 0x021A**; bit 0 -> shadow 0xF4A2 bit 2 -> **0x0800 bit 2** | sub_4CFC 0x4CFC-0x4D29 | C |
| reverbLevel 0xED97 | bit 0 -> 0xF4A3 bit 3 -> **0x0400 bit 3**; bits 1-2 -> 0xF4A2 bits 0-1 -> **0x0800 bits 0-1** | sub_4D2F 0x4D2F-0x4D67 | C |
| reverbTime 0xED96 | bits 0-2 -> 0xF4A3 bits 0-2 -> **0x0400 bits 0-2** | sub_4D6D 0x4D6D-0x4D86 | C |
| per partial | LA32 0x0D00 **bit 3 = 1 means no send**. 0x39C2[reverb switch]: 0 -> 0x18 (+pan), 1 -> 0x10 (+pan) | 0x345B-0x3489, 0x3505-0x3533 | C |

- **0x0200 and 0x021A share the shadow `rc8`.** **C** for the shared shadow; **I** that both decode to the same latch.
  - bit 0 = LED: on while any part has active partials or MIDI is active (0x51C1-0x51DD), = MAME "led".
  - bits 1-3 = reverb mode high bits.
  - The test mode clears bits 1-3 (0x71A1, 0x72B7, 0x72F1).
- Callers:
  - SysEx system write 10 00 01-03: L3D7C-L3DC1 (demo loader), and the SysEx path (B2).
  - Panel "Reverb mode" UI: preset 0-10 from 0x4F27 (0x54DE-0x5535).
  - Boot: 0x5088-0x508E.
- **Factory test values** (0x7297-0x7365): **C**

  | Test | 0x0800 | 0x0400 | Mode / time / level |
  |---|---|---|---|
  | "PCM REV. OFF" | 0 | 0 | 0 / 0 / 0 |
  | "REV.1" | 4 | 8 | mode 1, level 1 |
  | "REV.2" | 6 | 0x1D | mode 1, time 5, level 3; **0x0400 bit 4 also set** (I: an extra BOSS control bit) |

- Reverb ROM IC13 (32 KB): 4 different 4 KB programs at 0x0000/0x1000/0x2000/0x3000, mirrored at 0x4000. **C** (data)
  - **I:** mode 0-3 (Room/Hall/Plate/Tap) picks the 4 KB block. The two select bits are {0x0800 bit 2, latch bit 1}; the
    pin wiring is unverified.
- **Rhythm reverb switch 2-7 (CK-34 allows 0-7, 0x4842 = 7):** 0x39C2[2..7] = 0x18, 0x1F, 0x07, 0x0F, 0x00, 0x08. These
  are fixed pans (R/L) and **bit 4 clear** for 4-7. **C**
  - **I:** bit 4 = dry-bus enable, so 4/6 = reverb only and 5/7 = silent. Or bit 4 is a second output pair. Open.

## 8. Master tune, master volume
- **Master tune:** sub_4CE4 computes `0xF4A0 = (0xED94*171 - 10944) >> 6` (0xAB, 0x2AC0) = Munt `masterTunePitchDelta`. **C**
  - Boot sets 0xED94 = 0x4A but **0xF4A0 = 0** (0x5041-0x504D). So 440 Hz until the next tune write: the bug Munt reports
    for all ROMs. **C**
  - A step is 171/64 units, about 0.94 cent per value.
- **Master volume 0xEDAA:** the idle loop writes `0x3D13[vol]` to **PWM_CONTROL (SFR 0x17)** on every pass (0x529C-0x52A6).
  **C**
  - Boot writes 0xFF (0x2236). The test mode drives PWM from the knob (0x71CB-0x71D0).
  - **I:** the PWM drives an analog VCA; 0xFF = minimum (vol 0).
  - Digitally only 0x3CAE subtracts 8..0 (LAPC-I behaviour). **C**
- **Part volume:** CC7 -> 0x12F1 -> patchTemp output level 0xE008 (0x3B0F). CC11 -> 0xF289 (0x3B54). **C**
  - 0xF288 is always 100: set only at 0x235F, 0x3BFB and 0x4F9A, so it subtracts 0. **C**
  - Rhythm notes also subtract 0x1471[rhythm key level]. **C**
- Other CCs (jump table 0x39DE): **C**

  | CC | Effect |
  |---|---|
  | 1 | mod -> 0xF287 |
  | 6 | RPN 0/0 bend range (max 24) -> sub_4D8C `0xF280 = range*683` |
  | 10 | pan = v*8/68 -> 0xE009 |
  | 64 | hold 0xF286 |
  | 98/99 | NRPN: RPN off |
  | 100/101 | RPN select |
  | 121 | reset controllers |
  | 123-127 | all notes off |

  Bend: `(v-0x2000)*0xF280 <<2 >>16` -> 0xF312 (0x2476). **C**

---

## 9. Munt routine <-> CK-34 address

| Munt | CK-34 | Status |
|---|---|---|
| PartialManager::freePartials / abort* | 0x2702-0x2803, sub_2AA3 | C |
| Part::playPoly + PartialManager alloc | L2804, sub_2935, L2993, L2A38 | C |
| Partial::startPartial + TVP/TVF/TVA reset | sub_3416 0x3416-0x39C1 | C |
| TVA::nextPhase / TVF::nextPhase | EXTINT L30EA / L2FD3 | C |
| TVA/TVF::startDecay | sub_2E33 | C |
| TVP::updatePitch + TVA::recalcSustain | L2AE2-0x2DE9 | C |
| Synth::refreshSystemMasterTune / ReverbMode/Time/Level | sub_4CE4 / sub_4CFC / sub_4D6D / sub_4D2F | C |
| Part note on / off / CC / bend / program change | L25C7 / L251B / L39CA / L2476 / sub_5DB9 -> sub_4D9C | C |

## 10. Mod hooks

**Data:**
- **PCM table 0x8100** (256 x 4): change start/length/loop/pitch/fixed-pitch bits. New waves need new IC37/IC38 images plus
  the table; loops are whole power-of-two waves only. The 0x34C3 index rule gives 256 waves (2 banks). **C**
- **Timbres:** A/B maps 0x8000/0x8080, R map 0x8500, rhythm setup 0x8580. The timbres are compressed, so a rewritten timbre
  must keep the mute/omit rule. **C**
  - The data ends at 0xFE29 (bank 3, 470 B FF after it) and at 0xA8AF (bank 2, 1872 B FF at 0xA8B0-0xAFFF).
- **"Group 5"** = 16 extra ROM timbres via the empty map 0x8700: the handler exists (0x4DCA, pointer format like the A map).
  It is blocked by patch max 0x4843 = 3. Raising that byte to 5 would make group 5 selectable by SysEx. **I**
- **Scale tuning / microtuning:** 0x3C96 (12 words) is the only key-pitch table. Per part, 0xF318/0xF31A/0xF31B are set only
  by sub_4CCF 0x4CCF, so a patch there gives per-part scales. 0x3C78 already has 15 pointer slots. **C**

**Free space (FF):**

| Range | Size | Where |
|---|---|---|
| 0x606A-0x6FFF | 3990 B | fixed code space |
| 0x78A9-0x7FFF | 1879 B | fixed code space |
| 0x86D4-0x89FF | 812 B | bank 2 |
| 0xA8B0-0xAFFF | 1872 B | bank 2 |
| 0xFE2A-0xFFFF | 470 B | bank 3 |
| 0x1F0F-0x1FFF, 0x2019-0x207F, 0x2197-0x21FF | small | fixed |

**C**

**Code points:**
- **Spare level slot:** 0xF288 (always 100) sits in all three amp chains (0x2D36, 0x314C, 0x38A3). A free per-part level
  hook. **C**
- **Master volume curve:** 0x3D13 (PWM). Digital trim: 0x3CAE. **C**
- **Reverb:** sub_4CFC/4D2F/4D6D are the only latch writers in normal play, with shadows 0xF4A2/0xF4A3/`rc8`. Rhythm routing
  table: 0x39C2. **C**
- **LA32 access rules:** **C**
  - Mask EXTINT (`andb int_mask, #0x7F`) around multi-register LA32 or list edits; the stock code always does.
  - Write 0x0D00 before 0x0D01.
  - Write the pitch last (key-on).
  - Keep `rb7` valid: EXTINT restores the bank from it.
- **PCM index hook:** 0x34C3-0x34E4 (`ld r70, 0x8100[r74]`) is the single place where a PCM number becomes LA32 pos/len
  (+0x363B for pitch). A hook there could switch tables (e.g. a third bank). **C**

## 11. Open questions
- **0x0D00 bit 4** (and the rhythm reverb switch 2-7 routings) and **PCM bit 6**: what do they do in the LA32? Needs a
  scope/audio test: rhythm key with reverb switch 4-7 via SysEx 03 01 10+.
- **Global LA32 registers** 0x0D40/42/44 (x4 groups) and 0x0DC0-0x0DC3: their meaning is unknown.
- **Status bit 7 = 0 interrupt:** confirm on hardware that it fires at a PCM one-shot end. And why the index is off by one.
- **Reverb select pins:** which of 0x0800 bit 2 / latch bit 1 / 0x0400 bit 4 reach the BOSS chip and the IC13 address lines
  (CK-34 schematic needed; the Pro-E service notes do not cover the CK-34).
- **Entries 128-255:** byte-compare them against a real CM-32L control ROM (not on disk).
- **Pro-E rhythm switches:** does the Pro-E 68HC11 ever send rhythm reverb switch > 1? Grep the IC7 SysEx builders for
  `03 01 xx` writes (B2 sec. 4).

## TL;DR (again)
- The CK-34 is the CM-32L engine (Munt-exact tables and logic), with the CM-32L data layout. **C**
- PCM table 0x8100: 256 entries, 0-127 = MT-32 1.07 byte-for-byte. Len bit 0 = 1 means **no** master tune. **C**
- 122/128 presets = MT-32 1.07. The Pro-E tone list is in CK-34 timbre order. **C/I**
- LA32 per partial at base+2p: **C**
  - ramps 0x0C00 (TVF / PCM TVA) and 0x0C80 (synth TVA)
  - 0x0C40/41 PW/cutoff or PCM page
  - 0x0CC0 pitch (0xB000 = 1 kHz, write = key-on)
  - 0x0D00 control (PCM/SAW/ring/rev-off/pan3), 0x0D01 resonance or PCM len/loop
- EXTINT steps the envelopes and frees partials. The idle loop does pitch/LFO/bend/master tune. **C**
- Reverb: mode -> latch bits 1-3 + 0x0800 b2; time -> 0x0400 b0-2; level -> 0x0400 b3 + 0x0800 b0-1. Master volume =
  PWM 0x3D13. **C**
- Tools: `dump_pcm_table.py`, `dump_timbres.py`. Listings: `B3_pcm_table.txt`, `B3_timbres.txt`.
