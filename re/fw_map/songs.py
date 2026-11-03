"""Walk the 5 demo songs (IC7 bank 1, table $E716 in IC4: 6 track ptrs, track mask, $180D value; 14 B each).
Song event format = composer format (reader $D974-$D9F1, command fetch $E1B8):
  note:    [nn <$80] [v: bit7 = delta follows, bits0-6 velocity (0 = off)] [delta...]
  command: [ss >=$80, bit6 = delta follows, ss&$1F = cmd 0..27] [data] [data2 if cmd==1] [delta...]
  delta:   bytes with bit7 set = 127-tick... continue; last byte <$80 ($D97D-$D9A8)
  $FE = end of track
"""
import os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import styles as S
ic4 = S.ic4
def r4(a): return ic4[a - 0xC000]
TRACK = ['SOLO', 'LOWER', 'ARRANGER', 'M.BASS', 'M.DRUMS', 'SFX']
def walk(bank, a, limit=20000):
    t = 0; start = a; cmds = collections.Counter(); notes = 0
    rd = lambda x: S.rd(bank, x)
    for _ in range(limit):
        b = rd(a)
        if b == 0xFE:
            return t, notes, cmds, a - start + 1
        if b & 0x80:
            cmd = b & 0x1F; cmds[cmd] += 1
            a += 2 + (cmd == 1); flag = b & 0x40
        else:
            v = rd(a + 1); notes += (v & 0x7F) != 0
            a += 2; flag = v & 0x80
        if flag:
            while True:
                d = rd(a); a += 1
                t += d & 0x7F
                if not d & 0x80: break
    return None
if __name__ == '__main__':
    names = ['TIME OUT', 'YAH YAH!', 'PASADENA', 'MY RADIO', 'YUPPI']
    lo = 1 << 20; hi = 0
    for k in range(5):
        e = 0xE716 + 14 * k
        ptrs = [r4(e + 2 * i) << 8 | r4(e + 2 * i + 1) for i in range(6)]
        mask = r4(e + 12); bk = r4(e + 13) >> 4
        print(f'DEMO{k + 1} "{names[k]}"  entry ${e:04X}  mask ${mask:02X}  $180D=${r4(e + 13):02X} (bank {bk})')
        for i, p in enumerate(ptrs):
            if not p: continue
            res = walk(bk, p)
            if res is None: print(f'   {TRACK[i]:8s} ${p:04X}  no $FE'); continue
            t, n, c, size = res
            lo = min(lo, p); hi = max(hi, p + size)
            print(f'   {TRACK[i]:8s} ${p:04X}-${p + size - 1:04X} {size:5d} B {t:6d} ticks ({t / 96:.1f} bars 4/4) {n:4d} note-ons cmds {dict(sorted(c.items()))}')
    print(f'demo data span ${lo:04X}-${hi - 1:04X}')
