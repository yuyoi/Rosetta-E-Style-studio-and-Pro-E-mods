# LA32 hacks: more wave shapes from the same chip (theories to test)

None of this can hurt her: the CK-34 only writes LA32 registers, worst case is silence, noise or a loud squeal.
Keep the volume low on first tries. Sources: Munt LA32WaveGenerator/Partial (behaviour), our CK-34 map (fw_map B3).

| # | Hack | Theory | Needs | Odds |
|---|---|---|---|---|
| 1 | **RES DECAY** | The resonance byte the CK-34 writes is `r \| ((r << 3) & 0xE0)`: bits 0-4 = resonance amount, bits 5-7 a copy of r bits 2-4. Munt uses r >> 2 for the decay of the resonance sine (table 31,16,12,8,5,3,2,1). So bits 5-7 are probably a separate decay register. Decoupled: low resonance that rings long (glassy, sync-like) or high resonance that dies fast (bark). A new knob. | IC28: LIVECUT writes our own top bits | good |
| 2 | **SYNC sweep** | LA resonance is a decaying sine restarted every half-cycle: sweeping cutoff with high resonance sounds like hard sync. Mod wheel to resonance + cutoff together = a sync lever. | IC28 (LIVECUT already has both) | good |
| 3 | **CRUNCH via ring slave** | Munt: a PCM partial that is the *slave of a ring structure* (S&P, P&P, S*P, P*P) plays **without interpolation**: raw stair-step PCM = SP-1200 grit. Ring it with a master that is nearly a constant (synth square, high cutoff, fixed low pitch) and the product is the raw PCM. | IC7 menu only (struct + params) | worth a try |
| 4 | **Free wavetables from stock ROM** | Table entries can point anywhere in IC37/IC38 with a 2048-sample loop. Entries at steps through a long sample = dozens of new looped waves from data already in her, zero new samples. | IC28 table (wave studio) | certain |
| 5 | **Live PCM loop length** | 0x0D01 on a PCM partial = length/loop code. Rewriting it mid-note may shrink the loop live = buzzy grain / tape-stop shapes. | IC28 test patch | unknown |
| 6 | **Live PCM address = wave scanning** | If the LA32 reads the PCM start register while playing, moving it walks through a sample like a wavetable. | IC28 test patch | unknown |
| 7 | **Unknown control bits** | 0x0D00 bit 4 (routing?) and PCM bit 6 (SAW on PCM) are written but not understood. Setting them on purpose may give a dry/wet route, a second output, or nothing. | IC28 test patch | unknown |
| 8 | **Sub-audio ring = gate** | Ring a pad with a synth square at a few Hz (key follow 0, coarse 0, pitch env down): a free trance gate / chopper. Depends on how low LA pitch goes. | IC7 menu only | good if pitch goes low enough |
| 9 | **PWM** | Write the pulse-width value live from an LFO (planned). | IC28 | good |
| 10 | **Stepped audio-rate pitch** | Rewrite partial pitch from the main loop: crude FM / grit. Rate limited by how often the idle service visits a partial (1 in 32 passes). | IC28 | low |

## The efficient way to test: one "LAB" IC28
One IC28 burn with a small RAM override block (a new SysEx address area, table 0x4502/0x450E) that LIVECUT applies:
RES DECAY bits, resonance/cutoff from the wheel, PCM loop-length override, PCM address offset, control-bit OR/AND masks.
Then every experiment is a LAB page in SYNTH EDIT (IC7) poking those bytes live. No more IC28 burns per idea.
Hacks 3, 4 and 8 need no IC28 change at all.
