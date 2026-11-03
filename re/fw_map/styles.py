"""Parse the 32 internal PRO-E styles (bank-0 directory at $A701, 197 bytes each) and walk every pattern.
usage: python -I styles.py [--events STYLE PART SECTION CLASS]
Record layout (from the loader at $CF3B-$D1FE):
 +00..+02 drum bank nibbles (section k: byte k/2, lo nibble for even k, hi for odd)
 +03..+0E drum pattern pointers, sections 0..5
 +0F ticks per bar (24 ppqn)   +10 preset tempo (BPM)
 then 4 parts x 45 bytes: 9 bank-nibble bytes + 18 pointers [section][class Ma/mi/7]
   bank of (section k, class c): pair m=k//2, bytes b[3m..3m+2]:
     even k: c0=b[3m].lo c1=b[3m].hi c2=b[3m+1].lo ; odd k: c0=b[3m+2].lo c1=b[3m+2].hi c2=b[3m+1].hi
"""
import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', '..', 'dumps')
ic7 = open(os.path.join(D, 'proe_ic7_R15179983_LH53234L_v2.00.bin'), 'rb').read()
ic4 = open(os.path.join(D, 'proe_ic4_os_v2.00_051289_27c128.bin'), 'rb').read()
NAMES_AT = 0x63D9
SECT = ['BASIC', 'VARIATION', 'FILL>ORIG', 'FILL>VAR', 'INTRO', 'ENDING']
PARTS = ['DRUMS', 'A.BASS', 'ACC1(adv)', 'ACC2(adv)', 'ACC3(simple)']
PART_OFF = [None, 0x11, 0x3E, 0x6B, 0x98]
CLS = ['Ma', 'mi', '7']

def rd(bank, a):
    if a >= 0xC000: return ic4[a - 0xC000]
    return ic7[bank * 0x8000 + a - 0x4000]

def name(i):
    a = NAMES_AT + 8 * i - 0x4000
    return ic7[a:a + 8].decode('latin1')

def nib(b, i):
    return (b[i // 2] >> 4) if i & 1 else (b[i // 2] & 15)

def record(i):
    a = 0xA701 + 197 * i - 0x4000
    return ic7[a:a + 197]

def pointers(r):
    out = {}
    for k in range(6):
        out[(0, k, 0)] = (nib(r, k), r[3 + 2 * k] << 8 | r[4 + 2 * k])
    for p in range(1, 5):
        o = PART_OFF[p]; b = r[o:o + 9]; w = o + 9
        for k in range(6):
            m = k // 2
            if k % 2 == 0:
                bk = [b[3*m] & 15, b[3*m] >> 4, b[3*m+1] & 15]
            else:
                bk = [b[3*m+2] & 15, b[3*m+2] >> 4, b[3*m+1] >> 4]
            for c in range(3):
                j = w + 2 * (3 * k + c)
                out[(p, k, c)] = (bk[c], r[j] << 8 | r[j + 1])
    return out

def walk(bank, a, limit=4000):
    """returns (ticks, n_notes, n_prog, end_byte, size, events)"""
    t = 0; notes = 0; progs = 0; ev = []; start = a
    for _ in range(limit):
        b0 = rd(bank, a); b1 = rd(bank, a + 1)
        if b0 & 0x80:
            kind = ('prog', (b0 & 0x3F) | (b1 & 0x40)); progs += 1
        elif (b0 & 0x3F) >= 0x3E:
            ev.append((t, 'end', b0)); return t, notes, progs, b0, a - start + 1, ev
        elif (b0 & 0x3F) == 0x3D:
            kind = ('nop', 0)
        else:
            kind = ('note', b0 & 0x3F, b1 >> 4); notes += (b1 >> 4) != 0
        if b0 & 0x40:
            dt = (b1 & 15) << 8 | rd(bank, a + 2); n = 3
        else:
            dt = b1 & 15; n = 2
        ev.append((t,) + kind)
        t += dt; a += n
    return t, notes, progs, None, a - start, ev

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--events':
        s, p, k, c = map(int, sys.argv[2:6])
        bk, ptr = pointers(record(s))[(p, k, c)]
        print(f'{name(s)} {PARTS[p]} {SECT[k]} {CLS[c]} bank {bk} ${ptr:04X}')
        for e in walk(bk, ptr)[5]:
            print(' ', e)
        sys.exit()
    use = collections.defaultdict(list)
    print('# style directory (bank 0 $A701 + 197*n)\n')
    print('| # | name | rec | tempo | ticks/bar | drum banks | part banks used |')
    print('|---|------|-----|-------|-----------|-----------|-----------------|')
    for i in range(32):
        r = record(i); ps = pointers(r)
        banks = sorted({bk for (p, k, c), (bk, ptr) in ps.items() if ptr < 0xC000})
        db = ''.join(str(ps[(0, k, 0)][0]) for k in range(6))
        print(f'| {i} | {name(i).strip()} | ${0xA701+197*i:04X} | {r[0x10]} | {r[0x0F]} | {db} | {banks} |')
    print()
    print('# per-pattern lengths (bars) DRUMS: sections B V F>O F>V I E ; parts: Ma/mi/7 per section\n')
    for i in range(32):
        r = record(i); ps = pointers(r); tb = r[0x0F]
        line = []
        for p in range(5):
            cells = []
            for k in range(6):
                cs = []
                for c in (range(1) if p == 0 else range(3)):
                    bk, ptr = ps[(p, k, c)]
                    t, n, pr, end, size, _ = walk(bk, ptr)
                    if ptr < 0xC000:
                        use[bk].append((ptr, ptr + size))
                    cs.append(('e' if ptr >= 0xC000 else '') + (f'{t / tb:g}' if end is not None else '??'))
                cells.append('/'.join(cs))
            line.append(f'{PARTS[p]}: ' + ' '.join(cells))
        print(f'{i:2d} {name(i)}  ' + ' | '.join(line))
    print('\n# bank usage by style patterns (union of [start,end) ranges)')
    for bk in sorted(use):
        iv = sorted(use[bk]); tot = 0; cur = None
        merged = []
        for s, e in iv:
            if merged and s <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        tot = sum(e - s for s, e in merged)
        print(f'bank {bk}: {len(iv)} pattern refs, {tot} bytes covered, span ${merged[0][0]:04X}-${merged[-1][1]-1:04X}, {len(merged)} runs')
