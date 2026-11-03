import re, collections, sys
c = collections.Counter()
where = collections.defaultdict(list)
for l in open(sys.argv[1]):
    m = re.search(r'^\s+([0-9A-F]{4})\s+\S+\s+(\w+)\s+.*\$([0-9a-f]{4})\b', l)
    if not m:
        continue
    a = int(m.group(3), 16)
    if 0x1000 <= a < 0x2400:
        key = (a, m.group(2))
    elif 0x3000 <= a < 0xC000:
        key = (a & 0xFF00, m.group(2))
    else:
        continue
    c[key] += 1
    where[key].append(m.group(1))
for (a, mn), n in sorted(c.items()):
    print(f'{a:04X} {mn:6s} {n:3d}  at {" ".join(where[(a, mn)][:6])}')
