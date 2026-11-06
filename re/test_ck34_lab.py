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
# ---- IC28 v4: the panel's JUNO CHORUS (mode 1) plays chorus B
s = rig(1, 2, 4)
s.m[0xC8] = 0x00                                       # rc8 as sub_4CFC leaves it for mode 1 (bits 1-3 = 0)
ps, both, modes = [], 0, set()
for i in range(4000):
    l0 = (s.m[0x0400], s.m[0x0800])
    tick(s)
    ps.append(pos_b(s))
    modes.add(6 + ((s.m[0x0800] >> 2) & 1))
    if i and l0[0] != s.m[0x0400] and l0[1] != s.m[0x0800]:
        both += 1
check(s.m[0xC8] & 0x0E == 0x06 and s.m[0x021A] & 0x0E == 0x06, 'mode 1 -> IC13 modes 6/7: mode bits 1-3 = 3 (rc8 %02X, latch %02X)' % (s.m[0xC8], s.m[0x021A]))
check(min(ps[200:]) == B_LO and max(ps[200:]) == B_HI, 'mode 1 sweeps chorus B %d-%d of 128 (%d-%d)' % (B_LO, B_HI, min(ps[200:]), max(ps[200:])))
check(both == 0 and modes == {6, 7}, 'mode 1 chorus B: one latch per step, rows across modes 6/7 (%d, %r)' % (both, modes))
s.m[0xC8] = (s.m[0xC8] & 0xF1)                         # the stock code rewrites mode 1 (e.g. a reverb SysEx)
for i in range(300):
    tick(s)
check(s.m[0xC8] & 0x0E == 0x06, 'mode bits re-asserted after a stock rewrite')
s.m[0xED95], s.m[0xED96], s.m[0xED97] = 2, 5, 3        # leave for DELAY
tick(s)
check(s.m[0xC8] & 0x0E == 0x02 and s.m[0x021A] & 0x0E == 0x02 and s.m[0x0800] & 0x04 == 0,
      'leaving: stock mode 2 back in rc8 / 0x021A / 0x0800 bit 2 (%02X %02X %02X)' % (s.m[0xC8], s.m[0x021A], s.m[0x0800]))
s = rig(1, 0, 0)
s.m[0x0400], s.m[0x0800] = 0x10, 0x04
for i in range(50):
    tick(s)
check(s.m[0x0400] == 0x10 and s.m[0x0800] == 0x04 and s.m[0xC8] & 0x0E == 0, 'mode 1 OFF: hands off (IC13 mode 1 OFF = silent)')
print('ALL OK, %d checks' % len(OK))
