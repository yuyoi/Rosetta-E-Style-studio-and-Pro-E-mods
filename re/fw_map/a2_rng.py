import sys, re
f, lo, hi = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
for l in open(f, encoding='utf-8'):
    m = re.match(r'^\s+([0-9A-F]{4})\s', l) or re.match(r'^L([0-9A-F]{4}):', l)
    if m and lo <= int(m.group(1), 16) < hi and l.strip():
        print(l.rstrip())
