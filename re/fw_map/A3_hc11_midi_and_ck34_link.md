# A3: 68HC11 MIDI and the link to the CK-34 voice board (PRO-E OS v2.00)

Image: `re/map_bank0.bin` (IC7 bank 0 at $4000-$BFFF + IC4 at $C000-$FFFF). Every address below was read in code or data.
**C** = CONFIRMED (seen in code/data), **I** = INFERRED (reasoned, not fully traced).
Helpers: `fw_map/A3_lin.py` (linear disasm, hex immediates), `fw_map/A3_link_tables.py` (prints every channel/status table below from the ROM and rebuilds the boot byte stream).

## TL;DR
- **The link is plain MIDI.** The HC11 sends the CK-34 standard channel messages and **MT-32 DT1 SysEx (`F0 41 10 16 12 ...`)** at 31250 baud, TX only, with running status. Everything passes through one routine, **`$E82E`** (IC4). (C)
- **The CK-34 is used as an MT-32: 8 melodic parts on ch2-9 plus rhythm on ch10.** M.BASS=ch2, LOWER=ch3, SOLO=ch4, ACC1=ch5, ACC2=ch6, ACC3=ch7, A.BASS=ch8, RX-ONLY=ch9, DRUMS+SFX=ch10. (C)
- Program change = tone number 0-127 (the MT-32 preset order of the name list). A SOLO/LOWER/M.BASS change also sends CC7 = part level + a per-tone trim from `$A601`. (C)
- At boot the HC11 queues an MT-32 **partial-reserve SysEx** (4,4,4,0,0,4,4,0,12), then CC7, pan 64 and program changes. A 20 ms task scheduler (`$51C3`, mask `$2673`) then sends bender range, reverb, master tune and master volume as SysEx. **The volume slider is MT-32 master-volume SysEx.** (C)
- MIDI IN: an ACIA on XIRQ fills ring $2000; IC4 `$FF0B`/`$FF31` pumps it into the IC7 parser pieces (`$9703` status, `$9745` data). The parser handles 12 receive parts with their own channels, running status, $F8/$FA/$FC sync, active sensing, and Roland DT1/RQ1 data dumps (`F0 41 10 22 ...`, 4-bit nibbles, Roland checksum). (C)
- Keys: IC15 on IRQ → word ring $2200 → `$FD3F` routes by key mode → part routines → MIDI OUT (`$EBxx`) + CK-34 (`$ECxx`) + song recorder `$D7F1`. (C)

---

## 1. Interrupt and ring layer (IC4)

| Ring | Buffer | Write idx / read idx | Producer | Consumer | Overflow |
|---|---|---|---|---|---|
| MIDI IN | $2000-$20FF (bytes) | $00 / $01 | XIRQ RX `$E7C9` | `$E88B` (C=1 if empty) | $56.3 set, idx reset to 02/01 (`$E7F5`); consumer then calls `$96B2` (reset all) |
| MIDI OUT | $2100-$21FF | $02 / $03 | `$E84D` / `$E85A` | XIRQ TX `$E7FF` | writer spins while full |
| Keys | $2200-$22FF (16-bit words, step 2) | $04 / $05 | IRQ `$E75C` | `$E86F` (D=word, C=1 if empty) | $56.4 set, idx reset (`$E77E`); consumer calls `$E8B5` (all internal parts off) |
| **CK-34 link** | **$2300-$23FF** | **$06 / $07** | **`$E82E` only** | SCI ISR `$E787` | writer spins while full |

All four init in `$E8A8` (write idx = read idx + 1 = empty) (C). Ring semantics: the reader pre-increments, so "empty" means read+1 == write and "full" means write == read (C).

**RAM paging (C):** each ISR forces `$180D` bits 0-1 = 0 before touching the rings and restores `$0A` after (`$E7DD`, `$E79B`, `$E762`). The rings live in RAM page 0. `$180D` bits 0-1 = RAM page for $2000-$3FFF (4 x 8 KB). Proof: the dump mapper `$E6BE` writes `aH` (0-3) into `$180D` and uses CPU addresses $2000-$3FFF. The maskable ISRs (IRQ, SCI) first call `$FC21`. It writes ACIA CR = $16 (ACIA IRQs off) because XIRQ cannot be masked and also writes `$180D`. `$FD95` restores `$180D` and sets CR = $B6.

### XIRQ = HD63B50 ACIA (MIDI) `$E7BA` (C)
- Init `$C015`: CR=$03 (reset), then $96 = RX IRQ on, 8N1, /64 (E clock 2 MHz → 31250). TX IRQ on = $B6 (`$E869`). TX ring empty → $96 (`$E828`).
- RX `$E7C9`: reads $1401. A `cmpa #$F8` at `$E7CC` leads to `brclr $244D,#$80,+0` at `$E7D3`: the branch offset is 0, so it is **dead**. $F8 gets no special ISR handling. The byte then goes through **`$FC97` (ISR SysEx filter)**:
  - Any status < $F8 is latched in `$C7`. $F0 clears the counter `$C5:C6`.
  - While `$C7`=$F0, data bytes are counted. **The 3rd data byte after F0 (= model ID) is replaced by $22** (`$FCB8-$FCBD`). So any model ID passes the parser's `$22` check. (C)
- TX `$E7FF`: sends `$2100[++$03]`. After any byte < $F8 it reloads `$50` = 13 (active-sensing idle timer, §5).

### SCI = link to the CK-34 `$E787` (C)
- Init `$C209`: BAUD=$20 (2 MHz/64 = **31250**). `$C20E` SCCR2=$08 (**TE only, receiver off**). The CK-34 never talks back.
- ISR: if TDRE=0, it reads SCDR and returns. Else it increments `$07`. If the ring is empty it clears TIE (`$E7B3`). Otherwise it pages RAM 0 and writes `$2300[$07]` to SCDR (`$E7A8-$E7AA`).

### IRQ = keyscan (IC15) `$E75C` (C/I)
- Reads a 16-bit word at **`$1B7C`** (`ldy $1B7C`, `$E76D`) and stores it at `$2200+$04`. This is the only access to $1B7C, so the read most likely acknowledges IC15 (I).
- At boot `$C01F-$C052` copies tables `$A4F5-$A5F4` into $1A00-$1AFF and a few bytes into $1B57-$1B7F. They look like velocity curves, so **$1A00-$1BFF is most likely the IC16 keyscan RAM shared with IC15** (I).
- `$1B7F` is written $0A at boot and during dumps (`$D2D4`) and $08 once running (`$D2CE`). Most likely keyscan disable/enable (I).

---

## 2. MIDI IN parser

### Pump (C)
- The live pump is **IC4 `$FF0B`**, called from the main loop at `$C3D4`. IC7 bank 0 has an older pump loop at `$9694-$96B1` that nothing references (dead; a raw search for the bytes 96 94 finds nothing). IC4 patches over it. The reset at `$96B2` right after it is still live.
- `$FF0B`: if `$4C`=0 (no $F8 for 7x20 ms) it re-enables the internal tempo IRQ (TMSK1.OC1I) and clears $56.5 and $5A.4 (external sync lost).
- Then for each byte: `$269A`=$10 (active-sensing watchdog reload). If $5D.7 is set the byte is dropped. Otherwise `$FF31`:
  - data → `$9745`
  - status < $F8 → `$9703`
  - $FE → `$9721`
  - $F8 → `$9BD3` with `$4C`=7
  - $FA → `$9BB7`
  - others → `$9B92`

### State (C)
| Var | Meaning |
|---|---|
| `$268A` | running status (last status < $F8) |
| `$2696` | data bytes still expected. $FF = idle, 2 or 1 = channel message, $0B = SysEx header countdown |
| `$268B`/`$269C`, `$268C` | data1 (plus a copy), data2 |
| `$2697` | receive-part index 0-11 being dispatched |
| `$58.0` | active sensing seen. Afterwards `$269A` counts down in `$9C5D`; at 0 it runs `$96B2` (reset) |

### Status handling `$9703` (C)
- Status while `$268A`=$F0 → `$9EB4` (end of SysEx, §4).
- $F0 → `$2696`=$0B.
- $F1-$F7 → `$2696`=$FF (ignored).
- Channel message → `$2696`=2, or 1 for Cn/Dn (`$9731-$9743`).

### Data handling `$9745` (C)
- Sets $5B.6, `$269B`=5, $0E.5 and $14.5 (MIDI-activity flags; `$9C49` clears them about 5 polls after the last note).
- If `$2696`=$FF, the byte is ignored. If in SysEx → `$9D90`.
- On a complete message (`$9766`), it **loops over all 12 parts** (`$9772-$9798`). For each part whose `$243F+i` has bit 7 set and whose low nibble = the message channel, it jumps through `$97CE`. Several parts can share one channel.
- `$97CE` jumps through `$F62D + ((status>>4)-8)*4`:

| Status | Handler | Notes |
|---|---|---|
| 8n | `$97FF` | forces velocity 0 → note path |
| 9n | `$9D72` → `$9802` | Velocity: `$241A` bit 7 clear = fixed velocity `$241A&$7F` ("MIDI VELOCITY rx"). Notes outside $0C-$78 are dropped. Then `jsr $8AF5` (not traced), then **per-part table `$F64C`** |
| An | `$97E7` | used only by part 10: soft thru `$9CC3` |
| Bn | `$9886` | CC7 (if `$244D.6`, "MIDI VOLUME CC7 rx/tx") → value\*100/127+$80 → table `$F690`. CC1, 10, 11, 64 → table `$F6B2`. **CC ≥ $7B → `$9B27`** = note-offs for every note held on that part (bitmap `$24EF+16*part`). Other CCs are ignored |
| Cn | `$9977` | only if `$244C.5` ("STYLE-TONE PRG C rx/tx") → table `$F6D4` |
| Dn | `$97F3` | part 10 only: soft thru `$9CDE` |
| En | `$9852` | table `$F66E` |

- Every handler re-arms `$2696` (2 at `$97DD`, 1 at `$97E1`), so **running status works** (C).
- After the part loop: a Cn on the `$2450` channel ("STYLE PRG CHANGE midi ch") → `$F5D0` (style select) (C).
- MIDI-in notes set `$5B.3` (`$9802`). That bypasses the part on/off gate on the link (§6.3). MIDI-in notes are **not** echoed to MIDI OUT by these paths. For example, SOLO from MIDI uses entry `$425F`, which sets $62.0 and skips `$EBA0`. (C)

### Receive-part map (index = `$2697`, channel byte = `$243F+i`, limits = `$241C+3i` low/upper/note-shift checked in `$9ABA`) (C)

| i | Part (MIDI menu) | Default ch | Note → | CK-34 result |
|---|---|---|---|---|
| 0 | SOLO | 4 ($83) | `$9A24`→`$425F` | 9n on **ch4** |
| 1 | LOWER | 3 | `$9A2F`→`$4178`→`$EC15` | ch3 |
| 2 | ACCOMP1 | 5 | `$9A3A`→`$EC27` | ch5 |
| 3 | ACCOMP2 | 6 | `$9A45`→`$EC30` | ch6 |
| 4 | ACCOMP3 | 7 | `$9A50`→`$EC39` | ch7 |
| 5 | A.BASS | 8 | `$9A5B`→`$EC42` | ch8 |
| 6 | M.BASS | 2 | `$9A67`→`$4163`→`$EC1E` | ch2 |
| 7 | DRUMS | 10 | `$9A72` (note < $4C) →`$404F`→`$EC66` | ch10 |
| 8 | EFFECT | 11 | `$9A81` ($4C ≤ note < $71) →`$4063` | ch10 via SFX slots, `$EC7A` |
| 9 | RX ONLY | 9 | `$9A94`→`$EC96` | ch9 |
| 10 | NOTE TO ARRANGER | 1 | `$9A9F`→`$42ED` (chord recognition) | none (soft thru for An/Bn/Dn/En) |
| 11 | (12th slot, `$244A`) | 10 | `$F66D` = rts | none |

Default channels come from ROM `$A40E-$A419`, copied to `$243F` by `$D2E3`. They are set to mirror the internal CK-34 layout (C).

Other RX tables: PB `$F66E`, CC7 `$F690`, other CC `$F6B2`, PC `$F6D4`, note-off-all `$F6F8` (used by `$9B60`). Parts 2-5 and 9 call the CK-34 senders directly, e.g. PC `$EB52/$EB65/$EB79/$EB8D/$EADE` and CC `$4896/$489C/$48A2/$4890/$481C`. SOLO/LOWER/M.BASS/DRUMS/EFFECT go through recorder-coded paths instead: `$70` = event code ($80 CC7, $81 PB, $82 CC1, $83 CC64, $84 PC, $95 CC10, $96 CC11), `$71` = track, `$72` = value. Example: PB SOLO `$9857`→`$5555`→`$4923`. Those paths send to the CK-34 and record (C).

### Real-time `$9B8A` + IC4 overrides (C)
- **$F8** (`$9BD1`, IC4 `$FF51`): `$4C` = clock-alive timer, `$5A.4` = clock present. Counted only if `$56.5` (started by FA) and `$244D.7` ("MIDI REAL TIME rx/tx"). Each F8 schedules one internal tick `$E8F6` (inc `$B0`) via TOC4 5 ms later (`$9BEF`: TCNT+$09C4, 2 µs ticks); if one is still pending, it ticks at once. Internal clock = **24 PPQN**. `$2698` counts F8s for the tempo display (`$9C16` → `$E3CB`).
- **$FA**: `$56.0`, internal TOC1 tempo IRQ off, `$EA2C` start, `$56.5` = external sync.
- **$FC**: if `$244D.7` and running → `$E9D9` stop.
- **$FE**: arms the active-sensing watchdog. Timeout → `$96B2`.

### Reset `$96B2` (C)
Used on overflow and on active-sensing timeout. Note-offs for parts 10..0 (`$9B24`). Then it fakes received messages on all 16 channels (`$A0E0`):
- `En 00 40` (bend centre)
- `Bn 01 00` (mod 0)
- `Bn 40 00` (hold off)

These run through the normal dispatch, so they reach the CK-34. It then stops the sequencer if it was externally clocked. **There is no "buffer overflow" text on the HC11.** That string is in the CK-34 ROM.

---

## 3. SysEx: Roland data dump (DT1 $12 / RQ1 $11)

### Receive `$9D90` (C)
- Header bytes are stored downwards at `$268A+$2696`:

| Address | Byte |
|---|---|
| `$2695` | manufacturer |
| `$2694` | device ID |
| `$2693` | model ID |
| `$2692` | command |
| `$2691`/`$2690`/`$268F` | aH/aM/aL |
| `$268E`/`$268D`/`$268C` | size H/M/L (RQ1) |
| `$268B` | checksum (RQ1) |

- At the command byte (`$2696`=8): $12 → clear and check the header now. $11 → collect 7 more bytes. Anything else → abort `$9DCF`.
- Header check `$9DB8-$9DCD`: must be **41 10 22** (Roland, device ID $10 = unit 17, model $22). Byte 3 was already forced to $22 by the ISR, so in practice only `41 10` matters.
- **DT1:**
  - If `$2452.7` (INTERNAL MEMORY protection, default $80 = ON) is set → "INTERNAL MEMORY / PROTECTED !!" (`$9E63`, strings `$62F1/$6301`), abort.
  - Else it reads the 3 address bytes **synchronously** from the ring (`$9DEF` loop on `$E88B`) and adds them into `$268B`.
  - aH routing:
    - 0-3 → "DATA DUMP RECEIVING !!" (`$6331/$6341`), `$5A.3` = data mode, sequencer stopped (`$9B9D`)
    - $20 → `$8F94`/`$7DFC`
    - 4-$0B → card/song paths `$5798/$9444/$9494/$9435` via `$AF` flags
    - else abort
  - Data `$9FD1`: **two nibbles per byte, low nibble first** (`$268E` = low, then high<<4 OR'd in). `$E66E` writes it, then reads it back to verify. A mismatch shows "WRITE ERROR" (`$5B81`). The address auto-increments in 7-bit pairs (`$E661`).
  - End: any status (normally F7) → `$9EB4`. If `$268B&$7F` ≠ 0 it shows **"CHECKSUM / ERROR"** (`$9EC0-$9ED3`, strings `$9EEF/$9EFF`).
- **RQ1** (`$9E75`):
  - aH must be ≤ $0B, and the Roland checksum over `$268C-$2691` must match (`$9E7C-$9E90`).
  - The range is checked (`$A01C`), size H must be 0, and size = (sizeM<<7)|sizeL ≠ 0.
  - `$5A.2` is set. At F7, `$9EB4` → `$9F0F` → **the dump transmit routine answers.**

### Address map (`$E680`, bounds table `$A04A`/`$A050`) (C)

| aH | Target | Valid aM:aL (CPU addr) |
|---|---|---|
| 0 | RAM page 0 | $617F-$7F7F → $30FF-$3FFF (system/backup area) |
| 1-3 | RAM page aH | $4000-$7F7F → $2000-$3FFF (8 KB each) |
| 4-7 / 8-$B | memory card, `$180D`=`$ED50` ($08) / `$ED51` ($0C) | CPU $4000-$BFFF |
| $20 | 32-byte block. `$E6CD` passes each byte to `$51A9`, which copies into LCD buffer `$262D` and redraws | $0000-$001F |

The $20 block looks like **LCD text**: (I) DT1 at 20 00 xx prints on the display.

### Transmit `$9F0F` / `$9F29` (C)
- Shows "DATA DUMP SENDING !!". Stops the tempo IRQ, sets `$1B7F`=$0A and runs all-notes-off `$E8B5`.
- Format: `F0 41 10 <$2693> 12 aH aM aL` then 128 bytes as **lo,hi nibble pairs** (`$9F62-$9F75`), then the checksum (two's complement of the sum of address + nibbles, &$7F) and `F7`.
- Repeats with the next address after a **100 ms** gap: `ldx #$8235` loop at `$9FA0`, 33333 x 6 E-cycles.
- Header bytes from the menu (`$A056`, type = (`$2451`>>4)&$0E, table `$A065`) come from `$F738-$F747`: **41 10 31 11**. So a menu dump goes out as **`F0 41 10 31 12 ...`** (model $31). An RQ1 reply echoes the received header, which reads **$22** after the ISR rewrite.
- Menu dump types:

| Type | Source |
|---|---|
| system | 00 61 7F, size $0F00 (`$A071`) |
| page 1 | 01 40 00, size $2000 (`$A08D`) |
| page 2 / page 3 | same block with aH = 2 / 3 (`$A095`, `$A0A0`) |
| all of the above | `$A0AE` |
| pages 1-3 | `$A0B1` |

---

## 4. MIDI OUT (ACIA TX)

- **`$E84D`** = send A. It does nothing if `$5D.7` is set. Running status uses **`$09`**. It spins on a full ring, queues at `$2100+$02`, and sets CR=$B6 (C).
- **`$E85A`** = raw queue (real-time). It skips running status and the `$5D` mute (C).
- **Part TX channel = the same byte `$243F+i` as RX** (bit 7 = on) (C):

| Message | Routines | Channel byte |
|---|---|---|
| Note | `$EBA0` SOLO, `$EBB9` LOWER, `$EBC0` M.BASS, `$EBC7` ACC1, `$EBCE` ACC2, `$EBD5` ACC3, `$EBDC` A.BASS, `$EBE3` DRUMS, `$EBEA` EFFECT | `$243F,40,45,41,42,43,44,46,47` |
| CC | `$479F...$4813` | same, + `$244D.6` gate for CC7 (converted %→0-127 by `$EC9D`) |
| PB | `$48E4/$48FF/$4908/$4911/$491A` | same |
| PC | `$EA83..$EAD5` (`Cn pp`, gate `$244C.5`), `$EA78` on `$2450`, `$EAD5` on `$244A` | same |

- Real-time out (C):
  - **F8** for each internal tick when `$244D.7` is set (`$C42F-$C438`)
  - **FA** at start (`$EA44`)
  - **FC** at stop (`$EA15`, not sent if started by an external FA)
  - **FE** after 13 x 20 ms with no other output (`$4DED-$4DFB`), which also clears `$09` so the next status is re-sent
- Soft thru (C): `$9CC3`/`$9CDE` re-send the received 3- or 2-byte message when `$244C.3` is set. Wired only to part 10 for An/Bn/Dn/En.

---

## 5. Link to the CK-34: format, routing, examples

### 5.1 Transport (C)
**`$E82E`** (IC4) is the only writer of the $2300 ring:
- `tsta / bpl` → data byte
- `cmpa $08 / beq skip` → **running status in `$08`**
- spin while `$06`==`$07`
- `staa $2300,$06`, inc `$06`
- `bset SCCR2,#$80` (TIE)

A raw-byte search finds 29 JSR/JMP $E82E (listed in §5.3) and no other references. Only these statuses ever reach the CK-34: **9x (91-99), Bx, Cx, Ex, F0/F7**.
- There are **no 8x note-offs**: note-off is `9n kk 00`.
- No An/Dn, no real-time.

On the CK-34 side, `int_serial` 0x1D0F is a MIDI parser. It compares #$F0 at 0x1D46 and treats Cx/Dx as 2-byte messages at 0x1D5D-0x1D61 (C, CK-34 ROM).

### 5.2 Channel map (all C; statuses are immediates read by `A3_link_tables.py`)

| CK ch | PRO-E part | Note-on | Gate / level byte | PC (cache) | CC | PB | MT-32 part |
|---|---|---|---|---|---|---|---|
| 2 | MANUAL BASS | `$EC1E` $91 | `$2403` | `$EB3D` $C1 (`$267A`) +CC7 | `$4878` $B1 | `$493B` $E1 | 1 |
| 3 | LOWER | `$EC15` $92 | `$2401` | `$EB27` $C2 (`$267F`) +CC7 | `$4860` $B2 | `$4935` $E2 | 2 |
| 4 | SOLO | `$EBF1` $93 | `$2400` | `$EAEA` $C3 (`$2680`) +CC7 | `$4834` $B3 | `$4923` $E3 | 3 |
| 5 | ACCOMP1 | `$EC27` $94 | `$2402` | `$EB52` $C4 (`$267E`) | `$4896` $B4 | `$4947` $E4 | 4 |
| 6 | ACCOMP2 | `$EC30` $95 | `$2406` | `$EB65` $C5 (`$267D`) | `$489C` $B5 | `$494D` $E5 | 5 |
| 7 | ACCOMP3 | `$EC39` $96 | `$2407` | `$EB79` $C6 (`$267C`) | `$48A2` $B6 | `$4953` $E6 | 6 |
| 8 | ACCOMP BASS | `$EC42` $97 | `$2408` | `$EB8D` $C7 (`$267B`) | `$4890` $B7 | `$4941` $E7 | 7 |
| 9 | RX ONLY | `$EC96` $98 | none | `$EADE` $C8 (`$2D66`) +CC7 from `$2D65` | `$481C` $B8 | `$495F` $E8 | 8 |
| 10 | DRUMS (arranger) | `$EC4B` $99 | `$2404`, velocity scaled | - | `$48A8` $B9 | `$4959` $E9 | rhythm |
| 10 | DRUMS (keys / MIDI in) | `$EC66` $99 | none; **remaps key 57→73, 58→75** (`$EC66-$EC72`) | - | | | rhythm |
| 10 | SOUND EFFECTS | `$EC7A` $99 | `$2405`, velocity scaled | - | | | rhythm keys 76-108 |

- **Level bytes `$2400-$2408`**: bit 7 = part on, bits 0-6 = level 0-100.
- **Tone bytes**: `$2409` SOLO, `$240A` LOWER, `$240B` M.BASS.
- Factory defaults (`$A3CF` → `$2400` by `$D2E3`):

| Byte | Default |
|---|---|
| levels `$2400-$2408` | E4 D0 CB DA DA DA CB CB DA = SOLO 100, LOWER 80, ACC1 75, M.BASS 90, DRUMS 90, SFX 90, ACC2 75, ACC3 75, A.BASS 90 |
| SOLO tone | 03 |
| LOWER tone | $32 = 50 |
| M.BASS tone | $40 = 64 |

The bank-1 call `jsr $BA21` at `$C08C` was not traced and may change these. (C, defaults)

### 5.3 Note and controller rules (C)
- **Note path `$EBF8-$EC11`:**
  - With `$5B.3` clear (keyboard or arranger), the note is sent only if the level byte has bit 7 set. MIDI-in sets `$5B.3`, which bypasses the gate.
  - Velocity 0 → 0.
  - **Else, if master volume `$2670`=0, velocity is forced to 1** (`$EC0A-$EC0F`).
- **Drums/SFX velocity** (`$EC4B`/`$EC7A`): v' = ((v · (lvl·127/100)·2) >> 8) + 1, where lvl = `$2404` or `$2405` (`$EC50-$EC5D`).
- **PC + volume** (`$EAFD-$EB24`): `Cn pp` then `Bn 07 vv`.
  - The CC status is `$08&$0F|$B0`: it reuses the channel just latched.
  - vv = max(0, level + trim[`$A601`+pp]) · 127/100 (`$EC9D`: mul $7F, idiv 100).
  - A PC is skipped if pp equals the cached program.
  - Trim values are -40..0 per tone. Full table in `A3_link_tables.py`.
- **CC7 for SOLO/LOWER/M.BASS/RX** (`$4834/$4860/$4878/$481C`) adds the same tone trim. The ACC/rhythm CC7 senders do not.
- **Callers of `$E82E`:**

| Callers | Purpose |
|---|---|
| `$484A`/`$484F`/`$485C` | CC |
| `$4927`/`$492C`/`$4931`, `$4963`-`$496D` | PB |
| `$525F`, `$5279`, `$5286`, `$528C` | SysEx |
| `$EAFD`-`$EB24` | PC + CC7 |
| `$EB5C`-`$EB9D` | PC |
| `$EBFE`-`$EC11` | notes |

### 5.4 SysEx to the CK-34: MT-32 DT1 (C)
- `$5251` sends the `$FF`-terminated header **`F0 41 10 16 12`** from `$53B2` and clears the checksum `$2676`.
- `$526B` sends bytes from (Y) up to `$F7`, summing them, then sends `(-sum)&$7F` and `F7`, and clears `$5D.4`.
- **Task scheduler `$51C3`** (called each 20 ms from `$FCC0`):
  - Takes the lowest set bit of **`$2673`** and clears it.
  - Fills `$6C-$78` with $F7 so the message is terminated.
  - Jumps through **`$F89E` + 3·bit**.
  - Boot sets `$2673`=$7A (`$C0DD`).

| Bit | Routine | Message (address = MT-32 map) | Trigger |
|---|---|---|---|
| 0 | `$F89D` (rts) | **unused slot** | - |
| 1 | `$5352` | `03 00 {24,14,04} rr` = **bender range** of patch-temp part 3/2/1 (SOLO/LOWER/M.BASS). rr = `$53B8`[`$244B`&7] = {1,2,3,4,5,6,7,12}. Part mask `$2682` (boot = 7), one part per tick | boot, bender menu |
| 2 | `$52A3` | **reverb switch**: `03 00 {26,16,06} s` for SOLO/LOWER/M.BASS. DRUMS → rhythm-setup key addresses `$58CB` (33 keys: 36-51,54,56,60-73,75), one key per tick via `$2660`. SFX → `$590D` (keys 76-108) via `$2661`. s = `$2451` bit per part, mask `$2681` | reverb part menu |
| 3 | `$520F` | if `$0C.5` (REVERB ON, toggled by `$7142`) → bit-4 message, else `10 00 02 00 00` (time 0, level 0 = off) | REVERB ON/OFF |
| 4 | `$5213` | `10 00 01 mm tt ll` **reverb mode/time/level**. idx = (`$244D`&$3F)>>3. mode<<4\|time from `$53C6` = 01 03 14 17 21 23 36 37, level `$53CE` = 05 04 04 03 06 05 04 07 (Room1/2, Hall1/2, Plate1/2, Delay1/2) | reverb type |
| 5 | `$5398` | `10 00 00 tt` **master tune** = `$30AD`. Factory $4A (`$D7C2`) = MT-32 440 Hz | tune menu |
| 6 | `$53A4` | `10 00 16 vv` **master volume** = `$2670`. Set by the **volume slider**: ADC `$1033` → curve `$A681` (0-100) → `$5706`. Also fade in/out `$4DFD-$4E37` | slider, fades |
| 7 | would jump into `$F8B3` (the next table, mod-lever targets) | no writer seen setting it (I) | - |

### 5.5 Boot byte stream (as queued; defaults; checksums computed) (C)
`$C125`/`$C14E` queue the partial reserve before `$C210` writes SCCR2=$08, which clears the TIE just set by `$E82E`. So **nothing leaves until the first `$E82E` after `$C24B`**, at least about 2 s of `$ED35` delays later. Ring order is kept.
```
F0 41 10 16 12 10 00 04 04 04 04 00 00 04 04 00 0C 4C F7   partial reserve p1-8 + rhythm = 4,4,4,0,0,4,4,0,12 ($C128-$C14E)
B4 07 5F  B5 07 5F  B6 07 5F  B7 07 72  B9 07 7F             CC7 ACC1/2/3, A.BASS, rhythm ($C2CB-$C315)
B3 0A 40  B2 0A 40  B1 0A 40  B7 0A 40  B4 0A 40  B5 0A 40  B6 0A 40  B9 0A 40  B8 0A 40   pan centre ($C32C-$C35F)
C3 03 B3 07 74   C2 32 B2 07 42   C1 40 B1 07 72   C8 03 B8 07 74   PC+vol SOLO, LOWER, M.BASS, RX-ONLY ($C362-$C379)
```
Then one message per 20 ms:
```
F0 41 10 16 12 03 00 24 02 57 F7    bender SOLO = 2 semitones
F0 41 10 16 12 03 00 14 02 67 F7    bender LOWER
F0 41 10 16 12 03 00 04 02 77 F7    bender M.BASS
F0 41 10 16 12 10 00 01 01 04 04 66 F7   reverb Hall 1 (sent twice: tasks 3 and 4)
F0 41 10 16 12 10 00 00 tt cs F7          master tune
F0 41 10 16 12 10 00 16 vv cs F7          master volume (slider)
```
ACC1/2/3 and A.BASS get no program at boot. Their tones come from style data (§6) or MIDI in. MIDI OUT gets the part levels as CC7 on the part channels (`$479F...`, needs `$244D.6`) without the tone trim, e.g. `B3 07 7F` for SOLO.

### 5.6 Other runtime examples (C)
- Key on SOLO, velocity 100: `93 kk 64`. Key off: `kk 00` with running status.
- Part controller reset (`$82C9` SOLO; trigger not traced (I)): `E3 00 40  B3 01 00  40 00` (bend centre, mod 0, hold off with running status). `$82F0`/`$8317`/`$833E` do the same for LOWER/M.BASS/rhythm. Key-mode buttons send the same kind of reset inline (`$7713-$7728`, `$7839-$784E`).
- Panel mod lever (ADC `$1031` → curve `$D724`) → `Bn 01 vv`. Bender (`$1032` → 14-bit table `$D624`) → `En ll mm`. Both go to the keyboard's current part, picked by `$55AA` from `$0E/$0F`, through tables `$F8B3`/`$F8D5` (`$546B`, `$5511`).
- Song playback (`$E26C`/`$E2CB`) uses the same senders per track: 0 SOLO, 1 LOWER, 3 M.BASS, 4 DRUMS, 5 SFX.

---

## 6. Key → note → part → link flow

1. **IRQ `$E75C`** queues the IC15 word (`$1B7C`) in ring $2200 (C).
2. **Main loop `$C3B8`**: `$E86F` → if `$5D.7` drop → **`$FD3F`** (IC4) (C):
   - B&$7F = velocity. If 0 while A.7 is set, velocity = 127.
   - A&$7F = key code.
   - A.7 = key down (I).
3. **Routing by mode flags** (C for branches, I for names):

| Mode | Route | Result |
|---|---|---|
| `$0E.2` (SFX on keys) | `$406B` | key+$4C, velocity>>2, 4 SFX slots `$3B-$46` (init `$D250`) → `$EC7A` |
| `$0E.0` (drums on keys) | `$403D` | key+$24 → `$EBE3` (MIDI OUT) → `$EC66` (ch10) |
| SOLO | `$4266` | key+$24 (`$4266`), `$4545` (+`$244B`>>3 transpose when `$0C.0`), octave `$243D` low nibble (`$48AE`), held map `$248C`, mono/legato `$2457-$2459`, `$EBA0` OUT, `$EBF1` ch4, harmony `$4394` if `$0C.1` |
| LOWER | `$418A`/`$4193` | octave = `$243D` high nibble, held map `$247C`, chord recognition `$44E1/$459C` in arranger modes, `$EBB9`, `$EC15` ch3 |
| M.BASS | `$4148` | octave `$243E`, `$EBC0`, `$EC1E` ch2 |

   Split at key code $13 (`$4229`, `$423C`): key codes below it go to LOWER / M.BASS.
4. Each part path ends in **`$D7F1`** (song recorder; stores when `$10.6` and `$0E.7` are set). Track ids: SOLO 0, LOWER 1, M.BASS 3, DRUMS 4, SFX 5 (C).
5. **Arranger playback** (IC4 `$C900-$CEC6`) (C):
   - It reads style tracks from the IC7 bank picked by `$24C4` (`$C943`: `$ED48` table → `$180D`).
   - A word with bit 7 set is a **program change** for the track: (hi&$3F)|(lo&$40) (`$CCA0-$CCA8`). It goes to `$EB52` ACC1 or `$EB79` ACC3 (selected by `$0C.3`), and to MIDI OUT (`$EA9E`/`$EAC3`).
   - Sounding notes are kept in zero-page slots ($FF = free; init `$D239/$D250`):

| Slots | Part |
|---|---|
| `$27-$2E` | drums |
| `$2F` | A.BASS |
| `$31-$34` | ACC1 or ACC3 |
| `$36-$39` | ACC2 |

   - Note-offs go out at `$C90A` (drums `$EC4B`), `$C932` (A.BASS `$EC42`), `$CB23/$CB42` (`$EC27`/`$EC39`) and `$CB61` (`$EC30`), each paired with the MIDI OUT twin.

---

## 7. RAM variables used here
| Var | Use |
|---|---|
| `$06/$07` | link ring write/read |
| `$08` | link running status |
| `$09` | MIDI OUT running status |
| `$0A` | `$180D` shadow |
| `$1F/$20` | note/value scratch |
| `$4C` | clock-alive timer |
| `$50` | FE idle timer |
| `$5B.3` | "from MIDI IN" |
| `$5D.4` | link SysEx busy |
| `$5D.7` | MIDI/keys muted |
| `$2400-$2408` | part on + level |
| `$2409-$240B` | SOLO/LOWER/M.BASS tone |
| `$241A` | RX velocity mode |
| `$241C-$243C` | 11 x (low, upp, shift) RX limits |
| `$243D/$243E` | octaves |
| `$243F-$244A` | part channels |
| `$244B` | bender range (bits 0-2), transpose (bits 3-7) |
| `$244C.3` | soft thru |
| `$244C.5` | PC rx/tx |
| `$244D.7` | real-time rx/tx |
| `$244D.6` | CC7 rx/tx |
| `$244D` bits 3-5 | reverb type |
| `$2450` | style-PC channel |
| `$2451` | reverb on per part (bits 0-4), dump type (bits 5-7) |
| `$2452.7` | memory protect |
| `$2670` | master volume |
| `$2673` | link SysEx task mask |
| `$2676` | link checksum |
| `$267A-$2680` | last program per CK channel |
| `$2681/$2682` | reverb-switch / bender part masks |
| `$268A-$269C` | MIDI parser |
| `$24EF+16i` | per-part MIDI-held-note bitmap |
| `$2D65/$2D66` | RX-ONLY level/program |
| `$30AD` | master tune |

---

## Mod hooks
- **`$E82E` (IC4)**: the single choke point for CK-34 traffic. Hook it to log or remap channels, or to merge a second source.
- **`$2673` bit 0** dispatches to `$F89D` (rts). This is a **free task slot**: point the `$F89E` JMP at your own routine. The 20 ms scheduler then gives you `$6C-$78` pre-filled with F7, ready for `$5251` + `$526B`, so you can send any **MT-32 DT1 to the CK-34** (tone/timbre edits, part setup).
- **LA SysEx from outside:** today an MT-32 SysEx on MIDI IN dies at `$9DC9` (model must be $22) and byte 3 is rewritten by `$FCBD`. A passthrough (header 41 10 16 → `$E82E`) needs a patch at `$FCB8` plus the `$9DB8` check. Then a computer could edit CK-34 tones through the PRO-E's MIDI IN.
- **Partial reserve:** `ldaa`/`ldd` immediates at `$C12E-$C146` (IC4). The data bytes are at $C12E (address low), $C132-33, $C137-38, $C13C-3D, $C141-42 and $C146.
- **Channel map:** status immediates at `$EAEA-$EC98`, `$4834-$48AA`, `$4923-$4961`. Defaults at `$A3CF-$A42D` (IC7 bank 0). Tone trims at `$A601`.
- **MIDI-in routing:** tables `$F62D/$F64C/$F66E/$F690/$F6B2/$F6D4/$F6F8` (IC4). Re-point a part, e.g. make part 11 (`$244A`, rts at `$F66D`) a second RX-ONLY-style CK part.
- **Back channel:** the SCI receiver is off (`$C20E` SCCR2=$08). Setting RE plus an RDRF branch in `$E787` would let the HC11 read the CK-34. The CK-34 `int_serial` does write SBUF.
- **Free bytes:** IC4 `$FFB1-$FFD5` (37 x $FF) for small patches.
- **Dead code:** IC7 `$9694-$96B1` (old pump) is unreferenced.

## Open questions
- The exact IC15 word format at `$1B7C`. What `$1B7F` $08/$0A does. The 61-key code range.
- The names of the `$0F` bit 0/2/4/6 key modes and `$0C.3` (ACC1 vs ACC3 routing).
- Why menu dumps use model $31 while RX forces $22. Does the owner's manual list $31 or $22?
- What the bank-1 call `$BA21` at boot does. Does it restore panel state over the `$A3CF` defaults?
- `$8AF5` (called for every MIDI-in note), `$EEA6` (MIDI-in CC7 → part level), and the `$244A` slot / `$EAD5` PC-out purpose.
- CK-34 side: does it accept MT-32 timbre and patch-memory writes at 08 xx xx / 05 xx xx? That decides the LA-editing mod.
