# A4 - PRO-E 68HC11 arranger engine + style data (IC4 v2.00 + IC7 R15179983)

Static analysis only. Addresses: `$xxxx` = CPU address (bank 0 + IC4 image unless a bank is named; "b1:$xxxx" = IC7 bank 1 in the window).
Tags: **[C]** = CONFIRMED (seen in code/data), **[I]** = INFERRED (reasoned, not fully traced).

Helper files in this folder:
| File | What |
|---|---|
| `hexify.py` | rewrites `../bank0_ic4.lst` with hex immediates/offsets -> `bank0_ic4_hex.lst` |
| `hcdis.py ADDR N [bank]` | linear HC11 disassembly of IC7 bank N + IC4 (reaches jump-table code the recursive lst misses) |
| `styles.py` | parses the 32-style directory and walks every pattern -> `styles_dir.txt`; `--events S P K C` dumps one pattern |
| `sfx.py` | walks the 37 sound-effect sequences -> `sfx_list.txt` |
| `songs.py` | walks the 5 demo songs (composer format) -> `songs_list.txt` |

Every one of the 2496 style pattern pointers, 37 SFX sequences and 28 demo tracks walks cleanly to its end marker with the formats below, and lengths agree across parts/tracks. That is the main check on the formats **[C]**.

---

## 1. IC7 bank map (which banks are data)

`$180D` latch (shadow `$0A`) **[C]**: bits 4-6 = IC7 bank (`$ED48` = 00 10 .. 70), bit 3 = card (`$ED50`=$08; `$ED51`=$0C), **bits 0-1 = battery-RAM page in the $2000-$3FFF window** (DA36 loop writes 1,2,3; DD44 `orab $ED48`; D382 `$08|3`). ISRs force page 0 before touching the MIDI rings (`andb #$FC`, E7DF/E80A).

Every bank starts with a 3-byte header **[C]** (checker `$ECA6`): `$4000-$4001` = 16-bit complement so that word($4000) + Σbytes($4002..$BFFF) = 0 mod 65536 (checked numerically for all 8 banks); `$4002` = ID byte compared with table `$FC1D` = 06 07 11 12 (one per bank pair: banks 0/1=06, 2/3=07, 4/5=$11, 6/7=$12).

| Bank | Content |
|---|---|
| 0 | code, LCD text `$59E1-$6380`, style names `$63D9`, tone names `$64D9`, chord names `$6AD9`, chord tables `$A42E-$A4F4`, default panel `$A3CF-$A41E`, **style directory `$A701-$BFA0`**, SFX tables `$BFA1-$BFFE` |
| 1 | **mixed**: style patterns `$4003-$52E0` + `$5926-$70D6`; SFX sequences `$52E1-$5925`; 5 demo songs `$70D7-$B05B`; $FE pad `$B05C-$B066`; **code** `$B067-~$BBB9` (test mode entry `$B067` from C25D, user-program check `$BA21` from C08C/D3F5, CK-34 SysEx test sender `$BB7A` from C26C); CK-34 SysEx data `$BBBA-$BC6E`; factory user programs `$BC6F-$BEEE`; byte copy of bank 0 `$BEEF-$BFFF` (style-31 tail + SFX tables) **[C]** |
| 2-7 | **pure style pattern data**, each `$4003-$BFFF` fully used (styles.py union) **[C]**. Bank 6 has 3 unreferenced patterns at `$4A30`, `$4B58`, `$4C13` (37-38 B, end $3F) = dead data **[C]** |

Data banks per style are in the directory table (sect. 3). Styles span bank pairs: e.g. FUNK2 = banks 2+3.

---

## 2. Timebase and tempo

| Item | Detail | Tag |
|---|---|---|
| Timer clock | TMSK2=$91 -> prescale /4 -> 500 kHz, 2 µs/count | C |
| Arranger clock | TOC1 `$E8E5`: TOC1 += word `$21:$22`, `inc $B0` (pending ticks). If `$59.7`, also `inc $B1` | C |
| Tempo -> period | `$476A`: period = $1312D0 / BPM = **1,250,000 / BPM** counts = 2.5 s/BPM per tick = **24 PPQN** | C |
| Tempo variable | `$241B` = BPM (default panel $6E=110). Preset tempo = style record +$10, loaded at `$7AC0-$7AC5` | C |
| Tap tempo | `$6F39`: interval in 2.5 ms units (`$49`), taps = beats per bar (`$26A8`), clamp $60..$4B0, BPM = 24000/interval -> **20..250** | C |
| TOC2 `$E901` | every 2.5 ms (+$04E2): `$49` ms counter, `$47/$48` timeouts, LED/scan mux via `$180E`/PORTA; every 8th (20 ms): `$4B/$4C`, and `inc $B1` if `!$59.7`, set `$56.1` | C |
| SFX clock `$B1` | tempo-locked if `$59.7`, else fixed 20 ms. `$59.7` = "Style sync" for sound effects | C mech / I label |
| MIDI clock out | each tick, if `$244D.7` send $F8 (`$C432`, `jsr $E85A`) | C |
| MIDI clock in | `$9BD1`: OC1I off (`$9BBA`), each received F8 schedules TOC4 at TCNT+$09C4 (5 ms) or ticks at once if one is pending; TOC4 `$E8DD` = one-shot tick | C |
| Chord debounce | `$4336`: TOC5 one-shot, +$0FA0 (8 ms) after a key-on, +$FFFF (131 ms) after a key-off; `$C3D7` polls TFLG1.3 then re-runs chord detection (`$453F`) | C |

Main loop `$C37F`. Per pending tick (`$C428`, `dec $B0`): beat counter `$23` (24..1), bar counter `$24` (ticks left in bar, reload = style +$0F), downbeat window `$56.2` (set at bar end `$C4E1`, cleared 20 ticks into the beat `$C4BC`), song player `jsr $D8D0`, arranger loop `jsr $A118`, then drums (`$C56B`), then bass/acc via the chord dispatch (`$C5E1`). Effects run from `$B1` at `$C612` **[C]**.

---

## 3. Style storage

### 3.1 Directory
- Internal: 32 records of **197 ($C5) bytes at `$A701 + 197·n`** (n = 0..31, ends at `$BFA0`) **[C]** (`$4783`, `$CF4D`).
- Card: 8 records at **RAM `$2729 + 197·n`** when style number bit 5 is set (`$CF3E-$CF47`, `$478F`) **[C]**.
- Style number: `$240C` (panel; $00-$1F internal, $20|n = card style n). The engine uses the copy `$2679`. While playing, `$2679` is updated only at a drum-pattern end (`$C7E1`), so a style change waits for the pattern end. When stopped, it is updated at once and the preset tempo is loaded (`$7AB4-$7AC5`) **[C]**.
- Names: internal 8 B at `$63D9 + 8·n`; card 16 B at `$26A9 + 16·n` (display `$4ECE`) **[C]**. There are **32** internal names (ROCK1 .. FUSION), not 36.
- Panel numbering: bank b, number m -> n = 8(b-1)+(m-1) (manual "44 CHA CHA" = n 27; default style `$240C`=5 = FUNK2, as the manual says) **[C]**.

### 3.2 Record layout (loader `$CF3B-$D1FE`) **[C]**
| Off | Size | Field |
|---|---|---|
| +$00 | 3 | drum bank nibbles, section k: byte k/2, low nibble for even k, high for odd |
| +$03 | 6×2 | **drum pattern pointers**, sections 0-5 |
| +$0F | 1 | **ticks per bar** (96 = 4/4, 72 = 3/4 WALTZ, 48 = 2/4 POLKA) (`$4783`->`$26/$24/$24D6`) |
| +$10 | 1 | **preset tempo** BPM |
| +$11 | 9+36 | part 1 = **ACCOMP BASS**: 9 nibble bytes + 18 ptrs |
| +$3E | 9+36 | part 2 = **ACCOMP1** (Advanced arrangement only) |
| +$6B | 9+36 | part 3 = **ACCOMP2** (Advanced only) |
| +$98 | 9+36 | part 4 = **ACCOMP3** (Simple arrangement only) |

- In each part, pointer index = 3·section + class, at +9+2·(3k+c). Class c: 0 = Major, 1 = minor, 2 = 7th.
- Bank nibbles: pair m = k/2 uses bytes b[3m..3m+2]. Even k: c0=b[3m].lo, c1=b[3m].hi, c2=b[3m+1].lo. Odd k: c0=b[3m+2].lo, c1=b[3m+2].hi, c2=b[3m+1].hi. Proof: section 5 (`$CF78`: $24C4=+$19, $24C5.lo = +$18 hi), section 4 (`$CFE8`), section 2 (`$D058`).
- Bank nibble -> `$ED48[n]`: 0-7 = IC7 bank, **8 = card ($08), 9 = card $0C** **[C]** table / **[I]** use.
- Pointers ≥ $C000 point at **IC4 silent patterns `$ED84-$EDA4`**: `7D 00 tt 3F` = one rest of tt ticks then end. tt = $30, $57, $5C, $60, $90, $C0, $120, $180, $1E0 at $ED84, $ED88 .. $EDA0. Styles use these for "part tacet" (e.g. FUNK2 ACC fills -> `$ED90` = 96-tick bar) **[C]**.

Runtime copies **[C]**: `$24C2` = drum ptr; `$24BC/$24BE/$24C0` = address of the current section's 3-pointer triple for bass / acc-B / acc-C; `$24C4-$24C9` = their bank nibbles (`$C943`, `$CBB9`, `$CB8A` pick the nibble by class `$25` ∈ {0,2,4}).

### 3.3 Sections (6) **[C]** (flag logic `$CF54-$D1BC`, button handlers)
| k | Ptr | Section | Selected when | Handler |
|---|---|---|---|---|
| 0 | +$03 | BASIC (original) | default, `$0C.2`=0 | `$D151` |
| 1 | +$05 | VARIATION | default, `$0C.2`=1 (VARIATION LED) | `$D1BD` |
| 2 | +$07 | FILL-IN "to ORIGINAL" | `$57.1`; clears `$0C.2` afterwards | `$6DA7` (`$6DD4`) |
| 3 | +$09 | FILL-IN "to VARIATION" | `$57.3`; sets `$0C.2` | `$6E1C` (`$6E49`) |
| 4 | +$0B | INTRO | `$57.4` and not deferred (start from stop) | `$6EA6-$6EB6` |
| 5 | +$0D | ENDING | `$57.4` + deferred `$57.2` at the downbeat, or `$58.3` | `$6E7E-$6E88` |
| - | `$24CE` | BREAK MUTE | `$57.5`: every part -> `$24CE` -> RAM `$24D4` = a one-bar rest with `$24D6` = ticks/bar | `$6EE4`, `$D127`, `$C1F2` |

- Timing: a button pressed with `$24` ≤ 24 ticks left in the bar (the 4th beat) sets the deferred flag `$57.2` and fires at the next downbeat (`$56.2`). Otherwise the section reloads at once (`$6DDD`: `$CF36`, drum notes off `$C90A`, relocate `$C895`). This matches the manual **[C]**.
- At the end of a fill or intro, the section flags are cleared (`$C800-$C80E`) and BASIC/VARIATION resumes. At the end of the ending pattern, `$58.3` -> `jmp $E9D9` stop (`$C526`, `$C7F5`) **[C]**.
- The drum pattern end drives all section and style switching (`$C585` -> `$C7D9`). The other parts loop on their own end markers within the section (`$C98C`, `$CBFF`, `$CDBE`) **[C]**.
- A program change goes out on the "STYLE PRG CHANGE" channel `$244A` (`$EAD5`) when a section button fires: FILL>ORIG $51 (`$6DAF`), FILL>VAR $50 (`$6E24`), INTRO/ENDING $53 (`$6E92`), BREAK $54 (`$6EF7`). It is sent again from the pending-request bits `$5C`.1/.3/.5 at `$C55A` **[C]**.

### 3.4 Parts -> voices -> CK-34 channels **[C]**
| Part | Data | Engine / ptr / counter / bank | Voices | Note = field + | Int. MIDI (enable byte) | Ext. ch byte |
|---|---|---|---|---|---|---|
| DRUMS | header | `$C56B` / `$C0` / `$B8` / via `$24C5`.hi | 8 (`$27-$2E`) | 36 | $99 ch10, vel × `$2404` level (`$EC4B`) | `$2446` |
| A.BASS | part 1 | `$CA57` / `$BA` / `$B2` / `$C4` | mono `$2F` | 24 | $97 ch8 (`$2408`) | `$2444` |
| ACC1 (adv) | part 2 | `$CC8D` / `$BC` / `$B4` / `$C2` | 4 (`$31-$34`) | 36 | $94 ch5 (`$2402`) | `$2441` |
| ACC2 (adv) | part 3 | `$CE40` / `$BE` / `$B6` / `$C3` | 4 (`$36-$39`) | 36 | $95 ch6 (`$2406`) | `$2442` |
| ACC3 (simple) | part 4 | `$CC8D` / `$BC` (same as ACC1) | 4 (`$31-$34`) | 36 | $96 ch7 (`$2407`) | `$2443` |
| SFX | sect. 7 | `$C612` / `$24D9+2i` / `$24E1+2i` / `$24E9+i` | 4 | 60 | $99 ch10 × `$2405` (`$EC7A`) | `$2447` |

- `$0C.3` = ADVANCED ARRANGER (toggle `$6FF9`, LED `$12.3`, reload `$CF36`). Advanced = ACC1+ACC2. Simple = ACC3 on the same engine and voices as ACC1 (`$CB23` vs `$CB42`, `$CD1F`) **[C]**.
- The other panel parts use the same senders: SOLO $93 ch4 (`$2400`/`$243F`), LOWER $92 ch3 (`$2401`/`$2440`), M.BASS $91 ch2 (`$2403`/`$2445`). Ext. channel byte: bit 7 = TX on, low nibble = channel-1. Int. enable byte: bit 7 = on, bits 0-6 = level %. `$5B.3` forces internal output (`$EBF8`) **[C]**.

### 3.5 Pattern event format (all style parts, SFX) **[C]** (`$C579-$C5DF`, `$C980-$C9DC`, `$CA61-$CB20`)
```
byte0: b7 = 1 -> PROGRAM CHANGE: value = (byte0&$3F)|(byte1&$40)  (MT-32 tone #; drums skip it)
       b6 = 1 -> 3-byte event, delta = (byte1&$0F)<<8 | byte2   (else 2-byte, delta = byte1&$0F)
       b5-0  : $00-$3C note field, $3D = no-op (delta only), $3E/$3F = END (all data uses $3F)
byte1: b7-4 = velocity index -> $ED5A table {0=OFF,15,23,31,..,119,127}; b3-0 = delta (hi bits if long)
delta 0 = next event at the same tick. Patterns are written in C (bass field 12 = C2; drum field 0 = kick 36).
```
- A program change goes out on the int. channel `$C4-$C7` (cached `$267B-$267E`, `$EB52-$EB9D`) and ext. if `$244C.5` (`$EA9E-$EACC`). Seen: bass 64/65/68/70 = ACOU BASS1/2, SLAP BASS1, FRETLESS1; acc 3/6/29 = ELEC PIANO1/4, SYN BASS2 **[C]**.
- Pattern lengths (styles_dir.txt): BASIC/VARIATION 1, 2, 4 or 8 bars; fills 1 bar; intros 1-5 bars; endings end mid-bar on the last hit **[C]**.
- Bar counters `$24CA-$24CD` (drum/bass/acc-B/acc-C) are reset to 1 at a section start (`$D22F`) and +1 per bar (`$C4F3`). Each part keeps its own bar count, so parts of different lengths loop independently **[C]**.

### 3.6 Style directory (from `styles.py`)
| # | Name | Rec | BPM | Ticks/bar | Drum banks (S0-S5) | Data banks |
|---|---|---|---|---|---|---|
| 0 | ROCK1 | $A701 | 140 | 96 | 777777 | 7 |
| 1 | ROCK2 | $A7C6 | 140 | 96 | 333333 | 3 |
| 2 | DISCO1 | $A88B | 110 | 96 | 777777 | 7 |
| 3 | DISCO2 | $A950 | 110 | 96 | 332233 | 2,3 |
| 4 | FUNK1 | $AA15 | 104 | 96 | 777777 | 7 |
| 5 | FUNK2 | $AADA | 110 | 96 | 232233 | 2,3 |
| 6 | BALLAD | $AB9F | 120 | 96 | 777777 | 7 |
| 7 | SL ROCK | $AC64 | 64 | 96 | 776667 | 6,7 |
| 8 | 8BEAT1 | $AD29 | 74 | 96 | 666666 | 6 |
| 9 | 8BEAT2 | $ADEE | 84 | 96 | 222222 | 2 |
| 10 | 16BEAT1 | $AEB3 | 80 | 96 | 666666 | 6 |
| 11 | 16BEAT2 | $AF78 | 80 | 96 | 222222 | 2 |
| 12 | REGGAE | $B03D | 140 | 96 | 666666 | 6 |
| 13 | BOOGIE | $B102 | 162 | 96 | 666666 | 6 |
| 14 | ROCK'N | $B1C7 | 162 | 96 | 666666 | 6 |
| 15 | DIXIE | $B28C | 162 | 96 | 666666 | 6 |
| 16 | SWING | $B351 | 140 | 96 | 556655 | 5,6 |
| 17 | BIG BAND | $B416 | 140 | 96 | 555555 | 5 |
| 18 | SHUFFLE | $B4DB | 140 | 96 | 555555 | 5 |
| 19 | COUNTRY | $B5A0 | 130 | 96 | 555555 | 5 |
| 20 | WALTZ1 | $B665 | 182 | 72 | 555555 | 5 |
| 21 | WALTZ2 | $B72A | 110 | 72 | 222222 | 2 |
| 22 | POLKA | $B7EF | 128 | 48 | 444444 | 4 |
| 23 | MARCH | $B8B4 | 120 | 96 | 444444 | 4 |
| 24 | BAROQUE | $B979 | 130 | 96 | 555444 | 4,5 |
| 25 | BOSSA N | $BA3E | 120 | 96 | 444444 | 3,4 |
| 26 | RHUMBA | $BB03 | 120 | 96 | 222222 | 2 |
| 27 | CHA CHA | $BBC8 | 140 | 96 | 333333 | 3 |
| 28 | SALSA | $BC8D | 100 | 96 | 333334 | 3,4 |
| 29 | TANGO | $BD52 | 112 | 96 | 444444 | 4 |
| 30 | SAMBA | $BE17 | 120 | 96 | 111111 | 1 |
| 31 | FUSION | $BEDC | 110 | 96 | 212111 | 1,2 |

Worked example, FUNK2 (+$00 = `32 22 33`): drums BASIC b2:$41EF, VAR b3:$BD12, F>O b2:$4C9C, F>V b2:$4D0B, INTRO b3:$BEEB, END b3:$BF96. A.BASS BASIC Ma/mi/7 = b2:$4003/$4003/$446F, so Ma and mi share the bass line.

---

## 4. Chord recognition **[C]**

Input bitmaps (128-note, 16 B each): `$249C-$24AB` (lower/arranger keys), `$258F-$259E`, `$25FF-$260E` (MIDI "note to arranger" / arranger-loop sources **[I]**). They are ORed into `$24AC-$24BB` (`$4354-$436F`), then:
1. `$44C5`: lowest note -> `$245A`. `$4485`: fold to a 12-bit pitch-class set in D.
2. `$459C`: list up to 5 pitch classes (`$1B..$1F`, `$1B` = lowest), make them intervals over the lowest, dispatch on the count via `$F61B` + 3n.
3. Result byte -> **`$2453` = (type<<4) | root**. Previous = `$2455`. `$2454` = the same detector run on `$247C` (other keyboard zone, `$41C7`). Display `$4FCE`: type name `$6AD9`+4·type, root name `$D7A4`+2·root.

| n | Routine | Table (entry = intervals..., code) |
|---|---|---|
| 0 | `$4767` | -> $A0 (no chord) |
| 1 | `$FEEB` | only if intelligence (`$244E.0`): Major on that note |
| 2 | `$FE84` | intelligence only: `$A42E-$A443`, 11×(i, code) |
| 3 | `$FE1D` | `$A47A-$A4A0`, 13×(i1,i2,code); else (intelligence) `$A444-$A479`, 18 incomplete 7ths |
| 4 | `$FDFA` | `$A4A1-$A4F4`, 21×(i1,i2,i3,code) |
| 5 / no match | `$45DD` | fallback: type 13 if a 10/11 interval is present, 12 if a 3/6, else 11; root = lowest |

Code: high nibble = type, low = root offset above the lowest note. $C = root is the lowest key (`$46A7`, `$FEA8`). Examples: (4,7)->Ma+0, (3,8)->Ma+8 (1st inversion), (4,8)->Aug/lowest, (2,7)->Su4+7, (3,6,9)->Dim, (4,7,10)->7, (4,7,11)->Ma7, (3,7,10)->mi7, (3,6,10)->m7b5, (5,7,10)->Su7.

**Types** (names `$6AD9`): 0 Ma, 1 Aug, 2 Su4, 3 mi, 4 Dim, 5 7, 6 Ma7, 7 mi7, 8 "0" (half-dim), 9 Su7, 10 = none ($A0), 11-13 = unrecognised.

**Chord -> pattern class** (dispatch `$C5F1` via jump table `$C722`, 14 entries): types 0-2 -> class 0 Major (`$C74C`); 3-4 -> 2 minor (`$C79E`); 5-9 -> 4 seventh (`$C7A6`); 10 -> accompaniment stops (`$C7AE`->`$E8D1`, drums go on **[I]**); 11/12/13 -> class 0/2/4 with `$6A.1` set (free-voicing mode, `$C7BA-$C7D0`). This runs every tick while playing (`$C5E9`) **[C]**.

## 5. Transposition by the chord **[C]**

`$D278` (all chord parts): note' = note + alteration(type, note mod 12) + root'.
- Alteration table **`$ED6A`**, 2 bytes per type. Each byte: low nibble = pitch class to change, high nibble = signed shift. Ma 00 00 | Aug 17 19 (G->G#, A->A#) | Su4 14 (E->F) | mi 00 | Dim F7 (G->Gb) | 7 00 | Ma7 1A (Bb->B) | mi7 F4 (E->Eb) | ø F4 F7 | Su7 14. So 10 chord types come from 3 recorded patterns (C, Cm, C7).
- root' = root, or root-12 if root ≥ 8 (`$D2B3-$D2BE`). The transposition range is -4..+7 semitones, so the accompaniment stays near its recorded register.
- After a chord change (`$57.6`): a result below 24 is raised one octave (`$D2BF`). Bass only (`$CA84`, `$D266`): the first note after a change snaps to the root's octave of the pattern note (skipped during intro/ending, `$57.4`).
- On a chord change: acc notes are cut (`$CB23/$CB42/$CB61`). Each part's new-class pattern is entered at the same bar and tick (`$C968`, `$CBDE`, `$CD9D` walk deltas up to `$26-$24`, using the bar counters). The bass re-strikes its current note at the new pitch if ≥ 3 ticks remain (`$CA18-$CA54`).
- Free-voicing (types 11-13, `$CD3A`/`$CED3`): the pattern's 3rd/5th/7th are swapped for the held notes `$1C-$1E`, over the lowest key `$1B` **[C]** code / **[I]** purpose.

---

## 6. Sound effects (SFX part) **[C]**

- 37 keys (notes 76..112) -> sequence ptr `$BFA1 + 2·(note-76)` (bank 0). Bank nibble `$BFEB + (note-76)/2` (all = bank 1). Start code `$40E7-$4123`. Data b1:`$52E1-$5925`, style event format, note = field + 60 (`$C693`), loop on end (`$C682`).
- Keys 76-108 = 33 SFX that each re-strike their own ch10 note (repeats/pans). Keys 109-112 = the 4 "effect mixtures" (multi-note), which take all 4 voices (`$C6A1` `cmpa #109`). This matches the manual's 33 SFX + 4 mixtures. Per-voice state: key `$3F-$42`, note `$3B-$3E`.

---

## 7. Composer / sequencer (6 tracks, 3 songs)

**Memory [C]**: song s (1-3) = battery-RAM page s at `$2000-$3FFF` (`$180D` bits 0-1, current page `$A6`, select `$DD40`). Init `$DA34`:
| Addr (in page) | Content |
|---|---|
| `$2000-$20BF` | 6 track block lists, 32 B each (track t at `$2000+32t`); entry = high byte of a data block |
| `$20C0-$20DE` | free-block stack, block #s $3F..$21 |
| `$20E0-$20EB` | per-track cursor into its block list (init `$2000+32t`); `$E195` advances `$7A:$7B` and on wrap loads the next block # |
| `$20EC` | free-stack pointer (init $20DE) |
| `$20EE/$20EF` | track-used masks (`$DBC5`) |
| `$20F0-$20FF` | signature from `$DA83`: high-bit ASCII "GIOBBI", $0A, "ROBERTG", then `01 F4` (a hidden dev credit) |
| `$2100-$3FFF` | 31 data blocks × 256 B, shared by the 6 tracks; filled with $FE (= end) |

Tracks: 0 SOLO, 1 LOWER, 2 ARRANGER (chord notes + style/panel commands), 3 M.BASS, 4 M.DRUMS, 5 SFX **[C]**. The recorder `$D7F1` gets B = 0 from SOLO `$4292`, 1 from LOWER `$417D`, 2 from arranger chord `$4331`, 3 from M.BASS `$4168`, 5 from SFX `$4138`; the demo track contents match.

**Event format [C]** (reader `$D974-$D9F1`, fetch `$E1B8`, writers `$D7F1` note / `$D82E` command):
```
note:    nn(<$80)  vv (b7 = delta follows, b6-0 velocity, 0 = off)  [delta]
command: ss(>=$80, b6 = delta follows, ss&$1F = cmd 0-27)  dd  [dd2 if cmd=1]  [delta]
delta:   one or more bytes, each b7=1 -> 127 ticks and continue; last byte < $80 = remaining ticks (24 PPQN)
$FE = end of track.   The writer adds the delta to the previous event later ($DDBB).
```
Command dispatch `$E1EE` (28 entries). Known codes (from the recorder call sites, track in `$71`): cmd1 = 2-byte (pitch bend; centre $0040 at `$E278`) **[I]**; cmd7 = melody intelligence `$0C.1` (SOLO track); cmd8 = ADVANCED `$0C.3`; cmd9 = FILL>VAR; cmd10 = FILL>ORIG; cmd12 = INTRO/ENDING; **cmd13 = TEMPO** (data = BPM, `$83EE`); cmd23 = BREAK; cmd4 = tone change **[I]**; cmd11 = sync start **[I]**. Panel actions are recorded on the ARRANGER track as `[$70][$72]` (`$D862-$D885`) and replayed through `$E242`->`$EE9A`.

Transport **[C]** mech / **[I]** labels: `$0E.7` = record, `$0E.6` = play. `$A2` = record-track mask, `$A4` = play-track mask; per tick each track is either recorded (delta counter `$79` counts up) or played (counts down). Punch-in arms at a bar end (`$D93A-$D946`: `$24`=1, `$A3`->`$A4`). Song position `$9F:$A1`.

**Demo songs [C]**: table `$E716`, 5 × 14 B = 6 track ptrs + track mask + `$180D` value ($10 = bank 1). Start `$DBE2`, chain to the next demo `$C3A3`.
| Demo | Ptrs | Mask | Length |
|---|---|---|---|
| 1 TIME OUT | $9717.. | $2F | 28 bars |
| 2 YAH YAH! | $A287.. | $3F | 70.5 |
| 3 PASADENA | $70D7.. | $2F | 40.6 |
| 4 MY RADIO | $87F7.. | $3F | ~20 |
| 5 YUPPI | $7B07.. | $35 | 32.9 |

**Arranger loop [C]**: RAM `$2DA5-$30A2`, chord-note events in the same note+delta format, $FE end (`$A138-$A1F6`).

## 8. User programs / panel block **[C]**

- Panel = 80 B at **`$2400-$244F`**. Defaults are copied from bank 0 `$A3CF-$A41E` at factory init (`$D2E3`).
- Known fields: `$2400-$2408` part on/level (bit 7 = on, low 7 = %), in the order SOLO, LOWER, ACC1, M.BASS, DRUMS, EFFECT, ACC2, ACC3, A.BASS. `$240C` style. `$241B` tempo. `$243F-$2447` ext. TX channels (SOLO..EFFECT, default ch4,3,5,6,7,8,2,10,11). `$244A` style-PC channel. `$244C.5` style-tone PC TX. `$244D.7` clock TX. `$244E.0` chord intelligence **[I]**.
- Storage: slot address `$30AF + 80·n` (`$F3E7`), n = number (1-8, `$2683`) + 8·bank (`$2678`): **48 programs `$30FF-$3FFE`** plus slot 0 `$30AF`. Factory programs: bank 1 `$BC6F-$BEEE` (8 × 80 B) copied 6 times (`$D7C4-$D7E6`); marker `$30AD`=$4A. `b1:$BA21` loops over all 49 slots (`ldab #$31`), probably a range check **[I]**.

## 9. Memory card **[C]**

Card in the `$4000-$BFFF` window with `$180D`=$08 (+ RAM page in bits 0-1 for direct copies). Status = card `$BFFF` & 3 -> `$AF` (bit 1 = card present **[I]**; PORTD.3 -> `$AF.7`, write protect **[I]**). Removing the card while a card style plays -> stop + `clr $240C` (`$D4DC-$D4F4`).

**Header check `$D49B`**: compare card `$4000-$400B` with "Roland PROE " (`$D441`). On a mismatch at index ≥ 7, compare the rest against "E-20 " (`$D44A+i` = `$D451`) (`$D513`), so it accepts "Roland E-20 ". Then `$400C/$400D` = 'D'/~'D' (or 'N'/~'N' -> `$AF.6`), and `$400E/$400F` = 'X'/~'X' (Pro-E RAM card, `$AF.5`) or 'Q'/~'Q' (style card, `$AF.4`).

| Card | Layout |
|---|---|
| **TN-SC1 style ROM** (E-20 format) | word at card `$4020` -> 128 B names (8 × 16) -> RAM `$26A9-$2728`; word at `$4022` -> **8 × 197 B style records -> RAM `$2729-$2D50`** (`$D546-$D581`). Pattern bank nibbles 8/9 -> `$180D`=$08/$0C **[I]** |
| **Pro-E RAM card** (writer `$D419`) | `$4000-$400F` "Roland PROE D" $BB 'X' $A7, `$4010-$401F` zero; `$50FF-$5FFE` 48 user programs (`$D3B8`/`$D410`); songs 1/2/3 at `$6000-$7FFF` / `$8000-$9FFF` / `$A000-$BFFE` (`$D3A6`/`$D394`/`$D382`). Load `$D3C8`/`$D3DD`; save `$D3FB`/`$D410`, write-verify 5 retries (`$D369`->`$D347` WRITE ERROR) |

## 10. Key RAM (arranger)
`$0C` panel mode bits (b0 transpose `$4545` [I], b1 melody intell. [I], b2 VARIATION, b3 ADVANCED, b6 SYNC STOP, b7 SYNC START (`$6EB9`, `$4573`, `$458C`)) · `$10.6` style playing · `$23` beat tick · `$24` ticks left in bar · `$25` class 0/2/4 · `$26` ticks/bar · `$56.2` downbeat · `$57` section flags (b1 F>O, b2 deferred, b3 F>V, b4 intro/end, b5 break, b6 chord changed) · `$58.3` ending active · `$5C` pending fill requests · `$B0/$B1` tick queues · `$B2-$B8` part delta counters · `$BA-$C0` part ptrs · `$C2-$C4` part banks · `$2453/$2455` chord now/prev · `$24C2-$24C9` section ptrs/banks · `$24CA-$24CD` bar counters.

## 11. Mod hooks
- **Bank checksum**: any IC7 patch must re-fix that bank's `$4000-$4001` so that word + Σ($4002..$BFFF) = 0 (checker `$ECA6`, used by test mode). `../build_fw.py` v0.1 patches the bank-0 banner (file 0x19E1) without this, so the test-mode ROM check will fail **[I]** (normal play does not seem to call `$ECA6`).
- **New styles**: change a 197-B record at `$A701+197n` and point it at data in banks 2-7, which are data only. Valid bank nibbles are 0-9 only: 10-15 would index the bitmask table `$ED52`. Reusable silent bars: IC4 `$ED84-$EDA4`.
- **Chord tables**: `$A42E-$A4F4` (bank 0); alterations `$ED6A` (IC4, 2 B per type); class map `$C722` (14 jmp entries).
- **Time**: tempo constant `$476A` (`ldx #$1312`/`#$D0`); tap limits `$6F7B`/`$6F83` and 24000 at `$6F8B`; velocity curve `$ED5A`; note offsets `$C58E` (+36 drums), `$CA77` (+24 bass), `$CCEA`/`$CE91` (+36 acc), `$C693` (+60 SFX).
- **Section program changes**: `$6DAF` ($51), `$6E24` ($50), `$6E92` ($53), `$6EF7` ($54); fill deadline `$6DDD` (`ldab #$18`).
- **Free / dead space [I]**: bank 6 `$4A30-$4A54`, `$4B58-$4B7D`, `$4C13-$4C37` (unreferenced patterns); bank 1 `$B05C-$B066` ($FE pad); bank 1 `$BEEF-$BFFF` duplicates bank 0 (the SFX tables are read with bank 0 selected, `$40F2`), so it is probably free.
- **Card styles**: 8 records at RAM `$2729`, names at `$26A9`. A homemade "Roland E-20 "+DQ card image with records whose nibbles = 8 would add 8 styles without touching IC7 **[I]**.
