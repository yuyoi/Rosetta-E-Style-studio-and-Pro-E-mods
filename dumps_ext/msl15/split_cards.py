"""Split the MSL-15 dump (16 x 32 KB TN-SC1 style cards) into one file per card + CARDS.txt."""
import hashlib, os

D = os.path.dirname(os.path.abspath(__file__))
b = open(os.path.join(D, 'msl15_read2.bin'), 'rb').read()
IN_MAME = {1, 2, 4, 5, 6}
lines = []
for i in range(16):
    blk = b[i * 0x8000:(i + 1) * 0x8000]
    card = blk[0x10:0x19].decode('latin1')
    names = []
    for k in range(8):
        n = blk[0x30 + 16 * k:0x40 + 16 * k].decode('latin1').strip()
        if n and n not in names:
            names.append(n)
    tag = card if i < 14 else card + ('_asia' if i == 14 else '_turkey')
    fn = f'card{i:02d}_{tag}.bin'
    open(os.path.join(D, fn), 'wb').write(blk)
    where = '(= MAME)' if i in IN_MAME else '(NOT in MAME)'
    lines.append(f'{hashlib.sha1(blk).hexdigest()}  {fn}  styles: {", ".join(names)}  {where}')
head = 'MSL-15 = 16 x TN-SC1 style cards (32 KB each), from msl15_read2.bin (reads 2 and 3 identical; read 1 = all FF, failed).\n'
open(os.path.join(D, 'CARDS.txt'), 'w', encoding='utf-8').write(head + '\n'.join(lines) + '\n')
print('\n'.join(lines))
