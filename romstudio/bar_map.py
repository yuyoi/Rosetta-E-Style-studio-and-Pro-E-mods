"""Print a per-bar fingerprint of a MIDI file (same id = same notes in that bar) to find a song's sections.

  python bar_map.py song.mid CH[,CH...]   channels are 1-based, e.g. 2,1,10 = guitar, bass, drums
"""
import hashlib, sys
import smf
from midi2style import bar_starts

s = smf.read(sys.argv[1])
chans = [int(c) - 1 for c in sys.argv[2].split(',')]
bars = bar_starts(s)
ids, rows = {}, []
for b in range(len(bars) - 1):
    a, e = bars[b], bars[b + 1]
    cells = []
    for ch in chans:
        ns = [(x.on - a, x.key) for x in s.notes if x.ch == ch and a <= x.on < e]
        if not ns:
            cells.append('--')
            continue
        h = hashlib.md5(repr(ns).encode()).hexdigest()[:6]
        ids.setdefault((ch, h), len([k for k in ids if k[0] == ch]))
        cells.append(f'{ids[(ch, h)]:02d}')
    lo = min([x.key for x in s.notes if x.ch == chans[1] and a <= x.on < e] or [0])
    rows.append(f'{b:3d}:{"/".join(cells)} {lo:2d}')
for i in range(0, len(rows), 6):
    print('   '.join(rows[i:i + 6]))
