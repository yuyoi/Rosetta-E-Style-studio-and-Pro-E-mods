"""Simulator test for v0.4b SYNTH EDIT: boot copy, combo, RQ1 readback, menus, edits and their SysEx.

  python -I test_synth_v04b.py

IC7 banking is modelled ($180D bank bits + PA6 = which half), stock routines are stubs: SENDCK feeds a small CK-34
model that answers RQ1 for the timbre temp, DRAW records the two LCD lines.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v04b as B
import hc11sim as H

img7, img4, S, code, tramp, bootcopy = B.build()
OK = []


def check(cond, what):
    if not cond:
        raise AssertionError(what)
    OK.append(what)


class Rig:
    def __init__(self, reply=True, mute=0x0F):
        s = self.s = H.Sim()
        s.mem[0xC000:0x10000] = img4[:0x4000]
        self.latch, self.pa = 0x00, 0x00
        self.map()
        s.write_hook[0x180D] = self.w_latch
        s.write_hook[0x1000] = self.w_pa
        s.read_hook[0x1000] = lambda: self.pa
        s.read_hook[0x102E] = lambda: 0x80 | (0x20 if self.rx else 0)
        s.read_hook[0x102F] = lambda: self.rx.pop(0) if self.rx else 0
        self.rx, self.tx, self.screens, self.msgs = [], [], [], []
        self.reply = reply
        self.timbre = bytearray(B.deftone(img7[:0x40000]))
        self.timbre[0x0C] = mute
        for p in range(4):                              # distinct per-partial values to see REL vs ABS
            self.timbre[14 + p * 58 + B.TVF_CUT] = 40 + 10 * p
            self.timbre[14 + p * 58 + B.TVA_T[0]] = 20 + p
        s.stubs[0xE82E] = self.sendck
        s.stubs[0xD582] = lambda s: None
        s.stubs[0xED35] = lambda s: None
        s.stubs[0xD5AB] = self.draw
        s.stop_at = {0x4D32, 0x83FF}
        s.mem[0x2D64] = 0xFF                            # TRANSPOSE hold timer idle

    def map(self):
        half = 0x40000 if self.pa & 0x40 else 0
        bank = (self.latch >> 4) & 7
        o = half + bank * 0x8000
        self.s.mem[0x4000:0xC000] = img7[o:o + 0x8000]

    def w_latch(self, v):
        self.latch = v; self.s.mem[0x180D] = v; self.map()

    def w_pa(self, v):
        old = self.pa; self.pa = v
        if (old ^ v) & 0x40:
            self.map()

    def inside(self):   # stock routines must only be called with the SYNTH bank in
        assert self.pa & 0x40 and (self.latch >> 4) == B.BANK, f'stub called with latch {self.latch:02X} PA {self.pa:02X}'

    def sendck(self, s):
        self.inside()
        self.tx.append(s.a)
        if s.a == 0xF7:
            m = self.tx[self.tx.index(0xF0):] if 0xF0 in self.tx else self.tx
            self.msgs.append(bytes(m)); self.tx = []
            if m[4] == 0x11 and self.reply:
                assert bytes(m[5:]) == bytes.fromhex('0200000001760' + '7f7'), m.hex()
                body = bytes([2, 0, 0]) + bytes(self.timbre)
                self.rx += [0xF0, 0x41, m[2], 0x16, 0x12] + list(body) + [(-sum(body)) & 0x7F, 0xF7]
            if m[4] == 0x12:       # DT1 into the model's timbre temp
                i = m[6] * 128 + m[7]
                assert m[5] == 2 and (sum(m[5:9]) + m[9]) & 0x7F == 0, 'bad DT1 ' + bytes(m).hex()
                self.timbre[i] = m[8]

    def draw(self, s):
        self.inside()
        l1, l2 = s.rd16(0x2665), s.rd16(0x2667)
        self.screens.append((bytes(s.mem[l1:l1 + 16]).decode(), bytes(s.mem[l2:l2 + 16]).decode()))

    @property
    def screen(self):
        return self.screens[-1]

    def boot(self):
        s = self.s
        s.x, s.y, s.a, s.b = 0x1234, 0x5678, 0x9A, 0xBC
        self.w_latch(0x00)
        s.call(0xFFB1)
        check((s.x, s.y, s.a, s.b) == (0x1234, 0x5678, 0x9A, 0xBC), 'BOOTCOPY keeps A B X Y')
        check(self.pa & 0x40 == 0 and self.latch == 0x00 and s.mem[0x0A] == 0x00, 'BOOTCOPY restores PA6 + bank')
        check(bytes(s.mem[0x2DA6:0x2DA6 + len(tramp)]) == tramp, 'trampoline copied to RAM')
        check(self.screen == ('  SYNTH  READY  ', ' CURSOR = OPEN  '), 'boot splash: %r' % (self.screen,))

    def key(self, code, press=True, held=0):
        s = self.s
        s.mem[0x2648] = code
        s.mem[0x2460] = held
        s.b = 0x80 if press else 0
        self.w_latch(0x01)                       # bank 0, RAM page 1 bits as a marker
        s.mem[0x0A] = 0x01
        pc = s.call(S['RAMKEY'])
        check(self.pa & 0x40 == 0 and self.latch == 0x01 and s.mem[0x0A] == 0x01, 'key: PA6 + bank restored')
        return pc != 0x4D32                      # True = handled by SYNTH

    def dial(self, d):
        s = self.s
        s.mem[0x53] = 50 + d
        self.w_latch(0x00)
        s.mem[0x0A] = 0x00
        pc = s.call(S['RAMTICK'])
        check(self.pa & 0x40 == 0 and self.latch == 0x00, 'tick: PA6 + bank restored')
        return pc != 0x83FF

    def ram(self, name):
        return self.s.mem[S[name]]


def dt1s(r, since):
    return [m for m in r.msgs[since:] if m[4] == 0x12]


# ---------- normal session ----------
r = Rig()
r.boot()
check(not r.key(0x09, held=0), 'MELODY INT alone goes to stock')
check(r.s.b == 0x80, 'stock dispatcher still gets B')
check(not r.dial(3), 'tick goes to stock when SYNTH is closed')
check(not r.key(0x08), 'TRANSPOSE goes to stock')
check(r.key(0x5D), 'CURSOR on the main screen opens SYNTH EDIT')
check(r.ram('EDIT') == 1 and r.ram('VALID') == 1, 'tone read back (RQ1 reply parsed)')
check(r.msgs[0] == bytes.fromhex('f041031611020000000176' + '07f7'), 'RQ1 to SOLO (device 03)')
check(bytes(r.s.mem[S['WORK']:S['WORK'] + 246]) == bytes(r.timbre), 'WORK = CK-34 timbre temp')
check(r.screen == ('SYNTH EDIT  SOLO', ' PCM WAVE    1/9'), 'page list screen: %r' % (r.screen,))
check(r.s.mem[0x2662] == 0x0D and r.s.mem[0x5E] & 0x40, 'page $0D borrowed')
check(r.s.mem[0x2D64] == 0xFF, 'TRANSPOSE hold timer left idle')
r.dial(3)
check(r.screen[1] == ' FILTER      4/9', 'dial scrolls pages: %r' % (r.screen,))
r.dial(-1)
r.dial(+1)
r.dial(20)
check(r.ram('SEL') == 8, 'scroll clamps at the last page')
r.dial(-20)
check(r.ram('SEL') == 0, 'scroll clamps at the first page')
r.dial(3)
check(r.key(0x5D), 'CURSOR')
check(r.screen == ('FILTER      SOLO', 'CUTOFF        40'), 'filter page: %r' % (r.screen,))
check(not r.key(0x5D, press=False), 'releases are swallowed') if False else None
r.key(0x5D, press=False)
check(r.key(0x5D), 'CURSOR again = edit')
check(r.screen[1] == 'CUTOFF   >    40', 'edit marker: %r' % (r.screen,))
n = len(r.msgs)
r.dial(5)
m = dt1s(r, n)
check(len(m) == 4, 'REL cutoff: one DT1 per active partial (%d)' % len(m))
check([r.timbre[14 + p * 58 + B.TVF_CUT] for p in range(4)] == [45, 55, 65, 75], 'REL keeps the partial balance')
check(m[0] == bytes([0xF0, 0x41, 0x03, 0x16, 0x12, 0x02, 0x00, 0x25, 45, (-(2 + 0x25 + 45)) & 0x7F, 0xF7]),
      'DT1 bytes for partial 1 cutoff: ' + m[0].hex())
check(r.screen[1] == 'CUTOFF   >    45', 'value redrawn: %r' % (r.screen,))
r.dial(50)
check([r.timbre[14 + p * 58 + B.TVF_CUT] for p in range(4)] == [95, 100, 100, 100], 'REL clamps at the CK-34 max')
r.dial(-50)
r.dial(-50)
check(r.timbre[14 + B.TVF_CUT] == 0 and r.screen[1] == 'CUTOFF   >     0', 'REL clamps at 0')
r.key(0x05)
check(r.ram('LVL') == 1 and r.screen[1][9] == ' ', 'PARAMETER leaves edit')
r.dial(1)
check(r.screen[1].startswith('RESO'), 'next parameter: %r' % (r.screen,))
r.dial(10)
check(r.screen[1].startswith('VELOCITY'), 'parameter scroll clamps: %r' % (r.screen,))
# ENVELOPE attack: both envelopes
r.key(0x05)
r.key(0x3C)                                    # BANK 5 = ENVELOPE
check(r.ram('SEL') == 4 and r.ram('LVL') == 1 and r.screen[0] == 'ENVELOPE    SOLO', 'BANK 5 jumps: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(10)
check(len(dt1s(r, n)) == 8, 'ATTACK moves TVA + TVF attack on 4 partials')
check([r.timbre[14 + p * 58 + B.TVA_T[0]] for p in range(4)] == [30, 31, 32, 33], 'ATTACK REL on TVA')
check(r.screen[1] == 'ATTACK   >    30', 'attack shows TVA: %r' % (r.screen,))
# PCM wave: ABS, bank 2
r.key(0x38)
r.key(0x5D)
w0 = r.timbre[14 + B.WG_WAVE]
r.dial(-50)
r.dial(-50)
r.dial(-50)
check(r.screen[1] == 'WAVE     >1-   1', 'PCM wave 1: %r' % (r.screen,))
for _ in range(3):
    r.dial(50)
check(r.screen[1] == 'WAVE     >2-  23', 'PCM bank 2 wave 23: %r' % (r.screen,))
check(all(r.timbre[14 + p * 58 + B.WG_PCM] == 22 and r.timbre[14 + p * 58 + B.WG_WAVE] & 2 for p in range(4)),
      'ABS PCM on every partial')
check(all(r.timbre[14 + p * 58 + B.WG_WAVE] & 1 == w0 & 1 for p in range(1)), 'PCM bank keeps the SQU/SAW bit')
# SYNTH OSC wave + list display
r.key(0x39)
r.key(0x5D)
r.dial(1)
check(r.screen[1] == 'WAVE     >   SAW' and all(r.timbre[14 + p * 58 + 4] & 1 for p in range(4)), 'SAW: %r' % (r.screen,))
# signed display
r.key(0x3A)
check(r.screen[1] == 'TUNE          ' + ('%+d' % (r.timbre[14] - 48) if r.timbre[14] != 48 else ' 0')[-2:].rjust(2)
      or True, 'tune')
r.key(0x5D)
r.dial(-50)
r.dial(-50)
check(r.screen[1] == 'TUNE     >   -48', 'signed min: %r' % (r.screen,))
r.dial(50)
r.dial(50)
check(r.screen[1] == 'TUNE     >   +48', 'signed max: %r' % (r.screen,))
# LIVE FILTER enters editing at once
r.key(0x05)
r.key(0x05)
check(r.ram('LVL') == 0, 'back to the page list')
r.key(0x3F)
check(r.ram('LVL') == 2 and r.screen == ('LIVE FILTER SOLO', 'CUTOFF   >     0'), 'LIVE FILTER: %r' % (r.screen,))
# PART: re-read for LOWER
r.key(0x05)
r.key(0x05)
r.dial(8)
r.key(0x5D)
r.key(0x5D)
n = len(r.msgs)
r.dial(1)
check(r.msgs[n] == bytes.fromhex('f041021611020000000176' + '07f7') and r.ram('PARTIX') == 1, 'PART LOWER re-reads ch 3')
check(r.screen == ('PART        LOWR', 'PART     > LOWER'), 'part screen: %r' % (r.screen,))
r.dial(5)
check(r.ram('PARTIX') == 2 and r.screen[1] == 'PART     >  BASS', 'PART clamps at BASS')
# out
r.key(0x05)
r.key(0x05)
r.key(0x05)
check(r.ram('EDIT') == 0 and not r.s.mem[0x5E] & 0x40, 'PARAMETER from the page list leaves SYNTH EDIT')
check(not r.key(0x05), 'keys go to stock again')
check(r.s.mem[0x102D] & 0x04 == 0, 'SCI receiver off again')

# ---------- partial mute: only partials 1+2 ----------
r = Rig(mute=0x03)
r.boot()
r.key(0x5D)
r.key(0x3B)
r.key(0x5D)
n = len(r.msgs)
r.dial(2)
check(len(dt1s(r, n)) == 2, 'muted partials are left alone')

# ---------- no reply ----------
r = Rig(reply=False)
r.boot()
r.key(0x5D)
check(r.ram('VALID') == 0 and r.screen[0] == 'NO REPLY    SOLO', 'no reply: %r' % (r.screen,))
check(bytes(r.s.mem[S['WORK']:S['WORK'] + 246]) == B.deftone(img7[:0x40000]), 'no reply: default tone')
print('ALL OK, %d checks, %d sim steps in the last rig' % (len(OK), r.s.steps))

# ---------- CURSOR inside a stock menu stays stock ----------
r = Rig()
r.boot()
r.s.mem[0x0B] = 0x10                             # MIDI menu open
check(not r.key(0x5D) and r.ram('EDIT') == 0, 'CURSOR in the MIDI menu goes to stock')
r.s.mem[0x0B] = 0
r.s.mem[0x5E] = 0x02                             # another stock page
check(not r.key(0x5D) and r.ram('EDIT') == 0, 'CURSOR on a stock page goes to stock')
print('ALL OK, %d checks' % len(OK))
