"""Simulator test for the IC28 LAB build (build_ck34_lab.py): routing table, clamps, moving-chorus stepper.

  python -I test_ck34_lab.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'ref_tools'))
import build_ck34_lab as LAB
from mcs96_sim import Sim

rom, code, asm = LAB.build()
OK = []


def check(c, what):
    if not c:
        raise AssertionError(what)
    OK.append(what)


check(rom[LAB.ROUTE:LAB.ROUTE + 4] == bytes([0x98, 0x90, 0x80, 0x88]), 'routing: 2 = wet only (theory), 3 = bit 4 off + no send')
check(rom[LAB.PATCH_REV_MAX] == 7 and rom[LAB.SYS_MODE_MAX] == 7, 'clamps: part reverb switch 0-7, reverb mode 0-7')
d = int.from_bytes(rom[LAB.TURN + 1:LAB.TURN + 3], 'little')
check((LAB.TURN + 3 + d) & 0xFFFF == LAB.STEPPER, 'idle turn-around jumps to STEPPER')


def rig(mode, time, level):
    s = Sim(rom)
    s.stubs[LAB.IDLE] = lambda s: None                 # the idle loop = return to the test
    s.m[0xED95], s.m[0xED96], s.m[0xED97] = mode, time, level
    s.m[0xF4A3], s.m[0xF4A2] = 0x10, 0x04              # bit 4 / mode bit kept by the stepper
    for a in range(LAB.CH_LAST, LAB.CH_BIG + 1):
        s.m[a] = 0
    s.t = 0
    return s


def tick(s, dt=500):
    s.t = (s.t + dt) & 0xFFFF
    s.st(0x0A, s.t, 2)
    s.call(LAB.STEPPER)


def pos_of(s):                                         # latches -> sweep position (snake order, gen_chorus.snake)
    c = (s.m[0x0400] & 0x0F) | ((s.m[0x0800] & 0x03) << 4)
    return (c & 0x30) | ((c & 15) ^ (15 if c & 16 else 0))


# chorus I: time 2 (0.51 Hz), level 4 (span 32 -> positions 16-47)
s = rig(4, 2, 4)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
ps = []
both = 0
for i in range(4000):                                  # 4 s of 1 ms ticks
    l0 = (s.m[0x0400], s.m[0x0800])
    tick(s)
    ps.append(pos_of(s))
    if l0[0] != s.m[0x0400] and l0[1] != s.m[0x0800]:
        both += i > 0                                  # tick 0 = the jump from the stock latches onto the sweep
        print("  both latches changed at tick", i)
check(both == 0, 'snake: no step changes both latches (%d did): no in-between positions' % both)
check(min(ps[200:]) == 16 and max(ps[200:]) == 47, 'depth: LEVEL 4 sweeps positions 16-47 (%d-%d)' % (min(ps[200:]), max(ps[200:])))
tops = [i for i in range(1, len(ps) - 1) if ps[i] == 47 and ps[i - 1] < 47]
period = (tops[-1] - tops[0]) / (len(tops) - 1) if len(tops) > 1 else 0
check(abs(period - 1000 / 0.51) < 40, 'rate: TIME 2 = 0.51 Hz (period %.0f ms)' % period)
check(s.m[0x0400] & 0xF0 == 0x10 and s.m[0x0800] & 0xFC == 0x04, 'other latch bits kept (%02X %02X)' % (s.m[0x0400], s.m[0x0800]))
check(s.m[0xF4A3] == s.m[0x0400] and s.m[0xF4A2] == s.m[0x0800], 'shadows follow the latches')
steps = sum(1 for i in range(1, len(ps)) if ps[i] != ps[i - 1])
check(all(abs(ps[i] - ps[i - 1]) <= 1 for i in range(201, len(ps))), 'moves one position at a time (%d moves in 4 s)' % steps)
# a slow main loop: 3 ms between passes keeps the same rate
s = rig(4, 2, 4)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
ps = []
for i in range(1400):
    tick(s, 1500)
    ps.append(pos_of(s))
tops = [i for i in range(1, len(ps) - 1) if ps[i] == 47 and ps[i - 1] < 47]
period = 3 * (tops[-1] - tops[0]) / (len(tops) - 1) if len(tops) > 1 else 0
check(abs(period - 1000 / 0.51) < 60, 'rate holds with a slow main loop (period %.0f ms)' % period)
# under 1 ms: no step
s = rig(4, 2, 4)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
tick(s, 500)
p0, l0 = pos_of(s), bytes(s.m[0x0400:0x0401])
tick(s, 200)
check(s.m[LAB.CH_LAST] | s.m[LAB.CH_LAST + 1] << 8 == 500, 'passes under 1 ms do not step')
# chorus II fast + deep
s = rig(4, 7, 7)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
ps = []
for i in range(1000):
    tick(s)
    ps.append(pos_of(s))
check(min(ps[50:]) <= 2 and max(ps[50:]) >= 61, 'LEVEL 7 sweeps 1-62 (%d-%d)' % (min(ps[50:]), max(ps[50:])))
# REVERB OFF in chorus mode: hands off
s = rig(4, 0, 0)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
s.m[0x0400], s.m[0x0800] = 0x10, 0x04
for i in range(50):
    tick(s)
check(s.m[0x0400] == 0x10 and s.m[0x0800] == 0x04, 'REVERB OFF: latches untouched')
# leaving chorus mode restores the stock time/level latches once
s = rig(4, 2, 4)                                      # the 64-position path (FLANGER; mode 1 = chorus B since IC28 v4)
for i in range(300):
    tick(s)
s.m[0xED95], s.m[0xED96], s.m[0xED97] = 2, 5, 3        # DELAY, time 5, level 3
tick(s)
exp400 = (s.m[0xF4A3] & 0xF0) | 5 | ((3 & 1) << 3)
check(s.m[0x0400] & 0x0F == (5 | 8) and s.m[0x0800] & 0x03 == (3 >> 1), 'mode change: stock time/level back (%02X %02X)' % (s.m[0x0400], s.m[0x0800]))
check(s.m[LAB.CH_POS] == 0xFF, 'restored once (marker set)')
w = (s.m[0x0400], s.m[0x0800])
s.m[0x0400] = 0x77
tick(s)
check(s.m[0x0400] == 0x77, 'and then stays out of the way')
s = rig(4, 2, 7)
ps = []
for i in range(1000):
    tick(s)
    ps.append(pos_of(s))
check(len(set(ps)) > 20, 'FLANGER mode 4 sweeps too (%d positions)' % len(set(ps)))
# ---- v3: JUNO CHORUS B = modes 6 + 7, 128 positions (mode bit 0 = row bit 2 in 0x0800)
def pos_b(s):
    c = (s.m[0x0400] & 0x0F) | ((s.m[0x0800] & 0x07) << 4)
    return (c & ~15) | ((c & 15) ^ (15 if c & 16 else 0))


s = rig(6, 2, 4)
ps, both, modes = [], 0, set()
for i in range(4000):
    l0 = (s.m[0x0400], s.m[0x0800])
    tick(s)
    ps.append(pos_b(s))
    modes.add(6 + ((s.m[0x0800] >> 2) & 1))
    if i and l0[0] != s.m[0x0400] and l0[1] != s.m[0x0800]:
        both += 1
B_LO, B_HI = 64 - LAB.SPAN2[4] // 2, 64 - LAB.SPAN2[4] // 2 + LAB.SPAN2[4] - 1   # p = base + span * tri >> 16
check(min(ps[200:]) == B_LO and max(ps[200:]) == B_HI, 'chorus B depth: LEVEL 4 sweeps %d-%d of 128 = the full Juno range (%d-%d)' % (B_LO, B_HI, min(ps[200:]), max(ps[200:])))
check(len(set(ps[200:])) == LAB.SPAN2[4], 'chorus B: every 1/4-frame position in the sweep is used (%d)' % len(set(ps[200:])))
check(both == 0, 'chorus B: one latch per step, also across the mode 6/7 row (%d)' % both)
check(modes == {6, 7}, 'chorus B moves between modes 6 and 7: %r' % modes)
tops = [i for i in range(1, len(ps) - 1) if ps[i] == B_HI and ps[i - 1] < B_HI]
period = (tops[-1] - tops[0]) / (len(tops) - 1) if len(tops) > 1 else 0
check(abs(period - 1000 / 0.51) < 40, 'chorus B rate: TIME 2 = 0.51 Hz (period %.0f ms)' % period)
check(s.m[0x0400] & 0xF0 == 0x10 and s.m[0x0800] & 0xF8 == 0x00, 'chorus B keeps the other latch bits (%02X %02X)' % (s.m[0x0400], s.m[0x0800]))
check(s.m[0xF4A3] == s.m[0x0400] and s.m[0xF4A2] == s.m[0x0800], 'chorus B shadows follow')
s.m[0xED95], s.m[0xED96], s.m[0xED97] = 2, 5, 3          # leave for DELAY
tick(s)
check(s.m[0x0800] & 0x04 == 0 and s.m[0x0400] & 0x0F == (5 | 8) and s.m[0x0800] & 0x03 == 1,
      'leaving chorus B: stock mode bit 0 (2 -> 0), time and level back (%02X %02X)' % (s.m[0x0400], s.m[0x0800]))
check(s.m[0x021A] & 0x0E == 2, 'leaving chorus B: mode bits 1-3 rewritten for mode 2 (%02X)' % s.m[0x021A])
s = rig(7, 2, 4)
tick(s); tick(s)
check(s.m[LAB.CH_POS] != 0, 'mode 7 is chorus B too')
s = rig(6, 0, 0)
s.m[0x0400], s.m[0x0800] = 0x10, 0x04
for i in range(50):
    tick(s)
check(s.m[0x0400] == 0x10 and s.m[0x0800] == 0x04, 'chorus B OFF: latches untouched')
# ---- IC28 v6 (IC13 v7 SUPER FX): mode 1 = HALL, static; the panel's Juno types send mode 6 itself
s = rig(1, 5, 5)
s.m[0xC8] = 0x00
tick(s)                                                # first pass: the stock latches handed back once
l1 = (s.m[0x0400], s.m[0x0800], s.m[0xC8])
for i in range(2000):
    tick(s)
check((s.m[0x0400], s.m[0x0800], s.m[0xC8]) == l1 and s.m[LAB.CH_POS] == 0xFF and l1[2] & 0x0E == 0 and l1[1] & 0x04,
      'mode 1 HALL: stock latches (mode 1), then the stepper never touches them (%02X %02X %02X)' % l1)
# mode 6 (the panel's JUNO I) from a stock state: chorus B, and it survives a stock rewrite of the mode bits
s = rig(6, 2, 4)
s.m[0xC8] = 0x06                                       # rc8 as sub_4CFC leaves it for mode 6 (bits 1-3 = 3)
ps, both, modes = [], 0, set()
for i in range(4000):
    l0 = (s.m[0x0400], s.m[0x0800])
    tick(s)
    ps.append(pos_b(s))
    modes.add(6 + ((s.m[0x0800] >> 2) & 1))
    if i and l0[0] != s.m[0x0400] and l0[1] != s.m[0x0800]:
        both += 1
check(s.m[0xC8] & 0x0E == 0x06, 'mode 6: mode bits 1-3 = 3 (rc8 %02X)' % s.m[0xC8])
check(min(ps[200:]) == B_LO and max(ps[200:]) == B_HI, 'mode 6 sweeps chorus B %d-%d of 128 (%d-%d)' % (B_LO, B_HI, min(ps[200:]), max(ps[200:])))
check(both == 0 and modes == {6, 7}, 'mode 6 chorus B: one latch per step, rows across modes 6/7 (%d, %r)' % (both, modes))
s.m[0xC8] = (s.m[0xC8] & 0xF1)                         # a stock rewrite with the wrong mode bits
for i in range(300):
    tick(s)
check(s.m[0xC8] & 0x0E == 0x06, 'mode bits re-asserted after a stock rewrite')
s.m[0xED95], s.m[0xED96], s.m[0xED97] = 2, 5, 3        # leave for DELAY
tick(s)
check(s.m[0xC8] & 0x0E == 0x02 and s.m[0x021A] & 0x0E == 0x02 and s.m[0x0800] & 0x04 == 0,
      'leaving: stock mode 2 back in rc8 / 0x021A / 0x0800 bit 2 (%02X %02X %02X)' % (s.m[0xC8], s.m[0x021A], s.m[0x0800]))
# mode 5 JUNO + REVERB: the 64-position path, mode bits untouched
s = rig(5, 2, 7)
s.m[0xC8] = 0x04                                       # mode 5: bits 1-3 = 2
ps, both = [], 0
for i in range(4000):
    l0 = (s.m[0x0400], s.m[0x0800])
    tick(s)
    ps.append(pos_of(s))
    if i and l0[0] != s.m[0x0400] and l0[1] != s.m[0x0800]:
        both += 1
lo, hi = 32 - LAB.SPAN[7] // 2, 32 - LAB.SPAN[7] // 2 + LAB.SPAN[7] - 1
check(min(ps[200:]) == lo and max(ps[200:]) == hi, 'mode 5 sweeps %d-%d of 64 (%d-%d)' % (lo, hi, min(ps[200:]), max(ps[200:])))
check(both == 0 and s.m[0xC8] & 0x0E == 0x04 and s.m[0x0800] & 0x04 == s.m[0xF4A2] & 0x04,
      'mode 5: one latch per step, mode bits 1-3 + mode bit 0 left alone (%d, rc8 %02X)' % (both, s.m[0xC8]))
s = rig(5, 0, 0)
s.m[0x0400], s.m[0x0800] = 0x10, 0x04
for i in range(50):
    tick(s)
check(s.m[0x0400] == 0x10 and s.m[0x0800] == 0x04, 'mode 5 OFF: latches untouched')
# ---- v7: REVERB OFF (time 0 + level 0) routes every new note dry (entry 0), for the dry-B mod ----
for site in LAB.ROUTE_READS:
    rel = int.from_bytes(rom[site + 1:site + 3], 'little')
    check(rom[site] == 0xEF and (site + 3 + rel) & 0xFFFF == LAB.DRYOFF and rom[site + 3:site + 5] == bytes([0xFD, 0xFD]),
          'routing read at %04X -> lcall DRYOFF' % site)
for sw in range(8):
    for t, l, name in ((0, 0, 'OFF'), (0, 3, 'level 3'), (2, 0, 'time 2'), (5, 5, 'on')):
        s = Sim(rom)
        s.m[0xED96], s.m[0xED97] = t, l
        s.m[0x70] = sw
        s.call(LAB.DRYOFF)
        want = rom[LAB.ROUTE + (0 if (t, l) == (0, 0) else sw)]
        check(s.m[0x74] == want, 'DRYOFF switch %d, %s -> %02X (got %02X)' % (sw, name, want, s.m[0x74]))
# ---- v8: REAL PWM (PWMLFO at the end of the live-filter hook) ----
import build_ck34_live as LIVEB
_, lcode, _ = LIVEB.build()
ret = LIVEB.LIVECUT + len(lcode) - 1
check(rom[ret] == 0xE7 and (ret + 3 + int.from_bytes(rom[ret + 1:ret + 3], 'little')) & 0xFFFF == LAB.PWMLFO,
      'LIVECUT ends in ljmp PWMLFO (was ret)')
PB = 0xE300                                            # a partial's params (timbre temp)


def pw_rig(pcm_byte=0x73, wave=0, pw=0, rate=50, pcm_partial=False):
    s = Sim(rom)
    s.m[0x40], s.m[0x41] = 4, 0                        # r40 = 2p (partial 2)
    s.m[0x56], s.m[0x57] = PB & 0xFF, PB >> 8          # r56 = its params
    s.m[0x76], s.m[0x77] = 0x5A, 0xA5                  # the caller's r76/r77
    s.m[0xEF80 + 4] = 0x80 if pcm_partial else 0x00
    s.m[PB + 4], s.m[PB + 5], s.m[PB + 6], s.m[PB + 0x14] = wave, pcm_byte, pw, rate
    s.m[0x0C40 + 4] = 0x11                             # marker: untouched?
    s.t = 0
    return s


def pw_run(s, ticks=4000, dt=250):                    # 250 x 2 us = 0.5 ms per visit, 2 s
    out = []
    for _ in range(ticks):
        s.t = (s.t + dt) & 0xFFFF
        s.st(0x0A, s.t, 2)
        s.call(LAB.PWMLFO)
        out.append(s.m[0x0C40 + 4])
    return out


s = pw_rig()
v = pw_run(s)
swing = 36 * 255 >> 7
check(min(v[10:]) == 128 and max(v) <= 128 + swing and max(v) >= 128 + swing - 2,
      'PWM 3 on a square: width sweeps 128..%d (got %d..%d)' % (128 + swing, min(v[10:]), max(v)))
cross = sum(1 for a, b in zip(v, v[1:]) if a < 160 <= b)
f = 640 * 51 / 65536 / 65536 / 2e-6
check(abs(cross - 2 * f) <= 1, 'LFO RATE 50: about %.2f Hz (%d rising crossings in 2 s)' % (f, cross))
check(s.m[0x76] == 0x5A and s.m[0x77] == 0xA5, "the caller's r76/r77 are kept")
for dt, rate in ((4, 10), (2, 0), (40, 10), (250, 100)):   # visits 8 / 4 / 80 / 500 us apart: no step may be lost
    s = pw_rig(rate=rate)
    n = 3000
    pw_run(s, n, dt)
    ph = (s.m[LAB.PW_PHASE] | s.m[LAB.PW_PHASE + 1] << 8) << 16 | s.m[LAB.PW_FRAC] | s.m[LAB.PW_FRAC + 1] << 8
    want = (LAB.PW_K * (rate + 1) * n * dt) & 0xFFFFFFFF
    check(ph == want, 'visits %d us apart, RATE %d: LFO phase exact (%08X, want %08X)' % (dt * 2, rate, ph, want))
s = pw_rig(pcm_byte=0x7A, pw=75)
v = pw_run(s, 400)
check(max(v) == 255 and min(v[5:]) >= 128, 'PWM 10 + a narrow PW: clamps at 255 (got %d..%d)' % (min(v[5:]), max(v)))
for kw, what in ((dict(pcm_byte=0), 'byte 0 (off)'), (dict(pcm_byte=49), 'a stray PCM byte (DoctorSolo 49)'),
                 (dict(pcm_byte=0x7B), '$7B (past 10)'), (dict(wave=1), 'a saw partial'), (dict(pcm_partial=True), 'a PCM partial')):
    s = pw_rig(**kw)
    v = pw_run(s, 50)
    check(set(v) == {0x11}, 'PWM leaves the width alone for %s' % what)
print('ALL OK, %d checks' % len(OK))
