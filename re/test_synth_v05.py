"""Simulator test for v0.5 SYNTH EDIT: boot copy, keys, RQ1 readback, menus, edits and their SysEx, partial select /
on-off on the tempo LEDs, VOICE page.

  python -I test_synth_v05.py

IC7 banking is modelled ($180D bank bits + PA6 = which half), stock routines are stubs: SENDCK feeds a small CK-34
model that answers RQ1 for the timbre temp, DRAW records the two LCD lines.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v05 as B
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
check(not r.key(0x38), 'BANK 1 goes to stock while SYNTH EDIT is closed')
r.s.mem[0x10] = 0x45; r.s.mem[0x16] = 0x41          # arranger flag + beat LEDs + fade LED, to see them restored
check(r.key(0x5D), 'CURSOR on the main screen opens SYNTH EDIT')
check(r.ram('EDIT') == 1 and r.ram('VALID') == 1, 'tone read back (RQ1 reply parsed)')
check(r.msgs[0] == bytes.fromhex('f041031611020000000176' + '07f7'), 'RQ1 to SOLO (device 03)')
check(bytes(r.s.mem[S['WORK']:S['WORK'] + 246]) == bytes(r.timbre), 'WORK = CK-34 timbre temp')
check(r.screen == ('SYNTH EDIT  SOLO', 'VOICE       1/10'), 'page list screen: %r' % (r.screen,))
check(r.s.mem[0x10] & 0xF0 == 0x40 and r.s.mem[0x10] & 0x0F == 0x0F and r.s.mem[0x16] & 0x0F == 0x0F,
      'all selected: 4 tempo LEDs steady, other bits of $10 kept (%02X/%02X)' % (r.s.mem[0x10], r.s.mem[0x16]))
check(r.s.mem[0x2662] == 0x0D and r.s.mem[0x5E] & 0x40, 'page $0D borrowed')
check(r.s.mem[0x2D64] == 0xFF, 'TRANSPOSE hold timer left idle')
r.dial(4)
check(r.screen[1] == 'FILTER      5/10', 'dial scrolls pages: %r' % (r.screen,))
r.dial(20)
check(r.ram('SEL') == 9 and r.screen[1] == 'PART       10/10', 'scroll clamps at the last page: %r' % (r.screen,))
r.dial(-20)
check(r.ram('SEL') == 0, 'scroll clamps at the first page')
r.dial(4)
check(r.key(0x5D), 'CURSOR')
check(r.screen == ('FILTER       ALL', 'CUTOFF        40'), 'filter page: %r' % (r.screen,))
r.key(0x5D, press=False)
check(r.key(0x5D), 'CURSOR again = edit')
check(r.screen[1] == 'CUTOFF   >    40', 'edit marker: %r' % (r.screen,))
n = len(r.msgs)
r.dial(5)
m = dt1s(r, n)
check(len(m) == 4, 'REL cutoff: one DT1 per active partial (%d)' % len(m))
check([r.timbre[14 + p * 58 + B.TVF_CUT] for p in range(4)] == [51, 61, 71, 81], 'REL keeps the partial balance (dial 5 -> step 11, accelerated)')
check(m[0] == bytes([0xF0, 0x41, 0x03, 0x16, 0x12, 0x02, 0x00, 0x25, 51, (-(2 + 0x25 + 51)) & 0x7F, 0xF7]),
      'DT1 bytes for partial 1 cutoff: ' + m[0].hex())
check(r.screen[1] == 'CUTOFF   >    51', 'value redrawn: %r' % (r.screen,))
# ---- NUMBER 1-5: partial select / on-off ----
r.key(0x39)                                          # BANK 2: select partial 2
check(r.ram('SELP') == 2 and r.screen == ('FILTER       P2*', 'CUTOFF   >    61'), 'BANK 2 selects P2: %r' % (r.screen,))
check(r.s.mem[0x10] & 0x0F == 0x04 and r.s.mem[0x16] & 0x0F == 0x04, 'only the P2 LED lit, steady')
n = len(r.msgs)
r.dial(3)
check([r.timbre[14 + p * 58 + B.TVF_CUT] for p in range(4)] == [51, 66, 71, 81] and len(dt1s(r, n)) == 1,
      'macros edit only the selected partial')
n = len(r.msgs)
r.key(0x39)                                          # BANK 2 again: partial 2 off
m = dt1s(r, n)
check(r.timbre[0x0C] == 0x0D and len(m) == 1 and m[0][6:9] == bytes([0x00, 0x0C, 0x0D]),
      'NUMBER 2 again switches P2 off: mute byte 0D sent (%s)' % (m[0].hex() if m else '-'))
check(r.screen[0] == 'FILTER       P2 ', 'corner shows P2 off: %r' % (r.screen,))
check(r.s.mem[0x10] & 0x0F == 0x04 and r.s.mem[0x16] & 0x0F == 0x00, 'P2 LED blinks (one frame only)')
r.dial(1)
check(r.timbre[14 + 58 + B.TVF_CUT] == 67, 'a switched-off selected partial can still be edited')
r.key(0x3C)                                          # BANK 5: all
check(r.ram('SELP') == 0 and r.screen[0] == 'FILTER       ALL', 'NUMBER 5 = all')
check(r.s.mem[0x10] & 0x0F == 0x0F and r.s.mem[0x16] & 0x0F == 0x0B, 'all: P2 LED blinks, the others steady')
n = len(r.msgs)
r.dial(1)
check(len(dt1s(r, n)) == 3, 'all: macros skip the switched-off partial')
r.key(0x39); r.key(0x39)                             # P2 back on
check(r.timbre[0x0C] == 0x0F, 'P2 back on')
r.key(0x3C)
r.s.mem[0x10] = (r.s.mem[0x10] & 0xF0) | 0x08        # the tempo code draws a beat over them
r.dial(0)
check(r.s.mem[0x10] & 0x0F == 0x0F, 'the 20 ms tick puts the partial LEDs back')
r.key(0x05)
check(r.ram('LVL') == 1 and r.screen[1][9] == ' ', 'PARAMETER leaves edit')
r.dial(1)
check(r.screen[1].startswith('RESO'), 'next parameter: %r' % (r.screen,))
r.dial(10)
check(r.screen[1].startswith('VELOCITY'), 'parameter scroll clamps: %r' % (r.screen,))
# ---- ENVELOPE attack: both envelopes ----
r.key(0x05)
r.key(0x45)                                          # NUMBER 6 = ENVELOPE
check(r.ram('SEL') == 5 and r.ram('LVL') == 1 and r.screen[0] == 'ENVELOPE     ALL', 'BANK 6 jumps: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(10)
check(len(dt1s(r, n)) == 8, 'ATTACK moves TVA + TVF attack on 4 partials')
check([r.timbre[14 + p * 58 + B.TVA_T[0]] for p in range(4)] == [55, 56, 57, 58], 'ATTACK REL on TVA (dial 10 -> step 35)')
# ---- PCM wave: ABS, bank 2 ----
r.key(0x41)                                          # NUMBER 2 = PCM WAVE
r.key(0x5D)
for _ in range(3):
    r.dial(-50)
check(r.screen[1] == 'WAVE     >1-   1', 'PCM wave 1: %r' % (r.screen,))
for _ in range(3):
    r.dial(50)
check(r.screen[1] == 'WAVE     >2- 128', 'fast spin reaches the last PCM wave: %r' % (r.screen,))
check(all(r.timbre[14 + p * 58 + B.WG_PCM] == 127 and r.timbre[14 + p * 58 + B.WG_WAVE] & 2 for p in range(4)),
      'ABS PCM on every partial')
# ---- VOICE page ----
r.key(0x40)                                          # NUMBER 1 = VOICE
st0 = r.timbre[0x0A]
check(r.screen == ('VOICE        ALL', 'STRUCT1-2 ' + B.LISTS['struct'][st0].rjust(6)), 'VOICE / STRUCT1-2: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(-20)
check(r.timbre[0x0A] == 0 and r.screen[1] == 'STRUCT1-2>   S+S', 'STRUCT1-2 -> S+S: %r' % (r.screen,))
m = dt1s(r, n)
check(m and m[-1][6:9] == bytes([0x00, 0x0A, 0x00]), 'structure DT1 at common 0x0A')
r.dial(3)
check(r.timbre[0x0A] == 5 and r.screen[1] == 'STRUCT1-2>   P+P', 'STRUCT1-2 -> P+P (audition PCM on any tone): %r' % (r.screen,))
r.key(0x05)
r.dial(2)                                            # RING 1-2
check(r.screen[1] == 'RING 1-2     OFF', 'RING 1-2 shows OFF for P+P: %r' % (r.screen,))
r.key(0x5D)
r.dial(1)
check(r.timbre[0x0A] == 6 and r.screen[1] == 'RING 1-2 >    ON', 'RING on: P+P -> P&P: %r' % (r.screen,))
r.dial(-1)
check(r.timbre[0x0A] == 5, 'RING off: P&P -> P+P')
r.dial(-1)
check(r.timbre[0x0A] == 5, 'RING off again: no change')
r.key(0x05)
r.dial(3)                                            # row 5 = LEVEL P2
check(r.screen[1].startswith('LEVEL P2'), 'LEVEL P2 row: %r' % (r.screen,))
r.key(0x5D)
lv = [r.timbre[14 + p * 58 + B.TVA_LEVEL] for p in range(4)]
n = len(r.msgs)
r.dial(-5)
check([r.timbre[14 + p * 58 + B.TVA_LEVEL] for p in range(4)] == [lv[0], max(0, lv[1] - 11), lv[2], lv[3]] and len(dt1s(r, n)) == 1,
      'LEVEL P2 edits only partial 2, whatever is selected')
# ---- LIVE FILTER = NUMBER 8 ($59) ----
r.key(0x05); r.key(0x05)
check(r.ram('LVL') == 0, 'back to the page list')
r.key(0x59)
check(r.ram('LVL') == 2 and r.screen[0] == 'LIVE FILTER  ALL' and r.screen[1].startswith('CUTOFF   >'), 'LIVE FILTER: %r' % (r.screen,))
# ---- PART: re-read for LOWER ----
r.key(0x05); r.key(0x05)
r.dial(20)
r.key(0x5D); r.key(0x5D)
n = len(r.msgs)
r.dial(1)
check(r.msgs[n] == bytes.fromhex('f041021611020000000176' + '07f7') and r.ram('PARTIX') == 1, 'PART LOWER re-reads ch 3')
check(r.screen[1] == 'PART     > LOWER', 'part screen: %r' % (r.screen,))
# ---- out ----
r.key(0x05); r.key(0x05); r.key(0x05)
check(r.ram('EDIT') == 0 and not r.s.mem[0x5E] & 0x40, 'PARAMETER from the page list leaves SYNTH EDIT')
check(r.s.mem[0x10] == 0x45 and r.s.mem[0x16] == 0x41, 'tempo LEDs restored on exit (%02X %02X)' % (r.s.mem[0x10], r.s.mem[0x16]))
check(not r.key(0x05), 'keys go to stock again')
check(r.s.mem[0x102D] & 0x04 == 0, 'SCI receiver off again')

# ---------- partial mute: only partials 1+2 ----------
r = Rig(mute=0x03)
r.boot()
r.key(0x5D)
r.key(0x44)
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

# ---------- tempo-LED hooks: her own IC4 beat code, run through the patched sites ----------
r = Rig()
r.boot()
hb, hl = S['HOOKBASE'], S['HOOK_LEN']
check(bytes(r.s.mem[hb:hb + hl]) == code[S['HOOK_IMG'] - B.CODE:S['HOOK_IMG'] - B.CODE + hl], 'tempo-LED hooks copied to RAM at boot')
sites = ((0xC490, 0xC49C), (0xC4A7, 0xC4B5), (0xC4C7, 0xC4CD), (0xC4D5, 0xC4E1), (0xC859, 0xC867))


def run_site(a, end, edit, v10, v16, b=0x03):
    r.s.mem[S['EDIT']] = edit
    r.s.mem[0x10], r.s.mem[0x16] = v10, v16
    r.s.pc, r.s.b, r.s.a = a, b, 0
    r.s.run(stop={end})
    return r.s.mem[0x10], r.s.mem[0x16], r.s.a


for a, end in sites:
    out0 = run_site(a, end, 0, 0x42, 0x41)
    out1 = run_site(a, end, 1, 0x42, 0x41)
    check(out1[:2] == (0x42, 0x41), 'site $%04X: no tempo-LED write while SYNTH EDIT is open' % a)
    check(out0[:2] != (0x42, 0x41) and out0[0] & 0xF0 == 0x40 and out0[1] & 0xF0 == 0x40,
          'site $%04X: stock tempo-LED write when closed (%02X %02X)' % (a, out0[0], out0[1]))
    if a in (0xC4A7, 0xC859):
        check(out0[2] == out1[2], 'site $%04X: A comes out the same either way' % a)

# ---------- v0.5b rows: NUMBER = pages (7/8 are $58/$59), BANK 6-8 do nothing ----------
r = Rig()
r.boot()
r.key(0x5D)
r.key(0x58)
check(r.ram('SEL') == 6 and r.screen[0].startswith('AMP'), 'NUMBER 7 ($58) = page 7 AMP: %r' % (r.screen,))
sel = r.ram('SELP')
for k in (0x3D, 0x3E, 0x3F):
    check(r.key(k) and r.ram('SELP') == sel and r.ram('SEL') == 6, 'BANK %d is swallowed, changes nothing' % (k - 0x37))
check(r.s.rd16(0xFFB1 + 15) == 0xA003 or bytes(img4[0x3FB1:0x3FD5]).find(bytes([0xBD, 0xA0, 0x03])) >= 0, 'BOOTCOPY jsr = fixed $A003')

# ---------- v0.5c: dial acceleration (values only) ----------
acc = lambda d: (1 if d > 0 else -1) * min(100, abs(d) + d * d // 4)
check([acc(d) for d in (1, 2, 3, 4, 6, 10)] == [1, 3, 5, 8, 15, 35], 'curve: 1 3 5 8 15 35')
r = Rig()
r.boot()
r.key(0x5D)
r.dial(4)
check(r.ram('SEL') == 4, 'page list: 4 clicks = 4 pages, no acceleration')
r.key(0x5D)
r.dial(3)
check(r.ram('ROW') == 3, 'parameter list: no acceleration')
r.dial(-3)
r.key(0x5D)
c0 = r.timbre[14 + B.TVF_CUT]
r.dial(1)
check(r.timbre[14 + B.TVF_CUT] == c0 + 1, 'slow click = 1')
r.dial(-6)
check(r.timbre[14 + B.TVF_CUT] == c0 + 1 - 15, 'fast spin (6/tick) = 15')
print('ALL OK, %d checks' % len(OK))
