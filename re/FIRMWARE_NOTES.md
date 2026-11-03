# PRO-E firmware notes (IC4 OS v2.00, 05-12-89)

Source: dumps/proe_ic4_os_v2.00_051289_27c128.bin, mapped at $C000-$FFFF.
Listing: re/ic4.lst (recursive disasm from the vectors, capstone M680X 6811; covers 7.5 of 16 KB, the rest is data/tables).
Rebuild: `python -I hc11dis.py <bin> ic4.lst`, then `python -I refs.py ic4.lst` for the I/O tally.

## Big picture
- The EPROM is only the **kernel**: reset/init, interrupt handlers, MIDI and serial drivers, LCD, bank switching.
- Most of the program (arranger, composer, UI) runs out of **IC7 (LH532355, 2 Mbit mask) through a window at $4000-$BFFF**. IC4 jsr/jmp's into $4000-$BFFF all over.
- $180D = gate-array latch that selects the IC7 bank (and other bits); RAM shadow at $0A. Pattern: `ldaa table; staa $180D; jsr $Bxxx; restore`.
- So custom firmware needs IC7 dumped too, and the "512/2M" jumper suggests IC7 can be an EPROM.

## Memory map (from code)
| Addr | What |
|------|------|
| $0000-$00FF | HC11 internal RAM (zero page vars; SP = $00FF) |
| $1000-$103F | HC11 registers |
| $1200 | switch matrix read (column via PORTA $1000) |
| $1400/$1401 | HD63B50 ACIA = **MIDI** (ctrl/status, data). Init $03 reset, then $96 = RX IRQ, 8N1, /64 |
| $160D/$160E | LCD (HD44780-style; $160E bit 7 = busy) |
| $180D, $180E | gate-array control latch (IC7 bank etc.) |
| $1A7F.. | RAM table copied from ROM $A4F5-$A574 at boot |
| $2000-$20FF | MIDI IN ring buffer (idx $00/$01) |
| $2300-$23FF | CK-34 TX ring buffer (idx $06/$07) |
| $2400-$2DA4 | RAM cleared at boot (work area) |
| $4000-$BFFF | IC7 window (code + style data, banked) |
| $C000-$FFFF | IC4 EPROM (this dump) |

## Interrupts
| Vector | Addr | Use |
|--------|------|-----|
| RESET/COP/CLKMON/ILLOP | $C003 | cold start |
| XIRQ | $E7BA | ACIA MIDI RX/TX (non-maskable = MIDI has top priority; handles $F8 clock) |
| SCI | $E787 | TX to CK-34 |
| IRQ | $E75C | probably IC15 keyscan |
| TOC1/TOC2/TOC4 | $E8E5/$E901/$E8DD | timers: OC2 +1250 ticks (2.5 ms), OC3 +10000 (20 ms) at E/4 |
| PAI | $E998 | pulse accumulator (tempo dial/encoder?) |

## Link to the voice board (CK-34)
- HC11 SCI: BAUD=$20 -> 2 MHz / 64 = **31250 baud = MIDI speed**, SCCR2=$08 (TX only).
- So the main CPU most likely **talks plain MIDI to the CK-34**: the voice board is an internal MIDI sound module, MT-32/CM-32L style.
- If so, we can test the CK-34 directly: tap its RX line and feed it MIDI/SysEx from a USB-MIDI interface. Big question: does its 128 KB firmware accept LA SysEx (tone editing)?

## Boot
- Clock: E = 2 MHz (8 MHz crystal). OPTION=$9A (A/D on), HPRIO=$26 (expanded mode), TMSK2=$91.
- Boot keys: reads $1200 with PORTA = $08/$20/$28/$38 (four switch columns) and PORTA bit 2 -> flags $2460/$2463/$2464/$246A. These are the REVERB TYPE / REVERB ON-OFF / WRITE power-on modes.
- Version string "ROLAND PRO E  VER 02.00 051289" at $EDA7 (file 0x2DA7).

## IC7 dumped (2026-11-02)
- dumps/proe_ic7_R15179983_LH53234L_v2.00.bin: 256 KB, read as AM27C020 with -x. The pinout matches the 27C020 and CE/OE are active-low (a clean read proves it). SHA1 DBF467CF...43FD.
- **Bank 0 (file 0x0000-0x7FFF) = main program at $4000-$BFFF.** re/map_bank0.bin = bank0 + IC4 as one 48 KB image at $4000. re/bank0_ic4.lst = disasm: 9.5k insns, every IC4 call into $4xxx-$Bxxx resolves (one stray jmp $357E).
- Banks 1-7 = presumably style/pattern data, switched in through $180D.
- Strings (bank 0): "ROLAND PRO-E INTELL. ARRANGER" ($59E3), all UI/LCD text, MIDI menu, card messages, the 128 tone names (= **the MT-32 preset list**: OBOE 2001, DOCTOR SOLO, SCHOOLDAZE, BELLSINGER, ORCHE HIT...), the 8 reverb names, 36 style names, 5 demo songs.
- **Easter egg: the Italian dev credits "DEMETRIO LUIGI PAOLO PIERO ROBY"** at file 0x23B9 ($63B9), just before the style-name table.
- **"CHECKSUM ERROR"** at $9EF1: the OS checksums its ROM(s), so patches must fix the sum (or skip the check). TODO: find the routine.

## Next
1. Dump IC7 (2 Mbit mask, 32-pin; minipro `-x`, try as 27C020/27C2001 + compare 2 reads). Check the pinout first: mask ROMs move pins 1/31/24 around.
2. Sniff HC11 TXD -> CK-34 with a USB-UART or MIDI interface at 31250 to confirm it is MIDI.
3. Disassemble IC4+IC7 together with the bank map.
