# A2 - PRO-E 68HC11 user interface (IC4 v2.00 + IC7 banks 0/1)

**TL;DR**
- Panel = 8 strobes (PORTA b5-3) x 11 inputs (8 on `$1200` + PA0-PA2) = **88 switches**, scanned every 20 ms by `$4C42`, edge-detected against `$245F[12]`, dispatched through the **96-entry `jmp` table at `$F74B`** with `$60` = code | $80 (pressed). No debounce counter: the 20 ms sample interval is the debounce.
- The firmware's own test mode carries **a 5-char name for every switch** (IC7 bank 1 `$B809`, 88 x 5). Name index = strobe*11 + row. All 88 key codes below are named from that table (mapping CONFIRMED, sec. 2.4).
- **48 LEDs** = `$0B-$10` (6 x 8), multiplexed by the 2.5 ms TOC2 ISR through `$180E` (active low). `$11-$16` = the alternate frame, swapped every 500 ms: steady = same bit in both, blink = bit in one. LED `$0B+n` bit k = LED of key code n*8+k; `$10.0-3` = the 4 tempo beat LEDs.
- LCD: HD44780 on `$160D` (ctrl: b0=E, b1=R/W, b2=RS) / `$160E` (data), busy-polled. A screen = two windows (`$2663/$2664`) + two text pointers (`$2665/$2667`) drawn by `$D5AB`; `$A109` = same as a 1.3 s timed message.
- UI state = page ID `$2662` + mode flags (`$0B.4/.5` LED bits, `$5E` bits). Every 20 ms the page handler (`$FA78 + 3*(page-$0C)`) compares the dial value `$53` with its parameter. MIDI (40 items), PARAMETER (11), REVERB (6) are 32-byte-per-item list menus with a blinking-field cursor.
- The dial ("alpha dial") = **incremental encoder on PAI (PA7) + PD2**, counted in the PAI ISR `$E998` into `$53` with per-page min/max/pulses-per-step (`$51/$52/$54`).
- Power-on: RevTp = TEST MODE (bank 1 `$B067`), **FadeI = AUDIO TEST** (bank 1 `$BB7A`, sends MT-32 SysEx to the CK-34), RevOF = version, Write = factory setup. Branches at `$C24E-$C29D`.

Conventions: CPU addresses (IC7 bank 0 at $4000-$BFFF unless "bank 1" is said, IC4 at $C000-$FFFF). Timer tick = 2 us (TMSK2=$91 at `$C006`: PR=01, E/4). "20 ms tick" = `$56.1`, set by the TOC2 ISR every 8th interrupt.

Files written for this (all in `re/fw_map/`):
- `a2_bank0_full.lst` - bank 0 + IC4, 15.1k insns: vectors + every run of >=4 `7E hi lo` jump-table entries (incl. `$F74B`, `$FA72`, `$F89E`, `$F8D5`). The old `re/bank0_ic4.lst` misses all button handlers. Rebuild: `python -I a2_dis_full.py 0 a2_bank0_full.lst`.
- `a2_bank1_test.lst` - bank 1 test/audio-test code: `python -I a2_dis_entry.py 1 a2_bank1_test.lst b067 bb7a b0c2 b1e1 b3c0 b469 b20e b25e b29f b30a b5d3 b32b`.
- `a2_keymap_table.md` (made by `a2_keytable_md.py`), `a2_rng.py <lst> <lo> <hi>` (print an address range of a listing), `a2_rom.py` (byte/word/string peeks into map_bank0.bin).

---

## 1. Timing skeleton

| Source | Period | Does (UI-relevant) | Evidence |
|---|---|---|---|
| TOC2 ISR `$E901` | 1250 ticks = **2.5 ms** (`addd #$04E2`) | `$49` up-counter, `$47/$48` down-counters; every 8th tick (`$4F` & 7): dec `$4B/$4C`, set **`$56.1` = 20 ms tick**; **LED column multiplex** (sec. 3); every 200 ticks (`$17` reload $C8) toggle `$56.6` = blink phase (500 ms) | CONFIRMED `$E901-$E989` |
| TOF ISR `$E98B` | 65536 ticks = **131 ms** | dec `$19` while nonzero (UI timeout) | CONFIRMED |
| OC3 (polled flag, no IRQ) | 10000 ticks = 20 ms | gates held-key auto-repeat in `$7F1B` | CONFIRMED `$7F1B-$7F28` |
| TOC1 `$E8E5` | `$21` = 1250000 / tempo (`$476A`: `ldx #$1312`, D=$D0 ... `idiv`) | MIDI clock 24 ppqn, inc `$B0`; beat LEDs via `$C487` | CONFIRMED |
| PAI `$E998` | dial edges | dial value `$53` | sec. 6 |
| main loop `$C37F` | free-running; on each `$56.1`: `$4DED` (active sensing $FE every 13 ticks + FADE IN/OUT ramps), `$FCC0` (UI tick), `$53F1` | | CONFIRMED `$C37F-$C391` |

`$ED40` = clear `$56.1`, wait for the next 20 ms tick while polling the dial phase (`$ED40 -> $FF6C`); used as a 20 ms delay everywhere, also by bank 1. `$ED35` = busy delay of Y x 65535 x 6 cycles (Y=5 is about 1 s).

### UI tick `$FCC0` (every 20 ms)
```
$FCC0 jsr $51C3 ; jsr $9C49
      $5D.7 (demo playing)?  -> jmp $FD08 -> scan $4C42 (no page logic)
      dec $18 ; hold timers: $2D64 (TRANSPOSE hold) -> $8F02 ; $2D79 (PLAY/REC hold) -> $8FA2
      $2662==$FF (no page) -> $4B92
      $2674 != 0 (dial lock-out) -> dec, PAII off (bclr $1024.4) -> $4B88
      else $4B40: derive $2662 from mode flags, jsr $838C (page dial handler)
$4B88 dec $4D -> <0: jsr $4BD8 (cursor blink)
$4B92 no menu open ($0B.4/.5 and $5E.1-6 clear) and $19==0 -> timed message over -> main screen
$4BD0 $58.1 (timed message up)? rts ; else jmp $7F1B (auto-repeat, then switch scan $4C42)
```
CONFIRMED (`$FCC0-$FD08`, `$4B40-$4BD5`). So **the panel is not scanned while a timed message (`$A109`) is up** (`$4BD0`).

---

## 2. Panel switch matrix

### 2.1 Hardware as the code sees it
- Strobe = **PORTA bits 5-3** (value strobe*8; bits 7-6 kept: `anda #$C0; aba`), strobes 0-7. CONFIRMED `$4C5B-$4C73`.
- Returns, active low: **`$1200` D0-D7** (8 rows) + **PA0-PA2** (3 more rows: the HC11 input-capture pins, read back from `$1000`). CONFIRMED `$4C64`, `$4C69`, `$4D20`.
- 8 x 11 = 88 switches. The bank 1 test scans the same 88 in strobe-major order (`$B2C5-$B301`: per strobe 8 bits of `$1200`, then 3 bits of PORTA; name index `$71` += 8 then += 3). CONFIRMED.
- LED rows share the strobe: `$180E` = LED row latch, active low (`$FF` = all off, written before every strobe change). CONFIRMED `$4C53`, `$E949`, bank 1 `$B5E1/$B5F5`.

### 2.2 Scan routine `$4C42` (IC7 bank 0)
```
$4C42 clr $6F ; bclr TMSK1($1022).6  -> OC2 IRQ (LED mux) off during the scan
      $2647 = PORTA & $3F (current LED strobe) ; $180E = $FF (LEDs dark)
      for b = 0,8,..,$38:  PORTA = (PORTA&$C0)+b ; $246B[i] = $1200 ; $2473[i] = PORTA
      $180E = ~LED[($2647>>3)-1 (+6 if $56.6)] ; PORTA = $2647 ; OC2 IRQ on   (no flicker)
      $4D20 x4: pack PA0-2 of strobe pairs: $2473+k = $C0 | (PA[2k]&7)<<3 | (PA[2k+1]&7)
      -> 12 raw bytes $246B-$2476 (bytes 8-11 bits 7-6 forced 1 = never pressed)
$4CB9 for i in 0..11: new = ~raw[i]; diff = new ^ $245F[i]; if diff -> $4CCC:
      $245F[i] = new   (state updated BEFORE dispatch -> handlers can test held keys)
      $264A = new & diff (pressed) ; $264B = diff ^ pressed (released) ; $2648 = i*8
$4CF1 per bit, ascending: released -> $4D32(B=0), then pressed -> $4D32(B=$80) ; inc $2648
$4D32 $60 = B | code ; X = $F74B + code*3 ; filters (2.3) ; jmp 0,x
```
CONFIRMED (`$4C42-$4D66`). Handlers start with `ldaa $60 ; bpl <release path>` (e.g. `$7178`, `$7688`, `$7988`).

**Key code** = byte*8 + bit of `$245F[12]`: bytes 0-7 = `$1200` of strobe 0-7; byte 8+k: bits 5-3 = PA2-0 of strobe 2k, bits 2-0 = PA2-0 of strobe 2k+1. Valid: $00-$45, $48-$4D, $50-$55, $58-$5D (88).

**Debounce:** none beyond the sample rate. Each 20 ms scan is compared once with the last accepted state; no counter, no second sample (CONFIRMED: nothing between `$4C64` and `$4CCC` but the compare). Bounce shorter than 20 ms is only seen if a sample lands in it.

**Callers of the scan:** `$7FB4` (end of auto-repeat `$7F1B`, normal path) and `$FD08` (demo playing); both only from the 20 ms UI tick. CONFIRMED.

### 2.3 Key filters at dispatch (`$4D41-$4D66`)
| Flag | Meaning | Lets through | Evidence |
|---|---|---|---|
| `$5D.7` | demo song playing (set `$790B`) | only code $2E START/STOP (press and release) | CONFIRMED |
| `$5E.0` | demo select (PLAY/DEMO held + USER n, set `$F446`) | releases of $10-$15 (USER1-6) and $1E (PLAY/DEMO), presses of $2E only | CONFIRMED |
| `$58.1` | timed message up | no scan at all (`$4BD0`) | CONFIRMED |

### 2.4 How the names were tied to codes (CONFIRMED)
Bank 1 switch test `$B29F`: `$B51C` -> pointer = `$B809 + 5*($71+bit)` -> `$2667` -> `$D5AB`. Its exit = strobe 4 bits 5+7 together (`$B52A: cpx #$0068 ; brclr 0,x #$A0`) = FrCrd+ToCrd, which the service notes call "TO CARD and FROM CARD together". Cross-checks, all consistent: the four boot keys (`$C095-$C0CA`) are codes $0D/$23/$2D/$5A = **RevOF / Write / FadeI / RevTp** (the service notes' REVERB ON/OFF, WRITE, FADE IN, REVERB TYPE); test-menu keys UP1-UP4 = strobe 2 D0-3 (`$B5A3`) = **User1-4**; START/STOP $2E is the one key allowed during a demo; the LED test lights exactly the 48 LED bits (sec. 3).

### 2.5 Button table
Handler = target of `$F74B + 3*code` (`7E hi lo`). LED = byte.bit in `$0B-$10` (sec. 3), "-" = no LED. Impossible codes $46/$47/$4E/$4F/$56/$57 jump to `$755E` (`rts`). "meaning" expands the 5-char test name with the owner's-manual section names (INFERRED wording; the names themselves are CONFIRMED).

| code | $245F byte.bit | strobe (PORTA b5-3) | row | test idx | test name | meaning (INFERRED from name/manual) | handler | LED bit |
|---|---|---|---|---|---|---|---|---|
| $00 | 0.0 | 0 | $1200 D0 | $00 | Style | STYLE select mode | $754B | $0B.0 |
| $01 | 0.1 | 0 | $1200 D1 | $01 | MnlBs | MANUAL BASS tone sel. | $755F | $0B.1 |
| $02 | 0.2 | 0 | $1200 D2 | $02 | LwrTn | LOWER tone sel. | $7628 | $0B.2 |
| $03 | 0.3 | 0 | $1200 D3 | $03 | SolTn | SOLO tone sel. | $7658 | $0B.3 |
| $04 | 0.4 | 0 | $1200 D4 | $04 | Midi | MIDI menu | $7178 | $0B.4 |
| $05 | 0.5 | 0 | $1200 D5 | $05 | Prmtr | PARAMETER menu | $7688 | $0B.5 |
| $06 | 0.6 | 0 | $1200 D6 | $06 | AlR/P | ARR.LOOP rec/play | $A34B | $0B.6 |
| $07 | 0.7 | 0 | $1200 D7 | $07 | AlExe | ARR.LOOP execute | $A261 | $0B.7 |
| $08 | 1.0 | 1 | $1200 D0 | $0B | Trans | TRANSPOSE (tap on/off, hold 640 ms = page) | $8EC4 | $0C.0 |
| $09 | 1.1 | 1 | $1200 D1 | $0C | MldyI | MELODY INTELLIGENCE | $FD2B | $0C.1 |
| $0A | 1.2 | 1 | $1200 D2 | $0D | Vartn | VARIATION | $76B5 | $0C.2 |
| $0B | 1.3 | 1 | $1200 D3 | $0E | AdvAr | ADVANCED ARRANGER | $6FF9 | $0C.3 |
| $0C | 1.4 | 1 | $1200 D4 | $0F | ArrHd | ARRANGER HOLD | $7031 | $0C.4 |
| $0D | 1.5 | 1 | $1200 D5 | $10 | RevOF | REVERB ON/OFF | $7142 | $0C.5 |
| $0E | 1.6 | 1 | $1200 D6 | $11 | SynSp | SYNC STOP | $6FA1 | $0C.6 |
| $0F | 1.7 | 1 | $1200 D7 | $12 | SynSt | SYNC START | $6FC8 | $0C.7 |
| $10 | 2.0 | 2 | $1200 D0 | $16 | User1 | USER PROGRAM 1 | $F41A | $0D.0 |
| $11 | 2.1 | 2 | $1200 D1 | $17 | User2 | USER PROGRAM 2 | $F41A | $0D.1 |
| $12 | 2.2 | 2 | $1200 D2 | $18 | User3 | USER PROGRAM 3 | $F41A | $0D.2 |
| $13 | 2.3 | 2 | $1200 D3 | $19 | User4 | USER PROGRAM 4 | $F41A | $0D.3 |
| $14 | 2.4 | 2 | $1200 D4 | $1A | User5 | USER PROGRAM 5 | $F41A | $0D.4 |
| $15 | 2.5 | 2 | $1200 D5 | $1B | User6 | USER PROGRAM 6 | $F41A | $0D.5 |
| $16 | 2.6 | 2 | $1200 D6 | $1C | User7 | USER PROGRAM 7 | $F41A | $0D.6 |
| $17 | 2.7 | 2 | $1200 D7 | $1D | User8 | USER PROGRAM 8 | $F41A | $0D.7 |
| $18 | 3.0 | 3 | $1200 D0 | $21 | KMMnD | key mode MANUAL DRUMS | $76D5 | $0E.0 |
| $19 | 3.1 | 3 | $1200 D1 | $22 | FllOr | FILL-IN to ORIGINAL | $6DA3 | $0E.1 |
| $1A | 3.2 | 3 | $1200 D2 | $23 | KMSnE | key mode SOUND EFFECTS | $76F0 | $0E.2 |
| $1B | 3.3 | 3 | $1200 D3 | $24 | FllVr | FILL-IN to VARIATION | $6E18 | $0E.3 |
| $1C | 3.4 | 3 | $1200 D4 | $25 | In/En | INTRO/ENDING | $6E7A | $0E.4 |
| $1D | 3.5 | 3 | $1200 D5 | $26 | Br/Tp | BREAK MUTE / TAP | $6EE4 | $0E.5 |
| $1E | 3.6 | 3 | $1200 D6 | $27 | Pl/Dm | PLAY / DEMO (hold 640 ms = PLAY SONG) | $FC89 | $0E.6 |
| $1F | 3.7 | 3 | $1200 D7 | $28 | Rc/Pi | REC / PUNCH IN | $FC90 | $0E.7 |
| $20 | 4.0 | 4 | $1200 D0 | $2C | KMSol | key mode SOLO | $7704 | $0F.0 |
| $21 | 4.1 | 4 | $1200 D1 | $2D | GrpAB | GROUP A/B | $FC49 | $0F.1 |
| $22 | 4.2 | 4 | $1200 D2 | $2E | KMLow | key mode LOWER | $FD0B | $0F.2 |
| $23 | 4.3 | 4 | $1200 D3 | $2F | Write | WRITE | $924E | $0F.3 |
| $24 | 4.4 | 4 | $1200 D4 | $30 | KMArr | key mode ARRANGER | $7829 | $0F.4 |
| $25 | 4.5 | 4 | $1200 D5 | $31 | FrCrd | FROM CARD menu | $5712 | $0F.5 |
| $26 | 4.6 | 4 | $1200 D6 | $32 | KMMnB | key mode MANUAL BASS | $782E | $0F.6 |
| $27 | 4.7 | 4 | $1200 D7 | $33 | ToCrd | TO CARD menu | $57E8 | $0F.7 |
| $28 | 5.0 | 5 | $1200 D0 | $37 | Solo+ | SOLO vol + | $7867 | ($10.0 = beat LED) |
| $29 | 5.1 | 5 | $1200 D1 | $38 | Solo- | SOLO vol - | $7867 | ($10.1 = beat LED) |
| $2A | 5.2 | 5 | $1200 D2 | $39 | SnE + | SOUND EFFECTS vol + | $786C | ($10.2 = beat LED) |
| $2B | 5.3 | 5 | $1200 D3 | $3A | SnE - | SOUND EFFECTS vol - | $786C | ($10.3 = beat LED) |
| $2C | 5.4 | 5 | $1200 D4 | $3B | FadeO | FADE OUT | $7871 | $10.4 |
| $2D | 5.5 | 5 | $1200 D5 | $3C | FadeI | FADE IN | $789C | $10.5 |
| $2E | 5.6 | 5 | $1200 D6 | $3D | St/Sp | START/STOP | $78BE | $10.6 |
| $2F | 5.7 | 5 | $1200 D7 | $3E | SnEHd | SOUND EFFECTS HOLD | $70FA | $10.7 |
| $30 | 6.0 | 6 | $1200 D0 | $42 | Lwr + | LOWER vol + | $796F | - |
| $31 | 6.1 | 6 | $1200 D1 | $43 | Lwr - | LOWER vol - | $796F | - |
| $32 | 6.2 | 6 | $1200 D2 | $44 | Acc + | ACC vol + | $7974 | - |
| $33 | 6.3 | 6 | $1200 D3 | $45 | Acc - | ACC vol - | $7974 | - |
| $34 | 6.4 | 6 | $1200 D4 | $46 | Bss + | BASS vol + | $797A | - |
| $35 | 6.5 | 6 | $1200 D5 | $47 | Bss - | BASS vol - | $797A | - |
| $36 | 6.6 | 6 | $1200 D6 | $48 | Drms+ | ACC DRUMS vol + | $7980 | - |
| $37 | 6.7 | 6 | $1200 D7 | $49 | Drms- | ACC DRUMS vol - | $7980 | - |
| $38 | 7.0 | 7 | $1200 D0 | $4D | Bank1 | BANK 1 | $7988 | - |
| $39 | 7.1 | 7 | $1200 D1 | $4E | Bank2 | BANK 2 | $7988 | - |
| $3A | 7.2 | 7 | $1200 D2 | $4F | Bank3 | BANK 3 | $7988 | - |
| $3B | 7.3 | 7 | $1200 D3 | $50 | Bank4 | BANK 4 | $7988 | - |
| $3C | 7.4 | 7 | $1200 D4 | $51 | Bank5 | BANK 5 | $7988 | - |
| $3D | 7.5 | 7 | $1200 D5 | $52 | Bank6 | BANK 6 | $7988 | - |
| $3E | 7.6 | 7 | $1200 D6 | $53 | Bank7 | BANK 7 | $7988 | - |
| $3F | 7.7 | 7 | $1200 D7 | $54 | Bank8 | BANK 8 | $7988 | - |
| $40 | 8.0 | 1 | PA0 | $13 | Nmbr1 | NUMBER 1 | $7988 | - |
| $41 | 8.1 | 1 | PA1 | $14 | Nmbr2 | NUMBER 2 | $7988 | - |
| $42 | 8.2 | 1 | PA2 | $15 | Nmbr3 | NUMBER 3 | $7988 | - |
| $43 | 8.3 | 0 | PA0 | $08 | Nmbr4 | NUMBER 4 | $7988 | - |
| $44 | 8.4 | 0 | PA1 | $09 | Nmbr5 | NUMBER 5 | $7988 | - |
| $45 | 8.5 | 0 | PA2 | $0A | Nmbr6 | NUMBER 6 | $7988 | - |
| $48 | 9.0 | 3 | PA0 | $29 | SnE g | SFX pad g | $7095 | - |
| $49 | 9.1 | 3 | PA1 | $2A | SnE h | SFX pad h | $7095 | - |
| $4A | 9.2 | 3 | PA2 | $2B | SnE i | SFX pad i | $7095 | - |
| $4B | 9.3 | 2 | PA0 | $1E | SnE j | SFX pad j | $7095 | - |
| $4C | 9.4 | 2 | PA1 | $1F | SnE k | SFX pad k | $7095 | - |
| $4D | 9.5 | 2 | PA2 | $20 | SnE l | SFX pad l | $7095 | - |
| $50 | 10.0 | 5 | PA0 | $3F | SnE a | SFX pad a | $7095 | - |
| $51 | 10.1 | 5 | PA1 | $40 | SnE b | SFX pad b | $7095 | - |
| $52 | 10.2 | 5 | PA2 | $41 | SnE c | SFX pad c | $7095 | - |
| $53 | 10.3 | 4 | PA0 | $34 | SnE d | SFX pad d | $7095 | - |
| $54 | 10.4 | 4 | PA1 | $35 | SnE e | SFX pad e | $7095 | - |
| $55 | 10.5 | 4 | PA2 | $36 | SnE f | SFX pad f | $7095 | - |
| $58 | 11.0 | 7 | PA0 | $55 | Nmbr7 | NUMBER 7 | $7988 | - |
| $59 | 11.1 | 7 | PA1 | $56 | Nmbr8 | NUMBER 8 | $7988 | - |
| $5A | 11.2 | 7 | PA2 | $57 | RevTp | REVERB TYPE menu | $7496 | - |
| $5B | 11.3 | 6 | PA0 | $4A | PlyTs | ? (PlyTs) | $7C75 | - |
| $5C | 11.4 | 6 | PA1 | $4B | UsrBk | USER (program) BANK | $F581 | - |
| $5D | 11.5 | 6 | PA2 | $4C | Cursr | CURSOR | $FC2B | - |

Groups (CONFIRMED by shared handlers): BANK1-8 + NUMBER1-8 -> one handler `$7988`, which dispatches on the tone-select mode LED: `$0B.0` STYLE -> `$7B9A` (style `$240C`), `$0B.3` SOLO -> `$7B88` (tone `$2409`), `$0B.2` LOWER -> `$7B91` (`$240A`), else MANUAL BASS (`$240B`) (`$7999-$79AE`, `$7B88-$7B9A`). STYLE/MnlBs/LwrTn/SolTn are a radio group (`$754F: bclr $0B,#$0E ; bset $0B,#$01`). SFX pads a-l -> `$7095` (pad 0-11 from the code: `andb #$0F`, -2 for the $48 row; acts when `$0E.2` KMSnE is lit). USER1-8 -> `$F41A`. Part +/- pairs -> `$7867/$786C/$796F/$7974/$797A/$7980` -> `$7CA3` with channel B = 0-5 (SOLO, LOWER, ACC, BASS, ACC DRUMS, SOUND EFFCTS).

### 2.6 Held keys, combos, hold timers
- **Auto-repeat** (`$7F1B`, runs when OC3 has expired): only the 12 +/- keys (`$2464` bits 0-3 = Solo+/-, SnE+/-; `$2465` bits 0-7 = Lwr/Acc/Bss/Drms +/-). Both keys of a pair held = no repeat (`$7FBC: brset 0,x #$02`). Direction `$56.7` (1 = +). Per channel i (0-5): `$264C+i` = ticks to next step, `$2652+i` = stage, `$2658+i` = steps left in the stage. Stage bytes **`$5847-$584A` = A1 A2 4F 0F** = (steps<<3 | period): a press arms stage 3 (`$7EB4`: X=`$584A`), giving 1 step after 7 ticks, 9 steps every 7 ticks (140 ms), 20 every 2 ticks (40 ms), then every tick. Each step -> `$EE71`. CONFIRMED `$7FC3-$8017`, `$7EB4-$7EEA`.
- **Hold timers** (UI tick, 20 ms units): TRANSPOSE press sets `$2D64 = $20` (`$8ECA`); still held at 640 ms -> `$8F02` TRANSPOSE page, released earlier -> tap toggles transpose on/off (`$8ECD-$8EEE`). PLAY/DEMO press sets `$2D79 = $20` (`$9061`); at 640 ms -> `$8FA2` = PLAY SONG page, or RECORD SONG if REC/PUNCH IN is also held. CONFIRMED.
- **Combos** read `$245F` directly: PLAY/DEMO($1E) + USER1-5 = choose demo, + USER6 = all demos (`$5D.5`) (`$F436-$F479`); WRITE($23) + USER n = store user program (`$F47A`); FrCrd+ToCrd held = USER ignored (`$F48B`); PlyTs($5B)/UsrBk($5C) + USER (`$F490/$F494`); WRITE+PlyTs held = main loop skips MIDI-in key processing (`$C3C1-$C3C8`). CONFIRMED addresses; what the PlyTs/UsrBk combos do is INFERRED/open.

### 2.7 Keyboard (not the panel)
IRQ `$E75C` pushes 2-byte events from `$1B7C/$1B7D` into ring `$2200` (head `$04`, tail `$05`; overflow -> `$56.4`, reset to $0200). INFERRED = IC15 37-key velocity keyscan (service notes); not traced further.

---

## 3. LEDs

| Item | Detail | Evidence |
|---|---|---|
| Frame A | `$0B-$10` = 6 bytes x 8 = 48 LEDs | CONFIRMED |
| Frame B | `$11-$16` (same layout), shown while `$56.6` = 1 | CONFIRMED `$E964-$E968` |
| Blink | `$56.6` toggles every 200 x 2.5 ms = 500 ms (`$E96E-$E97D`) = 1 Hz. Steady = `bset $0B+n` and `bset $11+n` (e.g. MIDI `$71CA/$71CD`); blink = one frame only (e.g. In/En `$0E.4` vs `$14.4`, `$6E8B/$6EC1/$6EC5`) | CONFIRMED |
| Multiplex | TOC2 ISR every 2.5 ms: `$180E=$FF`, PORTA strobe = `$4E`+8 (strobes 1-6), `$180E = ~LED[$4E>>3]`, `$4E` += 8 mod 48. 6 x 2.5 ms = 15 ms frame, 1/6 duty | CONFIRMED `$E947-$E988` |
| Mapping | LED byte `$0B+n` bit k = LED of key code n*8+k (n=0-5, codes $00-$2F), lit while PORTA strobe = n+1 | CONFIRMED by handlers: STYLE `$7555` $0B.0, MnlBs `$7572` $0B.1, LwrTn `$763B` $0B.2, SolTn `$766B` $0B.3, MIDI `$71CA` $0B.4, PARAMETER `$94E1` $0B.5, TRANSPOSE `$8EE8` $0C.0, AdvAr `$7007` $0C.3, ArrHd `$703C` $0C.4, RevOF `$714D` $0C.5, SynSp `$6FAC` $0C.6, SynSt `$6FD3` $0C.7, In/En `$6E8B` $0E.4, FadeO `$787C` $10.4, FadeI `$78A4` $10.5, SnEHd `$7116` $10.7 |
| Beat LEDs | `$10.0-$10.3` (the slots of Solo+/-, SnE+/-, keys without LEDs) = 4 tempo LEDs: downbeat lights bit 3 (`$C4D5-$C4DE`), other beats shift it (`$C4A4 jsr $D2D8`), off after 4 clocks (20 when stopped) (`$C4BC-$C4CD`) | CONFIRMED |
| LED test order | bank 1 `$B9C1-$BA20` = 48 (mask, byte) pairs lit one at a time (`$B342`): RevOF FadeI FadeO User1-3 Rc/Pi Pl/Dm User4-5 GrpAB Write FrCrd ToCrd FllOr FllVr KMSol KMLow KMArr KMMnB KMMnD KMSnE User6-7 ArrHd SynSt SynSp Vartn User8 Style AdvAr SnEHd MnlBs LwrTn SolTn AlR/P AlExe Midi Prmtr Trans MldyI In/En Br/Tp beat4..beat1 St/Sp. Likely a physical sweep across the panel (INFERRED) | CONFIRMED table |
| No LEDs | strobes 6-7 and all PA rows: part +/-, BANK/NUMBER, SFX pads, PlyTs, UsrBk, CURSOR, RevTp | CONFIRMED (not among the 48) |

LED bits double as UI state: `$0B.4` = MIDI menu open, `$0B.5` = PARAMETER open, `$10.6` = arranger running (46 tests), `$0F.0/.2/.4/.6` = key modes. CONFIRMED (`$4B40`, `$D5A1`, `$EF2E`).

---

## 4. LCD driver (IC4)

`$160D` = control latch: **bit0 = E, bit1 = R/W, bit2 = RS**; upper bits unused (`$F8` for commands, `$04` data write, `$06` data read). `$160E` = data (read: bit7 = busy). CONFIRMED.

| Routine | Does | Evidence |
|---|---|---|
| `$D5E9` | busy wait: `$160D` = `$02`,`$03`,`$02` (status-read strobe), read `$160E`, loop while bit7; falls into `$D5FD` | CONFIRMED |
| `$D5FD` | `$160D = B`, then `B|1` (E high); X = $160D | CONFIRMED |
| `$D611` | `$160E = A`, `$160D = B & $FE` (E low = write) | CONFIRMED |
| `$D609` | busy wait + write byte (Y)+ with control B | CONFIRMED |
| `$D607` | `$D609` with B = `$04` (data) | CONFIRMED |
| `$D619` | X x 3 us delay, then write `$30` with no busy check | CONFIRMED |
| `$D5C2/$D5D5/$D5E0` | window writer: command `$80+col` / `$C0+col` (DDRAM address), then len chars from Y | CONFIRMED |
| `$4C0F` | **reads DDRAM back** (control `$06`) into `$2D54+col` for the cursor blink | CONFIRMED |

**Init** (`$C151-$C17F`, after the boot-key read): `$30` after 15 ms (X=$1388), `$30` after 4.1 ms (X=$0557), `$30` after 102 us (X=$0022) = HD44780 init by instruction; 7 commands from **`$5982` = 38 0C 06 01 02 10 40** (8-bit, 2 lines, 5x8 / display on, cursor off / increment / clear / home / shift / CGRAM addr 0); then 64 bytes **`$5989-$59C8` -> CGRAM chars 0-7**. Banner `$59E1`/`$59F1` ("  ROLAND PRO-E  " / "INTELL. ARRANGER") for about 1 s (`$C18A-$C19D`). CONFIRMED.

**CGRAM glyphs** (IC7 file 0x1989-0x19E0, right before the banner):

| char | data at | Glyph | Use |
|---|---|---|---|
| 0 | `$5989` | inverse "3" | ACC BALANCE "1 2 3" marks (INFERRED) |
| 1 | `$5991` | eighth note | main screen "note=120" (`$4F08`: `ldab #$3D ; ldaa #$01` -> char 1 + "=") CONFIRMED |
| 2-5 | `$5999-$59B8` | bar graph 1/2/3/4 columns lit | balance level bars (INFERRED; a full cell is HD44780 $FF) |
| 6 | `$59B9` | inverse "1" | ACC BALANCE (INFERRED) |
| 7 | `$59C1` | inverse "2" | ACC BALANCE (INFERRED) |
| alt 2 | `$59C9` | small "b" | **group-B mark** after a tone number (`$4F44`: tone bit6 -> char 2) CONFIRMED |
| alt 3 | `$59D1` | inverse 3x5 "M" | BASS BALANCE "man" (INFERRED) |
| alt 4 | `$59D9` | inverse 3x5 "A" | BASS BALANCE "acc" (INFERRED) |

The 3 alternates are loaded into CGRAM 2-4 (command `$50` = CGRAM addr 16, data `$59C9-$59E0`) by the main screen (`$4F21`), the BASS balance page (`$7CC9`, `$7E13`) and `$7592`; the standard set comes back via `$7E30` (command `$40`, `$5989-$59C8`). CONFIRMED.

---

## 5. Display / menu system

### 5.1 Draw API
| Symbol | Meaning | Evidence |
|---|---|---|
| `$2663` / `$2664` | window for line 1 / line 2: high nibble = chars-1, low nibble = start column; high nibble 0 = line not drawn (so 1-char windows are impossible) | CONFIRMED `$D5C2-$D5D2` |
| `$2665` / `$2667` | text pointer for line 1 / line 2 (ROM string or the RAM buffer); text[0] lands at the window start | CONFIRMED |
| `$262D-$263C` | 16-byte RAM line buffer | CONFIRMED |
| `$D5AB` | draw both windows | CONFIRMED |
| `$D5A1` | `$D5AB` unless a menu owns the LCD (`$0B.4/.5` or any of `$5E.1-6`); used by background redraws | CONFIRMED |
| `$D582` / `$D58E` | windows = `$F0F0` (both lines full) / `$00F0` (line 2 only) | CONFIRMED |
| `$D593` | fill `$262D` with 16 spaces | CONFIRMED |
| `$4E9E` | `$2663/4 = D`, returns D = `$262D` (caller stores it into `$2665` or `$2667`) | CONFIRMED |
| `$5189/$5193`, `$5177`, `$517D` | byte / word -> ASCII decimal at `$6F-$71`; copy 3 digits to X; copy B+1 bytes (Y) -> (X) | CONFIRMED |
| `$A109` | **timed message**: page $0C, `$2D87=$FF` -> `$EF22` closes every menu, `$58.1` = on (scan paused), `$7DFC` ($19 = 10 TOF = 1.31 s, TOI on), full windows, draw | CONFIRMED |

Full screen: `ldd #line1 ; std $2665 ; ldd #line2 ; std $2667 ; jsr $D582 ; jsr $D5AB` (or `jsr $A109` for a message, e.g. at `$9E37`, `$9E6F`, `$9ED3`, `$9F12`, `$A006`). Field update: `ldd #$WWLL ; jsr $4E9E ; std $2667 ; <fill $262D> ; jsr $D5A1 ; jmp $D593`.

Message timeout (`$4B9E`, no menu open and `$19` = 0): TOI off, `$19=$80`, clear `$58.1`, `$265E=0`, dial = tempo (`$54/$55`=2, `$51/$52`=$15/$FA, `$53` = `$241B`), page $0C, redraw `$4E77`. CONFIRMED. Menus set `$19.7` and `$4B92` skips the check while they are open.

### 5.2 Main screen `$4E77` (page $0C)
| Window | Field | Source | Evidence |
|---|---|---|---|
| L1 col 0-10 (`$A000`) | style: bank digit 1-4 or "C" (card), number 1-8, 7-char name from `$63D9 + 8*i` (32 internal: ROCK1 ... FUSION) or card name in RAM `$26A9 + 16*n` when `$240C.5` | `$240C` | `$4EA8` CONFIRMED |
| L1 col 11-15 (`$4B00`) | char 1 (note) "=" tempo (3 digits) | `$241B` | `$4EFF` CONFIRMED |
| L2 col 0-2 / 3-5 / 6-8 | tone numbers "BN" (+ char 2 if group B) for MANUAL BASS / LOWER / SOLO | `$240B` / `$240A` / `$2409` (bits 5-3 bank, 2-0 number, 6 = group B) | `$4F21/$4F6C/$4F7B` + `$4F44`; part names from `$79AE/$7B88/$7B91` CONFIRMED |
| L2 col 9-10 (`$0019`) | digit '1'+`$2678` | `$2678` (not traced) | `$4F8B` |
| L2 col 11-15 (`$004B`) | chord: root from `$D7A4` (2-char note names) + type from `$6AD9` (4 bytes each: "Ma ","Aug","Su4","mi ","Dim","7  ","Ma7","mi7",...); "*****" if `$2453>>4 > $0A`, blank if = $0A | `$2453` | `$4FA5-$5002` CONFIRMED |

### 5.3 Page ID `$2662` and the per-tick dial dispatch
`$4B40` re-derives the page from flags every tick (first match wins): `$0B.4` -> $13, `$0B.5` -> $14, `$5E.6` -> $0D, `$5E.3` -> $15, `$5E.4` -> $0E, `$5E.5` -> $0F, `$5E.2` -> $10, `$5E.1` -> $11. Then `$838C`: page < $09 -> nothing; $09-$0B -> tempo (`$5B.7` reloads `$53` from the tempo); $0C-$15 -> `jmp $FA78 + 3*(page-$0C)`; >= $16 -> tempo. `$FF` = no page, dial ignored (`$FCE9`). CONFIRMED.

| Page | Screen | Flag | Opened by | Dial range, pulses/step | Tick handler | Close (`$F865` bit) |
|---|---|---|---|---|---|---|
| $00-$05 | balance SOLO / LOWER / ACC / BASS / ACC DRUMS / SOUND EFFCTS (titles `$7C97` -> `$5A01-$5A51`) | `$265E` bit i | part +/- (`$7CA3`); if the page is already shown -> `$7D39` | none (keys) | - | - |
| $0C | main / tempo | - | default, timeout | 20-250, 2 | `$83B8` (store `$241B`, `$476A`, redraw `$4EFF`, `$D82E`) | - |
| $0D | REVERB menu | `$5E.6` | RevTp `$74A4` | 0-5 items, 16 | `$83FF` | bit2 `$749A` |
| $0E | FROM CARD | `$5E.4` | FrCrd `$573A` -> `$5746` | 0-5, 8 (`$571F`) | `$8512` | bit7 `$5716` |
| $0F | TO CARD | `$5E.5` | ToCrd -> `$5808` | 0-5, 8 | `$8561` | bit6 `$57EC` |
| $10 | RECORD SONG / SELECT TRACK | `$5E.2` | hold PLAY + REC (`$8FA2`) | 1-3, 16 | `$857D` | bit5 `$90CB` |
| $11 | PLAY SONG / SELECT TRACK | `$5E.1` | hold PLAY (`$8FA2`) | 1-3, 16 | `$8588` | bit4 `$9046` |
| $12 | unused | - | - | - | `$85D5` = `rts` | - |
| $13 | MIDI menu | `$0B.4` (LED) | MIDI `$718D` | 0-39 items, 8 | `$8957` | bit0 `$7180` |
| $14 | PARAMETER menu | `$0B.5` (LED) | PARAMETER `$94A4` | 0-10 items, 12 | `$85D6` | bit1 `$7690` |
| $15 | TRANSPOSE | `$5E.3` | hold TRANSPOSE 640 ms (`$8F02`) | -11..+11, 16 | `$8914` | bit3 `$8EF1` |

All rows CONFIRMED from the entry code (`$51/$52/$54/$2662` stores) and the tables at `$FA78` and `$F865`.

**One menu at a time:** each entry stores a close mask in `$2D87` (MIDI $FE, PARAM $FD, REVERB $FB, TRANSPOSE $F7, PLAY $EF, REC $DF, TO CARD $BF, FROM CARD $7F, message $FF) and calls `$EF22`, which walks the bits and runs `$F865 + 7*bit` = `brclr <flag>,<bit>,rts ; jmp <close>`. CONFIRMED.

**Common entry code** (MIDI `$718D-$71DA`, PARAM `$94A4-$94F1`, REVERB `$74A4-$74EB`): close the others; `$54/$55` = pulses/step; `$51/$52` = range; `$53` = current item (`$2D51` MIDI / `$2D52` PARAM / `$2D53` REVERB); **`$2674 = $0C`** = dial locked for 240 ms (PAII off in `$FCF3`); `$19.7` (no timeout); page ID; line pointers `base + 32*item` and `+16`; LED on (MIDI/PARAM); `jmp itemtable + 3*item` (draws the value and sets the cursor fields). The same key again closes the menu (`$717C`, `$768C`: `$7164`, LED off, `$19=0` -> main screen on the next tick). CONFIRMED.

### 5.4 List menus
| Menu | Strings (16+16 per item) | Item display table | Item edit table | Items |
|---|---|---|---|---|
| MIDI | `$5BD1 + 32*i` | `$F911` | `$FAC9` | 40: BASIC USER PRG C(hange) ch; per part SOLO, LOWER, ACCOMP1-3, ACCOMP BASS, MANUAL BASS, DRUMS, EFFECT, RX ONLY: "midi ch=", "rx limit low= upp=", "rx note shift="; NOTE TO ARRANGER ch + limit; MIDI SOFT THRU FOR LOCAL=; STYLE PRG CHANGE ch; STYLE-TONE PRG C rx/tx; MIDI REAL TIME rx/tx; MIDI VOLUME CC 7 rx/tx; MIDI VELOCITY rx; DATA DUMP= PRESS WRITE |
| REVERB | `$60D1 + 32*i` | `$F989` | `$FA96` | 6: REVERB type; SOLO / LOWER / MANUAL BASS / DRUMS / SOUND EFFCT part REVERB |
| PARAMETER | `$6191 + 32*i` | `$FBFC` | `$FAA8` | 11: MASTER TUNE (" . Hz"); FOOT SWITCH to =; PITCH BENDER range; SOLO / LOWER / MANUAL BASS octave; ACC. BALANCE 1 2 3; BASS BALANCE acc man; SOUND EFFECTS Style sync; ARRANGER chord intelligence; INTERNAL MEMORY protection |

There is no FUNCTION page: the string "FUNC" occurs nowhere in IC4 or IC7 (CONFIRMED by search), and the only 32-byte-per-item list menus dispatched from `$FA78` are MIDI, PARAMETER and REVERB TYPE (CONFIRMED for the pages listed in 5.3).

Other UI strings in bank 0 (dumped): page titles `$5A01-$5A5F`, factory/battery `$5AA1-$5B60`, card/record messages `$5B12-$5BC0`, `$60E1` = 16 spaces (default line 2), TRANSPOSE `$6351`, transpose note names `$6B01`, card menus `$6C03-$6C92`, style names `$63D9`, chord types `$6AD9`. IC4: `$EDA8/$EDB8` version, `$EDCD` "ver 02.00 051289", note names `$D7A4`.

### 5.5 Cursor and field editing
- `$2645` = current field (0 = item select), `$2646` = number of fields (`$76A0` sets 2 and clears `$2641/$2643`), `$263F/$2641/$2643` = (start,end) DDRAM addresses of fields 1-3 (e.g. REVERB type `$74ED`: `$263F=$C0C1` = line 2 col 0-1; card `$5772`: `$CECF`), `$263D/$263E` = the field now blinking (0 = none; `$5005` clears it). CONFIRMED.
- **CURSOR** key (`$FC2B`, only while `$0B.4/.5` or `$5E` bits 1,2,4,5,6 are set) -> `$742C` (pages $0D-$14 only): `$58.6` = "load the dial for this field", `inc $2645`; past the last field it re-enters the menu at item select (`$7450-$7478` -> `$7195` / `$94AC` / `$74AC` / `$5746` / `$5808`); else `$4D`=0 and `jmp $83AC` (page handler with the new field). CONFIRMED.
- Page handler with `$2645 > 0` (e.g. MIDI `$8975-$898D`): copy field k's addresses into `$263D`, `jmp edittable + 3*item`; the editor sees `$58.6` on its first call and loads `$51/$52/$53/$54` with the parameter's range (e.g. `$898F-$899F`), then each tick compares `$53` and writes the parameter. CONFIRMED structure; per-item ranges not listed here.
- **Blink** `$4BD8` (when `$4D` underflows): reads the field back from DDRAM into `$2D54+col` (`$4C0F`), writes spaces over it (`$60E1`) for 25 ticks (500 ms, `$4D=$19`), restores it for 15 ticks (300 ms, `$4D=$0F`); phase in `$57.7`. The HD44780 hardware cursor is never on (`$0C` at init). CONFIRMED.

---

## 6. Alpha dial (tempo / value encoder)

The test mode calls it "α-D" (bank 1 `$B753`, LCD char $E0 = α) and shows `$53` (`$B3E2`). It is an incremental encoder: phase A on **PA7 = PAI** (PACTL `$1026 = $40` at `$C23E`: PAEN, event mode, falling edge; PAII on via TMSK2 $91), phase B on **PD2** (`$1008` bit 2). CONFIRMED.

```
PAI ISR $E998: clear PAIF ; jsr $FF9D
  $FF9D: PAII off ; toggle PEDGE ; if the edge just taken was rising -> pulx/rti (no count)
  dec $55 (pulse prescaler); != 0 -> rti ; $55 = $54
  $5F.2 (last PD2) = 0 -> up:   if $53 >= $52 rti else inc
                   = 1 -> down: if $53 <  $51 rti else dec
  ($52 == $FA -> unsigned compares (tempo); otherwise signed, so TRANSPOSE can use $F6..$0B)
main-loop poll $FF7E (via $FF74 on every pass while $2674 == 0, and inside every $ED40 wait):
  if PD2 != $5F.2: $5F.2 = PD2, clear PAIF, PAII back on
```
So an A edge counts only after B has changed since the last A edge (cheap quadrature debounce): one count per A falling edge, direction = B level. **Reachable range = [`$51`-1 .. `$52`]** (down stops only once below `$51`). The ISR never acts on `$53`; the 20 ms page handler compares it with the parameter (sec. 5.3). Tempo: `$83B8` -> `$241B` -> `$476A` -> OC1 interval `$21` = 1250000/tempo. CONFIRMED (`$E998-$E9D8`, `$FF74-$FFB0`, `$C0EF-$C0FD`).

Dial contexts (pulses/step, range): tempo 2, 20-250 (`$C0EF`, `$4BB8`); MIDI 8, 0-39; card 8, 0-5; PARAM 12, 0-10; REVERB 16, 0-5; TRANSPOSE 16, -11..+11; PLAY/REC 16, 1-3; test mode CON 1-127 (`$B3CC`). CONFIRMED.

A/D (not the dial): ADCTL `$1030 = $10` (multi-channel AN0-3, one conversion): ADR1-3 = MOD / BEND / VOLUME (boot `$C0FF-$C11A` -> `$266B/$266C/$2627/$266D/$266F`; test CON `$B3DD-$B43C`). CONFIRMED addresses; channel-to-control order INFERRED from the test screen order "Mod Bend Vol".

---

## 7. Hidden power-on modes

### 7.1 Boot-key sample (`$C095-$C0CA`, IC4, before LCD init)
| PORTA | Read | Mask -> flag | Code | Key |
|---|---|---|---|---|
| $08 | `$1200` | bit 5 -> `$2460` | $0D | REVERB ON/OFF |
| $20 | `$1200` | bit 3 -> `$2463` | $23 | WRITE |
| $28 | `$1200` | bit 5 -> `$2464` | $2D | FADE IN |
| $38 | `$1000` | bit 2 (PA2) -> `$246A` | $5A | REVERB TYPE |

The flags land in the normal state array `$245F` (bytes 1/4/5/11), so the first real scan sees these keys as already held and makes no press event for them. CONFIRMED.

### 7.2 Branches (`$C24E-$C29D`, after LCD init, banner, battery check, timer setup and `cli`)
| Order | Test | Action | Evidence |
|---|---|---|---|
| 1 | `$246A.2` REVERB TYPE | `$0A`/`$180D` = `$ED49` ($10 = IC7 bank 1), `jmp $B067` = **TEST MODE** (never returns) | CONFIRMED |
| 2 | `$2464.5` FADE IN | bank 1, `jmp $BB7A` = **AUDIO TEST** (never returns) | CONFIRMED |
| 3 | `$2460.5` REVERB ON/OFF | show `$EDA8` "  ROLAND PRO E  " / `$EDB8` "VER 02.00 051289", then normal boot (stays until the first redraw) | CONFIRMED |
| 4 | `$2463.3` WRITE | show `$5AA1` " FACTORY SETUP  " / `$5AB1` "   LOADED ! !   "; `$DA34` (SRAM page via `$180D`, fill `$2000-$3FFF` with $FE, rebuild headers = composer songs cleared); `$D7BC` (`$2450` = `$A41F`; master tune `$30AD` = $4A; copy the 640-byte factory block IC7 bank 1 `$BC6F-$BEEE` six times down from `$3FFE` to `$3101`); then normal boot | CONFIRMED code; what the data means is INFERRED |
| - | none | `$C29D`: push part tones/volumes to the CK-34, enter main loop `$C37F` | CONFIRMED |

Also at boot, **battery check** `$C1A3`: PD4 (`$1008.4`) low -> " CHECK INTERNAL " / "   BATTERY !!   " (`$5B41/$5B51`) for about 1 s. CONFIRMED.

### 7.3 TEST MODE (IC7 bank 1)
- `$B067`: SCI TX off (`$102D`=0), ACIA reset, LEDs off (`$B54C` clears `$0B-$17`), "PRO E TEST MODE" (`$B663`) / "ver 02.00 051289" (`$EDCD`), wait `$19 = $28` TOF = 5.2 s (`$B4E1`, the notes' "5/6 seconds"), main menu `$B673/$B683` "MEM PAN CON KBD / UP1 UP2 UP3 UP4". CONFIRMED.
- Own key readers: `$B5A3` = strobe 2 (`PORTA=$10`), D0-3 = UP1-4 (= USER1-4), edge vs `$64`, carry set = nothing new, else X = table + 3*(bit+1) -> `jsr 0,x`. `$B5D3` = strobe 4 D7 (TO CARD) = back, edge vs `$68`; `$78.7` keeps all LEDs on (`$180E`=0) during the LED test. CONFIRMED.
- Menu tables (`7E hi lo` after a 3-byte stub): main `$B0B3` -> MEM `$B0C2`, PAN `$B1E1`, CON `$B3C0`, KBD `$B469`; PAN `$B1FF` -> MIDI loopback `$B20E` (ACIA $96, sends $55 then $AA, expects the echo), PEDAL `$B25E` (PD5 `$1008.5` ON/OFF), SWITCHES `$B29F`, LEDS/LCD `$B30A` -> `$B328` -> LEDS `$B335` (order table `$B9C1`), LCD `$B380`. CONFIRMED.
- All test strings `$B663-$B808`, switch names `$B809-$B9C0`. CONFIRMED.

### 7.4 AUDIO TEST (bank 1 `$BB7A`)
ACIA reset, LEDs off, "PRO E AUDIO TEST" (`$B7F9`) / version, then **`$BBBA-$BC6E` (181 bytes) go to the CK-34** through the SCI ring (`$E82E`), with a 20 ms wait after each `$F7`; then SCI off and `bra *` (`$BBB8`). The bytes are Roland SysEx with **model ID $16 (MT-32)**, DT1 ($12): `F0 41 01 16 12 02 00 00 ...` (timbre-temp block, sent to device ID $01), `F0 41 10 16 12 10 00 01 00 00 00 6F F7` (reverb mode/time/level = 0), `F0 41 10 16 12 10 00 16 7F 5B F7` (master volume 127), `F0 41 01 16 12 00 00 08 7F 79 F7`, then `B1 0A 3F` (ch 2 pan centre) and `91 45 7F` (ch 2 note A4 on) = the service notes' 440 Hz right / 880 Hz left tone. CONFIRMED bytes and code; the address decode (MT-32 map, ID $01 = part-addressed temp areas) is INFERRED. So the **CK-34 takes MT-32 SysEx** on the internal link.

---

## 8. Mod hooks
- Button -> action: `$F74B + 3*code` (IC4 file 0x374B), 96 x `7E hi lo`. Repoint any key; $46/$47/$4E/$4F/$56/$57 can never fire.
- Key filters `$4D41-$4D66` (demo locks). Boot-key branch `$C24E-$C29D`: a new power-on mode = sample one more key in `$C095-$C0CA` (or test `$245F`), select a bank via `$0A`/`$180D`, jump into IC7 (bank 1 already hosts code at `$B067`, so other banks can host a Rosetta menu).
- Pages: free ID $12 (`$FA8A` -> `rts` `$85D5`); IDs >= $16 fall back to tempo. A new menu = entry routine like `$718D` + a flag bit + a `$4B40` case + a `$F865` close entry + a `$FA78` slot. The `$2D87` mask already uses all 8 bits.
- Menu content: MIDI `$5BD1`/`$F911`/`$FAC9` (max item `$27` at `$719B`), PARAMETER `$6191`/`$FBFC`/`$FAA8` (max `$0A` at `$94B2`), REVERB `$60D1`/`$F989`/`$FA96` (max 5 at `$74B2`). More items need string space plus table space (the tables sit packed in IC4).
- Messages: reuse `$A109` (1.3 s, pauses scanning) or `$D582` + `$D5AB`.
- LCD: init list `$5982`, CGRAM `$5989-$59E0` (all 8 chars used, 2-4 swapped per page), banner `$59E1`, version `$EDA8` (already patched by `re/build_fw.py`).
- Dial: set `$51/$52/$53/$54/$55` plus a page ID; `$52=$FA` = unsigned mode; `$2674` = lock-out ticks.
- LEDs: write `$0B+n` / `$11+n` (both = on, one = blink). All 48 used; the TOC2 ISR only cycles 6 strobes, so strobes 0/7 have no LED drive.
- Timing hooks: TOC2 ISR `$E901` (2.5 ms), UI tick `$FCC0` (20 ms), main loop `$C37F`.

## 9. Open questions
- Exact physical position of each key (the OM panel page is a scan; the LED test order `$B9C1` is a good proxy).
- PlyTs (code $5B, handler `$7C75`) and UsrBk ($5C, `$F581`) meanings; the `$2678` field on the main screen.
- Per-item value ranges of the MIDI/PARAMETER/REVERB editors (`$FAC9`, `$FAA8`, `$FA96`): not listed.
- `$180D` low bits as SRAM page select (seen in `$DA36`): confirm in the memory-map work.
- Which A/D channel is MOD, BEND or VOLUME (inferred from the test screen order only).

**TL;DR:** scan `$4C42` every 20 ms -> `$245F` edges -> `$F74B` jump table; names from bank 1 `$B809` (index = strobe*11+row); LEDs `$0B-$10`/`$11-$16` muxed by TOC2 through `$180E`; LCD `$160D/E` with windows `$2663/4` + pointers `$2665/7` -> `$D5AB`; page `$2662` + dial `$53` (PAI+PD2) polled every tick via `$FA78`; power-on RevTp = test `$B067`, FadeI = audio test `$BB7A`, RevOF = version, Write = factory.
