"""Repack test: long WAVs move to bigger slots, the IC12 table is rewritten, nothing else is damaged.
py -3.10 test_repack.py"""
import sys, os, importlib.util
import numpy as np
spec = importlib.util.spec_from_file_location('rs', 'rosetta_studio.pyw'); rs = importlib.util.module_from_spec(spec)
sys.argv = ['x']; spec.loader.exec_module(rs)

rom = rs.Rom(); R = rs.RATE
sec = lambda s: np.sin(np.arange(int(s * R)) / 30.0) * 0.7

def run(swaps, free, out):
    return rs.build(rom, swaps, {}, out, True, {3: 60}, {}, free)

# 1) a 3.9 s wave on a drum slot, an 8.0 s wave on an instrument slot; free enough waves for the two blocks
# e=7 (8.19 s) is deliberately absent. Measured on hardware: a slot that big is half the 1 MB wave space,
# and the only way to fit it is to park ~250 freed waves, which collapses the PCM table and kills the D-110's
# Edit screen. e=6 (4.10 s) is the longest that survives. See check_table_spread().
moves, errs, txt, park = rs.plan_layout(rom, {3: sec(3.9), 32: sec(2.0)}, discard=set(range(128)) - {3, 32})
print('plan', moves, errs, txt)
assert not errs and moves[3][1] == 6 and moves[32][1] == 5, 'expected exp 6 and 5'
files, lines = run({3: sec(3.9), 32: sec(2.0)}, set(range(128)) - {3, 32}, 'repack_out')
print('\n'.join(lines))
c = np.fromfile('repack_out/r15179873.ic12_patched.bin', np.uint8)
ic8 = np.fromfile('repack_out/r15179880.ic8_patched.bin', np.uint8); ic7 = np.fromfile('repack_out/r15179878.ic7_patched.bin', np.uint8)

# 2) every table entry stays legal: inside the 1 MB space and aligned to its own length
for i in range(256):
    pos, lb = int(c[0x900 + 4 * i]), int(c[0x901 + 4 * i]); e = (lb >> 4) & 7
    assert pos + (1 << e) <= 256 and pos % (1 << e) == 0, ('illegal entry', i, pos, e)
print('all 256 table entries aligned and in range')

# 3) the new waves decode to the input
for i, x in ((3, sec(3.9)), (32, sec(2.0))):
    pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
    r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
    d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2])); ref = rs.fit(x, n)
    print('wave %d -> pos 0x%05X slot %.2f s corr %.4f' % (i, a, n / R, np.corrcoef(d, ref)[0, 1]))
    assert np.corrcoef(d, ref)[0, 1] > 0.999

# 4) with nothing freed, a long wave must be refused cleanly (the ROM is 100% occupied)
m2, e2, t2, _ = rs.plan_layout(rom, {3: sec(3.9)}, discard=set())
print('no space free ->', e2[:1])
assert e2

# 5) same-size swap still works in place and leaves the table untouched
files, lines = rs.build(rom, {3: sec(0.2)}, {}, 'repack_out2')
c2 = np.fromfile('repack_out2/r15179873.ic12_patched.bin', np.uint8)
assert (c2 == rom.ctrl).all(); print('in-place swap leaves IC12 identical')

# 6) every length code e=0..7 allocates and lands legal. e=4 is not hypothetical: six bank-2 stock
# entries (222-227) are 1.02 s looped waves with lenb=0xC0, so the LA32 is known to handle it.
# e=5..7 (2.05 / 4.10 / 8.19 s) have no stock precedent and are only proven here in software.
hist = {}
for i in range(256):
    e = (int(rom.ctrl[0x901 + 4 * i]) >> 4) & 7
    hist[e] = hist.get(e, 0) + 1
print('stock length-code histogram', dict(sorted(hist.items())))
assert hist.get(4), 'expected stock 1.02 s entries (the e=4 precedent)'
for e in range(8):
    secs = (0x800 << e) / R
    free = set(range(128)) - {3}
    if e >= 7:
        # Hardware lesson, learned the expensive way. e=7 is 8.19 s, half the whole 1 MB wave space, so
        # fitting it means parking ~250 freed waves. The old planner stacked them all on one 0.06 s slot:
        # 242 of the 256 table entries shared it, the D-110 booted and drew its screen, and the Edit button
        # did nothing. Every entry was individually legal, which is why this test used to be happy.
        # plan_layout now caps sharing at 5 per slot (what factory itself does), which makes e<=6 fit and
        # leaves e=7 genuinely unplaceable. This asserts e=7 is refused with a message that says why.
        try:
            rs.render(rom, {3: sec(secs * 0.9)}, {}, True, discard=free)
            raise AssertionError('e=%d (%.2f s) built, but it should have been refused' % (e, secs))
        except ValueError as ex:
            assert ('nowhere to go' in str(ex)) or ('Edit screen' in str(ex)),                 'e=%d refused for the wrong reason: %s' % (e, ex)
        mv, er, _, _ = rs.plan_layout(rom, {3: sec(secs * 0.9)}, discard=free)
        assert er, 'e=%d should be unplaceable: a slot of %.2f s is half the wave space' % (e, secs)
        print('  e=%d %.2fs: allocated fine, REFUSED by check_table_spread (would kill Edit)' % (e, secs))
        continue
    mv, er, _, _ = rs.plan_layout(rom, {3: sec(secs * 0.9)}, discard=free)
    assert not er, 'e=%d (%.2f s) refused: %s' % (e, secs, er)
    where = 'moved to unit %d exp %d' % mv[3] if 3 in mv else 'fits wave 3 in place (stock exp kept)'
    rd = rs.render(rom, {3: sec(secs * 0.9)}, {}, True, discard=free)
    pos, lb = int(rd.ctrl[0x900 + 4 * 3]), int(rd.ctrl[0x901 + 4 * 3]); got = (lb >> 4) & 7
    if 3 in mv:
        assert mv[3][1] == got == e, 'e=%d (%.2f s) came out as exp %d' % (e, secs, got)
    else:
        assert got >= e, 'e=%d (%.2f s) shrank the slot to exp %d' % (e, secs, got)   # shrinking a wave is never forced
    assert pos % (1 << got) == 0 and pos + (1 << got) <= 256, ('unaligned slot', pos, got)
    print('  e=%d  %5.3f s  %-34s -> pos %3d exp %d' % (e, secs, where, pos, got))
files, lines = rs.build(rom, {3: sec(3.5)}, {}, 'repack_out3', True, {}, {}, set(range(128)) - {3})
c3 = np.fromfile('repack_out3/r15179873.ic12_patched.bin', np.uint8)
for i in range(256):
    pos, lb = int(c3[0x900 + 4 * i]), int(c3[0x901 + 4 * i]); e = (lb >> 4) & 7
    assert pos + (1 << e) <= 256 and pos % (1 << e) == 0, ('illegal entry after an e=6 build', i, pos, e)
d = [(int(c3[0x900 + 4 * i]), (int(c3[0x901 + 4 * i]) >> 4) & 7) for i in range(256)]
stock = len(set((int(rom.ctrl[0x900 + 4 * i]), (int(rom.ctrl[0x901 + 4 * i]) >> 4) & 7) for i in range(256)))
assert len(set(d)) * 2 >= stock, ('table collapsed', len(set(d)), stock)
assert max(d.count(z) for z in set(d)) <= 5, 'more than 5 waves share a slot; factory never does'
print('an e=6 build leaves all 256 entries aligned, %d/%d distinct slots, max 5 per slot'
      % (len(set(d)), stock))
print('NOTE: e=5 and e=6 are proven to build and to keep the table healthy. e=7 cannot be built at all.')
print('      Whether e=5/e=6 actually PLAY is still an open hardware test - that is the whole point.')
print('ALL OK')
