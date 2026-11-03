# B1: CK-34 8098 core, bank map, interrupts, debug monitor (IC28 "CK-34 v2.06 89-02-28")

Source: `dumps/ck34_ic28_control_R15179974_CK-34_v2.06.bin` (64 KB). Listing: `re/fw_map/ic28.lst` (5257 instructions
traced, 7 jump tables, 0 trace problems), built by `python -I re/fw_map/ck34_dis.py <bin> ic28.lst`. That wrapper reuses
`D110-rosetta-OS/mcs96_dis.py`, maps the window to file 0x8000 (bank 2) and renames the routines named in this file.
Tags: **C** = CONFIRMED (seen in code/data), **I** = INFERRED (reasoned, not fully traced).

## TL;DR
- IC28 is an **MT-32 2.x / CM-32L-family control ROM**. It has the same kernel layout as the D-110 OS: TRAP at 0x19D5,
  monitor at 0x1820, API jump table at 0x2080, LCD driver at 0x1B99, MIDI queue at 0xF9FB, SP 0xF9D0, LA32 at 0x0C00. **C**
- Bank latch 0x0100 only ever gets **2** (file 0x8000-0xBFFF), **3** (file 0xC000-0xFFFF) and **0x11** (2nd 16 KB of SRAM).
  No code runs in the window. File 0x0000-0x0FFF is FF and is never mapped. **C**
- Main loop 0x22C9: one MIDI event, else one partial update (32 round-robin), then once per lap the MT-32 UI task. **C**
- IRQs: EXTINT 0x2F2D = LA32 envelope IRQ (P2.2); serial 0x1D0F = MIDI RX parser + TX ring; SWT0 0x1A08 = 10 ms tick
  (buttons, ACH7 A/D, active sensing, LED); SWT1 = 3.1 ms tick counting `rc4`, which no traced code reads (period reloaded
  only by the demo player, so a demo-sequencer leftover, **I**); timer-ovf 0x22B7 = 24-bit time + display timeout. **C**
- **The debug monitor is present but deaf.** Commands W F R G + B C H (Intel-HEX loader). Output goes out on TXD at 31250 baud.
  Nothing calls it except a TRAP opcode (none in the ROM) or a jump to 0x2082 (no caller). Its input ring pointer
  `rf4` is set to 0x0000 and **nothing ever writes it**. The serial ISR **drops** `F0 00 ...` SysEx, which on the D-110 feeds the monitor. **C**
- So it **cannot** upload or test code on stock v2.06. One burned IC28 patch (about 20 bytes, sites listed below) would turn it into
  an Intel-HEX RAM loader over MIDI SysEx. SysEx DT1 cannot do it: data is 7-bit and clamped per address. **C**/**I**
- The MT-32 LCD and button code is **still live**. It runs the LCD init and the "** Roland MT-32 **" banner, refreshes the LCD on every UI lap
  and scans buttons every 10 ms. Boot combos still work: version, demo mode (the demo table is empty), factory test mode.
  The LCD status read must return 0, as MAME models it, or the LCD driver would hang. **C**/**I**

## 1. Reset / init
| Addr | What | Tag |
|---|---|---|
| 0x2080 | `sjmp 0x20EF` (reset vector start; 0x2082-0x209E = API table, §2) | C |
| 0x20EF cold_start | SP=0xF9D0, int_pending=0, di, PWM=0xFF (volume minimum, see §6), IOC1=0x75 | C |
| 0x20FD | 0x0280 <- 0xCA (gate array/LCD side latch, MT-32 heritage); `rc8`=0 -> SYS_OUT 0x0200 | C |
| 0x210C-0x2150 | reverb latches 0x0800/0x0400 = 0 (x3), LA32 0x0DC2=0, 0x0DC0=0xC000, 0x0CC0[2p]=0xFFFF for 32 partials, short delay | C |
| 0x2155-0x215B | BAUD = 0x8005 (XTAL source, B=5): 12 MHz/(64*6) = **31250**; SP_CON=0x09 = mode 1 8N1, **receiver on** | C |
| 0x2160 key_init (0x1994), 0x2163-0x2172 | HSO cmd 0x18 = SWT0 at T1+0x4E2; `rc2`=0x061A; HSO 0x19 = SWT1 at T1+rc2 | C |
| 0x2179 ser_init (0x1E92) | TX ring `re8/rea`=0xFF00, **monitor RX `rf4/rf6`=0x0000**, MIDI queue `rec/ree/rf2`=0xF9FB, `rfc`=0x20 (TX idle) | C |
| 0x217C lcd_init (0x1C20), 0x217F | LCD init + `lcd_print_at(0x1EEF)` = " ** Roland MT-32 ** " | C |
| 0x2186-0x2194 | ~0.5 s delay (3x65536 djnz), `ljmp 0x2200` -> `sjmp 0x222F` (version string sits at 0x2205) | C |
| 0x222F warm_start | clear EXTINT pending, SP=0xF9D0, int_mask \|= 0xA1 (T-ovf, SWT, EXTINT), ei, `r9e`=0, 0xEDB5 (MIDI echo)=0 | C |
| 0x2247-0x2253 | la32_init 0x2DEC, synth_reset 0x4F38, all_reset_defaults 0x502A, synth_reset, ui_init 0x535B | C |
| 0x2256-0x229B | boot key combos (table below), then `ljmp main_loop 0x22C9` | C |

The boot combos compare the raw button bytes. MT-32 key names from MAME `mt32.cpp`: SC0 bits 0-4 = 1, 2, 3, Sound group, Volume;
SC1 bits 0-4 = 4, 5, Rhythm, Sound, Master volume. All are active low, and bits 5-7 must read 1.

| Read | Value | Keys | Action | Tag |
|---|---|---|---|---|
| 0x021C (0x2256) | 0xEA | 4 + Rhythm + Master vol | `lcd_print_at(0x2205)` "CK-34 v2.06 89-02-28", wait (0x22A1) | C |
| 0x021C (0x2271) | 0xEF | Master vol | demo mode: 0xF6E6=1, 0xF6CE=1, `rb1`=2, 0x5BCE/0x545E ("Random Demo-Play"/"Chain Play") | C |
| 0x021A (0x2291) | 0xEB | 3 + Volume | `lcall test_mode 0x7000` (never returns, §8) | C |

- "by S.Ishida, T.Khono" (0x221B-0x222E) has **no terminator**. The 'q' after it is the opcode 0x71 at 0x222F, and nothing references 0x221B. **C**
- The monitor is **not** a boot option. **C**
- CCB at 0x2018 = 0xBD (8-bit bus config byte). **C** byte, **I** meaning.

## 2. API jump table 0x2080-0x20A0 (fixed ABI, same as D-110)
| Entry | Target | Function | ROM callers |
|---|---|---|---|
| 0x2082 | 0x20A1 -> 0x1820 | **monitor entry** (banner + command loop) | none |
| 0x2084 | 0x20A4 | mon_getc -> r70 | none |
| 0x2086 | 0x20AB | r70 -> ser_putc (TX ring) | 47 sites (MIDI echo, SysEx replies, test mode) |
| 0x2088 | 0x20B1 | r70 -> put_hex8 (serial) | none |
| 0x208A | 0x20B7 | lcd_print_at(r78) | many |
| 0x208C | 0x20BD | lcd_cmd(r70) | UI |
| 0x208E | 0x20C3 | key_get -> r70 (0 = none) | UI, test |
| 0x2090 | 0x20CA | key_wait | none |
| 0x2092 | 0x20D1 | key_init | none |
| 0x2094 | 0x20D4 | r70 = `re6` (ACH7 A/D) | UI, test |
| 0x2096 | 0x20D8 | mon_getc_nb | none |
| 0x2098 | 0x20DF | midi_get_event: r70 status, r75/r74 data or SysEx ptr | main loop |
| 0x209A / 0x209C | 0x20E9 / 0x20EC | ser_putc(rd0) / put_hex8(rd0) | none |
| 0x209E | 0x1E92 | ser_init | none |

All **C**. The unused entries (0x2082/84/88/90/92/96/9A/9C) exist only for external code. For RAM-resident test code they are a stable ABI.

## 3. Memory and bank map of this board
| CPU addr | What | Evidence | Tag |
|---|---|---|---|
| 0x0000-0x00FF | SFRs + register file (kernel globals, §4) | | C |
| 0x0100 | bank latch (write) | 31 writes | C |
| 0x0200 | SYS_OUT, shadow `rc8`: bit0 = MIDI LED (0x51D5/0x51DA), bit1-3 reverb mode bits, bit2/bit3 also changed by test mode | 0x2107, 0x4F3B, 0x51DD, 0x71A4, 0x72BA | C |
| 0x021A | SC0 buttons (read, 0x1A4D). **Also written** with `rc8` (0x46A9 LED on, 0x4D0D reverb mode bits) | | C; that the write lands in the SYS_OUT latch = I |
| 0x021C | SC1 buttons (read) | 0x1A57 | C |
| 0x0280 | gate-array/LCD latch, written 0xCA only | 0x2100, 0x1C23 | C |
| 0x0300 / 0x0380 | LCD data / LCD control (busy = bit0 of 0x0380 read) | 0x1BF6, 0x1BE8 | C |
| 0x0400 | REV_LATCH_A: bits0-2 reverb time (0xED96), bit3 level bit0 (shadow 0xF4A3) | 0x4D67/0x4D86 | C |
| 0x0800 | REV_LATCH_B: bits0-1 level bits1-2 (0xED97), bit2 mode bit0 (shadow 0xF4A2) | 0x4D29/0x4D4B | C |
| 0x0C00-0x0DFF | LA32 (per partial `*2`): 0x0C00 status read in EXTINT; 0x0C00/0x0C80, 0x0C40/41, 0x0CC0 pitch, 0x0D00/01, 0x0D40-44, 0x0DC0-C3 | 0x2F33, 0x2CF5, 0x2DEC | C (roles per D-110 PLATFORM.md = I) |
| 0x1000-0x7FFF | IC28 fixed, file offset = CPU address | | C |
| 0x8000-0xBFFF | 16 KB window, page = latch value | below | C |
| 0xC000-0xFFFF | fixed SRAM (first 16 KB of the 32 KB SRAM) | | C |

These are the only I/O addresses the code reads or writes. The other 0x01xx-0x0Fxx values in the disassembler summary
(0x01A5, 0x02AB, 0x04E2, 0x061A, 0x06AE ...) are immediates such as timer periods and scale factors, not I/O. **C**

Bank latch values written to 0x0100:
| Value | Window shows | Who | Tag |
|---|---|---|---|
| 0x02 | **file 0x8000-0xBFFF**: timbre A map 0x8000, timbre B map 0x8080, PCM table 0x8100, rhythm timbre map 0x8500, rhythm setup 0x8580, demo-song ptrs 0x86E0 (all FF), rhythm/SFX timbres 0x8A00+, group-A timbres 0xB000+ | 0x261F, 0x2696, 0x4DD7, 0x4E0C, 0x4E7C, 0x50D1->0x5109, 0x5F04 | C |
| 0x03 | **file 0xC000-0xFFFF**: the rest of the timbres (group B "Acou Bass1" at file 0xD752 ...) | `incb rb7` at 0x2632 when ptr bit14 is set | C |
| 2 + (p>>14) | general 16-bit "ROM pointer" p (relative to file 0x8000): bank = 2+(p>>14), window = 0x8000+(p&0x3FFF) | sub_4EEA (0x4EEA-0x4EFD) | C |
| 2 + (p>>13) | demo stream (word pointer p, banks 2..9 = sized for a 128 KB MT-32 2.x ROM) | 0x3D86-0x3D95, 0x5ED6-0x5EE5, reader 0x3E2B | C |
| 0x11 | **SRAM 0x4000-0x7FFF** = timbre memory (SysEx area 08), cleared by all_reset 0x50D1-0x50E4; RAM test 0x7033 | 0x264A, 0x40E8, 0x4970, 0x4E57, 0x7033 | C |
| per partial / part | copies of the above kept in 0xF201[2p] / 0xF317[part] (re-applied in the partial loop 0x2B05 and EXTINT 0x2FBF) | | C |

- Timbre maps check out against the data. File 0x8000 = `00 30 ...`, so ptr 0x3000 -> bank 2, 0xB000 = "AcouPiano1". File 0x8080 = `52 57 ...`,
  so ptr 0x5752 -> bank 3, 0x9752 = file 0xD752 "Acou Bass1". File 0x8500 = `00 8A ...` -> file 0x8A00 "Acou BD". This is the same layout as Munt's
  `ctrl_cm32l_1_00` / `ctrl_mt32_2_06` map (pcmTable 0x8100, timbreA/B 0x8000/0x8080 with offset 0x8000, timbreR 0x8500, rhythm 0x8580).
  The startup message also sits at the address Munt gives for those two ROMs (0x1EF0). **C** (our side) / Munt table
- Pages 0 and 1 (file 0x0000-0x7FFF via the window) are **never** selected. Banks 4-9 only come from the empty demo table. The
  trace has **no instruction in 0x8000-0xBFFF**, and no code is copied into RAM. **C**
- vs MAME mt32.cpp: same map (entries 0-3 = 16 KB ROM pages, 0x10/0x11 = RAM pages, fixed 0xC000 = RAM base). 0x10 is never written. **C**
- vs D-110: same kernel and LA32/reverb/LCD addresses. The D-110 uses pages 0x20-0x27 (IC15) and 0x30/0x31 (card). The CK-34 uses
  pages 2/3 of its own ROM and has no card. Both share the `rb7` convention: the EXTINT handler uses `rb8` and restores the latch
  from `rb7` on exit (0x2F8F, 0x3030). **C**
- The chip is a 1 Mbit TC531000 but the image is 64 KB (dump note: pin 22 = A16 makes no difference). The firmware never sets a bank ≥4 on purpose. **C**/**I**

## 4. RAM usage
Register file (kernel globals):
| Reg | Use | Tag |
|---|---|---|
| `rb7` / `rb8` | bank latch shadow, foreground / EXTINT | C |
| `rc8` | SYS_OUT shadow | C |
| `rc2`/`rc3` | SWT1 period (default 0x061A; reloaded from the demo stream at 0x3DA4) | C |
| `rc4` | SWT1 tick counter (only cleared by the demo player 0x3E1C) | C |
| `rc5` | active-sensing timeout (0x1E x 10 ms); `rc6`/`rc7` = LED hold counters (set to 8) | C |
| `rc9` | 0xFF = UI refresh request (set by SysEx end 0x3FF6), seen as key code 0xF0 | C |
| `rd0-rdf` | kernel scratch; `rd8/rda` key ring ptrs; `rdc/rde` button state | C |
| `re0-re7` | key repeat/debounce (`re2` 0x50 = 800 ms delay, `re3` 8 = 80 ms repeat), `re6` = ACH7 A/D, `re7` = IOS1 accumulator | C |
| `re8/rea` | TX ring write/read (page 0xFF) | C |
| `rec/ree/rf0/rf2` | MIDI queue write / read / SysEx data ptr / consumer copy | C |
| `rf4/rf6` | monitor RX ring write/read (page 0x00, never fed) | C |
| `rf8` rx byte, `rfa` running status/SysEx state, `rfb` data count, `rfc` serial flags (bit5 TX idle, bit6 RX) | | C |
| `r40` | partial loop index (2*p); `r4b` = Timer1 bits 16-23 | C |
| `r90` | UI state handler pointer (`br [r90]` at 0x52BA); `r9e` = display timeout (timer-ovf ticks) | C |

Fixed SRAM 0xC000-0xFFFF (bank 0x11 = timbre memory, §3):
| Range | What | Tag |
|---|---|---|
| 0xC000-0xDFFF | SysEx area **06 xx xx** (8 KB = 64 x 128-byte records, clamped per byte by 0x4800); no other code uses it | C (purpose unknown) |
| 0xE000-0xE08F | patch temp, 9 parts x 16 (SysEx 03 00 00 / 00) | C (table 0x450E) |
| 0xE090-0xE1E3 | rhythm setup temp, 85 x 4 (SysEx 03 01 10 / 01), init from file 0x8580 (0x50FD) | C |
| 0xE1E4-0xE993 | timbre temp, 8 x 246 (SysEx 04 / 02) | C |
| 0xE994-0xED93 | patch memory 128 x 8 (SysEx 05) | C |
| 0xED94-0xEDB4 | system area (SysEx 10): ED94 master tune (0x4A), ED95-97 reverb mode/time/level, ED98 reserve x9, EDA1 MIDI ch x9, EDAA master volume | C |
| 0xEDB5 / 0xEDB7 | MIDI echo flag (0 at boot) / unit (device) number 0x10 | C |
| 0xEDC0-0xF27F | per-partial arrays, stride 2, one 0x40 block each (state, part, timbre ptr, env phase 0xEF00, LA32 shadows 0xEF80, pitch 0xEFC0, bank 0xF201 ...) | C |
| 0xF280-0xF31F | per-part records (9 x 0x10): bend 0xF280, channel 0xF28B, reserve 0xF28C, timbre ptr 0xF310, bank 0xF317 | C |
| 0xF3A0-0xF4FF | partial allocation lists, pan, display buffers, SysEx state 0xF4F8-FB | C |
| 0xF6A4-0xF6AA | SysEx address being processed | C |
| 0xF6AB-0xF6C0 | 20-char display message (SysEx 20 00 00) | C |
| 0xF6CE | demo-mode selector (SysEx 30 00 00, 1 byte) | C |
| 0xF6E6-0xF6EA | UI/demo flags | C |
| ...-0xF9CF | **stack**, grows down from SP=0xF9D0 (test mode uses 0xF000) | C |
| 0xF9D0-0xF9DF | key event ring (16 B) | C |
| 0xF9E0 / 0xF9E2 / 0xF9E4 | monitor: SP at break / break address / saved byte | C |
| 0xF9E5-0xF9FA | LCD line buffer (ctrl byte + text + 0) | C |
| 0xF9FB-0xFDE4 | MIDI event queue (3-byte events, wrap at ≥0xFDE3) | C |
| ...-0xFEF2 | inline SysEx bodies may run up to 0xFEF3 | C |
| 0xFF00-0xFFFF | serial TX ring (256 B) | C |

## 5. Main loop (0x22C9)
1. int_mask |= 0x40, ei. `midi_get_event` (0x1C98). If there is no event: int_mask |= 0xE1, `ljmp partial_loop 0x2AE2`. **C**
2. Channel message: index = `(status & 0x70) >> 3` into `jtab_2466`. Values: 8n 0x251B, 9n 0x25C7, An ret, Bn 0x39CA, Cn 0x2499, Dn ret, En 0x2476 (bend, x 0xF280 range), Fn 0x2332.
   If 0xEDB5 bit0 is set, the message is first echoed on TX (0x2306-0x2315). The handler then runs once per part whose channel 0xF28B[part] matches (r50 = 0..0x80 step 0x10, 9 parts). **C**
3. 0xF0 -> `sysex_entry 0x3FE9` (model 0x16 path 0x413C, 0x14 path 0x4A42). 0xFE (queue overflow marker) -> parts_reset + SysEx error display. 0xFF -> parts_reset 0x234D. 0xFC is queued but ignored. **C**
4. `partial_loop`: advance `r40` by 2. Skip inactive partials (0xEDC0[2p] bit7). Select the partial's bank (0xF201). Update pitch/LFO, then write LA32 pitch 0x0CC0[2p] (0x2CF5, clamp 0xE800).
   Return to **main_loop after each single partial**, so MIDI is serviced between every partial update. **C**
5. After all 32 partials -> `ui_task 0x529C`: PWM = d_3D13[master volume 0xEDAA], LED/LCD refresh 0x51BA, key -> `jtab_52E6` or `br [r90]`. If `rb1` bit1 is set (demo mode), it goes to 0x5B88 instead. **C**
- Dead leftovers in the ROM: an older dispatcher at 0x237C-0x2465, an older trap handler at 0x1E5D-0x1E91, an "adrs err" stub at 0x1914. **C**

## 6. Interrupts
Fixed 8096 priority, highest first: EXTINT > serial > SWT > ... > timer-ovf. Every handler starts with `pushf`, which saves INT_MASK and masks all.
EXTINT and SWT then set int_mask=0x40 and ei, so **MIDI RX can nest inside them**. **C**

| Vector | Handler | What | Tag |
|---|---|---|---|
| 0x2000 timer-ovf | 0x22B7 | `incb r4b` (Timer1 high byte, 2 µs x 65536 = 131 ms/tick). Display timeout `r9e`: at 0 sets `r90`=0x54AF (back to the main display) | C |
| 0x200A SWT | 0x1A08 | IOS1 into `re7`. **SWT1**: re-arm +`rc2`, `incb rc4`. **SWT0** (every 5000 ticks = **10 ms**): `rc7`/`rc6`-- (LED hold); `rc5`-- active sensing, which on expiry injects 0xFF into the RX parser (0x1A3E -> 0x1D3D); ACH7 result -> `re6`, restart conversion (AD_CMD 0x0F); button scan of 0x021A/0x021C with debounce, auto-repeat, key codes 1-10 (+0x10 while SC1 bit4 is low) into ring 0xF9D0 | C |
| 0x200C serial | 0x1D0F | reads SP_STAT (TI bit5 / RI bit6, accumulated in `rfc`). TX: next byte from 0xFF00 ring, or mark idle. RX: MIDI parser (§7) | C |
| 0x200E EXTINT | 0x2F2D | only if P2.2 is high (IOC1=0x75 selects P2.2). Reads LA32 0x0C00: bits = partial number + type. Steps the partial's envelope phase 0xEF00[2p] (0..7) and writes the next segment to 0x0C00/0x0D00. Uses `rb8` for the bank and restores `rb7` | C (LA32 = I, matches D-110) |
| 0x2010 TRAP | 0x19D5 | debug break -> monitor (§7) | C |
| 0x2002-0x2008 | 0xFFFF | A/D, HSI, HSO, HSI0 unused | C |

int_mask: 0xA1 at warm start, \|0x40 in the main loop, \|0xE1 before the partial loop, 0x60 (serial+SWT) in the monitor and test tones. **C**
Timing assumes the 8098 Timer1 = 12 MHz/24 = 2 µs. The 10 ms SWT0 is cross-checked by active sensing 0x1E = 300 ms (MIDI spec). **I**

## 7. Serial port: MIDI parser and the debug monitor
MIDI RX (0x1D31-0x1E5B):
- Running status is in `rfa`. Channel messages become 3-byte events at `[rec]`. 0xFE (re)arms `rc5`. 0xFC is queued. F8/FA/FB/FD and F1-F6 are dropped. **C**
- SysEx state `rfa`: F0 -> wait for the ID byte. **0x41** -> state F1: store the body inline after an F0 event; at F7, write the end pointer into the event (0x1E48).
  **0x00 -> state 0xFF = drop everything until F7 or a status byte** (0x1DB6-0x1DBE, 0x1DC0 `je 0x1E17` popf/ret). Other IDs -> rfa=0 (ignored).
  Buffer full (0xFEF3) queues `F0 00 F7`. Queue overrun (0x1E19) resets the queue and queues 0xFE. **C**
- TX: `ser_putc 0x1CF0` puts the byte in the 0xFF00 ring. If TX is idle (`rfc` bit5) it jumps into the ISR body to start sending. TX users: MIDI echo (off by default),
  SysEx handshake/RQ1 replies (0x457F-0x4B71), UI 0x5EB0-0x5EC3, test-mode loopback. **C**

### Debug monitor ("mon 7/28", "88/07/28", 0x1820-0x1A05, strings 0x1EB4-0x1F0E)
Entry:
- **0x2082 -> 0x1820**: prints "\r88/07/28\r" on serial (`ser_puts 0x198B`) and "mon 7/28" on the LCD, then mon_loop. **No caller in the ROM.** **C**
- **TRAP (opcode 0xF7) -> 0x19D5**: saves SP to 0xF9E0 and prints "#break at:" + `(2[sp])-1`, `[sp]`, `SP+4` in hex, then mon_loop. There is **no 0xF7 in any traced code.** **C**
- No boot key, port pin or special MIDI byte leads to it. **C**

mon_loop 0x182D: SP=0xF9D0, int_mask \|= 0x60, ei. Sends prompt `>` (0x3E). Polls `mon_getc_nb`. The **commands are upper-case ASCII; hex digits are 0-9 A-F (lower case = "hex err")**.
| Cmd | Syntax | Action | Code |
|---|---|---|---|
| `W` | `Waaaadd` | write byte | 0x1844 |
| `F` | `Fsssseeeedd` | fill sss..eee inclusive | 0x1852 |
| `R` | `Raaaa` | read byte, prints 2 hex digits | 0x186D |
| `+` | `+` | next address (`rd2`+1), print byte | 0x1888 |
| `G` | `Gaaaa` | SP=0xF9D0, jump to aaaa | 0x187B |
| `B` | `Baaaa` | saves the byte at aaaa (0xF9E4) and aaaa (0xF9E2), then **jumps to aaaa**. It does **not** plant the 0xF7 itself | 0x1896 |
| `C` | `C` | SP = word at 0xF9E0. If 2[sp] == word at 0xF9E2, write the byte from 0xF9E4 back. Then `popf; ret` | 0x18B0 |
| `H` | `H` + Intel-HEX | wait for `:`, then count, addr, type, data written straight to `[addr]`, checksum (sum incl. checksum must be 0, else "sum err"). Type 01 or count 0 ends it: reads checksum + 2 chars (CR LF), prints "load ok" | 0x18CF-0x1912 |
- Errors: "hex err" (0x1957), "sum err" (0x191A). "adrs err" is reachable only from dead code (0x1914). **C**
- B and C expect a stack frame of [PSW][PC], but the 8096 TRAP pushes only PC. Plant breakpoints with `W` (0xF7) and treat `B`/`C` as unreliable. **I**

Why it is deaf on the CK-34:
- `mon_getc` (0x1CE3) waits for `rf6 != rf4` and reads `[rf6]` (ring in page 0x00). `rf4` is set to 0 at 0x1E9A and **never written anywhere** in the 5257 traced instructions (no direct, indexed or long-op writer). **C**
- The D-110 IC19_MAP.md says D-110 v1.10 stores `F0 00 ...` bytes into an `rf4/rf6` ring at 0xFF00 for this monitor. In the CK-34 that path is removed:
  the TX ring moved to 0xFF00 and the F0 00 state just drops bytes. **C** (CK-34 code) / D-110 side per its doc.
- **Verdict: the stock v2.06 monitor cannot be used to upload or test code.** **C**
- SysEx DT1 is no substitute. It writes only into the table areas at 0x450E (RAM 0x8000-0xBFFF via bank 0x11, 0xC000-0xED93, system, display, 0xF6CE). Each byte is 7-bit and clamped to its max (0x4236-0x4246, max 0 = read-only), and nothing executes RAM. **C**

## 8. Factory test mode (SC0 = 0xEB at boot, 0x7000)
- SP=0xF000, int_mask \|= 0x61, banner "Welcome! TEST MODE". **C**
- RAM test: bank 0x11, walking-1 over 0x8000-0xDFFF, so it tests the 16 KB page plus 0xC000-0xDFFF. Prints "RAM TEST ok/Error". **C**
- Bank test: write 0x8000 (bank 0x11) =FF and 0xC000=00, read back. LA32 0x0C00 must read 0. Prints "BANK SELECT Error" on failure. **C**
- "CHECK VR PUSH 2:100": shows ACH7 0-100 until key 2. **C**
- MIDI loopback: sends `90 nn 40/00` (nn 0x15-0x6C) on TX and expects the same event on RX. Needs TXD->RXD looped. "MIDI TEST ok PUSH 3", "MIDI Receive/Verify Error". **C**
- "CHECK ANALOG OUTPUT": LA32 test tones on keys 1/2/3 = SIN 100 Hz/1 k/3 k left, 4/5/Rhythm = 200 Hz/2 k/4 k right, Sound group/Volume/Master = PCM reverb off/1/2, Sound = 440 Hz.
  Key 0x15 (Volume while Master is held) exits to main_loop via 0x2202. **C**
- "CHECK LED PUSH 1", "SW TEST ok", "PART[1]".."[VOLUME]" (0x75BF-0x76B9) are **unreferenced**: the panel tests were cut for the CK-34. **C**
- No ROM checksum test exists, and none was seen elsewhere. A patched IC28 likely needs no checksum fix-up (D-110 found the same). **I**

## 9. MT-32 LCD/button code on the CK-34
- **Active.** LCD init and banner at boot (0x217C/0x217F). `lcd_flush` 0x1BE8 polls 0x0380 bit0 and then writes. The UI task refreshes every partial-loop lap.
  SysEx errors ("Exc. Checksum error" 0x4013, "MIDI Buffer overflow" 0x3FFD ...) go to the LCD. **C**
- MAME `lcd_ctrl_r` returns 0 (the LCD /RD is pulled high), so the busy-wait never blocks without an LCD. The CK-34 runs, so its gate array must behave the same. **I**
- Buttons are scanned every 10 ms (0x1A4D-0x1A5C). Without a panel the lines presumably read idle (bits 0-4 = 1) and no key events happen. The boot combos still read these lines (§1). **I**
- PWM output = master volume control: d_3D13[vol] gives 0xFF at vol 0 and 0 at vol ≥69. At boot the volume = d_12F1[ACH7/2], so the **ACH7 voltage sets the initial master volume**. **C** code / analog wiring **I**

## 10. Mod hooks
- **Free IC28 space (FF):** 0x606A-0x6FFF (3990 B, directly executable), 0x78A9-0x7FFF (1879 B), 0x1F0F-0x1FFF (241 B), 0x2197-0x21FF, 0x2019-0x207F.
  In the window: file 0x86D4-0x89FF (812 B, bank 2), 0xA8B0-0xAFFF (1872 B), 0xFE2A-0xFFFF (470 B, bank 3).
- **Free RAM candidate:** 0xC000-0xDFFF (only SysEx area 06 and the test-mode RAM test touch it).
- **Monitor revival patch (one IC28 burn, ~20 B):**
  1. 0x1E9A `a1 00 00 f4` -> `a1 00 df f4`: RX ring at 0xDF00-0xDFFF.
  2. 0x1DC0-0x1DC4 `99 ff fa df 52` (`cmpb rfa,#0xff; je 0x1E17` = drop) -> `lcall stub; nop; nop` (`ef lo hi fd fd`). The stub goes in 0x606A:
     if `rfa`==0xFF then `stb rf8,[rf4]; incb rf4`, drop the return address, `popf; ret`; else `ret`. Then `F0 00 <ASCII> F7` feeds the monitor.
     0x1E17 is reached only from 0x1DC3. The monitor protocol is 7-bit ASCII, so it fits inside SysEx.
  3. An entry trigger, e.g. 0x229B `lcall 0x7000` -> `lcall 0x2082` (boot combo 3+Volume). The main loop could also check a flag the stub sets. Do not enter from the ISR.
  Replies come out on the CK-34 TXD at 31250 8N1, which needs a wire. Loading also works blind: `H` + records, then `G`, on RX alone.
  After that, RAM code (0xC000-0xDEFF) loads and runs without further burns. **I** (design, not tested)
- API ABI 0x2082-0x209E for RAM code: ser_putc 0x2086, lcd 0x208A, keys 0x208E, MIDI events 0x2098. **C**
- Bank convention: set `rb7` before writing 0x0100, because EXTINT restores the latch from `rb7`. **C**
- MIDI hook points: parser 0x1D31 (RX byte in `rf8`), dispatcher `jtab_2466` (8 words), SysEx area table 0x4502/0x450E (add an address area here). **C**
- Timbre/PCM tables are in banks 2/3 at the Munt CM-32L offsets, so a wave-table patch (WAVE_FORMAT.md) goes at file 0x8100 (4 B/entry, 256 entries). **C** location / entry count per Munt **I**

## 11. Open questions
- What drives IC28 pin 22 (A16 on the 1 Mbit mask, /OE on a 27C512) on the CK-34? That decides whether a 27C512 drops straight in.
- Are the CK-34 SC0/SC1 lines, P2.2 (EXTINT) and TXD reachable on the board (pads, test points), and what do the button lines read (pull-ups)? This decides whether test mode or a patched monitor entry can be triggered.
- Is CK-34 TXD connected to anything in the Pro-E? The HC11 SCI is TX-only, so probably not.
- What is SysEx area 06 (0xC000-0xDFFF, 64 x 128 B records, max table 0x4843/0x4853)? Likely Pro-E specific. And the model-0x14 SysEx path at 0x4A42?
- What is wired to ACH7 on the CK-34 (sets the boot master volume)? Does the Pro-E send master volume afterwards?
- Exact meaning of the 0x0280 write (0xCA) and of SYS_OUT bits 2/3.

## TL;DR
- Map: 0x1000-0x7FFF ROM fixed. Window bank 2/3 = file 0x8000/0xC000 (tables only). Bank 0x11 = 16 KB timbre RAM. 0xC000-0xFFFF RAM. SP 0xF9D0, MIDI queue 0xF9FB, TX ring 0xFF00. **C**
- Loop: event, else one partial (x32), else UI. IRQs: LA32 EXTINT, MIDI serial, 10 ms SWT (keys/AD/sensing), 3.1 ms SWT1 (demo), T-ovf (time). **C**
- Monitor W/F/R/+/G/B/C/H exists but has no entry and no input on v2.06. **Not usable without a one-time IC28 patch**; the patch sites are in §10. **C**/**I**
- The MT-32 LCD/button/test-mode code still runs. The panel tests were cut and the demo table is empty. **C**
