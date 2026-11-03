# Roland PRO-E docs (grabbed 2026-11-02)

## Have
- PRO-E_service_notes_1989.pdf: service notes, July 1989 (manualslib print, 21 pp). Parts list, IC pinouts, test mode, block diagram, board layouts. No full schematic.
- PRO-E_OM.pdf: owner's manual, 106 pp, scanned with no text layer. MIDI/SysEx section reportedly starts ~p.85.
- mame_roland_tnsc1.cpp / mame_hash_roland_tnsc1.xml: TN-SC1 style cards (shared with the E-5/E-20/E-30/E-35/E-70/RA-50/RA-90/CA-30/KR-500/KR-3000). Dumped: -02/-03/-05/-06/-07, 32 KB each, 16-bit. The Pro-E OS ROM is not dumped anywhere public.

## Hardware (from the service notes)
Main board = CPU PCB 7623602000. Sound = separate CK-34 voice board, fed over serial.

| IC | Part | Role |
|----|------|------|
| IC1 | MC68HC11A0P (48-pin DIP) | main CPU, expanded mode (AD0-7 multiplexed, A8-15); its SCI (TXD/RXD) talks to the CK-34 |
| IC4 | PROG ROM, 27C512-25 EPROM (64 KB, 28-pin) | **OS = a socketed EPROM -> dump with TL866, burn your own** |
| IC5 | HM62256LP-12 | 32 KB battery-backed SRAM (CR2032) |
| IC7 | PATTERN ROM, LH532355 2M mask (32-pin, 256 KB) | style/pattern data; board has "512"/"2M" jumper by J1 |
| IC11 | HD63B50 ACIA | MIDI UART (IC12 6N138 opto on IN) |
| IC2 | uPD65005G-062 gate array | address decode CS0-CS5, LEDs, LCD bus, switch matrix |
| IC15 | keyscan custom + IC16 RAM | 37-key velocity scan |
| IC10/19/20/21 | card interface | RAM card (M-256E style) |
| 27C128-25 | EPROM, also in the IC list | location not labeled; check the board |

CPU TXD/RXD go to the **CK-34 voice board**: an LA-synth module of the D-10/D-110/MT-32 family.
- P8098 CPU + 1M mask ROM (its own firmware)
- LA32 synth chip, PCM ROM TC534000P-7476 (4 Mbit), M5M4416 DRAM
- HG61H15B72F gate array + HG61H20R36F reverb, PCM54 DAC, M5207 VCA
- Spec: 32 partials, 13 structures, 30 PCM drums, 33 SFX, 8 reverb types

No built-in speakers (confirmed by owner): outputs are L/Mono, R and phones only. The "5W x 2" in the spec table and the TDA1905 power amp are likely the phones amp.

LCD = LM16x21A, 16x2 HD44780-type, driven via IC2's LD0-7 bus.

## Hidden modes
- Test mode: hold REVERB TYPE at power-on. Tests memory (RAM/ROM/card), panel (MIDI loopback, pedal, switches), controls (mod/bend/volume/tempo), and keyboard (velocity).
- Version: hold REVERB ON/OFF at power-on; shows the ROM version and date.
- Factory init: hold WRITE at power-on. Shows "FACTORY SETUP LOADED"; clears composer songs, Master Tune 442.0 Hz, bend range 2.
- Adjust: VR2 on the CPU board = A/D ref, 4.750 V on IC13 pin 1. VR1 = LCD contrast.

## Her board (owner photo 2026-11-02)
- IC4 has a sticker "PRO E / IC4 / 02.00" = OS v2.00, a labelled EPROM. Socket not confirmed yet.
- IC1 MC68HC11A0P, IC5 SRAM, IC7 LH5323xx mask (pattern ROM), CR2032 in its holder (top right).
- IC4 confirmed **socketed** (28-pin, empty while the chip was in the T48).
- IC7 = **Roland R15179983 LH53234L (datecode 8923 D)**, soldered. 2 Mbit mask, 32-pin.
- IC6/IC18 have 28/32-pin dual outlines (pin-1 marks "28" and "32"): alternate ROM footprints. Jumpers marked "512/2M" at J1 (by IC7) and J3 (by IC8).
- Keybed ribbons plug in at F1/F2 (silkscreened, red IDC plugs).
- Empty footprints IC17, IC18 (+ IC6?) between IC4 and IC7: unpopulated ROM/RAM spots, a possible expansion route.
- Red wire near R37/R38 by IC2: factory jumper or old repair, leave it alone.
- CK-34: TC534000P-7476 PCM ROM, second Roland TC53x000P mask (8098 code), 16.384 MHz + 12.000 MHz crystals.
- CK-34 close-up: Intel P8098 @ 12 MHz; control ROM = Roland R15179974 TC531000CP-H607 (1 Mbit = 128 KB, datecode 8922); NEC D43256AC-15L (IC26) = 32 KB work SRAM.
  Compare against MAME: MT-32 = P8098 @ 12 MHz, 32 KB SRAM, 512 KB TC534000P PCM. D-10/D-110 = 128 KB control ROM (R15179873) but 1 MB PCM.
  So the CK-34 looks like an MT-32/CM-32L-class LA board (512 KB PCM) with its own 128 KB firmware. MAME says the CM-32L PCM R15449121 is shared with the RA-50 (an arranger) "and others".
- CK-34 full-board photo (2026-11-02), label "CK-34 VOICE BOARD 79529210":
  - Wave ROM A: **Roland R15449121 TC534000P-7476** = MAME's MT-32 (newer PCB)/CM-32L/RA-50 PCM, 512 KB, CRC 573e31cc.
  - Wave ROM B: Roland R151799?5 HN62304BP (4 Mbit). Probably **R15179945 = CM-32L extended sounds** (fits the "33 PCM SFX" spec). Last digits still to confirm.
  - IC13: **R15179917 HN623257** = BOSS reverb ROM, same as CM-32L/RA-50/MT-100.
  - LA32 R15229896 (QFP), gate array R15239106 HG61H15B72F, BOSS reverb HG61H20R36F + 4x MSM4416 DRAM, PCM54HP DAC.
  - Control: P8098 + R15179974 TC531000CP-H607 (128 KB): the only CK-34 ROM not in MAME.
  - => The CK-34 is **CM-32L hardware**: same PCM and reverb ROMs, with its own control firmware.
  OLD TODO (resolved): read the R15xxxxxx number on the PCM ROM. If it is R15449121 = CM-32L/MT-32 PCM, we already have a dump to compare against.

## Dumps (../dumps)
- proe_ic4_os_v2.00_051289_27c128.bin: IC4 is a **27C128 (16 KB)**, not the 27C512 the parts list implies. Read 2x on the T48, both reads identical, SHA1 600D50B2...6551.
  - String "ROLAND PRO E  VER 02.00 051289" at 0x2DA7. "$Roland PROE D" at 0x1440. Note-name table at 0x17A4.
  - Mapped at $C000-$FFFF. 68HC11 vectors at the top; RESET = $C003, which starts with LDS #$00FF, then TMSK2/OPTION setup ($1024/$1039). Valid HC11 code.
  - Code references $A5xx+, so more code or tables likely sit in other ROM space (IC7 pattern ROM, banked?).

## Missing
- Full schematic (the service notes only have layouts and the block diagram). Altervista lists one in its catalog; ask them by email or trace the board ourselves.
- OS ROM dump: we pull IC4 and read it ourselves.

## Next
1. Open the unit and photo the CPU board: confirm IC4 is socketed, the EPROM label/version, the 27C128's location, and the 512/2M jumper.
2. Dump IC4 (27C512) + IC7 (2M mask, 32-pin; needs an adapter or TL866 support) + CK-34 mask ROM.
3. Disassemble the 68HC11 code (vectors at 0xFFC0-FFFF of the 64 KB EPROM).
