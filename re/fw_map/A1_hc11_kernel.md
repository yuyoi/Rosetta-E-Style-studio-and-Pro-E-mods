# A1 - PRO-E 68HC11 kernel (IC4 v2.00, $C000-$FFFF) + its use of IC7 bank 0

Static analysis of `dumps/proe_ic4_os_v2.00_051289_27c128.bin` + IC7 bank 0 (`re/map_bank0.bin`) and bank 1.
Tags: **[C]** = CONFIRMED (seen in code/data at the cited address), **[I]** = INFERRED (reasoned, not fully traced).
E clock = 2 MHz (0.5 us/cycle). TCNT runs at E/4 = 500 kHz (2 us/tick), see TMSK2 below.

Listings and tools made for this pass (all in `re/fw_map/`):
- `bank0_ic4_x.lst`: recursive listing of bank 0 + IC4 with **hex immediates**, HC11 register names, xrefs on every label, and jump-table following (runs of `7E hi lo`). 14.3k insns. Built with `-B067 -BA21 -BB7A` so the three bank-1 entry points are not decoded with bank-0 bytes (the old `re/bank0_ic4.lst` decodes bank-0 data at $BA21.. as code, which also produced fake zero-page refs above $C8).
- `bank1_ic4_x.lst` + `map_bank1.bin`: bank 1 + IC4, entries $BA21/$B067/$BB7A (only code reached from those is meaningful in bank 1).
- `ram_xref.txt`: every RAM/IO address below $4000 with the instructions that touch it.
- `hc11x.py` (full / at / xref / ram / ff), `gaps.py` (unreached ranges), `deadscan.py` (pointer search into gaps), `rng.sh` (print a listing range).

---

## 1. Boot: RESET $C003 to the main loop

### 1.1 HC11 registers written (all of them; everything else is left at reset value)

| Addr | Reg | Value | Where | Meaning / why |
|---|---|---|---|---|
| - | SP | $00FF | C003 `lds #$00FF` | stack at top of internal RAM [C] |
| $1024 | TMSK2 | $91 | C006 (2nd insn, inside the 64-cycle protected window) | TOI=1 (TOF int), PAII=1 (PAI edge int), PR1:0=01 = TCNT/4 -> 2 us tick [C] |
| $1039 | OPTION | $9A | C00B (protected window) | ADPU=1 (A/D on), CSEL=0, IRQE=0 (IRQ **level** sensitive, needed for IC15 INT), DLY=1, CME=1 (clock monitor -> CLKMON vector = $C003), CR1:0=10 (COP 262 ms, but COP is never serviced: no write to COPRST $103A anywhere, so NOCOP must be set in CONFIG) [C]/[I] |
| $103C | HPRIO | $26 | C010 | MDA=1 (expanded), IRV=0, PSEL=0110 = IRQ is the highest I-bit source (same as reset default) [C] |
| $1400 | ACIA CR | $03 then $96 | C015/C01A | master reset, then RIE=1, TC=00 (TX int off), 8N1, /64 [C] |
| $102C | SCCR1 | $00 | C058 | 8N1 [C] |
| $1000 | PORTA | $00 | C05B | PA3-PA5 column select = 0 [C] |
| $1022 | TMSK1 | $00 | C05E | all OC/IC ints off during init [C] |
| $1030 | ADCTL | $10 | C101 | SCAN=0, MULT=1, CD:CA=00: one conversion of AN0-AN3 -> ADR1-4 [C] |
| $102B | BAUD | $20 | C20B | SCP=/4, SCR=/1: 2 MHz/64 = 31250 baud [C] |
| $102D | SCCR2 | $08 | C210 | TE only (TX-only link to the CK-34); TIE is set/cleared on demand later [C] |
| $1016 | TOC1 | TCNT+($21) | C21B | tempo clock, $21 set by $476A just before [C] |
| $1018 | TOC2 | TCNT+$04E2 | C224 | 1250 ticks = 2.5 ms system tick [C] |
| $101A | TOC3 | TCNT+$2710 | C22D | 10000 ticks = 20 ms; OC3 int stays off, flag is polled ($7F1B) [C] |
| $1023 | TFLG1 | $C0 | C236 | clear OC1F/OC2F [C] |
| $1022 | TMSK1 | $C0 | C239 | OC1I + OC2I on [C] |
| $1026 | PACTL | $40 | C23E | DDRA7=0 (PA7 in), PAEN=1, event mode, PEDGE=0 (falling); RTR=00 [C] |
| CCR | | $00 | C24B `cli` + C24C `clra; tap` | clears I **and X**: XIRQ (MIDI ACIA) armed only here [C] |

Never written: INIT (RAM $0000 / regs $1000 default), CONFIG, DDRD (PD2-PD5 inputs), SPCR (SPI off, PD2-5 plain GPIO), TCTL1/2, OC1M/OC1D (no OC pin outputs, so PA3-PA6 are plain outputs), PPROG, CFORC [C: no refs in `ram_xref.txt`].

### 1.2 Boot sequence

| Addr | Step |
|---|---|
| C003-C01C | SP, TMSK2, OPTION, HPRIO, ACIA reset + config (above) [C] |
| C01F-C052 | Copies ROM (bank 0, which the gate array must select at reset: no $180D write yet [I]) into the IC15/IC16 window: $A4F5-$A574 -> $1A00-$1A7F, $A575-$A5F4 -> $1A80-$1AFF, and $1B00-$1B57 (88 bytes) = $A5F5[i mod 12] = `00 80 00 80 00 00 80 00 80 00 80 00` (black-key flags per key). The two 128-byte tables are velocity-conversion curves [C copy; I meaning] |
| C054 | `jsr $D2D4`: $1B7F = $0A (keyscan halted/config) [C write; I meaning] |
| C057-C05E | SCCR1=0, PORTA=0, TMSK1=0 [C] |
| C061-C07A | Clears $0000-$00C8 and $2400-$2DA4 (RAM page 0), **preserving $2450** [C] |
| C07D | `jsr $D2E3`: ROM $A3CF-$A41E -> $2400-$244F (80 bytes of system defaults), ROM $A422-$A42D -> $0B-$16 (LED images), $2679=$240C, $244F=$28 [C] |
| C080 | $2451/$2452 = word at $A420 [C] |
| C086-C092 | **bank 1 call**: $180D=$10, `jsr $BA21` (bank 1), $180D=$00. $BA21 range-clamps the battery-backed user-program records at $30AF.. (stride $50, field mask/min/max via $BB07) [C] |
| C095-C0CA | Boot keys, PORTA column then read $1200 (inverted): col 1 bit5 -> $2460, col 4 bit3 -> $2463, col 5 bit5 -> $2464, col 7 PORTA bit2 (PA2) -> $246A [C] |
| C0CD | `jsr $E8A8`: ring indices $00/$01=$02/$01, $02/$03=$02/$01, $06/$07=$02/$01, $04/$05=$02/$00 [C] |
| C0D0-C0FD | $59.4 set, $2D76-$2D78=1,2,3, $2673=$2662=$7A, $2682=7, $266A=2, dial: $54=$55=2, $51/$52=$15/$FA, $53=$241B (tempo) [C] |
| C0FF-C11A | One A/D pass, seeds $266B=ADR1, $266C=ADR2, $2627=ADR1, $266D=$266F=ADR3+3 (forces a first volume send) [C] |
| C11D-C122 | $2D64=$2D79=$FF (two 20 ms one-shots off) [C] |
| C125 | `jsr $5251`: queues `F0 41 10 16 12` (MT-32 DT1 header, $53B2) to the CK-34 ring [C] |
| C128-C14E | Builds $60-$6C = `10 00 04 | 04 04 04 00 00 04 04 00 0C | F7`, `jsr $526B` adds the Roland checksum: **CK-34 partial reserve** (MT-32 sys addr $10 00 04) = parts 1-3: 4, parts 4-5: 0, parts 6-7: 4, part 8: 0, rhythm: 12 (= 32 partials) [C] |
| C151-C17F | HD44780 init: 3x `$30` with delays $1388/$0557/$0022 loops ($D619), 7 commands from $5982 (`38 0C 06 01 02 10 40`), 64 bytes CGRAM from $5989 [C] |
| C181-C19D | Banner `$59E1/$59F1` "ROLAND PRO-E / INTELL. ARRANGER", `$ED35` Y=5 (Y x 65535 x 6 cyc = 0.98 s) [C] |
| C1A3-C1BF | PD4 low -> "CHECK INTERNAL / BATTERY !!" ($5B41/$5B51) + 1 s. **PD4 = battery-low input** [C] |
| C1C2-C206 | Variable init ($267A-$267E, $49, $2680, $2457-$245B, $1B/$1D = $FFFF; $2453/$2455=$A0; $24CE-$24D2=$24D4; $24D4=$7D00; $24D7=$3F) [C] |
| C209-C245 | BAUD/SCCR2, `$476A` (tempo -> $21), TOC1/2/3, $19=10, TFLG1/TMSK1=$C0, PACTL=$40, 1 s delay [C] |
| C248-C24D | `$D582` (LCD cursor $2663/4=$F0F0), CLI + TAP [C] |
| C24E-C25D | **$246A.2 -> test mode**: $0A=$180D=$10, `jmp $B067` (bank 1, "PRO E TEST MODE" at $B663) [C] |
| C260-C26C | **$2464.5 -> audio test**: bank 1, `jmp $BB7A` ("PRO E AUDIO TEST" $B7F9; sends 181 bytes of MT-32 SysEx/notes from $BBBA-$BC6E to the CK-34 via $E82E, 20 ms wait after each F7, then `bra *` at $BBB8) [C]. Service notes: audio test = hold FADE IN [doc] |
| C26F-C282 | $2460.5 -> version screen $EDA8/$EDB8 "ROLAND PRO E / VER 02.00 051289" [C] |
| C284-C29A | $2463.3 -> "FACTORY SETUP / LOADED ! !" ($5AA1/$5AB1), `$DA34` (fill RAM pages 1-3 $2000-$3FFF with $FE, song headers), `$D7BC` (copy bank 1 $BC6F-$BEEE x6 -> $30BF-$3FFE, $2450=$A41F, $30AD=$4A) [C] |
| C29D | `$ED40` = wait for the next 20 ms tick [C] |
| C2A0-C37C | $A6=1 (song RAM page 1), `jsr $E625` (3 NOPs, then song header read), voice-slot init $D239/$D250, CK-34 part setup from $2400-$2408 (`$479F,$47CB,$47EF,$47D4/$4896,...,$481C`), reverb $2409-$240B (`$EAEA,$EB27,$EB3D`), `$EADE`, `$D2CE` ($1B7F=$08 = keyscan run) [C] |
| C37F | **main loop** [C] |

Boot-key to front-panel name: test = REVERB TYPE, version = REVERB ON/OFF, factory = WRITE, audio = FADE IN (docs/INDEX.md + service notes; the bit-to-key mapping itself is [I]).

---

## 2. Main loop $C37F (cooperative, no RTOS; back edge `jmp $C37F` at C62F)

| # | Addr | Runs | What |
|---|---|---|---|
| A | C37F `jsr $FF74` | every pass | if dial lockout $2674==0: `$FF7E` re-arms the dial (PD2 change -> PAII on); then `jmp $D456` card-slot poll (bank $08, status = $BFFF&3, debounce via $18, header check at $D4A3: "Roland PROE " + D/N + X, or "Roland E-20 " + Q -> E-20 card import to $26A9-$2D50) [C] |
| B | C382 | when $56.1 (20 ms flag from TOC2) | clear flag, then: `$4DED` active-sensing TX ($FE after 13x20 ms of silence) + FADE IN/OUT volume ramp $2670->$266F; `$FCC0` = `$51C3` (CK-34 update requests in $2673, lowest bit first), `$9C49` (MIDI timeouts $269B/$269A), 20 ms timers $18, $2D64->$8F02, $2D79->$8FA2, display/dial mode ($2662, $2674) `$4B40/$4B88/$4B92` (cursor blink $4D, TOF display timeout), then panel scan `$4BD0 -> $7F1B` (TOC3 key repeat) `-> $4C42` (skipped while $58.1; in demo $FCC6 jumps straight to $4C42); `$53F1` foot switch (`$5621`, PD5) + A/D (section 6) [C] |
| B2 | C392-C3B5 | 20 ms, if not playing ($10.6=0) and demo ($5D.7) | demo song cycling: `$792F` stop, or next demo `$A5` 1..4, `$F5BF`, LCD, `$EA2C` start [C] |
| C | C3B8 loop | every pass | drain key ring ($E86F, carry set = empty): each event -> `$FD3F` dispatch by mode bits in LED bytes $0E/$0F to bank-0 keyboard handlers $406B/$403D/$4141/$42F1/$4035/$4239/$418A. Ignored while $5D.7, or while switch-image bits $2463.3 and $246A.3 are both set [C] |
| D | C3D4 `jsr $FF0B` | every pass | if ext-clock watchdog $4C==0: OC1I back on (internal tempo), clear $56.5/$5A.4; drain MIDI-IN ring ($E88B) through `$FF31`: data -> $9745, channel msg -> $9703, $FE -> $9721, $F8 -> $9BD3, $FA -> start (`$9BB7`, only if stopped and $244D.7), else $9B92 ($FC stop). $269A=$10 on every byte [C] |
| E | C3D7-C404 | if $57.0 and TFLG1.OC5F (TOC5 one-shot, ~131 ms, armed at $434D) | OR of the 16-byte flag arrays $249B/$258E/$25FE -> `$453F` [C] |
| F | C407-C425 | $5A.0 and $47==0 -> `$FD9E`; $5A.1 and $48==0 -> `$4394` | delayed chord-recognition jobs ($47/$48 = 2.5 ms down-timers) [C code; I purpose] |
| G | C428-C60F | while $B0>0 (TOC1 ticks, 24 PPQN) | one clock: `dec $B0`; $F8 out if $244D.7; on start ($59.5) reset counters/pointers; `$A118`; `$D8D0` composer song tick; beat/bar counters $23 (24..0), $24, beat LED nibble in $10/$16; arranger pattern engine $C540-$C5DF (rhythm part: event ptr $C0, countdown $B8, style bank from $24C5 hi nibble via `$C882`); chord-change dispatch through jump table $C722 (`$2453>>4`, 14 entries); restores bank 0 at C5E1 [C] |
| H | C612-C71F | while $B1>0 | $59.7 = $244E.7 (aux clock = tempo or 20 ms); 4 aux tracks x=4..1 (state $3F-$42, note $3B-$3E, ptr table $24D9-$24DF, countdown at +8, bank index $24E9-$24EC): reads events from the track's IC7 bank, loops via $BFA1 table (bank 0), notes out via `$EC7A` ($99 = ch 10) [C] |

Approximate pass time when idle: a few hundred us (no blocking waits) [I]. The loop never sleeps (no WAI); all time bases come from the interrupt counters $B0, $B1, $56.1, $47/$48/$4B/$4C, $19.

---

## 3. Interrupt handlers

Vectors $FFD6-$FFFF [C]: SCI $E787, SPI/PAOV/TOC5/TOC3/TIC1-3/RTI/SWI -> $E98A (`rti`), PAI $E998, TOF $E98B, TOC4 $E8DD, TOC2 $E901, TOC1 $E8E5, IRQ $E75C, XIRQ $E7BA, ILLOP/COP/CLKMON/RESET $C003.
Priority: XIRQ (non-maskable after TAP, nests into every handler) > IRQ (HPRIO) > TOC1 > TOC2 > TOC4 > TOF > PAI > SCI (HC11 fixed order).
Cycle counts below are hand-summed from the code (+14 entry, +12 rti) [I].

| Vector | Addr | Trigger / rate | What it does | Cost |
|---|---|---|---|---|
| XIRQ | E7BA | HD63B50 ACIA $1400 IRQ: MIDI IN byte (max 3125/s) or TDRE when TX int on | **RX** (SR bit0): read $1401; (`cmpa #$F8 ... brclr $244D` at E7CC-E7D6 is a no-op, both paths go to E7D7); if ring full ($00==$01): $56.3=1, ring reset to $0201; else force RAM page 0 (`$0A&$FC` -> `$FC97`), store at $2000+$00, inc $00, restore $180D=$0A. `$FC97` also tracks running status in $C7 and counts SysEx data bytes in $C5: **the 3rd data byte after F0 (the Roland model ID) is replaced by $22**, so the PRO-E parser ($9DB8: requires F0 41 10 22) accepts dumps sent with any model ID. **TX** (SR bit1): next byte from $2100+(++$03) to $1401 (page 0 forced), a non-realtime byte reloads the active-sensing timer $50=13; ring empty -> ACIA CR=$96 (TX int off) [C] | RX ~120 cyc = 60 us/byte (19% CPU at full MIDI rate) [I] |
| IRQ | E75C | IC15 keyscan INT (level) | if key ring full ($04==$05): $56.4=1, ring reset $04/$05=$02/$00 (IRQ re-enters and reads); else `$FC21` (ACIA ints off: CR=$16, A=$0A&$FC), $180D=A (page 0), word at **$1B7C/$1B7D** -> $2200+$04, $04+=2, `$FD95` ($180D=$0A, ACIA CR=$B6 = RX+TX int on) [C] | ~117 cyc = 59 us [I] |
| TOC1 | E8E5 | tempo: period $21 = **1,250,000 / BPM** ticks ($476A: $1312D0/$241B) = **24 PPQN** | clear OC1F, TOC1 = TCNT + $21 (re-based on TCNT, so ISR latency adds drift), `$E8F6`: inc $B0, and inc $B1 if $59.7 [C] | ~76 cyc |
| TOC2 | E901 | 1250 ticks = **2.5 ms** | clear OC2F, TOC2 = TCNT+1250; $49 (16-bit up-counter, stops at $8000); $47, $48 down to 0; $4F /8 -> every **20 ms**: $4B, $4C down to 0, inc $B1 if !$59.7, set $56.1. Then **LED multiplex**: $180E=$FF (blank), PORTA PA3-5 = column+1, $180E = ~($0B+col) or ~($11+col) when blink phase $56.6; next column of 6 ($4E = col*8). Blink: $17 counts 200 ticks -> $56.6 toggles every 500 ms. Full LED refresh 15 ms (67 Hz) [C] | ~190 cyc = 95 us every 2.5 ms (3.8% CPU) [I] |
| TOC4 | E8DD | one-shot, armed by `$9BD3` at TCNT+$09C4 (5 ms) after each received **$F8** while slaved to external clock | OC4I off, then the same tick as TOC1 (`$E8F6`). If a second $F8 arrives before it fires, $9BEA calls `$E8F6` directly. External sync: $FA -> `$9BB7` (OC1I off, start, $56.5, $4B=150), $F8 -> $4C=7 (140 ms watchdog, back to internal clock in $FF0B) [C] | ~60 cyc |
| TOF | E98B | TCNT overflow, 131 ms | clear TOF; if $19 > 0: dec $19. $19 = 10 at boot and on re-arm (`$7DFC`), so ~1.3 s; at 0 `$4B9E` disables TOI, $19=$80, resets the dial to tempo ($51-$55), $2662=$0C, redraws the main screen = **display timeout** [C] | ~35 cyc |
| PAI | E998 | PA7 edge = **alpha dial "L TRIG"** (block diagram) | clear PAIF, `$FF9D`: PAII off, toggle PEDGE; on a rising-edge interrupt return (`pulx; rti` at FFAF), on a falling edge continue: divider $55 (reload $54); step $53 up or down by the direction latched in $5F.2 (= PD2 "L DIR", sampled by `$FF7E`), clamped to $51..$52 ($52=$FA selects unsigned compare). PAII is re-enabled only by `$FF7E` when PD2 changes, so each detent needs both phases (debounce) [C] | ~60 cyc |
| SCI | E787 | TDRE with TIE (TX only, 31250 baud, 320 us/byte) | not TDRE: read SCDR, rti. Else next byte $2300+(++$07), page 0 forced via `$FC21`/`$FD95`; ring empty -> clear TIE in SCCR2 [C] | ~110 cyc per byte (17% CPU when the CK-34 link is saturated) [I] |

Polled timer flags (no interrupt): TOC3 OC3F = 20 ms key auto-repeat in `$7F1B` (keys in $2464 bits 0-3), re-armed with +10000 at 7F28; TOC5 OC5F = 131 ms one-shot ($433F-$4350, TOC5 = TCNT+$FFFF) [C].

Notes for mods:
- The ACIA-mask dance in `$FC21`/`$FD95` exists because XIRQ nests into IRQ/SCI and restores $180D from $0A on exit. Without masking, an XIRQ between "$180D = page 0" and the ring write would put the old page back [I, the code shape is C]. `$FD95` always leaves ACIA TX int **on** ($B6); an empty TX ring costs one spurious XIRQ.
- TOC1/TOC2 re-base on TCNT (`ldd $100E; addd`), not on the previous compare, so tempo runs slightly slow by the ISR latency [C].

---

## 4. Bank switching ($180D, shadow $0A)

### 4.1 Latch layout

| Bits | Use | Evidence |
|---|---|---|
| 0-1 | **SRAM page in $2000-$3FFF** (IC5 32 KB = 4 x 8 KB). Page 0 = system (rings, work area, user programs); pages 1-3 = composer songs | $DA34 loops B=1..3, `stab $180D`, fills $2000-$3FFF with $FE [C]; all ISRs force `andb #$FC` before ring access [C]; test-mode RAM test $B627 walks pages 3..0 with `orab $ED49` [C] |
| 2-3 | memory card: $08 = card window at $4000-$BFFF (header at $4000, status bits at $BFFF&3), $0C = second card page for MIDI-address pages >= 8 | $D456-$D4B7, $E6B4-$E6B9 [C read; I for $0C] |
| 4-6 | **IC7 bank 0-7** ($4000-$BFFF window) | table $ED48 = `00 10 20 30 40 50 60 70 08 0C` [C] |
| 7 | never set by any table [C]; may be a spare output (A18 for a 27C040?) [I, untested] |

Reset state must be $00 (boot reads $A4F5 in bank 0 and clears page-0 RAM before the first $180D write at C089) [I].

### 4.2 Discipline [C unless marked]
- **Home state = $00 (ROM bank 0 + RAM page 0).** IC4 code `jsr`s straight into $4000-$BFFF (399 distinct bank-0 targets in `bank0_ic4_x.lst`), and bank-0 code calls 86 distinct IC4 kernel entries (top: $D82E x31, $D582, $E84D, $D5A1, $D5AB, $D593, $E82E, $EF22).
- **No code in IC7 writes $180D** (raw search of all 8 banks for `B7/F7/FD 18 0D`: none). Every switch is in IC4 (32 sites).
- Write order is always shadow first, then latch (`staa $0A; staa $180D`), so an XIRQ in between restores the new value. The only latch writes without the shadow are at boot (C089/C092, ints masked) and inside ISRs.
- ROM bank and RAM page are independent fields: selecting a song page (`$DD40`: `$A6 | $ED48`) keeps bank-0 code mapped, but page-0 RAM ($2000-$3FFF incl. rings and $2400 work area) is then invisible; song code works in zero page ($7A-$7C, $9C-$A4, $AA-$AE).
- Data in banks 1-7 is read only by IC4 code: select, read, restore bank 0 before touching any bank-0 code. Only $0000-$00FF, I/O and IC4 are usable meanwhile.
- Running code in another bank: only these IC4 stubs: C086 (`jsr $BA21` in bank 1, returns), C255 (`jmp $B067`, test mode, no return), C264 (`jmp $BB7A`, audio test, no return). There is **no generic far-call trampoline** [C].

### 4.3 Helpers

| Addr | Name | Does |
|---|---|---|
| $FC21 | isr_enter | ACIA CR=$16 (RX/TX ints off), A=$0A&$FC (current ROM bank, page 0). Caller writes $180D (not $0A) [C] |
| $FD95 | isr_exit | $180D=B (caller loads $0A), ACIA CR=$B6 [C] |
| $FC97 | xirq_page0 | $180D=B ($0A&$FC) + the SysEx model-byte filter on A [C] |
| $D324 / $DD60 | bank0 | $0A=$180D=$ED48 (=0) [C] |
| $DD40 / $DD46 | song_page | $0A=$180D=$A6\|$ED48 (B\|$ED48 at $DD46); in demo ($5D.7) bank from $E723+$A5*14 [C] |
| $C882 | style_bank | bank = $ED48[$24C5>>4] (rhythm part) [C] |
| $C943 | part_bank | bank = $ED48[nibble of $24C4/$24C5 chosen by $25], also into $C4 [C] |
| $C648-$C65E | aux-track bank | bank = $ED48[$24E8+x] [C] |
| $E680 / $E652 / $E66E | far peek/poke for the SysEx address space | page $2691 (0-3 RAM page, $20 special, 4-7 card $08, >=8 card $0C), offset $268F/$2690 (7-bit pair); $E652 reads to $AB, $E66E writes A and verifies ($AB=$FF ok); both return through $E659 (bank 0) and auto-increment the address [C] |
| $ECA6 | rom_check(B) | select bank B, compare $4002 with $FC1D[B/2] (`06 07 11 12`), sum $4002..$4000+$67, add word $4000, zero = OK; returns with **bank 1** selected (only test mode calls it, $B4FE) [C] |
| $ECF7 | ram_check | page/bank in B, used by test mode $B639/$B65C [C] |
| $D7BC | bulk copy from bank 1 | factory defaults, see boot [C] |

---

## 5. RAM map

### 5.1 Zero page ($0000-$00C8 cleared at boot; $00C9-$00FF = stack, 55 bytes)
Reached code never touches direct-page addresses above $C7 (`ram_xref.txt`), so stack = $00C9-$00FF [C]. Worst case: main-loop calls + one I-bit frame (9) + one XIRQ frame (9) + their jsr's. **Leave it alone:** new code must not nest deeper.

| Addr | Use |
|---|---|
| $00/$01 | MIDI IN ring $2000: write / read index [C] |
| $02/$03 | MIDI OUT ring $2100: write / read [C] |
| $04/$05 | key ring $2200 (2-byte entries): write / read [C] |
| $06/$07 | CK-34 TX ring $2300: write / read [C] |
| $08 / $09 | running status to CK-34 / to MIDI OUT [C] |
| $0A | $180D shadow [C] |
| $0B-$10 | LED image, 6 columns, steady phase. Also the mode-state bits: $0E/$0F mode LEDs used by $FD3F/$55AA, $10.6 = playing, $10.4/.5 = FADE, $10 bits 0-3 = beat LED [C bit use; I names] |
| $11-$16 | LED image, blink phase [C] |
| $17 | blink divider (200 x 2.5 ms) [C] |
| $18 | card debounce (dec per 20 ms; $F6 check at D47A) [C] |
| $19 | TOF down-counter (display timeout) [C] |
| $1B-$1E | chord root/type state, saved/restored around $FD9E [I] |
| $1F/$20 | note-send temps ($EBE3.., $EC7A) [C] |
| $21/$22 | TOC1 period (tempo) [C] |
| $23, $24, $25, $26 | clocks-in-beat (24..0), beats left in bar, part index, beats per bar [C use; I names] |
| $27-$2E, $2F, $31-$34, $36-$39 | active note slots ($FF = free): 8 rhythm notes, 1 bass, 2x4 chord notes (cleared $D239) [C] |
| $3B-$3E / $3F-$42 / $43-$46 | aux tracks: current note / state (bit7 = off) / param [C] |
| $47, $48 | 2.5 ms down-timers [C] |
| $49/$4A | 2.5 ms up-counter (saturates) [C] |
| $4B, $4C | 20 ms down-timers ($4C = ext-clock watchdog 7, $4B = 150 after FA) [C] |
| $4D | LCD cursor-blink counter (25 x 20 ms) [C] |
| $4E, $4F | LED column x8, TOC2 /8 divider [C] |
| $50 | active-sensing countdown (13 x 20 ms) [C] |
| $51/$52/$53/$54/$55 | dial min / max / value / divider reload / divider [C] |
| $56 | kernel flags: .1 20 ms tick, .3 MIDI-IN overflow, .4 key overflow, .5 ext-sync running, .6 blink phase, .0 FA start [C] |
| $57-$5F | state flags (sequencer, demo $5D.7/$5D.5, panel freeze $58.1, timers armed $5A.0/.1, ext clock seen $5A.4, dial DIR $5F.2, aux clock $59.7, start pending $59.5) [C use; I names] |
| $60-$6F, $70-$77 | scratch / parameter passing (SysEx build at boot uses $60-$6C) [C] |
| $79-$7F, $9C-$A4, $AA-$AE | composer song player [C] |
| $A5, $A6 | demo index, current song RAM page [C] |
| $AF | card status: .1 present, .4 E-20 card, .5 PRO-E card, .6 'N' type, .7 PD3 (write protect?) [C/I] |
| $B0, $B1 | pending tempo ticks, pending aux ticks [C] |
| $B2/$B4/$B6, $BA/$BC/$BE, $C2-$C4 | 3 accompaniment parts: countdowns, event pointers, bank shadows [I] |
| $B8/$B9, $C0/$C1 | rhythm part countdown, event pointer [C] |
| $C5/$C6, $C7 | XIRQ SysEx byte counter, last MIDI-IN status [C] |

### 5.2 I/O and windows $1000-$1FFF

| Addr | What |
|---|---|
| $1000-$103F | HC11 registers |
| $1200 | switch return lines K0-K7 (read, column on PA3-PA5) [C] |
| $1400/$1401 | ACIA CR/SR, data [C] |
| $160D / $160E | LCD control (bit0 E, bit1 R/W, bit2 RS; $F8/$04/$06 patterns) / LCD data; busy = $160E.7 [C] |
| $180D | bank latch [C] |
| $180E | LED segment latch (written inverted, $FF = off) [C] |
| $1A00-$1B57 | velocity tables + key-colour table loaded at boot [C]; lives in **IC15/IC16** (keyscan RAM) [I, block diagram p.13] |
| $1B7C/$1B7D | key event word read by IRQ [C] |
| $1B7F | keyscan control: $0A at boot and during bulk dumps ($9F1E), $08 = run ($D2CE) [C] |

Ports: PA0-PA2 = extra switch inputs (PA2 read at boot), PA3-PA5 = column select (LEDs + switch matrix; the 20 ms scan disables OC2I while it owns PORTA, $4C45/$4C95), PA7 = dial TRIG (PAI). PD0/1 = SCI to CK-34, PD2 = dial DIR, PD3 = card bit ($D490), PD4 = battery low, PD5 = foot switch ($5621) [C].

### 5.3 SRAM pages ($2000-$3FFF, all battery backed)

| Page 0 range | Use |
|---|---|
| $2000-$20FF | MIDI IN ring [C] |
| $2100-$21FF | MIDI OUT ring [C] |
| $2200-$22FF | key-event ring, 127 events [C] |
| $2300-$23FF | CK-34 TX ring [C] |
| $2400-$244F | system parameters from ROM $A3CF ($2400-$2408 part setup, $2409-$240B reverb, $240C, $241B tempo, $243E foot-switch assign, $244D.7 MIDI clock out/sync, $244E.7 aux clock) [C use; I names] |
| $2450 | kept across boot (factory writes $A41F) [C] |
| $2453-$245E | chord state [I]; $245F-$246A debounced switch image (12 bytes); $246B-$247A raw scan [C] |
| $249B/$258E/$25FE | 3 x 16-byte flag arrays (loop step E) [C] |
| $24BC-$24EC | style pointers, banks ($24C4/$24C5 nibbles), counters, aux tracks [C] |
| $2625-$2627 | bender (14-bit) / mod value [C] |
| $262D-$263C | LCD line buffer; $2663-$2668 cursor + line pointers [C] |
| $266B-$2670 | A/D last raw ADR1-3, volume target / current [C] |
| $2673 | CK-34 update-request bits (served by $51C3) [C] |
| $268E-$2691 | SysEx address / page [C] |
| $26A9-$2D50 | card-loaded data buffer: E-20 card import copies 128 B to $26A9-$2728 and $628 B to $2729-$2D50 ($D546-$D572) [C]; other users not traced |
| $2D64, $2D79 | 20 ms one-shot timers [C] |
| $2DA4 | last byte cleared at boot [C] |
| $2DA5-$30AE | persistent, not cleared ($2DA5=$FE marker) [C] |
| $30AF-$3FFF | user programs, 80-byte records, clamped at boot by bank 1 $BA21 [C] |

Pages 1-3: composer songs (header $20C0-$20FF, track pointers $20E0.., $20EC-$20EF) [C].

---

## 6. Controllers: A/D, dial, foot switch

- A/D runs once per 20 ms in `$53F1` (polled, ADCTL=$10, waits for CCF at $5404): AN0-AN3 in one go (~64 us). **ADR4 is never read** [C].
- Each channel has +/-1 LSB hysteresis against the last raw value ($266B/$266C/$266D) and is skipped while $2463.3 and $246A.3 are both set, or in demo ($5D.7) [C].

| Ch | Control (service notes: pins 17/18/19) | Path |
|---|---|---|
| ADR1 | modulation | `$546B`: raw/2 -> exp curve $D724 (128 B, 0..$7F) -> $2627; message type $70=$82, sent through jump table $F8B3 indexed by destination $6F (from `$55AA`, mode LEDs $0E/$0F) [C] |
| ADR2 | pitch bender | `$5511`: raw&$FE -> word table $D624 (128 x 2, MSB:LSB 7-bit pairs, dead zones: 0 for raw 0-59, $4000 centre for raw 122-135, $7F7F for raw 196-255) -> $2625; $70=$81, table $F8D5 [C] |
| ADR3 | volume | `$56E0`: raw/2 -> curve $A681 -> $266F; if no fade, $2670 = it and $2673.6 = "send volume" [C] |

- Tempo is not analog: it is the **alpha dial** (PAI + PD2) whose value $53 defaults to tempo $241B with range $15-$FA; other screens reload $51-$55 (refs at $4BBA, $5721, $7197, $74AE, $8F0F, $8FCF, $94AE) [C].
- Foot switch PD5: `$5621` compares with $58.5, acts on change [C].

---

## 7. ROM integrity

- **IC4**: word $C000 = -(sum of bytes $C002-$FFFF) mod 65536, and ID byte $C002 must be $04. Checked: `$137C + sum = $0000` [C]. Verifier = test mode only (bank 1 $B146-$B163) [C].
- **IC7, every bank**: word at bank offset 0 = -(sum of offsets 2-$7FFF); ID byte at offset 2 = `06 06 07 07 11 11 12 12` for banks 0-7, checked against $FC1D by `$ECA6` [C: all 8 banks sum to 0].
- No normal-boot path calls either check (the only `addd $C000` / `addd $4000` sums are at bank 1 $B160 and IC4 $ECD4) [C]. **`re/build_fw.py` v0.1 does not fix these words**, so its images run but would fail the test-mode ROM test. Add the fix-up.

---

## 8. Free space and patch hooks

| Where | Size | State |
|---|---|---|
| IC4 $FFB1-$FFD5 | 37 B | all $FF, just below the vectors, unreferenced [C]. The only true free run in IC4 |
| IC4 $E625-$E627 | 3 B | NOPs at the target of boot `jsr $E625` (C2A4): a ready-made **boot hook** (put `jsr`/`jmp` here) [C] |
| IC4 $E7CC-$E7D6 | 11 B | no-op compare/branch inside XIRQ RX (both paths reach E7D7, X is reloaded later): **MIDI-IN hook** in interrupt context [C] |
| IC4 $E765, $E79E | 1 B each | NOP after `jsr $FC21` in IRQ/SCI [C] |
| IC4 $ED46-$ED47 | 2 B | `nop; rts` after `jmp $FF6C`, unreachable [C] |
| IC4 $E6E9-$E70F | 39 B | code that no jsr/jmp/ldx/ldd in IC4 or any IC7 bank points at (song counter $20FE helpers) [I: probably dead, check for computed jumps first] |
| IC7 bank 0 | ~0 | no $FF run >= 6 bytes; 77 $FF bytes in total, scattered; space only by reclaiming strings/tables [C] |
| IC7 bank 1 | 4 runs: $A91A-$A940 (39), $ADBE-$ADE3 (38), $AF54-$AF73 (32), $B026-$B04F (42) | $FF, but only mapped with $180D=$1x (test-mode bank) [C] |
| IC7 banks 2-7 | none | style data [C] |
| Bigger IC7 | +256 KB | only if $180D bit 7 really drives IC7 A18 on a 27C040 [I, needs a probe/scope test] |

Other hook points:
- Jump tables in IC4 (easy redirects without moving code): panel switches $F74B (3-byte `jmp`, index = col*8+bit, through `$4D32`), mod destinations $F8B3, bend destinations $F8D5, chord-change $C722, more at $F61B/$F911/$FA7B/$DDE2/$E1EE [C].
- MIDI-IN dispatcher `$FF31` (IC4) -> bank-0 handlers $9703/$9745/$9721/$9B92 [C].
- CK-34 output: every byte goes through `$E82E` (running status in $08). A far-call trampoline (save $0A, select, `jsr 0,x`, restore) fits in the 37 free bytes at $FFB1 [I].
- Do not use direct-page RAM above $C7 (stack), and remember that while a song page is selected the $2000-$3FFF system RAM is gone.

---

## 9. CK-34 link facts found here
- Link = plain MIDI bytes at 31250 baud with running status ($E82E) [C].
- Boot sends MT-32 DT1 (model $16, device $10) `F0 41 10 16 12 10 00 04 04 04 04 00 00 04 04 00 0C sum F7`: partial reserve [C].
- The audio test ($BB7A bank 1) sends MT-32 DT1 to tone/patch temp (`F0 41 01 16 12 02 00 00 ...` 140 bytes, device **$01**), system `10 00 01` (reverb) and `10 00 16 7F` (master volume), then `B1 0A 3F`, `91 45 7F` [C]. So the CK-34 accepts MT-32 SysEx incl. tone editing, under device IDs $10 and $01 [C for what is sent; I that both IDs are honoured].

---

## 10. Open questions
1. Is $180D bit 7 wired to IC7 pin 1/31 (A18 on a 27C040)? If yes, 8 more 32 KB banks for new code. Needs a probe test with a burned 512 KB image whose upper half differs.
2. Exact IC15 register map at $1B7C-$1B7F and the key word layout (A = key + bit7 flag, B = velocity; $FD3F turns velocity 0 with A.7=1 into $7F) [I].
3. Are $E6E9-$E70F (39 B) and $DCAD-$DD3F (147 B) really dead, or reached through a computed jump? No absolute pointer to them exists in any ROM.
4. Does the CK-34 honour device ID $01 (audio-test stream) as well as $10, or does it ignore the device byte?
5. What is the $2463.3 + $246A.3 switch combination that mutes keyboard and controllers ($C3C1, $546B, $5511, $5621)?
6. Gate-array reset state of $180D (assumed $00: boot reads bank 0 and clears page-0 RAM before the first write).
