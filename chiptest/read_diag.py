"""Compare several reads of one chip: which address lines flicker, which data bits flip, and a majority-vote image."""
import sys, zlib, collections

reads = [open(f, 'rb').read() for f in sys.argv[2:]]
n = len(reads[0])
vote = bytearray(n)
unstable = 0
for i in range(n):
    c = collections.Counter(r[i] for r in reads)
    v, k = c.most_common(1)[0]
    vote[i] = v
    if k < len(reads):
        unstable += 1
open(sys.argv[1], 'wb').write(vote)
print('bytes not unanimous', unstable, 'vote crc %08x' % zlib.crc32(vote))
for idx, r in enumerate(reads):
    d = [i for i in range(n) if r[i] != vote[i]]
    if not d:
        print(f'read{idx}: identical to vote')
        continue
    lines = {k: sum(1 for i in d if r[i] == vote[i ^ (1 << k)]) for k in range(19)}
    top = sorted(lines.items(), key=lambda t: -t[1])[:3]
    bits = 0
    for i in d:
        bits |= r[i] ^ vote[i]
    print(f'read{idx}: {len(d)} off vote; address-line hits {[(f"A{k}", h) for k, h in top]}; data bits {bin(bits)}')
