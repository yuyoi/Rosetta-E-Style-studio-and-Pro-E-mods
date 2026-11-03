# B2 - CK-34 voice board (P8098, IC28 v2.06): MIDI input + SysEx

**TL;DR**
- **Yes. The CK-34 accepts standard MT-32 SysEx and you can edit LA tones with it**: Roland DT1/RQ1 plus the full handshake set, model **0x16**, with a correct checksum. The address map is the MT-32 one (00/01/02 per channel, 03, 04, 05, 08, 10, 20, 7F). The data is copied into the live tone RAM, each value capped at its legal maximum.
- **The PRO-E uses this itself.** Its "AUDIO TEST" (IC7 bank 1 $BB98) loads a full 2-partial LA timbre with `F0 41 01 16 12 02 00 00 ...`. Its boot code sends a DT1 that sets the partial reserve.
- **Things the CK-34 has that the MT-32 does not:**
  - `06 xx xx`: 8 KB of RAM, which looks like 64 "performance" slots.
  - `10 00 17-20`: 10 extra system bytes.
  - `30 00 00`: starts the demo player.
  - `40 0m ll`: write/store commands that send a status DT1 back.
  - Model **0x14** = D-50 SysEx. It is converted into LA timbre-temp writes.
- **Limits:**
  - Everything resets at every power-on: the factory init runs unconditionally at 0x224D and wipes timbre memory.
  - Replies (RQ1 data, handshake, 40-area status) go out the 8098 TX. The stock HC11 never reads them, because SCCR2=$08 (TX only).

Legend: **C** = CONFIRMED (read in code or bytes), **I** = INFERRED (reasoned or only partly traced).
Tools: `ck34_ic28.lst` (full traced listing, mcs96_dis.py), `ck34_summary.txt`, `ck34_sysex_tables.py` (prints every table below straight from the ROM).

---

## 1. Serial setup and RX interrupt

| What | Where | Detail | |
|---|---|---|---|
| UART init | 0x2155-0x215B | `baud_rate` = 0x05 then 0x80 (B=0x8005, XTAL1 clock), `sp_con` = 0x09 (mode 1 = 8N1, REN=1). At 12 MHz, 12e6/(64*6) = **31250** | C regs, I formula |
| Queue init | sub_1E92 | TX ring re8/rea = 0xFF00 (256 bytes, `incb` wrap). MIDI queue rec/ree/rf2 = 0xF9FB. rfa (running status) = rfb = 0. rfc = 0x20 (TX idle) | C |
| Interrupt enable | 0x223C, 0x22C9, 0x22D3 | int_mask bit 6 (serial) set in the main loop | C |
| ISR | int_serial 0x1D0F | Reads sp_stat until TI and RI are clear (0x1D10-0x1D19), ORing the flags into rfc. On TI it sends the next TX-ring byte (0x1D1C-0x1D29). On RI it feeds the byte into the parser (0x1D31). The same code also runs from the TX enqueue (0x1D0A) to start the transmitter | C |

### Parser state machine (inside int_serial)

Registers: rf8 = byte, rfa = status (00 none, 8x-Ex running, F0 SysEx head, F1 Roland SysEx body, FF swallow until F7), rfb = data-byte phase, rec = queue write pointer, rf0 = SysEx write pointer, rc5 = active-sensing counter.

| Byte in | Action | Addr |
|---|---|---|
| 80-EF | rfa = status, rfb = 0 (running status kept) | 0x1DAF |
| F0 | rfa = F0 | 0x1DAF |
| F1-F6 | rfa = 0 (cancels running status) | 0x1DA8-0x1DAF |
| F7 | rfa=FF: clear. rfa=F1: close the SysEx record (store F7, put the end pointer in the record header, rec = end) | 0x1DFE, 0x1E48 |
| F8 FA FB FD | ignored | 0x1DE6 |
| FC | queued as a 1-byte record. The main loop then ignores it (0x233A-0x2343) | 0x1DEB |
| FE | rc5 = 0x1E (turns active sensing on), not queued | 0x1DF9 |
| FF | queued as `FF FF FF` | 0x1D95 |
| data, rfa = 0 | dropped | 0x1D40 |
| data after F0 | `41`: start a Roland record (rfa = F1). `00`: rfa = FF. Anything else: rfa = 0. **So only Roland (0x41) SysEx is kept; universal 7E/7F is dropped** | 0x1DB6, 0x1DF0, 0x1E07 |
| data, Cx/Dx | 1-byte message: written as [st][d1][C0], queued | 0x1D5D-0x1D68 |
| data, other 8x-Ex | 2-byte message: stored on the second byte | 0x1D88, 0x1D66 |
| data, rfa = F1 | stored at [rf0]+. Overrun and end-of-buffer checks follow | 0x1DC0-0x1DD1 |

### Event queue (C)
- 3-byte records `[status][d1][d2]` in a ring at **0xF9FB-0xFDE2**: 1000 bytes, about 333 events. The ring wraps when rec >= 0xFDE3 (0x1D70).
- **A SysEx is stored inside the ring itself**: header `[F0][end lo][end hi]`, then `41 dev model cmd ... F7`. It may run past the wrap point up to **0xFEF2**, so even the worst start position leaves at least 270 bytes. A full 256-byte DT1 (264 bytes plus F7) therefore always fits.
- Reader **sub_1C98** (called through api_2098 at 0x20DF) returns r70 = status, r75 = d1, r74 = d2. For F0 it returns r74 = pointer to the `41` byte. While the SysEx is being handled, rf2 keeps the writer off it (0x1CBE-0x1CC6).
- **Overrun** (0x1E19): the writer has caught up with the reader. The ISR drops everything queued after the record being processed, or resets the whole ring, and writes an `FE` marker. In the main loop, FE runs sub_234D (on all 9 parts: hold/mod off, expression and 0xF288 back to 100, bend centre, all notes off). Then the SysEx path shows **"MIDI Buffer overflow"** (string 0x3FFD, pointer 0x3FFC, used at L409C) (C).
- **Active sensing**: the 10 ms software timer (int_sw_timer 0x1A37-0x1A41) counts rc5 down. When it underflows, the ISR injects `FF` (reset) into the parser at 0x1D3D, and rc5 = FF switches sensing off again. Every received byte reloads rc5 = 30 (0x1D37) (C). 30 x 10 ms = **300 ms** (I: Timer1 = 2 us/tick at 12 MHz, period 0x1388 at 0x1A24).
- Quirks (I):
  - An `FC` arriving inside a SysEx overwrites the open record's header (0x1DEB).
  - An over-long SysEx (more than 0xFEF2) becomes record `F0 00 F7` (0x1DD3). The reader then loads ree = 0xF700, which is outside the ring (0x1CC6-0x1CD2). Keep each SysEx to 256 data bytes or fewer.

### TX path (C)
- api_2086 / sub_1CF0 puts bytes into the ring at 0xFF00 and waits when it is full (0x1CFB-0x1D04). The same ISR drains it.
- Users of TX:
  - RQ1/RQD replies
  - handshake frames
  - the 40-area status reply
  - D-50 RQ1 replies
  - Overflow Assign forwarding
  - test mode and the dead debug monitor
- The debug monitor at 0x1820 reads its input from an rf4/rf6 ring that only init (0x1E9A) ever writes. Nothing calls its entry api_2082, so **the monitor cannot be reached over serial** (C).

---

## 2. Main loop, parts, channel messages

Main loop **L22C9**: api_2098 fetches one event. With no event it runs the voice engine (L2AE2). With an event:
- r76 = (status & 0x70) >> 3 picks the handler from **jtab 0x2466**.
- r44 = channel, r45 = d1, r46 = d2.
- **Loop over the 9 parts**, r50 = 0x00..0x80 in steps of 0x10 (0x2318-0x232B). Every part whose channel byte **[0xF28B + r50]** equals r44 runs the handler. One channel can drive several parts. Channel value 16 (OFF) never matches (C).

| Status | Handler | Behaviour | |
|---|---|---|---|
| 8x | 0x251B | note off. Key shift from patch temp +2, folded into 0x24..0x84 (0x253C-0x255E). Rhythm (r50 = 0x80) is not shifted | C |
| 9x | 0x25C7 | velocity 0 goes to note off (0x25C7-0x25CC) | C |
| Ax, Dx | 0x2498 | `ret`: poly and channel aftertouch ignored | C |
| Bx | 0x39CA | CC via table 0x39DE (below) | C |
| Cx | 0x2499 | **ignored on the rhythm part** (`jbc r50,7`). Normal mode: patch memory 0xE994 + 8*pgm, copied to the part (sub_5DB9, sub_5DF8). Mode with rb1 bit 1 (boot key BTN_SC1 = 0xEF): ROM bank 2 at 0x8800, which is all FF in this dump (sub_5DDD) | C |
| Ex | 0x2476 | 14-bit bend into word 0xF312+r50, scaled by word 0xF280+r50 (= bend range * 0x2AB, set at 0x4F68) | C |
| F0 / FE / FF / FC | 0x2332 | SysEx L3FE9 / overflow / sub_234D reset / ignored | C |

**CC table 0x39DE** (C): CC1 sets 0xF287 (mod). CC6 sets the bend range at patch temp +4, capped at 24, **only when RPN = 0/0 and no NRPN is selected** (0x3AE7-0x3B04). CC7 sets patch temp +8 (level) through the 0-100 curve at 0x12F1. CC10 sets patch temp +9 (pan, v*8/68 = 0..14). CC11 sets 0xF289 through 0x12F1. CC64 sets 0xF286 and releases held notes below 64. CC98/99 set NRPN flag 0xF316. CC100/101 set RPN 0xF314/5 and clear 0xF316. CC121 resets controllers (sub_3BEE). CC123 is all notes off. CC124-127 turn hold off and all notes off. Everything else is ignored.

### Part table (C, init at sub_4F38 0x4F5A-0x4FD3), 9 parts x 16 bytes at 0xF280
| Offset | Meaning |
|---|---|
| +0 (word) | bend scale | 
| +3 | active partials/voices. Any nonzero value makes a WSD/RQD get RJC (sub_4673) |
| +5 | head of the voice list (FF = none) |
| +6 / +7 / +8 / +9 | hold / modulation / 100 (reset value, I: unused) / expression |
| **+0x0B** | **receive channel**, copied from system eda1+p (0x4FB2), and again after any SysEx write to 10 00 0D-15 (L3F49-L3F8D) |
| +0x0C | partial reserve (from ed98+p) |
| 0xF310+r50 / 0xF312 / 0xF314 / 0xF316 | timbre-temp pointer (0xE1E4 + p*0xF6) / bend / RPN (FFFF = null) / NRPN flag |

- Parts 0-7 are melodic, part 8 (r50 = 0x80) is rhythm. 32 partials (free list 0xF3C0, 0x4FD5-0x4FEF) (C).
- Defaults from sub_502A, **run on every boot at 0x224D** (C):
  - parts 1-8 on MIDI ch 2-9, rhythm on ch 10 (0x50A6-0x50B6)
  - partial reserve 3,10,6,4,3,0,0,0,6 (ROM 0x4F03)
  - master tune 0x4A (0x5041)
  - **unit number (device ID) 0x10** (0x5055)
  - timbre memory 0x8000-0xBFFF (RAM bank 0x11) cleared to 0 (0x50D1-0x50E4)
  - panel option "Channel 1 to 8" (0x5708) moves parts 1-8 to ch 1-8.
- **Overflow Assign** (flag 0xEDB5, cleared at boot 0x2242, set only from the panel menu 0x56B7) (C). When it is on:
  - Ax-Ex messages are re-sent on TX (0x22F9-0x2315).
  - Note-offs are forwarded as `9n kk 00` (0x2523-0x2533).
  - A note-on that finds no free partials is **forwarded instead of played** (0x2707-0x272C).
  - SysEx is echoed, and only DT1/DAT are handled (0x40FA-0x4119).

---

## 3. SysEx

### Entry and header (C)
- Main loop F0 goes to **L3FE9**, then **sub_40D9**. The CPU bank latch is set to 0x11 so timbre memory is visible at 0x8000 (0x40E8). Then r78 = pointer to `41`.
- Model byte at [r78+2] (0x411D-0x412B): **0x16 MT-32/LA** goes to L413C, **0x14 D-50** goes to L4A42. Anything else is dropped (or fed to the handshake wait while one is running).
- The device byte is not checked here. Each area checks it later (see below).

### Command byte: table 0x45EA, dispatch 0x45C0 (C)
| idx | cmd | handler | checksum checked? |
|---|---|---|---|
| 0 | 42 DAT | L4195 (= write like DT1, then ACK) | yes |
| 1 | 40 WSD | L415D (device = unit# or any part channel. Busy gets RJC, otherwise ACK and wait) | yes |
| 2 | 41 RQD | L417D / L4253 (send DAT packets, wait for ACK, resend on ERR, finish with EOD) | yes |
| 3 | **12 DT1** | **sub_41BB** | yes |
| 4 | **11 RQ1** | **L42A9** | yes |
| 5,6,8 | 43 ACK, 4E ERR, 4F RJC | L44B2 (clear handshake state 0xF4FA) | no |
| 7 | 45 EOD | L44A3 (ACK, end) | no |

- **Checksum: sub_458F.** It adds every byte from the first address byte up to the first byte with bit 7 set, checksum included. `& 0x7F == 0` means OK. It then **overwrites the checksum byte with F7** so the write loop stops before it.
- **On a bad checksum (L4054):**
  - The message is not applied.
  - The LCD string "Exc. Checksum error" (0x4013, pointer 0x4012) is shown.
  - In a handshake, ERR (4E) is also sent (sub_460F).
- **Handshake errors:**
  - Timeout (about 64K polls in sub_4690): "Exc. Timeout occured" (0x403F) and RJC.
  - Wrong frame inside a handshake (40C1-40D3): "HandshakeSequenceERR" (0x4029).
- Frames go out through sub_4617/sub_4632 as `F0 41 dev 16 cmd F7`.
- **Bug (I):** for DT1/DAT, sub_41BB sets 0xF4F8 to address-mid (0x41C6-0x41CB) instead of the device. So a timeout RJC after a DAT carries the wrong device ID.

### Address decode: sub_46AF, then sub_44B8 (C, tables 0x4502 / 0x450E)
- The 3-byte address is copied into 0xF6A5-7 (sub_455D). Offset = mid*128 + lo (0x44E1-0x44E9). Offset must be less than the length, otherwise the address is invalid.
- RAM pointer = base + offset. Remaining length = length - offset.

| Addr | Length | RAM | Device rule (sub_46AF) | MT-32? |
|---|---|---|---|---|
| 00 xx xx | 0x10 | 0xE000 + 16*part | dev = **MIDI channel** of a part (first match, rhythm allowed) | yes |
| 01 xx xx | 0x154 | 0xE090 rhythm setup (85 x 4) | dev = rhythm part's channel (0xF30B) | yes |
| 02 xx xx | 0xF6 | 0xE1E4 + 0xF6*part | dev = MIDI channel of a **melodic** part (0-7) | yes |
| 03 xx xx | 0x1E4 | 0xE000 patch temp x 9 + rhythm setup | dev = unit# (0xEDB7, default 0x10) | yes |
| 04 xx xx | 0x7B0 | 0xE1E4 timbre temp x 8 | unit# | yes |
| 05 xx xx | 0x400 | 0xE994 patch memory x 128 | unit# | yes |
| **06 xx xx** | **0x2000** | **0xC000-0xDFFF** (64 x 128-byte records, see below) | unit# | **no** |
| 08 xx xx | 0x4000 | 0x8000 (RAM bank 0x11) timbre memory 64 x 256 | unit# | yes |
| 10 xx xx | **0x21** | 0xED94 system (MT-32 = 0x17) | unit# | 23 bytes yes, **10 00 17-20 extra** |
| 20 xx xx | 0x81 | 0xF6AC display (only 21 bytes writable, clamp 0x479E) | unit# | yes |
| **30 xx xx** | 1 | 0xF6CE demo control | unit# | **no** |
| 7F xx xx | - | all-parameter reset (L41D5: sub_234D + sub_502A + sub_4F38, also **wipes timbre memory**) | unit# (sub_4720) | yes |
| **40 0m ll** | - | CK-34 command area (L48BB, below) | unit#, and no handshake in progress | **no** |

- **Write loop sub_41F7** (C):
  - Data that runs past the end of an area is cut off there (an F7 is planted at 0x421E-0x422B).
  - Each byte is passed through **sub_472E** (cap at the max value). A max of 0 means the byte is **skipped**: dummy bytes, timbre padding 0xF6-0xFF, display beyond 21 chars.
  - If the start address is invalid, the loop skips to the next address-hi block (sub_43B8) and carries on with the remaining data.
- **Max-value (clamp) tables** (C): patch 0x4843, rhythm 0x483F, system 0x485C (only 23 entries, so the 10 extra system bytes reuse the timbre-name maxes = 0x7F), timbre 0x4873 (14 common + 58 partial bytes; WG waveform max 3 = both PCM banks), performance records (0x4800-0x4829). These tables have the same layout and spacing as Munt's CM-32L 1.02 maxima (0x48CB/0x48CF/0x48E8/0x48FF), each 0x8C lower here. The startup string sits at 0x1EF0, the same as MT-32 2.0x / CM-32L 1.00, and ROM 0x8000/0x8100/0x8500/0x8580 = Munt's CM-32L timbre/PCM/rhythm table addresses. **So the SysEx core is MT-32 v2 / CM-32L code** (addresses C, shared code base I).
- **After a write, L3E40 dispatches on the address-hi byte (table 0x3E71/0x3E7A)** (C):
  - 00/03 (L3EE0): marks the part dirty in 0xF6E8 and refreshes it through sub_4D9C/sub_4D8C (+ sub_2EE5).
  - 01: sets bit 0 of 0xF6E9.
  - 02/04 (L3EAE): sets the timbre-dirty bits in 0xF6EA/0xF6E8 and bit 7 of 0xF6E9 (I: the voice engine reloads the timbre).
  - 10 (L3F49): copies the channels to the parts, then all-notes-off and controller reset, then partial reserve (sub_5D2C), master tune and reverb (sub_4CE4, reverb latches 0x0400/0x0800).
  - 20: LCD text.
  - 30: demo.
  - 05/06/08: nothing (stored only; patch/timbre memory takes effect on the next program change).
- **RQ1 (L42A9)** (C):
  - Needs the full 3-byte address and 3-byte size (0x42AB).
  - Serves **address-hi 00-10 only** (`cmpb 0xF6A5,#0x11`, 0x4303).
  - Builds `F0 41 dev 16 12 addr data cs F7` at 0xF4F6, at most **256 bytes** per packet, values capped on the way out. Sends with sub_5EA7, waits about 100 ms (sub_42F3) between packets.

### CK-34-only extensions (C unless marked)
1. **06 = 64 "performance" records of 128 bytes (0xC000 + 0x80*n).**
   - L5E57 builds one record:
     - 10 bytes from 0xEDAB (system 10 00 17-20)
     - 21 bytes from 0xED95 (reverb, partial reserve, channels)
     - 8 x 12 bytes of patch temp
     - the rhythm level (0xE088)
   - The only reader in traced code is RQ1. No code that loads a record back was found.
   - I: a store for arranger setups, and the 10 extra system bytes are probably a name.
2. **40 0m ll command area** (L48BB-L49DC):
   - Takes **one data pair (v1, v2)**. If ll is odd, the first data byte is skipped.
   - v2 bit 0 = 1 makes the stub sub_49DD return 1 ("refused").
   - Every command answers on TX with `F0 41 [unit] 16 12 40 10 00 rc cs F7` (L491E). rc = 0 OK, 1 refused, 3 for `40 03`.

   | Command | Effect |
   |---|---|
   | `40 00 2p` | timbre temp of part p goes to RAM 0x8000 + v1*256 + v2, 246 bytes (= **timbre WRITE** to slot v1). **No range check on v1: v1 >= 0x40 writes into fixed RAM 0xC000-0xFFFF** (I: possible code-poke path) |
   | `40 01 2p` | patch temp of part p, bytes 0-7, goes to patch memory slot v1 (0-127) |
   | `40 02 00` | store the current setup into performance slot v1 & 0x3F |
   | `40 03 xx` | ping |
3. **30 00 00 = v (max 6)**, through L3FA4 and sub_5C64:
   - It sets the demo-play mode: 1 = chain from song 0, more than 1 = random (sub_5C99).
   - It then plays song data from banked ROM (L3D78, sub_3E2B).
   - I: the meaning of each value is not fully traced.
   - Dead code at 0x237C (behind the unreachable `sjmp` at 0x22DA) stops the demo only on the exact bytes `41 10 16 12 30 00 01 00 4F F7` (0x2396).
4. **Model 0x14 (D-50) at L4A42:**
   - dev = MIDI channel of a melodic part. Address `00 hi lo` (offset < 0x1A5 = the D-50 temp area). cmd 11/12. Checksum checked (0x4A5B).
   - sub_4BEE maps D-50 offsets with the ranges at 0x4BD6:
     - lower P1/P2 go to LA partials 1/2, upper P1/P2 to partials 3/4 (0x3A each, from 0xE1F2)
     - common params go through map 0x4BAF: F0 = structure byte at 0xE1EE+0/1, F1 = partial-mute bits 0xE1F0
   - Values are copied raw and capped by the LA max table (sub_4AC7). The D-50 patch block (0x180-0x1A4) is ignored.
   - There is **no post-write refresh** call: it returns through L4159 (I: takes effect on the next note).
   - RQ1 converts back (sub_4CA1 into 0xF4F6) and sends `F0 41 dev 14 12 00 ..` packets of 256 bytes or fewer (0x4B0C-0x4B74).

---

## 4. What the PRO-E's 68HC11 actually sends (cross-check, C bytes and code)
- **Boot**, IC4 0xC125/0xC14E:
  - Bank 0 L5251 sends the template `F0 41 10 16 12` (bank 0 0x53B2).
  - L526B adds the checksum.
  - Message sent: `F0 41 10 16 12 10 00 04 04 04 04 00 00 04 04 00 0C cs F7`, i.e. partial reserve 4/4/4/0/0/4/4/0, rhythm 12.
- **"PRO E AUDIO TEST"**, IC7 bank 1 0xBB98-0xBBB8: streams bytes 0xBBBA-0xBC6E to the CK-34, then turns the SCI off and halts.
  - `F0 41 01 16 12 02 00 00` + 130 bytes (name, common, partials 1-2) = **an LA timbre loaded into the timbre temp of the part on ch 2**
  - `10 00 01 00 00 00` (reverb mode/time/level 0)
  - `10 00 16 7F` (master volume)
  - dev 01 `00 00 08 7F` (part level)
  - `B1 0A 3F` (pan)
  - `91 45 7F` (A4 note on)
- A byte search of IC4 and all IC7 banks found no fixed template for model 0x14, `06`, `30` or `40` messages (I: the HC11 may still build them at run time; not traced).

## 5. Conclusion: can LA tones be edited from outside?
**Yes, with standard MT-32/CM-32L SysEx (C).**
- **Per part, by MIDI channel:** `F0 41 <ch 0-15> 16 12 02 00 00 <name10><common4><partial 58 x 1-4> cs F7` writes that part's timbre temp. This is the same message type the PRO-E's own audio test sends.
- **Global:**
  - device 0x10: `04 xx xx` writes the timbre temp of all 8 parts.
  - `08 xx xx` writes the 64 user timbres (select them with patch timbre group 2 via `03`/`05`).
  - `03` patch temp, `10` system/reverb/channels/partial reserve.
- Waveform can reach both PCM banks (max 3), so the CM-32L extra samples are usable.

**Practical limits:**
1. The external MIDI IN goes to the HC11's ACIA, not to the CK-34. Stock firmware passes SysEx on only if its MIDI-thru logic does that (that is a Board-1 question). Other ways in: new HC11 firmware (send through $E82E, the SCI to the CK-34), or a MIDI source wired directly to the CK-34 RX pin.
2. Edits are lost at power-off: sub_502A runs on every boot and timbre memory is wiped. The HC11 has to store and resend them, for example from its battery-backed SRAM.
3. Nothing comes back (RQ1, handshake, 40-area status) unless HC11 firmware sets SCCR2 RE and the CK-34 TX is wired to the HC11 RXD (I). So use one-way DT1 only. Send at most 256 data bytes per message and leave a gap between messages (Roland practice is 20 ms or more; one 266-byte frame already takes about 85 ms on the wire). The MIDI queue holds about 1 KB. Do not use WSD/RQD: they block the CK-34 main loop for up to about 64K polls while waiting.
4. Device IDs: per-part areas use the part's MIDI channel (default parts 1-8 = ch 2-9 unless the HC11 changed 10 00 0D-15). Global areas need 0x10. Unit# and Overflow Assign cannot be set by SysEx (0xEDB5/0xEDB7 lie past the 0x21-byte system area).

## 6. Mod hooks
- 0x4502 / 0x450E (length, base) and 0x3E71 / 0x3E7A (post-write): **table-driven address map**. Adding an area means adding one entry.
- 0x45EA / 0x45C0: command table (9 entries, terminated by 00).
- 0x39DE: 128-entry CC table. Most entries are 0, so new CCs are free to add.
- 0x2466: channel-message table. Ax/Dx point at a `ret` (0x2498), so aftertouch is unused and free.
- L48BB / jtab 0x4918: the CK-34 command area 40 0m.
  - 40 03 is a free ping.
  - sub_49DD (0x49DD) is a 4-byte stub that always returns 1.
  - 0x49E1-0x4A41 is untraced code that builds a WSD frame (handshake sender).
- `40 00` has no slot check, so it can write 246 clamped bytes anywhere in 0xC000-0xFFFF (I).
- 0x06 area 0xC000-0xDFFF = 8 KB of SysEx-writable RAM that nothing reads back. Free scratch, or a place for code.
- 0x237C-0x2465: dead demo-time event loop, reusable space. Free 0xFF runs in IC28: 0x1F0F-0x1FFF (241 bytes), 0x2019-0x207F, 0x2197-0x21FF, **0x606A-0x6FFF (3990 bytes)**, **0x78A9-0x7FFF (1879 bytes)**. These are free space for a patched 27C512 replacement (C, byte scan).
- The 8098 TX ring at 0xFF00 is the reply channel for every protocol above.

## 7. Open questions
- Does stock HC11 firmware pass external SysEx through to the CK-34, and is the CK-34 TX wired to the HC11 RXD? Check the service-notes block diagram and the board.
- Is there a loader for the 06 "performance" records somewhere in untraced code? Is 10 00 17-20 a name?
- Values of the demo control 30 00 00 and the demo data bank: sub_5EFD, and `rac == 0x26` at 0x244D suggests bank numbers above 3. Is the TC531000 really 128 KB, with a 64 KB dump only half of it?
- Does a model-0x14 write or a `08` timbre-memory write sound on the next note-on without the dirty flags (0xF6E8/0xF6EA)? A hardware test is needed.

**TL;DR (again)**
- The CK-34 is an MT-32/CM-32L SysEx target: model 16, DT1/RQ1 plus handshake, checksum checked, device = MIDI channel for 00/01/02 and 0x10 for the rest.
- LA tones can be edited with DT1 to `02 00 00` (per channel) or `04`/`08` (device 0x10). The PRO-E's own audio test does exactly that.
- Extras: model 14 (D-50 converted to LA), 06 (8 KB performance RAM), 30 (demo), 40 (write/store commands with replies).
- Volatile across power cycles. Replies go nowhere on stock hardware.
