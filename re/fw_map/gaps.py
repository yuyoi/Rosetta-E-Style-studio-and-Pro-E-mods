"""gaps.py <img48k> <listing> <lo_hex> <hi_hex> [minlen]: unreached byte ranges + a guess of what they hold."""
import sys, re
img = open(sys.argv[1], 'rb').read(); base = 0x10000 - len(img)
lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
minlen = int(sys.argv[5]) if len(sys.argv) > 5 else 16
cov = bytearray(0x10000)
for l in open(sys.argv[2], encoding='utf-8'):
    m = re.match(r'^  ([0-9A-F]{4})  ([0-9a-f]+) ', l)
    if m:
        a = int(m.group(1), 16)
        for i in range(len(m.group(2)) // 2):
            cov[a + i] = 1
# all 16-bit big-endian words in the image (pointer candidates)
words = {}
for i in range(len(img) - 1):
    words.setdefault((img[i] << 8) | img[i + 1], []).append(i + base)
a = lo
tot = 0
while a <= hi:
    if not cov[a]:
        b = a
        while b <= hi and not cov[b]:
            b += 1
        n = b - a
        if n >= minlen:
            s = img[a - base:b - base]
            pr = sum(32 <= c < 127 for c in s) / n
            kind = 'FF' if s.count(0xFF) == n else ('text' if pr > 0.8 else 'bin')
            refs = [w for w in words.get(a, []) if not (a <= w < b)][:4]
            print(f'${a:04X}-${b-1:04X} {n:5d} {kind:4s} ptrs-to-start:{" ".join("%04X" % r for r in refs)}  {s[:24].hex(" ")}')
            tot += n
        a = b
    else:
        a += 1
print('total', tot)
