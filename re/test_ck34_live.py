"""LIVE CUTOFF patch test (MCS-96 simulator): LIVECUT gives exactly the cutoff Roland's note-on code gives.

  python -I test_ck34_live.py

For many random tones / keys / pitches: run the stock sub_3416 cutoff code (0x36AC-0x3735, r54 = 2p) and the patched
LIVECUT (r40 = 2p, key fetched through the partial's poly) and compare 0xF1C0[2p] / LA32 0x0C41[2p]. Also: PCM partials
untouched, an unchanged cutoff is not rewritten, r76 = 0xF040[2p] on return (the instruction the hook replaced).
"""
import os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'ref_tools'))
import build_ck34_live as L
from mcs96_sim import Sim

rom, code, lc_x = L.build()
stock = open(os.path.join(L.DUMPS, 'ck34_ic28_control_R15179974_CK-34_v2.06.bin'), 'rb').read()
OK = []


def check(c, what):
    assert c, what
    OK.append(what)


PARAMS = 0xE1F2                                  # timbre temp, part 1, partial 1


def setup(s, p, key, pitch, prm, pcm=False, poly=5, mod=0, part=0x20):
    s.m[PARAMS:PARAMS + 58] = bytes(prm)
    s.st(0x56, PARAMS, 2)
    s.st(0xEF40 + 2 * p, pitch, 2)
    s.m[0xEF80 + 2 * p] = 0x80 if pcm else 0x00
    s.m[0xEE01 + 2 * p] = poly
    s.m[0xF400 + poly] = key
    s.m[0xF040 + 2 * p] = 0x33
    s.st(0x50, part, 2)
    s.m[0xF287 + part] = mod


def stock_cut(p, key, pitch, prm):
    s = Sim(stock)
    setup(s, p, key, pitch, prm)
    s.st(0x54, 2 * p, 2)
    s.m[0x47] = key
    s.pc = 0x36AC
    n = 0
    while s.pc != 0x373A:
        s.step(); n += 1
        assert n < 1000
    return s.m[0xF1C0 + 2 * p], s.m[0x0C41 + 2 * p]


def live_cut(p, key, pitch, prm, pcm=False, shadow=None, visits=1, mod=0):
    s = Sim(rom)
    setup(s, p, key, pitch, prm, pcm, mod=mod)
    s.st(0x40, 2 * p, 2)
    s.m[0x47] = 0
    s.m[0xF1C0 + 2 * p] = 0x5A if shadow is None else shadow
    s.m[0x0C41 + 2 * p] = 0xA5
    seen = []
    for _ in range(visits):
        s.call(L.LIVECUT)
        seen.append(s.m[0x0C41 + 2 * p])
    return s.m[0xF1C0 + 2 * p], s.m[0x0C41 + 2 * p], s.m[0x76], seen


rnd = random.Random(7)
for t in range(300):
    p, key = rnd.randrange(32), rnd.randrange(24, 109)
    pitch = rnd.randrange(0x4000, 0xD000)
    prm = [rnd.randrange(0, 101) for _ in range(58)]
    prm[0x02], prm[0x19] = rnd.randrange(17), rnd.randrange(15)      # key follows
    prm[0x1A], prm[0x1B] = rnd.randrange(128), rnd.randrange(15)      # bias point / level
    prm[0x17] = rnd.randrange(101)                                    # cutoff
    want, _ = stock_cut(p, key, pitch, prm)
    old = rnd.randrange(256)
    got, la, r76, seen = live_cut(p, key, pitch, prm, shadow=old, visits=12)
    assert got == want, (t, want, got, seen)
    if want != old:
        assert la == want, (t, seen)
        d0 = abs(want - old)
        assert d0 < 2 or abs(want - seen[0]) <= (d0 + 1) // 2, ('first visit moves about half way', t, old, want, seen)
        steps = [old] + seen
        assert all(min(a, want) <= b <= max(a, want) for a, b in zip(steps, steps[1:])), ('glide overshoots', t, steps)
    else:
        assert la == 0xA5, 'no write when it is already there'
    assert r76 == 0x33
check(True, '300 random tones/keys/pitches: the glide lands exactly on the Roland note-on cutoff, no overshoot')
check(live_cut(3, 60, 0x8000, [50] * 58, pcm=True)[:2] == (0x5A, 0xA5), 'PCM partial left alone')
w, _ = stock_cut(3, 60, 0x8000, [50] * 58)
check(live_cut(3, 60, 0x8000, [50] * 58, shadow=w)[1] == 0xA5, 'unchanged cutoff is not rewritten')
_, _, _, seen = live_cut(3, 60, 0x8000, [50] * 58, shadow=(w + 128) & 0xFF, visits=12)
check(len([v for v in seen if v != seen[-1]]) <= 8, 'a full-range jump settles within 8 visits (%s)' % seen)
# the hook
s = Sim(rom)
check(bytes(rom[L.HOOK:L.HOOK + 5]) == b'\xef' + L.rel16(L.HOOK + 3, L.LIVECUT) + b'\xfd\xfd', 'hook = lcall LIVECUT + 2 nop')
diff = [i for i in range(0x10000) if rom[i] != stock[i]]
check(all(L.HOOK <= i < L.HOOK + 5 or L.LIVECUT <= i < L.LIVECUT + len(code) for i in diff),
      'only the hook and the free-space routine differ from stock (%d bytes)' % len(diff))
for mod in (0, 40, 127):
    w, _ = stock_cut(5, 64, 0x9000, [30] * 58)
    got = live_cut(5, 64, 0x9000, [30] * 58, shadow=0, visits=14, mod=mod)[0]
    check(got == min(255, w + mod), 'mod wheel %d: target = tone cutoff %d + wheel, clamped (%d)' % (mod, w, got))
# ---- live resonance = Roland's sub_3416 resonance byte ----
def stock_reso(p, prm, ef80=0x1C):
    s = Sim(stock)
    s.m[PARAMS:PARAMS + 58] = bytes(prm)
    s.st(0x56, PARAMS, 2); s.st(0x54, 2 * p, 2)
    s.st(0x70, ef80, 1)
    s.pc = 0x3573
    while s.pc != 0x3599:
        s.step()
    return s.m[0xEF81 + 2 * p], s.m[0x0D01 + 2 * p], s.m[0x0D00 + 2 * p]


def live_reso(p, prm, old=0x55, ef80=0x1C, pcm=False):
    s = Sim(rom)
    setup(s, p, 60, 0x8000, prm, pcm)
    if not pcm:
        s.m[0xEF80 + 2 * p] = ef80
    s.st(0x40, 2 * p, 2)
    s.m[0xEF81 + 2 * p] = old
    s.m[0x0D01 + 2 * p] = 0xA5; s.m[0x0D00 + 2 * p] = 0xA5
    s.call(L.LIVECUT)
    return s.m[0xEF81 + 2 * p], s.m[0x0D01 + 2 * p], s.m[0x0D00 + 2 * p]


for res in range(31):
    prm = [50] * 58; prm[0x18] = res
    want = stock_reso(7, prm)
    got = live_reso(7, prm, old=0x00)
    assert got == want, (res, want, got)
check(True, 'resonance 0-30: LIVECUT writes the same 0x0D00 / 0x0D01 bytes as Roland note-on')
prm = [50] * 58; prm[0x18] = 12
w = stock_reso(7, prm)[0]
check(live_reso(7, prm, old=w)[1:] == (0xA5, 0xA5), 'unchanged resonance is not rewritten')
check(live_reso(7, prm, old=0x80)[0] == w | 0x80, 'bit 7 of the partial is kept')
check(live_reso(7, prm, pcm=True)[1:] == (0xA5, 0xA5), 'PCM partial: resonance register (= PCM length) untouched')
print('ALL OK, %d checks' % len(OK))
