"""Walk the 37 sound-effect sequences (keys 76..112) from the bank-0 table $BFA1 (ptrs) + $BFEB (bank nibbles).
The effect engine ($C612-$C71F) adds 60 to the note field ($C693 adda #$3C) and sends on ch10 ($EC7A)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import styles as S
b0 = S.ic7[0:0x8000]
tab = [b0[0xBFA1 - 0x4000 + 2 * i] << 8 | b0[0xBFA2 - 0x4000 + 2 * i] for i in range(37)]
nib = [b0[0xBFEB - 0x4000 + i] for i in range(19)]
lo = 1 << 20; hi = 0
for i, p in enumerate(tab):
    bk = (nib[i // 2] >> 4) if i & 1 else nib[i // 2] & 15
    t, n, pr, end, size, ev = S.walk(bk, p)
    lo = min(lo, p); hi = max(hi, p + size)
    notes = sorted({e[2] + 60 for e in ev if e[1] == 'note'})
    print(f'key {76 + i:3d}: bank {bk} ${p:04X} {size:4d} B {t:5d} ticks {n:3d} note-ons -> ch10 notes {notes} end ${end:02X}')
print(f'span ${lo:04X}-${hi - 1:04X}')
