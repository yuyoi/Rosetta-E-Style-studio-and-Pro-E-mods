# CK-34 wave ROM format (from Munt mt32emu Synth.cpp / Structures.h)

## Chips
- IC37 R15449121 (TC534000P) = lower 512 KB, MT-32/CM-32L PCM. In MAME. Not read cleanly yet: its pin 8 (A4) leg didn't grip the ZIF. Fix = machined-pin socket in the ZIF.
- IC38 R15179945 (HN62304) = upper 512 KB, CM-32L extra sounds. **Dumped**: dumps/ck34_ic38_wave_R15179945_HN62304.bin == MAME crc 8e9ea06e.
- Together = the CM-32L 1 MB PCM set (Munt/MAME "cm32l_pcm.rom", crc 04204baa = IC37 + IC38).

## Sample encoding
- 1 sample = 2 bytes (s, c) from the raw chip = 16 bits, **bit-scrambled**.
  Munt order table `{0, 9, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 8}`: output bit (15-u) = input bit order[u], where 0-7 = byte s MSB-first and 8-15 = byte c MSB-first.
- The result is a **log-encoded** sample, not linear PCM. The LA32 does exp() on playback (Munt LA32WaveGenerator). Custom samples need linear -> LA32 log conversion, then the scramble.
- 1 MB = 512 K samples (32 kHz-class LA PCM).

## Where loops live: NOT in the wave ROM
The wave map is a table in the **control ROM** (on the Pro-E = IC28, still undumped), 4 bytes per wave:

| byte | meaning |
|------|---------|
| pos | start = pos * 0x800 samples (2048-sample = 4 KB granularity) |
| len | bits 4-6: length = 0x800 << n samples (2 K .. 256 K, powers of two). **bit 7 = loop flag**. bit 0 = follows master tune |
| pitchLSB, pitchMSB | root pitch |

So the loop on/off point, start and length of every wave come from IC28. The wave ROMs are just raw sample data.

## Consequences for custom samples
- Every wave = a power-of-two length (2 K-256 K samples) at a 2 K-sample-aligned start. Loops = the loop flag on the whole wave (check the exact loop region in Munt LA32WaveGenerator before relying on it).
- Changing the wave set = new IC37/IC38 contents **plus** a patched wave table in IC28 (or in the CM-32L control ROM if we go that route).
- Next: read IC28 (pin-22 adapter), find the 4-byte table, then write a pack tool: WAV -> log -> scramble -> W27C040 images + table patch.
