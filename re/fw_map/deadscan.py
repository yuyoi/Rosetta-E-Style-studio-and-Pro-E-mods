import os
"""deadscan.py <listing>: IC4 unreached ranges >= 8 bytes, and every 16-bit word in IC4 + all IC7 banks that points into each range."""
import sys, re
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dumps') + '/'
ic4 = open(D + 'proe_ic4_os_v2.00_051289_27c128.bin', 'rb').read()
ic7 = open(D + 'proe_ic7_R15179983_LH53234L_v2.00.bin', 'rb').read()
cov = bytearray(0x10000)
for l in open(sys.argv[1], encoding='utf-8'):
    m = re.match(r'^  ([0-9A-F]{4})  ([0-9a-f]+) ', l)
    if m:
        a = int(m.group(1), 16)
        for i in range(len(m.group(2)) // 2):
            cov[a + i] = 1
src = [('IC4', ic4, 0xC000)] + [(f'b{b}', ic7[b * 0x8000:(b + 1) * 0x8000], 0x4000) for b in range(8)]
a = 0xC000
while a < 0xFFD6:
    if cov[a]:
        a += 1; continue
    b = a
    while b < 0xFFD6 and not cov[b]:
        b += 1
    if b - a >= 8:
        hits = []
        for nm, s, base in src:
            for i in range(len(s) - 1):
                w = (s[i] << 8) | s[i + 1]
                if a <= w < b and not (nm == 'IC4' and a <= i + base < b):
                    hits.append(f'{nm}:{i+base:04X}->{w:04X}')
        print(f'${a:04X}-${b-1:04X} {b-a:4d}  {ic4[a-0xC000:a-0xC000+8].hex(" ")}  refs({len(hits)}): {" ".join(hits[:6])}')
    a = b
