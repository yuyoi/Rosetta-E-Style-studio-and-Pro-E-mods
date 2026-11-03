# Extra outputs: how the D-110 does it, and what the CK-34 already has

## D-110 (the author's own D-110 OS v1.10 dump)
LA32 control byte write at 0x36C2 (`stb r70, 0x0D00[r54]`), built at 0x365F-0x36BD:
- index = part's **output assign** (RAM 0xE006[part], rhythm 0xE093[key]) -> table **0x1725** (8 bytes)
- entry bit 7 set = "mix": pan comes from the pan table 0x17BE (3 bits). Otherwise the entry's own low 3 bits are a fixed pan.
- result = (ra8 & 0xE0) | entry bits -> LA32 0x0D00 (b4/b3 = routing group, b2-0 = pan)

| assign | byte | routing b4b3 | pan b2-0 | = |
|---|---|---|---|---|
| 0 | 90 | 2 | from pan table | MIX |
| 1 | 90 | 2 | from pan table | MIX |
| 2 | 18 | 3 | 0 (R) | multi |
| 3 | 1F | 3 | 7 (L) | multi |
| 4 | 07 | 0 | 7 | multi |
| 5 | 0F | 1 | 7 | multi |
| 6 | 00 | 0 | 0 | multi |
| 7 | 08 | 1 | 0 | multi |
=> **6 multi outs = 3 routing groups (b4b3 = 0, 1, 3) x hard L/R pan.** The LA32 puts each group into its own slot of the DAC stream, and the D-110 analog side samples more slots than L/R.

## CK-34 (IC28)
Table **0x39C2 = 98 90 18 1F 07 0F 00 08**: the same table (entry 0 = 98 = mix + no-reverb bit).
Stock code only indexes it with the "reverb switch" 0/1 (patch max 1), **but the rhythm-setup max is 7** (0x483F), so rhythm keys can already select entries 2-7 = multi routing.
So the LA32 on the CK-34 can already send partials to the multi slots. The board just doesn't demux them (only L/R are built).

## D-110 analog board (docs/ref_d110/Roland-D110-Service-Notes.pdf p.8)
PCM54HP (IC116, **parallel 16-bit SD0-SD15**) -> I/V op-amp M5238L (IC117) -> **4051 (IC113) COM**, selects A/B/C = SH1/SH2/SH3 + INH from the main board ->
**all 8 channels used**: each 4051 output -> 0.0047 uF hold cap -> NJM072 buffer (IC109-112) -> filter/out stage (IC101-108, uPC4570) -> MIX L, MIX R, MULTI 1-6.
The CK-34 has the same chain: PCM54HP + M5238L + **HD14051BP** (8 channels, only L/R needed for stereo).
=> **Probably the multi slots already reach the CK-34's 4051.** An extra out = 4051 pin -> 4.7 nF hold cap -> op-amp buffer -> D-110-style filter -> jack.
Check next: which HD14051BP channel pins (ch0-7 = pins 13,14,15,12,1,5,2,4) are connected on the CK-34, and that A/B/C come from the LA32 side (3 select lines = 8 slots).
Bonus: PCM54 input is parallel, so the AND-gate bitcrush idea works as planned.

## MT-32 main board (docs/ref_d110/roland-mt32-service-manual.pdf p.9): the closest match to the CK-34
4051 IC6: X0 pin13 = L REV, X1 pin14 = R REV, X3 pin12 = L SYN1, X7 pin4 = R SYN1, X2 pin15 = L SYN2, X6 pin2 = R SYN2, **X4 pin1 + X5 pin5 UNUSED**.
Each used slot: 0.0047 uF hold cap + NJM-072D buffer (IC18/19/2). SYN1 + SYN2 (6.8 K) + REV (10 K) are summed per side into an M5218 2-pole filter (IC1/IC3) -> out.
=> Extra outs on the CK-34 (if wired like the MT-32): (1) split SYN1 / SYN2 / REV after their buffers = dry1, dry2 and wet as separate stereo pairs, no new S/H; (2) X4/X5 = 2 more S/H slots (needs LA32 routing to them, test).

## What extra outs need
1. Hardware: sample-and-hold channels for the extra slots after the PCM54, copied from the D-110 output stage. **Needs the D-110 service notes** (soundprogramming.net Roland_D-110_ServiceNotes.pdf: user downloads, the site blocks scripts) for slot timing and the S/H clocks.
2. Firmware: allow patch "reverb switch"/output 0-7 (patch max table 0x4843 entry 1 -> 7) or a new output-assign byte, plus a synth-mode OUTPUT page.
3. Quick no-solder test once a path to the CK-34 exists: set a rhythm key's reverb switch to 2-7. If that drum vanishes from L/R, the routing works. Note that the HC11 MIDI parser swallows external SysEx (model forced to $22), so the test needs new HC11 firmware or a direct feed to the CK-34 RX.
