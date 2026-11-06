"""ROSETTA FX for the CK-34 reverb chip: IC13 with 4 new effect modes (one burn).

  python -I gen_fx.py      -> ../build/fx/IC13_fx_W27C256.bin + preview WAVs

  mode 0 REVERB   = Roland's own PLATE programs (proven on synths), TIME 0-7 x LEVEL 0-7 as stock
  mode 1 CHORUS   = JUNO CHORUS: 64 positions (see gen_chorus.py). Static with stock IC28 (position = 8*level + time),
                    moving with the IC28 stepper (TIME = rate, LEVEL = depth)
  mode 2 DELAY    = mono delay, feedback through a 2-tap average (darker repeats), right output 7 ms later for width.
                    TIME 16 steps (level*2 + time>>2) = 40-495 ms, FEEDBACK 4 steps (time & 3) = 0 / 38 / 63 / 75 %
  mode 3 LO-FI    = mono -> one-pole low-pass (TONE, time & 3) -> bit crush + drive into the clamp (CRUSH, 16 steps).
                    The chip only adds a wet copy to the clean dry sound, so this is a parallel crush layer.
Program index = level*2 + (time >> 2), sawBits = time & 3 (fw_map B3 sec. 7 + boss_reverb.py).
time 0 + level 0 = REVERB OFF on the PRO-E: every mode is silent there.
"""
import hashlib, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boss_reverb as BR
import gen_chorus as GC

OUT = os.path.join(HERE, '..', 'build', 'fx')
FS = 32000
ALL = 0xF


class Step:
    """one chip step: RAM access + two half-steps (clear, add mask, negate)"""
    def __init__(self):
        self.off, self.write, self.inp, self.load = 0, False, False, False
        self.h = [[False, 0, False], [False, 0, False]]       # clear, mask, neg

    def bytes(self):
        h0, h1 = self.h
        b1 = (1 if self.inp else 0) | (0 if self.write else 2) | (0 if self.load else 4) | (8 if h0[2] else 0) \
            | (0 if h0[0] else 0x10) | ((h0[1] & 0xE) << 4)
        # HARDWARE 2026-11-06 (chiplab on her): the b3 (second half-step) negate does NOT flip the accumulator like
        # the emulator says (every filter that used it squealed at 16 kHz). New code negates in h0 only.
        assert not h1[2] or getattr(self, 'h1neg_ok', False), 'negate in half-step 1: not what the real chip does'
        b3 = 0x07 | (8 if h1[2] else 0) | (0 if h1[0] else 0x10) | ((h1[1] & 0xE) << 4)
        b2 = ((self.off >> 8) & 0x3F) | ((h0[1] & 1) << 7) | ((h1[1] & 1) << 6)
        return bytes([self.off & 0xFF, b1, b2, b3])


class Prog:
    def __init__(self):
        self.s = [Step() for _ in range(64)]

    def half(self, step, e):
        """half-step that sees a value loaded at `step` scaled by 2^-e"""
        return (step + (e + 1) // 2, 0 if e % 2 else 1)

    def wrin(self, i, off, load=False):
        st = self.s[i]; st.off, st.write, st.inp, st.load = off & 0x3FFF, True, True, load

    def wracc(self, i, off, load=False):
        st = self.s[i]; st.off, st.write, st.load = off & 0x3FFF, True, load

    def read(self, i, off):
        st = self.s[i]; st.off, st.load = off & 0x3FFF, True

    def neg(self, i):
        """acc = ~acc in half-step 0 of step i (the negate the real chip does as documented). No add there."""
        assert not self.s[i].h[0][1], 'negate step %d has an add' % i
        self.s[i].h[0][2] = True

    def mac(self, i, exps, clear=False, sub=False, legacy=False):
        """value loaded at step i (read / write+load) times sum(2^-e): exps = {e: saw mask}. clear = acc 0 first.
        sub = subtract (acc - v*c = ~(~acc + v*c)) with negates in half-step 0 only: one before the first add, one on
        a free half-step 0 after the last (legacy = the LO-FI/DRIVE layout proven on her: the last may share an h0).
        Steps after i must not load until the last exponent. Returns the step of the last operation: a RAM write of
        the result must come after it."""
        if clear:
            self.s[i].h[1][0] = True
        es = sorted(exps)
        for e in es:
            st, hh = self.half(i, e)
            self.s[st].h[hh][1] |= exps[e]
        last = self.half(i, es[-1])[0]
        if sub:
            raise NotImplementedError('the chip inverts only together with an add (measured): build it add-only')
            st, hh = self.half(i, es[0])
            if hh == 1:
                self.neg(st)
            else:
                assert not self.s[st - 1].h[1][1], 'sub: half-step before the first add is busy'
                self.neg(st - 1)
            st, hh = self.half(i, es[-1])
            if legacy and hh == 0:
                self.s[st].h[0][2] = True
                last = st
            else:
                self.neg(st + 1)
                last = st + 1
        return last

    def bytes(self):
        return b''.join(st.bytes() for st in self.s)


def delay_frames(k):
    return round([40, 60, 80, 100, 120, 150, 180, 200, 230, 260, 300, 333, 375, 420, 460, 495][k] * FS / 1000)


FB = [{}, {3: ALL, 4: ALL}, {2: ALL, 4: ALL}, {2: ALL, 3: ALL}]      # per tap: f/2 = 0, 3/16, 5/16, 3/8


def delay_program(k):
    p = Prog()
    D = delay_frames(k)
    p.wrin(0, 1)                                   # scratch 1 = right input (offsets 1-2 hold samples older than any tap)
    p.wrin(32, 2, load=True)                       # left input -> shifter
    p.mac(32, {0: ALL}, clear=True)                # acc = L/2 (the chip halves its inputs)
    p.read(33, 1)
    p.mac(33, {0: ALL})                            # acc += R/2
    fb = {}
    for s in range(1, 4):
        for e in FB[s]:
            fb[e] = fb.get(e, 0) | (1 << s)
    p.read(34, (0x4000 - D))
    p.mac(34, fb)                                  # + f/2 * buf[n-D]       (steps 34-36)
    p.read(37, (0x4000 - D - 1))
    p.mac(37, fb)                                  # + f/2 * buf[n-D-1]     (steps 37-39)
    p.wracc(40, 0)                                 # buf[n]
    on = ALL if k else 0xE                         # program 0, time 0 = REVERB OFF: silent
    p.read(41, 0x4000 - D - 224)
    p.mac(41, {0: on}, clear=True)                 # out R = buf[n-D-7ms]   (latched at 47)
    p.read(47, 0x4000 - D)
    p.mac(47, {0: on}, clear=True)                 # out L = buf[n-D]       (latched at 56)
    return p.bytes()


CRUSH = [(0, 0), (0, 2), (2, 0), (2, 2), (3, 0), (3, 2), (4, 0), (4, 2), (5, 0), (5, 2), (6, 0), (6, 2),
         (7, 0), (7, 2), (8, 0), (8, 2)]            # (bits dropped, extra doublings = drive x4 into the clamp)
# v2 (2026-11-05, heard on her): 2 bits gentler. The send into the chip sits well below full scale, so the old
# 9-10 bit steps left only a few real bits: "barely intelligible".


TONE_A = {0: 0b0001, 1: 0b0010, 2: 0b0100, 3: 0b1000}    # a = 1, 1/2, 1/4, 1/8 for sawBits 1, 2, 4, 8 (TONE)
TONE_KEEP = {1: 0b1110, 2: 0b1100, 3: 0b1000}              # 1 - a = 0, 1/2, 3/4, 7/8


def tone_pole(p, zr, zw, i=0):
    """v4 (2026-11-06, the measured chip): z[n] = (1 - a) z[n-1] + a (L[n-1] + R[n]) / 2 with ADDS ONLY (the chip's
    invert bit only works together with an add, so the old ~(~acc + a z) subtract never subtracted on her = the
    stuck LO-FI / DRIVE). z read at zr, written at zw (the accumulator keeps z too). Returns the next free step."""
    p.read(i, zr); p.mac(i, TONE_KEEP, clear=True)          # (1 - a) z[n-1]       adds until i+2 h0
    p.read(i + 2, 4); p.mac(i + 2, TONE_A)                   # + a L[n-1]/2          (i+2 h1 .. i+4 h0)
    p.wrin(i + 4, 1, load=True); p.mac(i + 4, TONE_A)        # + a R[n]/2            (i+4 h1 .. i+6 h0)
    p.wracc(i + 7, zw, load=True)                            # z[n], also in the shifter
    return i + 7


def lofi_program(k):
    """runs at the start of the frame on this frame's R and last frame's L (1 sample later: inaudible),
    so the result sits in the accumulator for both output latches (47 and 56)."""
    p = Prog()
    c, d = CRUSH[k]
    i = tone_pole(p, 0x3FFF, 0)                    # z[n] at offset 0 (read back at 0x3FFF next frame), shifter = z
    p.mac(i, {c: ALL}, clear=True)                 # acc = z >> c (CRUSH drops c bits)
    i += (c + 1) // 2 + 1
    for _ in range(c + d):                         # double back up (c), then drive into the +-32767 clamp (d)
        p.wracc(i, 3, load=True)
        p.mac(i, {0: ALL})
        i += 1
    assert i <= 31, 'lo-fi program %d too long (%d)' % (k, i)
    on = ALL if k else 0xE                         # program 0 + time 0 = REVERB OFF: silent
    p.wracc(i, 6, load=True)                       # re-load the result to gate it for OFF
    p.mac(i, {0: on}, clear=True)                  # acc = result (or 0 when OFF), held until both latches
    p.wrin(40, 5)                                  # L[n] for the next frame
    return p.bytes()


def flange_delay(p):
    return 8 + round(120 * (p - 1) / 62) if p else 8      # 0.25-4 ms


def flanger_program(k):
    """two comb lines (R at 0x0000, L at 0x2000), feedback 0.75, opposite sweeps, 4 positions per program (sawBits)"""
    p = Prog()
    pos = [GC.snake(k * 4 + s) for s in range(4)]
    def line(start, inp_off, base, delays, wr):
        p.wrin(start, inp_off, load=True)
        p.mac(start, {0: ALL}, clear=True)         # acc = input/2
        i = start + 1
        for s, d in enumerate(delays):
            p.read(i, base - d)
            p.mac(i, {1: 1 << s, 2: 1 << s})       # + 0.75 * tap (only the tap of this sawBits value)
            i += 2
        p.wracc(i, base)                           # line[n]
        return i + 1
    dR = [flange_delay(q) for q in pos]
    dL = [flange_delay(63 - q) if q else 8 for q in pos]
    line(0, 1, 0x4000, dR, 0)
    line(32, 2, 0x2000, dL, 0)                      # steps 32-41
    for s, d in enumerate(dR):                     # out R = the R tap (steps 42-45, latched at 47)
        p.read(42 + s, 0x4000 - d)
        p.mac(42 + s, {0: (1 << s) if pos[s] else 0}, clear=(s == 0))
    for s, d in enumerate(dL):                     # out L (steps 48-51, latched at 56)
        p.read(48 + s, 0x2000 - d)
        p.mac(48 + s, {0: (1 << s) if pos[s] else 0}, clear=(s == 0))
    return p.bytes()


DRIVE = [(g, o) for g in (2, 3, 4, 5, 6, 7, 8, 9) for o in (5, 6)]   # (gain doublings into the clamp, output >> o)
# v4.1 (2026-11-06, measured on her): output >> 1-2 was +26 dB over the dry (a clipped full-scale wave). >> 5-6 = about the dry level.


def drive_program(k):
    """mono -> low-pass TONE (time & 3) -> gain 2^g -> clamp (hard clip) -> back down: a parallel distortion"""
    p = Prog()
    g, o = DRIVE[k]
    i = tone_pole(p, 0x3FFF, 0) + 1                # z[n] in the accumulator
    for _ in range(g):
        p.wracc(i, 3, load=True); p.mac(i, {0: ALL}); i += 1
    on = ALL if k else 0xE
    p.wracc(i, 6, load=True)
    p.mac(i, {o: on}, clear=True)                  # acc = clipped >> o (or 0 when OFF)
    p.wrin(40, 5)
    return p.bytes()


CH_A1, CH_A2 = {1: ALL, 2: ALL}, {1: ALL}       # 2-pole low-pass, a = 3/4 then 1/2 (about 3 kHz, like a BBD)


CH_KEEP1, CH_IN1 = {2: ALL}, {1: ALL, 2: ALL}   # stage 1: z1 = 1/4 z1 + 3/4 (L + R)/2-ish
CH_KEEP2, CH_IN2 = {1: ALL}, {1: ALL}           # stage 2: z2 = 1/2 z2 + 1/2 z1   (about 3 kHz together)
CH_IN2_HALF = {2: ALL}                           # v5: z2 = 1/2 z2 + 1/4 z1 -> line = x/2 (taps then weigh 1/4 1/2 1/4)
CH_SCR = 0x30                                    # v5 A: L output parked here between step 25 and 48


def chorus_line(p, in2):
    '''mono (L + R) -> 2-pole low-pass, adds only -> line at offset 0 (steps 0-10)'''
    p.read(0, 0x1FFF); p.mac(0, CH_KEEP1, clear=True)
    p.read(2, 4); p.mac(2, CH_IN1)
    p.wrin(4, 1, load=True); p.mac(4, CH_IN1)
    p.wracc(6, 0x2000)
    p.read(7, 0x3FFF); p.mac(7, CH_KEEP2, clear=True)
    p.read(8, 0x2000); p.mac(8, in2)
    p.wracc(10, 0)
    p.wrin(32, 5)


def chorus_block_a():
    '''JUNO CHORUS v5 A (mode 1, 64 positions, IC28 stepper as v2): v4 low-pass line at x/2, each position plays
    1/4 D(q-1) + 1/2 D(q) + 1/4 D(q+1) = a step moves weight between neighbouring taps instead of jumping a whole tap.
    6 taps per program (2 steps each: e = 1, 2). R taps steps 33-44 (latched 47); L taps steps 12-23, parked at
    CH_SCR (25), read back at 48 (latched 56). Combination 0 = OFF: silent.'''
    progs = []
    for k in range(16):
        p = Prog()
        chorus_line(p, CH_IN2_HALF)
        qs = [GC.snake(k * 4 + s) for s in range(4)]
        for ch, step0, dl in (('L', 12, lambda q: GC.delay(63 - q) if q <= 63 else GC.delay(0)), ('R', 33, GC.delay)):
            taps = list(range(min(qs) - 1, max(qs) + 2))
            for j, t in enumerate(taps):
                m1 = m2 = 0
                for s, q in enumerate(qs):
                    if k * 4 + s == 0:
                        continue                                 # OFF
                    if t == q:
                        m1 |= 1 << s
                    elif abs(t - q) == 1:
                        m2 |= 1 << s
                ex = {}
                if m1:
                    ex[1] = m1
                if m2:
                    ex[2] = m2
                d = round(53 + 118 * t / 63) if ch == 'R' else round(53 + 118 * (63 - t) / 63)
                i = step0 + 2 * j
                p.read(i, 0x4000 - d)
                p.mac(i, ex or {1: 0}, clear=(j == 0))
            if ch == 'L':
                p.wracc(25, CH_SCR)
        p.read(48, CH_SCR); p.mac(48, {0: ALL}, clear=True)
        progs.append(p.bytes())
    return b''.join(progs)


def delay128(q):
    return round(53 + 118 * q / 127)


POLE_HALF = ({1: ALL}, {1: ALL})                 # z = z/2 + x/2      (-3 dB ~3.7 kHz)
POLE_QUARTER = ({2: ALL}, {1: ALL, 2: ALL})      # z = 3/4 z + x/4    (-3 dB ~1.5 kHz)
CH_POST = [POLE_HALF, POLE_HALF]                # v5.2: 2 poles AFTER the taps: ticks -7 dB (emulator, mid-frame switches), wet -1..-4.5 dB at 2-3 kHz; [] = v5.1
CH_POST_SCR = {'R': 0x0800, 'L': 0x0C00}         # tap scratch; pole n state at Z + 0x100 n (read back at -1)
CH_POST_Z = {'R': 0x1000, 'L': 0x1400}


def pole_chain(p, i, ch, poles):
    '''value in acc (last add before step i) -> poles in series, adds only: z = keep z[n-1] + in x. The result
    is in acc at the end and written to the last state; returns the step of that write.
    Measured 2026-11-06 on her: the chorus fizz = a tick at every position step (frozen = as clean as dry at
    velocity 127, no clipping), so the filter goes after the taps, where the jump happens.'''
    scr = CH_POST_SCR[ch]
    for n, (ain, akeep) in enumerate(poles):
        zw = CH_POST_Z[ch] + 0x100 * n
        p.wracc(i, scr, load=True)                      # park the input (tap, or the last pole's z) + load it
        p.mac(i, ain, clear=True)
        st, hh = p.half(i, max(ain))
        j = st if hh == 0 else st + 1                   # a load here only reaches h1
        p.read(j, zw - 1); p.mac(j, akeep)
        st, hh = p.half(j, max(akeep))
        i, scr = st + 1, zw
    p.wracc(i, scr)
    return i


def chorus_block_b(m0, post=None):
    '''JUNO CHORUS v5 B (modes 6 + 7 = 128 positions, IC28 v3 stepper: mode bit 0 = the 3rd row bit in 0x0800):
    half-size tap steps (0.93 frames). Combination c = m0 * 64 + level * 8 + time, position = snake(c).
    v4 low-pass line at x/2, one tap per position (v1 layout). Mode 6, time 0 + level 0 = OFF: silent.
    v5.2 (post): L taps 12-15 + poles, parked, read back at 48 (latched 56); R taps 34-37 + poles (latched 47).'''
    post = CH_POST if post is None else post
    progs = []
    for k in range(16):
        p = Prog()
        chorus_line(p, CH_IN2)          # v5.1: line = x -> wet = dry level, the Juno mix (was x/2, too dry)
        tl, tr = (12, 34) if post else (48, 40)
        for s in range(4):
            c = m0 * 64 + k * 4 + s
            q = GC.snake(c)
            on = (1 << s) if c else 0
            p.read(tr + s, 0x4000 - delay128(q)); p.mac(tr + s, {0: on}, clear=(s == 0))         # out R (47)
            p.read(tl + s, 0x4000 - delay128(127 - q)); p.mac(tl + s, {0: on}, clear=(s == 0))   # out L (56)
        if post:
            w = pole_chain(p, 16, 'L', post)
            assert w < 32
            p.read(48, CH_POST_Z['L'] + 0x100 * (len(post) - 1)); p.mac(48, {0: ALL}, clear=True)
            w = pole_chain(p, 38, 'R', post)
            assert w <= 46, w
        progs.append(p.bytes())
    return b''.join(progs)


def chorus_block():
    """JUNO CHORUS v4: mono (L + R) -> 2-pole low-pass with ADDS ONLY (no invert: the measured chip) -> one line,
    R tap D(q), L tap D(63 - q), snake order (GC.snake, the IC28 v2 stepper). The low-pass takes the fizz off the
    1.9-frame tap steps. Taps at x1/2 (line = x, the v1 taps played x/2). Combination 0 = OFF: silent."""
    progs = []
    for k in range(16):
        p = Prog()
        p.read(0, 0x1FFF); p.mac(0, CH_KEEP1, clear=True)     # 1/4 z1[n-1]                 (1 h1)
        p.read(2, 4); p.mac(2, CH_IN1)                       # + 3/4 L[n-1]/2             (3 h0, 3 h1)
        p.wrin(4, 1, load=True); p.mac(4, CH_IN1)            # + 3/4 R[n]/2               (5 h0, 5 h1)
        p.wracc(6, 0x2000)                                   # z1[n]
        p.read(7, 0x3FFF); p.mac(7, CH_KEEP2, clear=True)     # 1/2 z2[n-1]                (8 h0)
        p.read(8, 0x2000); p.mac(8, CH_IN2)                  # + 1/2 z1[n]  (same-frame read, proven)  (9 h0)
        p.wracc(10, 0)                                       # line[n] = z2[n]
        p.wrin(32, 5)                                        # L[n] for the next frame
        for s_ in range(4):
            q = GC.snake(k * 4 + s_)
            on = (1 << s_) if k * 4 + s_ else 0
            p.read(40 + s_, 0x4000 - GC.delay(q)); p.mac(40 + s_, {1: on}, clear=(s_ == 0))        # out R (47)
            p.read(48 + s_, 0x4000 - GC.delay(63 - q)); p.mac(48 + s_, {1: on}, clear=(s_ == 0))   # out L (56)
        progs.append(p.bytes())
    return b''.join(progs)


def chorus_block_v3():
    """JUNO CHORUS v3 = the v1 structure that played clean on her (raw R line at 0, L line at 0x2000, one tap per
    position) in snake order (GC.snake, matches the IC28 v2 stepper). Combination 0 (time 0 + level 0) = OFF: silent."""
    progs = []
    for k in range(16):
        st = {0: BR.step_write_input(0), 32: BR.step_write_input(0x2000)}
        for s in range(4):
            q = GC.snake(k * 4 + s)
            st[40 + s] = BR.step_tap(GC.delay(q), 1 << s, clear=(s == 0))
            st[48 + s] = BR.step_tap(GC.delay(63 - q) + 0x2000, 1 << s, clear=(s == 0))
        progs.append(bytearray(BR.program(st)))
    for i in (40, 48):                             # combination 0: the sawBits-1 taps off
        progs[0][i * 4 + 2] &= ~0x40 & 0xFF
    return b''.join(bytes(x) for x in progs)


def chorus_block_lp():
    """JUNO CHORUS v2: OSCILLATED ON HER (16 kHz, -12 dB, also with no input), fine in the emulator. Kept for the lab. (heard on her: fizzy + clicky). Mono (L+R) -> 2-pole low-pass -> one line, R tap D(q), L tap
    D(63 - q). The low-pass takes the edge off every 1.9-frame tap step; the snake order (GC.snake) stops the
    in-between positions. Latch combination 0 (time 0 + level 0) = REVERB OFF: silent."""
    progs = []
    for k in range(16):
        p = Prog()
        p.read(0, 0x1FFF); p.mac(0, {0: ALL}, clear=True)      # acc = z1[n-1] (written at 0x2000 last frame)
        p.read(1, 4); p.mac(1, CH_A1)                            # + a1 * L[n-1]/2
        p.wrin(4, 1, load=True); p.mac(4, CH_A1)                 # + a1 * R[n]/2
        p.read(7, 0x1FFF); p.mac(7, CH_A1, sub=True)             # - a1 * z1[n-1]
        p.wracc(10, 0x2000)                                      # z1[n]
        p.read(11, 0x3FFF); p.mac(11, {0: ALL}, clear=True)     # acc = z2[n-1] = line[n-1]
        p.read(12, 0x2000); p.mac(12, CH_A2)                     # + a2 * z1[n]
        p.read(15, 0x3FFF); p.mac(15, CH_A2, sub=True)           # - a2 * z2[n-1]
        p.wracc(18, 0)                                           # line[n] = z2[n]
        p.wrin(32, 5)                                            # L[n] for the next frame
        for s in range(4):
            q = GC.snake(k * 4 + s)
            on = (1 << s) if k * 4 + s else 0
            p.read(40 + s, 0x4000 - GC.delay(q)); p.mac(40 + s, {1: on}, clear=(s == 0))        # out R (latched 47)
            p.read(48 + s, 0x4000 - GC.delay(63 - q)); p.mac(48 + s, {1: on}, clear=(s == 0))   # out L (latched 56)
        progs.append(p.bytes())
    return b''.join(progs)


LAB_D = 6000                                       # test echo, 187 ms (< 8192: clear of the 0x2000 scratch)
CANCEL_G3 = [1.18, 1.24, 1.30, 1.37]               # round 3 cancel gains (round 1 best ~1.3)
# round 3: what each accumulator operation really does. Every test computes from x/2 (the R input) and its result
# plays back LAB_D frames later; the tool correlates that echo with the dry note: sign + size per operation.
# emulator prediction in units of x/2:
LAB3 = [('OFF', None),
        ('REF acc = x/2', 1.0),
        ('h0 pure negate', -1.0),
        ('h1 pure negate', -1.0),
        ('h0 add x/4 + negate', -1.5),
        ('h1 add x/2 + negate', -2.0),
        ('h1 clear+add+negate (r1 cancel)', -1.0),
        ('h0 negate, then add x/2', 0.0),
        ('two h0 negates', 1.0),
        ('h0 negate, mask other saw', -1.0),
        ('doubled (x)', 2.0),
        ('h1 neg on add, h0 neg before', -1.0),
        ('add x/2 twice', 2.0),
        ('cancel -g x[n]', None), ('cancel -g (2x[n]-x[n-1])', None), ('cancel -g (3x[n]-3x[n-1]+x[n-2])', None)]
# measured on her 2026-11-06: the wet output comes out ONE FRAME LATER than the dry (delay echo +1.5 samples at
# 48 kHz), so the cancel has to lead: k14/k15 predict x[n+1] (1st / 2nd order). Built from plain adds and the
# round-1 minus (h0 negate + h1 clear+add+negate), the two things proven on her.


def gain_exps(gs):
    """4 gains (one per sawBits value) as {e: mask}: value * sum 2^-e, e 0-6 (1/64 steps), each gain < 2"""
    ex = {}
    for sb, g in enumerate(gs):
        q = round(g * 64)
        assert 0 < q < 128
        for e in range(7):
            if q & (64 >> e):
                ex[e] = ex.get(e, 0) | (1 << sb)
    return ex


def lab_block():
    """mode 7 LAB round 3 (k = level*2 + (time >> 2); sawBits = time & 3, the tool uses 0 except the cancel gains)."""
    def echo(p):
        p.read(41, 0x4000 - LAB_D); p.mac(41, {0: ALL}, clear=True)
        p.read(48, 0x4000 - LAB_D); p.mac(48, {0: ALL}, clear=True)

    def h1neg(p, i):
        p.s[i].h[1][2] = True
        p.s[i].h1neg_ok = True
    progs = [Prog().bytes()]
    for k in range(1, 13):
        p = Prog()
        p.wrin(0, 1)                                         # x/2 at offset 1
        p.read(2, 1); p.mac(2, {0: ALL}, clear=True)         # acc = x/2 at (2,1)
        w = 4
        if k == 2:
            p.neg(3); w = 5
        elif k == 3:
            h1neg(p, 3); w = 5
        elif k == 4:
            p.read(3, 1); p.mac(3, {1: ALL}); p.s[4].h[0][2] = True; w = 6      # add x/4 at (4,0) + negate there
        elif k == 5:
            p.read(3, 1); p.mac(3, {0: ALL}); h1neg(p, 3); w = 5               # add x/2 at (3,1) + negate there
        elif k == 6:
            p = Prog(); p.wrin(0, 1)
            p.read(2, 1); p.mac(2, {0: ALL}, clear=True); h1neg(p, 2); w = 4   # clear + add + negate at (2,1)
        elif k == 7:
            p.neg(3); p.read(3, 1); p.mac(3, {0: ALL}); w = 5                  # negate (3,0), add x/2 (3,1)
        elif k == 8:
            p.neg(3); p.neg(4); w = 6
        elif k == 9:
            p.s[3].h[0][1] = 0b1000; p.s[3].h[0][2] = True; w = 5              # negate on a half whose mask is saw 8 only
        elif k == 10:
            p.wracc(3, 2, load=True); p.mac(3, {0: ALL}); w = 5                # acc + acc = x
        elif k == 11:
            p = Prog(); p.wrin(0, 1)
            p.neg(2); p.read(2, 1); p.mac(2, {0: ALL}, clear=True); h1neg(p, 2); w = 4   # the exact r1 construct
        elif k == 12:
            p.read(3, 1); p.mac(3, {0: ALL}); w = 5                            # x/2 + x/2
        p.wracc(w, 0)
        echo(p)
        progs.append(p.bytes())
    G = gain_exps(CANCEL_G3)

    def term(p, i, src, minus, store):
        """steps i..i+6: RAM[store] = (-)a * x(src), x(src) = 2 * the stored half value. Returns the next free step."""
        p.read(i, src); p.mac(i, G, clear=True)              # a * x/2 (adds until i+3)
        p.wracc(i + 4, 30, load=True); p.mac(i + 4, {0: ALL})    # a * x
        if minus:
            p.wracc(i + 5, 31, load=True); p.mac(i + 5, {0: ALL}, clear=True)   # the r1 minus
            p.s[i + 5].h[0][2] = True
            h1neg(p, i + 5)
            p.wracc(i + 6, store)
            return i + 7
        p.wracc(i + 5, store)
        return i + 6
    for t in range(3):                                       # k13-15: cancel = -g * (x[n] / 1st / 2nd order x[n+1])
        p = Prog()
        p.wrin(0, 1)                                         # x[n]/2 at 1 (x[n-1] at 2, x[n-2] at 3 next frames? no:)
        p.wrin(4, 5)                                         # x[n]/2 -> offset 4 next frame, offset 3 the one after
        if t == 0:
            term(p, 20, 1, True, 20)
            p.read(40, 20); p.mac(40, {0: ALL}, clear=True)
        elif t == 1:                                         # -(2x - x1) = 2A + B, A = -a x, B = +a x1
            i = term(p, 14, 1, True, 20)
            term(p, i, 4, False, 21)
            p.read(40, 20); p.mac(40, {0: ALL}, clear=True)
            p.read(41, 20); p.mac(41, {0: ALL})
            p.read(42, 21); p.mac(42, {0: ALL})
        else:                                                # -(3x - 3x1 + x2) = 3A + 3B + C, C = -a x2
            i = term(p, 8, 1, True, 20)
            i = term(p, i, 4, False, 21)
            term(p, i, 3, True, 22)
            for j, src in enumerate((20, 20, 20, 21, 21, 21, 22)):
                p.read(38 + j, src); p.mac(38 + j, {0: ALL}, clear=(j == 0))
        progs.append(p.bytes())
    assert len(progs) == 16
    return b''.join(progs)


def build(stock):
    """lower 16 KB = modes 0-3 (the PRO-E's 8 types). Upper 16 KB = modes 4-7, only reachable if IC13 A14 follows
    reverb mode bit 2 (IC28 LAB unlocks mode 4-7): 4 FLANGER, 5 DRIVE, 6 HALL + 7 ROOM (Roland's, back again)."""
    rom = bytearray(0x8000)
    blocks = [stock[0x2000:0x3000],                # 0 REVERB = stock PLATE
              chorus_block(),                      # 1 JUNO CHORUS v4 (v5 A, blended taps, measured no better: dropped)
              b''.join(delay_program(k) for k in range(16)),     # 2 DELAY
              b''.join(lofi_program(k) for k in range(16)),      # 3 LO-FI
              b''.join(flanger_program(k) for k in range(16)),   # 4 FLANGER
              b''.join(drive_program(k) for k in range(16)),     # 5 DRIVE
              chorus_block_b(0),                   # 6 + 7 JUNO CHORUS B (v5: 128 positions, half-size steps)
              chorus_block_b(1)]
    for m, b in enumerate(blocks):
        assert len(b) == 0x1000
        rom[m * 0x1000:(m + 1) * 0x1000] = b
    return bytes(rom)


def render(rom, sig, mode, time, level, stereo_in=None):
    c = BR.Chip(rom)
    c.set_params(mode, time, level)
    L, R = [], []
    for x in sig:
        l, r = c.frame(x, x)
        L.append(x + 2 * l); R.append(x + 2 * r)
    return L, R


def pluck_signal(secs=4.0):
    """short synth plucks, to hear echoes"""
    n = int(FS * secs)
    out = [0.0] * n
    for t0, f in ((0.0, 220.0), (0.5, 330.0), (1.0, 261.6), (2.4, 196.0)):
        i0 = int(t0 * FS)
        ph = 0.0
        for i in range(i0, min(n, i0 + int(0.25 * FS))):
            env = math.exp(-(i - i0) / (0.06 * FS))
            out[i] += (2 * ph - 1) * env
            ph = (ph + f / FS) % 1.0
    return [int(16000 * v) for v in out]


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    stock = open(os.path.join(HERE, '..', 'dumps', 'ck34_ic13_reverb_R15179917_HN623257.bin'), 'rb').read()
    rom = build(stock)
    p = os.path.join(OUT, 'IC13_fx_W27C256.bin')
    open(p + '.tmp', 'wb').write(rom); os.replace(p + '.tmp', p)
    print('IC13_fx_W27C256.bin md5', hashlib.md5(rom).hexdigest())
    p512 = os.path.join(OUT, 'IC13_fx_W27C512.bin')       # doubled: A15 (27C256 pin 1 = VPP) is a don't-care
    open(p512 + '.tmp', 'wb').write(rom + rom); os.replace(p512 + '.tmp', p512)
    print('IC13_fx_W27C512.bin md5', hashlib.md5(rom + rom).hexdigest())
    # checks: OFF is silent in every mode, the delay comes back on time
    for m in range(8):
        c = BR.Chip(rom); c.set_params(m, 0, 0)
        e = sum(abs(l) + abs(r) for l, r in (c.frame(9000 if i % 50 < 25 else -9000, 9000) for i in range(20000)))
        print('mode %d OFF energy %d' % (m, e))
    for k, s in ((4, 0), (12, 2)):
        c = BR.Chip(rom); c.set_params(2, (k & 1) * 4 + s, k >> 1)
        resp = [c.frame(16000, 16000) if i == 0 else c.frame(0, 0) for i in range(3 * delay_frames(k) + 300)]
        hits = [(i, l, r) for i, (l, r) in enumerate(resp) if abs(l) > 200 or abs(r) > 200]
        print('DELAY k=%d fb=%d: expect L at %d, R at %d:' % (k, s, delay_frames(k), delay_frames(k) + 224), hits[:8])
    pad = GC.test_signal(4.0)
    pl = pluck_signal()
    GC.wav(os.path.join(OUT, '0_dry_pad.wav'), pad, pad)
    GC.wav(os.path.join(OUT, '0_dry_plucks.wav'), pl, pl)
    GC.wav(os.path.join(OUT, '1_reverb_plate.wav'), *render(rom, pl, 0, 4, 6))
    GC.wav(os.path.join(OUT, '2_chorus_static.wav'), *render(rom, pad, 1, 4, 4))
    GC.wav(os.path.join(OUT, '2_chorus_I_moving.wav'), *GC.render_chip(GC.build_rom(stock), pad, 0.513))
    GC.wav(os.path.join(OUT, '3_delay_150ms_fb38.wav'), *render(rom, pl, 2, 4 + 1, 2))
    GC.wav(os.path.join(OUT, '3_delay_375ms_fb63.wav'), *render(rom, pl, 2, 0 + 2, 6))
    for k, tone in ((4, 0), (10, 1), (14, 2), (15, 3)):
        c, d = CRUSH[k]
        GC.wav(os.path.join(OUT, '4_lofi_crush%d_drive%d_tone%d.wav' % (c, d, tone)),
               *render(rom, pad, 3, (k & 1) * 4 + tone, k >> 1))
    for k, tone in ((6, 0), (12, 1), (15, 2)):
        g, o = DRIVE[k]
        GC.wav(os.path.join(OUT, '5_drive_gain%d_tone%d.wav' % (g, tone)), *render(rom, pad, 5, (k & 1) * 4 + tone, k >> 1))
    # flanger, swept the way the IC28 stepper does it (1 ms steps, triangle 0.25 Hz, full depth)
    c = BR.Chip(rom)
    L, R = [], []
    for i, x in enumerate(pad):
        if i % 32 == 0:
            ph = (i / FS * 0.25) % 1.0
            tri = 2 * ph if ph < 0.5 else 2 - 2 * ph
            q = 1 + int(tri * 61.99)
            k, s_ = divmod(q, 4)
            c.set_params(4, (k & 1) * 4 + s_, k >> 1)
        l, r = c.frame(x, x)
        L.append(x + 2 * l); R.append(x + 2 * r)
    GC.wav(os.path.join(OUT, '6_flanger_0.25Hz.wav'), L, R)
    print('previews in', os.path.abspath(OUT))
