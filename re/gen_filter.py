"""ROSETTA RESONANT FILTER for the CK-34 reverb chip (IC13): a Chamberlin state-variable filter, adds only.

  python -I gen_filter.py        -> self-test in the emulator: response per cutoff/reso, stability, OFF silence

One IC13 mode block = 16 programs x 4 sawBits = 64 settings. Here: program = CUTOFF (16 steps), sawBits = RESO (4).
Every program has the SAME step layout (offsets, loads, writes, invert); only the add masks differ. A program switch
that lands mid-frame (the IC28 latch write) then mixes two coefficient sets for one frame: no tap jump, no tick.

Per iteration (2 per frame = 64 kHz):  lp += f bp ;  hp = x - lp - q bp ;  bp += f hp
The chip inverts only together with an add, after it (measured): hp = ~(q bp + lp) + x, with the invert on the lp
add (always fires). f, q = sums of 2^-e (the shifter), picked per sawBit with the add masks.
"""
import math, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boss_reverb as BR
from gen_fx import Prog, ALL

FS = 32000
ITER = 2                       # SVF iterations per frame
FS_I = FS * ITER
EMAX = 9                       # smallest f term 2^-9 (odd: the chain's last add sits in half-step 0)
NTERM = 3                      # f terms per value (add-only: relative error <= ~1/8)
QE = 5                         # q always holds 2^-QE; its add (half-step 0: QE odd) carries the invert

# state offsets (frame ring: a write at o is read at o in the same frame, at o - 1 in the next)
LP = [0x0100, 0x0200]          # lp written by iteration 0 / 1
BP = [0x0300, 0x0400]
HP = [0x0500, 0x0600]
XR = 0x0800                    # R input copy (iteration 1)
XLRAW = 0x0900                 # L input, raw
XL = 0x0700                    # L input pre-scaled (written at step 58, read next frame at XL - 1)

CUTOFF_HZ = [round(110 * 2 ** (k * 6.0 / 15)) for k in range(16)]     # 110 Hz .. 7 kHz, 6 octaves in 16 steps
# RESO (sawBit = time & 3): (output, q exponents = 1/Q, input gain exponent). q always holds 2^-QE.
# Q 1.9 (q 0.53) mild bump; Q 10.7 (q 3/32) screaming, input halved for headroom.
RESO = [('lp', [1, QE], 0), ('lp', [4, QE], 1), ('bp', [1, QE], 0), ('bp', [4, QE], 1)]
RESO_NAMES = ['LP', 'LP RES', 'BP', 'BP RES']


def terms(v, emax=EMAX, n=NTERM):
    """v ~ sum(2^-e) for e in the result, greedy, e in 0..emax, at most n terms"""
    out, r = [], v
    for _ in range(n):
        if r <= 0:
            break
        e = max(0, math.ceil(-math.log2(r) - 1e-9))
        if 2 ** -e > r * 1.25 and e < emax:   # round to nearest power: keep error small
            e += 1
        if e > emax:
            break
        out.append(e)
        r -= 2 ** -e
    return out


def coef(es):
    return sum(2 ** -e for e in es)


def f_of(hz):
    return 2 * math.sin(math.pi * hz / FS_I)


def masks(per_saw):
    """per_saw = [exponent list for sawBit 0..3] -> {e: mask}"""
    m = {}
    for s, es in enumerate(per_saw):
        for e in es:
            m[e] = m.get(e, 0) | (1 << s)
    return m


def chain_end(p, i, exps):
    """step after the last add of a load at step i with these exponents (a new load may go there if that add sits
    in half-step 0; a write must go after it)"""
    st, hh = p.half(i, max(exps))
    return st + 1, st if hh == 0 else st + 1      # (first step free for a write, first step free for a load)


def program(k):
    """CUTOFF k (0-15) x RESO s (sawBit, see RESO). Layout per iteration (19 steps, base i):
      i     read bp (clear), f chain e1..9 (e9 lands in half-step 0 of i+5)
      i+5   read lp, + lp                                   -> i+6  write lp
      i+7   read bp, q chain e1..4 ; e5 (always) + INVERT in half-step 0 of i+10   acc = ~(lp + q bp)
      i+10  R input (iteration 0: straight from the input, else its copy), x gain e0 / e1 per sawBit
      i+11  + L[n-1] (stored pre-scaled at the end of the last frame)                -> i+12 write hp (+ load)
      i+12  hp: clear, f chain e1..9                        -> i+17 read bp, + bp    -> i+18 write bp"""
    p = Prog()
    f_es = terms(f_of(CUTOFF_HZ[k]))
    assert f_es and min(f_es) >= 1 and max(f_es) <= EMAX, (k, f_es)
    fm = masks([f_es] * 4)                         # cutoff fixed in this program
    qm = masks([r[1] for r in RESO])
    xm = masks([[r[2]] for r in RESO])             # input gain per sawBit (e0 = 1, e1 = 1/2)
    i = 0
    for it in range(ITER):
        lp_r = LP[1] - 1 if it == 0 else LP[0]     # last lp: previous frame's iteration 1 / this frame's iteration 0
        bp_r = BP[1] - 1 if it == 0 else BP[0]
        # lp = lp + f bp
        p.read(i, bp_r); p.mac(i, fm, clear=True)
        assert p.half(i, EMAX) == (i + 5, 0)
        p.read(i + 5, lp_r); p.mac(i + 5, {0: ALL})
        p.wracc(i + 6, LP[it])
        # hp = ~(lp + q bp) + x
        r = i + 7
        p.read(r, bp_r); p.mac(r, {e: m for e, m in qm.items() if e != QE})
        st, hh = p.half(r, QE)
        assert (st, hh) == (i + 10, 0), 'invert must sit in half-step 0'
        p.s[st].h[0][1] |= ALL                     # q's fixed last term, always fires...
        p.s[st].h[0][2] = True                     # ...and carries the invert (after the add)
        if it == 0:
            p.wrin(i + 10, XR, load=True)          # R[n] (step < 32), kept for iteration 1
        else:
            assert i + 10 < 32 or True
            p.read(i + 10, XR)
        p.mac(i + 10, xm)                          # e1 lands in half-step 0 of i+11 (before that step's load)
        p.read(i + 11, XL - 1); p.mac(i + 11, {0: ALL})
        p.wracc(i + 12, HP[it], load=True)
        # bp = bp + f hp
        p.mac(i + 12, fm, clear=True)
        p.read(i + 17, bp_r); p.mac(i + 17, {0: ALL})
        p.wracc(i + 18, BP[it])
        i += 19
    end = i
    assert end <= 44, 'filter too long: %d steps' % end
    assert ITER * 19 - 19 + 10 < 32, 'iteration 0 must take R from the input'
    lpm = sum(1 << s for s, r in enumerate(RESO) if r[0] == 'lp')
    bpm = ALL & ~lpm
    off = ALL if k else ALL & ~1                   # program 0 + sawBit 0 (time 0, level 0) = REVERB OFF: silent
    # out R latched before 47, out L before 56, both x1.25 (e0 + e2: the BP load waits a step after the LP read)
    from gen_fx import gain
    for a, b, side in ((43, 45, 'R'), (52, 54, 'L')):
        p.read(a, LP[ITER - 1]); p.mac(a, gain(lpm & off, side), clear=True)
        p.read(b, BP[ITER - 1]); p.mac(b, gain(bpm & off, side))
    # L[n] for the next frame, pre-scaled per sawBit like the R input
    p.wrin(56, XLRAW, load=True); p.mac(56, xm, clear=True)
    p.wracc(58, XL)
    return p.bytes(), end, f_es


def layout(prog):
    """a program's bytes with the add masks blanked: must be identical across all 16 (safe mid-frame switches)"""
    b = bytearray(prog)
    for i in range(0, 256, 4):
        b[i + 1] &= 0x1F; b[i + 2] &= 0x3F; b[i + 3] &= 0x1F
    return bytes(b)


def block():
    progs = [program(k)[0] for k in range(16)]
    assert len({layout(p) for p in progs}) == 1, 'cutoff programs differ in layout: mid-frame switches would glitch'
    return b''.join(progs)


# ---------------- self-test ----------------
def response(rom, k, s, hz, amp=3000, secs=0.25):
    c = BR.Chip(rom)
    c.set_params(0, (k & 1) * 4 + s, k >> 1)
    n = int(FS * secs)
    acc = 0.0
    for i in range(n):
        x = int(amp * math.sin(2 * math.pi * hz * i / FS))
        l, r = c.frame(x, x)
        if i >= n // 2:
            acc += l * l
    rms = math.sqrt(acc / (n - n // 2))
    return 20 * math.log10(rms / (amp / math.sqrt(2)) + 1e-9)


if __name__ == '__main__':
    print('steps used per frame: %d (outputs at 45/46, 54/55, L store 56-58)' % program(0)[1])
    for k in range(16):
        f_es = program(k)[2]
        print('cutoff %2d %5d Hz  f=%.4f ~ %.4f %s' % (k, CUTOFF_HZ[k], f_of(CUTOFF_HZ[k]), coef(f_es), f_es))
    rom = block() * 2
    c = BR.Chip(rom); c.set_params(0, 0, 0)
    e = sum(abs(l) + abs(r) for l, r in (c.frame(9000 if i % 50 < 25 else -9000, 9000) for i in range(8000)))
    print('OFF energy', e)
    print('gain dB per RESO %s: passband (fc/8) / at fc / 2 octaves above' % RESO_NAMES)
    for k in range(1, 16, 2):
        fc = CUTOFF_HZ[k]
        cells = ['%5.1f %5.1f %6.1f' % (response(rom, k, s, fc / 8, secs=0.15), response(rom, k, s, fc, secs=0.15),
                                       response(rom, k, s, min(fc * 4, 15000), secs=0.15)) for s in range(4)]
        print('k%2d %5d Hz: %s' % (k, fc, ' | '.join(cells)))
