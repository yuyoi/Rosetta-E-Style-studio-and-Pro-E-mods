# dumps/: your own chips go here

Nothing from Roland is in this repo. Dump your own PRO-E and check the hashes against `SHA1SUMS.txt`.

| File the tools expect | Chip | How (T48 + minipro) |
|---|---|---|
| `proe_ic4_os_v2.00_051289_27c128.bin` | IC4, 27C128 (socketed) | `-p AM27C128@DIP28 -x -r` |
| `proe_ic7_R15179983_LH53234L_v2.00.bin` | IC7, 2 Mbit mask (desolder + socket) | `-p AM27C020@DIP32 -x -r` |
| `ck34_ic13_reverb_R15179917_HN623257.bin` | CK-34 IC13 | `-p AM27C256@DIP28 -x -r` (== MAME r15179917) |
| `ck34_ic38_wave_R15179945_HN62304.bin` | CK-34 IC38 | `-p AM27C040@DIP32 -x -r` (== MAME cm32l r15179945) |
| `ck34_ic28_control_R15179974_CK-34_v2.06.bin` | CK-34 IC28 | `-p W27C512@DIP28 -x -r`: the whole content is 64 KB. Pin 22 makes no difference and pin 20 is the enable |

Read every chip at least twice and compare. A desoldered leg with old solder on it can make one address line flicker
(one wave ROM did that on A4 / pin 8): sit the chip in a machined-pin socket inside the ZIF.
Only the ROM Studio needs IC4 + IC7. The CK-34 dumps are for the analysis notes.
