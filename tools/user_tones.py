"""Write 16 Juno-style tones straight into USER PROGRAMs 1-16 (USER bank 1 + 2), over the remote (IC7 v0.13+).

  py -3.10 user_tones.py            write all 16 and read them back
  py -3.10 user_tones.py list       just print the list

Each USER PROGRAM record (SRAM page 2/3, 256 bytes) = "RT" + SOLO timbre (246) + FX mode, time, level + BENDER mode.
Press USER n on her and the tone + effect come back (the panel part of the program stays whatever it was).
Base tone = her AUDIO TEST timbre from IC7 (like juno_patch.py), so unused fields stay valid.
PWM voices: pulse partial PCM byte $70 + depth, LFO DEPTH 100 (= the user's working PWM, 2026-11-08).
"""
import os, sys, time
import proe_link as P


class B:                             # build_v07 constants + deftone (same as juno_patch.py, which runs on import)
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

HERE = os.path.dirname(os.path.abspath(__file__))
_ic7 = [os.path.join(HERE, '..', 'build', n) for n in ('IC7_v0.13_W27C040.bin', os.path.join('studio', 'IC7_rosetta_W27C040.bin'))]
img7 = open(next((p for p in _ic7 if os.path.exists(p)), _ic7[-1]), 'rb').read()   # your v0.13 build (PRO-E Studio: build/studio)
BASE = B.deftone(img7[:0x40000])

# partial roles (wave 1 = saw, 0 = square/pulse; coarse 36 = 8', 24 = 16'; fine 50 = centre)
SAW, PULSE, SUB, DET = 0, 1, 2, 3
FX_CH1, FX_CH2, FX_JREV, FX_HALL, FX_DLY = (6, 2, 4), (6, 4, 5), (5, 2, 7), (1, 5, 5), (2, 4, 1)
FX_BP = (0, 3, 4)                       # resonant filter, band-pass + resonance, mid cutoff (bender wah)

# name, levels (saw, pulse, sub, det), pwm depth (0 = off), pw, lfo rate, cut, res, env depth, tvf times, tvf levels,
# tva times, tva levels, fx (mode, time, level), bender mode (0 pitch, 1 cutoff, 2 reso)
V = [
    ('JUNO BRASS', (100, 0, 60, 0), 0, 0, 70, 45, 9, 60, [0, 45, 40, 40, 35], [100, 55, 45, 35], [1, 20, 20, 20, 30], [100, 100, 100, 100], FX_CH1, 0),
    ('BRASS SWEL', (95, 0, 55, 70), 0, 0, 70, 28, 13, 80, [20, 55, 50, 50, 40], [100, 45, 35, 30], [15, 40, 40, 40, 35], [100, 90, 85, 80], FX_CH1, 0),
    ('HARD BRASS', (95, 0, 55, 70), 0, 0, 70, 12, 20, 100, [0, 60, 55, 55, 45], [100, 40, 30, 25], [1, 45, 45, 45, 35], [100, 90, 85, 80], FX_CH2, 0),
    ('JUNO PAD  ', (90, 0, 50, 70), 0, 0, 70, 55, 6, 35, [55, 70, 60, 60, 60], [100, 75, 65, 60], [55, 50, 50, 50, 65], [100, 100, 100, 100], FX_CH2, 0),
    ('PWM STRING', (0, 100, 25, 0), 7, 0, 10, 48, 3, 25, [40, 60, 60, 60, 60], [100, 85, 80, 75], [45, 50, 50, 50, 65], [100, 100, 100, 100], FX_CH2, 0),
    ('PWM STAB  ', (0, 100, 25, 0), 10, 0, 20, 40, 5, 55, [1, 35, 45, 45, 40], [100, 60, 50, 45], [1, 30, 40, 40, 40], [100, 90, 85, 80], FX_CH2, 0),
    ('JUNO PWM  ', (45, 95, 50, 0), 6, 0, 20, 50, 8, 35, [30, 60, 55, 55, 60], [100, 70, 60, 55], [25, 50, 50, 50, 55], [100, 100, 100, 100], FX_CH1, 0),
    ('FAST PWM  ', (0, 100, 40, 0), 10, 0, 60, 60, 4, 30, [10, 50, 50, 50, 50], [100, 80, 75, 70], [10, 40, 40, 40, 50], [100, 95, 90, 90], FX_CH1, 0),
    ('SAW LEAD  ', (100, 0, 30, 80), 0, 0, 70, 65, 10, 40, [0, 40, 40, 40, 30], [100, 70, 65, 60], [1, 30, 30, 30, 25], [100, 95, 90, 90], FX_DLY, 0),
    ('SQR LEAD  ', (0, 100, 40, 0), 0, 70, 70, 60, 6, 35, [0, 40, 40, 40, 30], [100, 70, 65, 60], [1, 30, 30, 30, 25], [100, 95, 90, 90], FX_DLY, 0),
    ('JUNO BASS ', (100, 0, 90, 0), 0, 0, 70, 30, 12, 70, [0, 35, 40, 40, 20], [100, 35, 25, 20], [1, 35, 40, 40, 15], [100, 85, 80, 75], FX_CH1, 0),
    ('SUB BASS  ', (0, 70, 100, 0), 0, 50, 70, 25, 5, 40, [0, 30, 40, 40, 15], [100, 40, 30, 25], [1, 30, 40, 40, 15], [100, 95, 90, 90], FX_CH1, 0),
    ('JUNO PLUCK', (90, 50, 40, 0), 0, 30, 70, 35, 14, 75, [0, 28, 35, 35, 25], [100, 20, 10, 5], [1, 35, 45, 45, 30], [100, 50, 30, 10], FX_JREV, 0),
    ('WAH STAB  ', (0, 100, 30, 0), 10, 0, 40, 60, 6, 30, [1, 35, 45, 45, 40], [100, 70, 60, 55], [1, 30, 40, 40, 40], [100, 90, 85, 80], FX_BP, 1),
    ('DEEP PAD  ', (80, 90, 40, 70), 5, 0, 15, 45, 4, 30, [70, 70, 60, 60, 70], [100, 80, 75, 70], [70, 60, 60, 60, 75], [100, 100, 100, 100], FX_JREV, 0),
    ('TECHNO ARP', (0, 100, 25, 0), 10, 0, 93, 40, 5, 55, [1, 35, 45, 45, 40], [100, 60, 50, 45], [1, 30, 40, 40, 40], [100, 90, 85, 80], FX_BP, 1),
]
assert len(V) == 16


def tone(v):
    name, lv, pwm, pw, rate, cut, res, env, ft, fl, at, al, fx, bm = v
    t = bytearray(BASE)
    t[0:10] = name.encode()
    t[10], t[11], t[13] = 0, 0, 0                       # S+S S+S, sustain env
    t[12] = sum(1 << p for p in range(4) if lv[p])      # partials that have a level
    for p in range(4):
        o = 14 + p * 58
        wave, coarse, fine = [(1, 36, 50), (0, 36, 50), (0, 24, 50), (1, 36, 56)][p]
        t[o + B.WG_COARSE], t[o + B.WG_FINE], t[o + B.WG_WAVE] = coarse, fine, wave
        t[o + B.WG_KEYF], t[o + B.WG_BEND] = 11, 1
        t[o + B.WG_PCM] = (0x70 + pwm) if (p == PULSE and pwm) else 0
        t[o + B.WG_PW] = pw if p == PULSE else 0
        t[o + B.PE_DEPTH] = 0
        t[o + B.LFO_RATE], t[o + B.LFO_DEPTH], t[o + B.LFO_MOD] = rate, (100 if pwm else 0), 15
        t[o + B.TVF_CUT], t[o + B.TVF_RESO], t[o + B.TVF_KEYF] = cut, res, 9
        t[o + B.TVF_DEPTH], t[o + B.TVF_VELO] = env, 20
        t[o + B.TVF_T[0]:o + B.TVF_T[0] + 5] = bytes(ft)
        t[o + 37:o + 41] = bytes(fl)
        t[o + B.TVA_LEVEL] = lv[p]
        t[o + B.TVA_T[0]:o + B.TVA_T[0] + 5] = bytes(at)
        t[o + 54:o + 58] = bytes(al)
    assert len(t) == 246 and max(t[10:]) < 0x80
    return bytes(t)


def record(v):
    fx, bm = v[12], v[13]
    return b'RT' + tone(v) + bytes([fx[0], fx[1], fx[2], bm])


def where(n):                                           # program 1-48 -> (page, address)
    s = n - 1
    return 2 + s // 32, 0x2000 + (s % 32) * 256


def ppoke(lk, page, addr, v):
    lk.send(0x14, addr >> 12 & 15, addr >> 8 & 15, addr >> 4 & 15, addr & 15, v >> 4, v & 15, page)


def ppeek(lk, page, addr, n):
    lk.send(0x15, addr >> 12 & 15, addr >> 8 & 15, addr >> 4 & 15, addr & 15, n, page)
    r = lk.reply(0x15)
    return lk.bytes_of(r) if r else None


if __name__ == '__main__':
    for n, v in enumerate(V, 1):
        print('USER %d-%d  %s  fx %s  bender %s' % ((n - 1) // 8 + 1, (n - 1) % 8 + 1, v[0], v[12], ['PITCH', 'CUTOFF', 'RESO'][v[13]]))
    if sys.argv[1:] == ['list']:
        sys.exit()
    lk = P.Link()
    print(lk.ping())
    bad = 0
    for n, v in enumerate(V, 1):
        page, a = where(n)
        rec = record(v)
        ok = True
        for c in range(0, len(rec), 16):                # poke 16, read back, re-poke what the link dropped
            want = rec[c:c + 16]
            todo = range(len(want))
            for _ in range(6):
                for i in todo:
                    ppoke(lk, page, a + c + i, want[i])
                    time.sleep(0.006)
                got = ppeek(lk, page, a + c, len(want)) or b''
                todo = [i for i in range(len(want)) if i >= len(got) or got[i] != want[i]]
                if not todo:
                    break
            ok &= not todo
        bad += not ok
        print('  program %2d %s: %s' % (n, v[0], 'OK' if ok else 'READBACK MISMATCH'))
    print('ALL 16 WRITTEN' if not bad else '%d FAILED' % bad)
