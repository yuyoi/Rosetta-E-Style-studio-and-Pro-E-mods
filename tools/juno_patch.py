"""Load a Juno-style tone into her SOLO part over the remote link (timbre temp, 3 bytes per DT1: the remote buffer).

  py -3.10 juno_patch.py [brass|pad]

Base = her own AUDIO TEST timbre (IC7 bank 1, build_v07.deftone), so every field she does not care about stays valid.
Juno voice: P1 saw 8', P2 pulse 8', P3 square sub 16', P4 off; S+S S+S; low-pass with an envelope sweep and key
follow; Juno chorus I on SOLO (IC13 mode 6, part FX on). MT-32 partial layout = build_v07 offsets.
"""
import os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
import proe_link as P


class B:                             # build_v07 constants + deftone (no capstone needed here)
    WG_COARSE, WG_FINE, WG_KEYF, WG_BEND, WG_WAVE, WG_PCM, WG_PW, WG_PWV = range(8)
    PE_DEPTH = 8
    LFO_RATE, LFO_DEPTH, LFO_MOD = 20, 21, 22
    TVF_CUT, TVF_RESO, TVF_KEYF, TVF_DEPTH, TVF_VELO = 23, 24, 25, 28, 29
    TVF_T = [32, 33, 34, 35, 36]
    TVA_LEVEL = 41
    TVA_T = [49, 50, 51, 52, 53]

    @staticmethod
    def deftone(ic7):
        o = 1 * 0x8000 + (0xBBBA - 0x4000)
        assert bytes(ic7[o:o + 8]) == bytes.fromhex('f041011612020000')
        t = bytearray(ic7[o + 8:o + 8 + 130])
        t += t[14 + 58:14 + 116] * 2
        return bytes(t)

VOICE = sys.argv[1] if len(sys.argv) > 1 else 'brass'
img7 = open(os.path.join(HERE, '..', 'build', 'IC7_v0.10_W27C040.bin'), 'rb').read()
t = bytearray(B.deftone(img7[:0x40000]))
assert len(t) == 246

name = {'brass': b'JUNO BRASS', 'pad': b'JUNO PAD  ', 'brass2': b'JUNO BRS 2', 'brass3': b'JUNO BRS 3', 'pwm': b'JUNO PWM  ', 'strings': b'PWM STRING',
        'stab': b'PWM STAB  '}[VOICE]
STRINGS = VOICE in ('strings', 'stab')   # stab = PWM STRING with a fast attack + filter punch, PWM 10
t[0:10] = name
t[10], t[11] = 0, 0                  # S+S, S+S (no ring)
t[12] = 0b0110 if STRINGS else 0b1101 if VOICE in ('brass2', 'brass3') else 0b0111   # brass2: P1 saw, P3 sub, P4 detuned saw (no pulse)
t[13] = 0                            # sustain env mode

KEYF_3_4 = 9                         # TVF key follow list index 9 = 3/4
for p in range(4):
    o = 14 + p * 58
    wave, coarse, pw, lvl = [(1, 36, 0, 100), (0, 36, 58, 70), (0, 24, 0, 65), (1, 36, 0, 0)][p]
    if VOICE in ('brass2', 'brass3'):
        wave, coarse, pw, lvl = [(1, 36, 0, 95), (0, 36, 58, 0), (0, 24, 0, 55), (1, 36, 0, 70)][p]
    t[o + B.WG_COARSE] = coarse
    t[o + B.WG_FINE] = 54 if (VOICE in ('brass2', 'brass3') and p == 3) else 50
    t[o + B.WG_PCM] = 0              # no stray PWM byte
    if VOICE == 'pwm':               # REAL PWM (IC28 v8): P2 pulse, PWM depth 6 ($76), saw + sub underneath
        wave, coarse, pw, lvl = [(1, 36, 0, 45), (0, 36, 0, 95), (0, 24, 0, 50), (1, 36, 0, 0)][p]
        t[o + B.WG_PCM] = 0x76 if p == 1 else 0
    if STRINGS:                      # classic Juno PWM strings: pulse only + a little sub, PWM 7, slow LFO
        wave, coarse, pw, lvl = [(1, 36, 0, 0), (0, 36, 0, 100), (0, 24, 0, 25), (1, 36, 0, 0)][p]
        t[o + B.WG_PCM] = (0x7A if VOICE == 'stab' else 0x77) if p == 1 else 0
    t[o + B.WG_KEYF] = 11            # 1 = normal tracking
    t[o + B.WG_BEND] = 1
    t[o + B.WG_WAVE] = wave          # 0 = square / pulse, 1 = saw (synth partial)
    t[o + B.WG_PW] = pw
    t[o + B.PE_DEPTH] = 0            # no pitch envelope
    t[o + B.LFO_RATE], t[o + B.LFO_DEPTH], t[o + B.LFO_MOD] = ({'pwm': 20, 'strings': 10, 'stab': 20}.get(VOICE, 70)), (100 if VOICE in ('pwm', 'strings', 'stab') else 0), 15   # LFO DEPTH 100 = the user's working PWM (2026-11-08)   # LFO RATE = PWM speed
    if VOICE == 'stab':                           # fast attack, filter punch that settles, medium release
        cut, res, env, ft, fl = 40, 5, 55, [1, 35, 45, 45, 40], [100, 60, 50, 45]
        at, al = [1, 30, 40, 40, 40], [100, 90, 85, 80]
    elif VOICE == 'strings':
        cut, res, env, ft, fl = 48, 3, 25, [40, 60, 60, 60, 60], [100, 85, 80, 75]
        at, al = [45, 50, 50, 50, 65], [100, 100, 100, 100]
    elif VOICE == 'pwm':
        cut, res, env, ft, fl = 50, 8, 35, [30, 60, 55, 55, 60], [100, 70, 60, 55]
        at, al = [25, 50, 50, 50, 55], [100, 100, 100, 100]
    elif VOICE == 'brass3':                       # hard sweep: dark start, full env, strong resonance
        cut, res, env, ft, fl = 12, 20, 100, [0, 60, 55, 55, 45], [100, 40, 30, 25]
        at, al = [1, 45, 45, 45, 35], [100, 90, 85, 80]
    elif VOICE == 'brass2':
        cut, res, env, ft, fl = 28, 13, 80, [0, 55, 50, 50, 40], [100, 45, 35, 30]
        at, al = [1, 40, 40, 40, 35], [100, 90, 85, 80]
    elif VOICE == 'brass':
        cut, res, env, ft, fl = 45, 9, 60, [0, 45, 40, 40, 35], [100, 55, 45, 35]
        at, al = [1, 20, 20, 20, 30], [100, 100, 100, 100]
    else:
        cut, res, env, ft, fl = 55, 6, 35, [55, 70, 60, 60, 60], [100, 75, 65, 60]
        at, al = [55, 50, 50, 50, 65], [100, 100, 100, 100]
    t[o + B.TVF_CUT], t[o + B.TVF_RESO], t[o + B.TVF_KEYF] = cut, res, KEYF_3_4
    t[o + B.TVF_DEPTH], t[o + B.TVF_VELO] = env, 20
    t[o + B.TVF_T[0]:o + B.TVF_T[0] + 5] = bytes(ft)
    t[o + 37:o + 41] = bytes(fl)     # TVF L1-L3 + sustain (TVF_SUS = 40)
    t[o + B.TVA_LEVEL] = lvl
    t[o + B.TVA_T[0]:o + B.TVA_T[0] + 5] = bytes(at)
    t[o + 54:o + 58] = bytes(al)     # TVA L1-L3 + sustain (TVA_SUS = 57)
assert max(t[10:]) < 0x80

lk = P.Link()
print(lk.ping())
base = 0x1EC                         # timbre temp of part 3 (SOLO): 04 00 00 + 0xF6 * 2
for i in range(0, 246, 3):
    a = base + i
    lk.dt1([0x04, a >> 7, a & 0x7F], list(t[i:i + 3]))
    time.sleep(0.012)
lk.fx(6, 4, 5) if STRINGS else lk.fx(6, 2, 4)   # JUNO CHORUS II for the strings, else I
lk.dt1([0x03, 0x00, 0x26], [1])      # SOLO part FX on
print('loaded %s into SOLO + Juno chorus %s' % (name.decode(), 'II' if STRINGS else 'I'))
