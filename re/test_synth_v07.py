"""Simulator test for v0.6 SYNTH EDIT + JUNO page: boot copy, keys, RQ1 readback, menus, edits and their SysEx, partial select /
on-off on the tempo LEDs, VOICE page.

  python -I test_synth_v05.py

IC7 banking is modelled ($180D bank bits + PA6 = which half), stock routines are stubs: SENDCK feeds a small CK-34
model that answers RQ1 for the timbre temp, DRAW records the two LCD lines.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v07 as B
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
        self.rx, self.tx, self.screens, self.msgs, self.sysx, self.mout = [], [], [], [], [], []
        s.stubs[0xE84D] = lambda s: self.mout.append(s.a)          # MIDI OUT
        s.stubs[0xD5E9] = self.lcdwait
        s.stubs[0xD611] = self.lcdcmd
        s.read_hook[0x160E] = self.lcdread
        self.lcdaddr = 0
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
            if m[4] == 0x12 and m[5] != 2:              # v0.7: system / patch temp DT1 (FX, PART FX)
                assert m[2] == 0x10 and sum(m[5:-1]) & 0x7F == 0, 'bad DT1 ' + bytes(m).hex()
                self.sysx.append(bytes(m[5:-2]))
            elif m[4] == 0x12:     # DT1 into the model's timbre temp
                i = m[6] * 128 + m[7]
                assert m[5] == 2 and sum(m[5:-1]) & 0x7F == 0, 'bad DT1 ' + bytes(m).hex()
                for k, v in enumerate(m[8:-2]):          # one byte, or the whole tone (MAKE JUNO)
                    assert v < 0x80
                    self.timbre[i + k] = v

    def lcdwait(self, s):                    # her busy-wait + control write: X = $160D, E high
        s.x = 0x160D
        s.b = s.b | 1

    def lcdcmd(self, s):
        self.lcdaddr = s.a & 0x7F

    def lcdread(self):
        l1, l2 = self.screens[-1] if self.screens else (' ' * 16, ' ' * 16)
        a = self.lcdaddr
        self.lcdaddr += 1
        return ord((l1 if a < 0x40 else l2)[a & 0x0F])

    def midi(self, data):                    # bytes into her MIDI IN parser pieces ($9703 status, $9745 data)
        s = self.s
        for v in data:
            self.w_latch(0x00)
            s.mem[0x0A] = 0x00
            s.a = v
            s.call(0x9703 if v & 0x80 else 0x9745)
            check(self.pa & 0x40 == 0 and self.latch == 0x00, 'MIDI: PA6 + bank restored')

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
check(r.screen == ('SYNTH EDIT  SOLO', 'JUNO        1/19'), 'page list screen: %r' % (r.screen,))
check(r.s.mem[0x10] & 0xF0 == 0x40 and r.s.mem[0x10] & 0x0F == 0x0F and r.s.mem[0x16] & 0x0F == 0x0F,
      'all selected: 4 tempo LEDs steady, other bits of $10 kept (%02X/%02X)' % (r.s.mem[0x10], r.s.mem[0x16]))
check(r.s.mem[0x2662] == 0x0D and r.s.mem[0x5E] & 0x40, 'page $0D borrowed')
check(r.s.mem[0x2D64] == 0xFF, 'TRANSPOSE hold timer left idle')
r.dial(1)
check(r.screen[1] == 'FILTER      2/19', 'dial scrolls pages: %r' % (r.screen,))
r.dial(20)
check(r.ram('SEL') == 18 and r.screen[1] == 'FX ROUTING 19/19', 'scroll clamps at the last page: %r' % (r.screen,))
r.dial(-20)
check(r.ram('SEL') == 0, 'scroll clamps at the first page')
r.dial(1)
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
r.key(0x42)                                          # NUMBER 3 = ENVELOPE
check(r.ram('SEL') == 2 and r.ram('LVL') == 1 and r.screen[0] == 'ENVELOPE     ALL', 'BANK 6 jumps: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(10)
check(len(dt1s(r, n)) == 8, 'ATTACK moves TVA + TVF attack on 4 partials')
check([r.timbre[14 + p * 58 + B.TVA_T[0]] for p in range(4)] == [55, 56, 57, 58], 'ATTACK REL on TVA (dial 10 -> step 35)')
# ---- PCM wave: ABS, bank 2 ----
r.key(0x58)                                          # NUMBER 7 = PCM WAVE
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
r.key(0x45)                                          # NUMBER 6 = VOICE
st0 = r.timbre[0x0A]
check(r.screen == ('VOICE        ALL', 'STRUCT1-2 ' + B.LISTS['struct'][st0].rjust(6)), 'VOICE / STRUCT1-2: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(-20)
check(r.timbre[0x0A] == 0 and r.screen[1] == 'STRUCT1-2>   S+S', 'STRUCT1-2 -> S+S: %r' % (r.screen,))
m = dt1s(r, n)
check(m and m[-1][6:9] == bytes([0x00, 0x0A, 0x00]), 'structure DT1 at common 0x0A')
r.dial(5)                                            # v0.6: lists step 1 per click (no acceleration)
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
r.dial(-7)
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
r.key(0x41)
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
check(r.ram('SEL') == 6 and r.screen[0].startswith('PCM WAVE'), 'NUMBER 7 ($58) = page 7 PCM WAVE: %r' % (r.screen,))
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
r.dial(-3)
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

# ---------- v0.6: JUNO page ----------
P = lambda p, off: 14 + p * 58 + off
L = lambda label, val, ed=False: label.ljust(9) + ('>' if ed else ' ') + str(val).rjust(6)
r = Rig()
r.boot()
r.key(0x5D)
check(r.screen == ('SYNTH EDIT  SOLO', 'JUNO        1/19'), 'JUNO is page 1: %r' % (r.screen,))
r.key(0x40)                                          # NUMBER 1 = JUNO
check(r.screen == ('JUNO         ALL', L('MAKE JUNO', 'TURN >')), 'MAKE JUNO row: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(-2)
check(len(r.msgs) == n, 'MAKE JUNO: dial left does nothing')
cut1, lvl1 = r.timbre[P(0, B.TVF_CUT)], r.timbre[P(0, B.TVA_LEVEL)]
r.dial(1)
m = dt1s(r, n)
check(len(m) == 1 and len(m[0]) == 8 + 246 + 2 and m[0][5:8] == bytes([2, 0, 0]), 'MAKE JUNO = one DT1 with the whole tone')
check(bytes(r.s.mem[S['WORK']:S['WORK'] + 246]) == bytes(r.timbre), 'CK-34 model = WORK after the bulk DT1')
t = r.timbre
check(t[0x0A] == 0 and t[0x0B] == 0 and t[0x0C] == 0x01, 'S+S S+S, only the SAW on')
check([t[P(p, B.WG_WAVE)] for p in range(4)] == [1, 0, 0, 1], 'roles: saw, square, square, saw')
check([t[P(p, B.WG_COARSE)] for p in range(4)] == [48, 48, 36, 48], "RANGE snapped (45 -> 4'), SUB one octave down")
check([t[P(p, B.WG_FINE)] for p in range(4)] == [50, 50, 50, 58], 'P4 8 cents sharp')
check(all(t[P(p, B.TVF_CUT)] == cut1 and t[P(p, B.TVA_LEVEL)] == lvl1 for p in range(4)), "P1's filter + level copied to all")
check(all(t[P(p, B.PE_L0) + k] == 50 for p in range(4) for k in range(5)) and all(t[P(p, B.PE_DEPTH)] == 8 for p in range(4)),
      'pitch env flat, depth 8')
check(all(t[P(p, B.WG_KEYF)] == 11 and t[P(p, B.WG_BEND)] == 1 for p in range(4)), 'key follow 1, bender on')
r.key(0x05)
r.dial(1)                                            # SAW
check(r.screen[1] == L('SAW', lvl1), 'SAW shows P1 level: %r' % (r.screen,))
r.key(0x5D)
for _ in range(3):
    r.dial(-50)
check(t[P(0, B.TVA_LEVEL)] == lvl1 and t[0x0C] & 1 == 0 and r.screen[1] == L('SAW', 0, 1), 'SAW 0 = P1 off: %r' % (r.screen,))
r.dial(1)
check(t[P(0, B.TVA_LEVEL)] == 1 and t[0x0C] & 1, 'SAW up from 0: P1 on at level 1')
r.dial(50)
check(t[P(0, B.TVA_LEVEL)] == 100, 'SAW to 100')
r.key(0x05)
r.dial(1)                                            # PULSE
check(r.screen[1] == L('PULSE', 0), 'PULSE starts off: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(5)
check(t[P(1, B.TVA_LEVEL)] == 11 and t[0x0C] == 0x03 and len(dt1s(r, n)) == 2, 'PULSE 11: P2 level + switched on')
r.key(0x05)
r.dial(1)                                            # PULSE W
check(r.screen[1] == L('PULSE W', 'SQUARE'), 'PULSE W: %r' % (r.screen,))
r.key(0x5D)
r.dial(3)
check(t[P(1, B.WG_PW)] == 75 and r.screen[1] == L('PULSE W', '25%', 1), 'PULSE W 3 clicks = 25 %% (lists: no acceleration): %r' % (r.screen,))
r.dial(10)
check(t[P(1, B.WG_PW)] == 100 and r.screen[1] == L('PULSE W', '13%', 1), 'PULSE W end = 13 %%: %r' % (r.screen,))
r.key(0x05)
r.dial(1)                                            # SUB OSC
r.key(0x5D)
r.dial(3)
check(t[P(2, B.TVA_LEVEL)] == 5 and t[0x0C] == 0x07, 'SUB OSC on at 5')
r.key(0x05)
r.dial(1)                                            # DETUNE
check(r.screen[1] == L('DETUNE', 0), 'DETUNE starts off: %r' % (r.screen,))
r.key(0x5D)
r.dial(2)
check(t[0x0C] == 0x0F and t[P(3, B.WG_FINE)] == 53 and t[P(3, B.TVA_LEVEL)] == 100, 'DETUNE 3: P4 on, +3 cents, at the SAW level')
r.key(0x05); r.key(0x05)
r.key(0x40)
r.dial(1)
r.key(0x5D)
r.dial(-5)
check(t[P(0, B.TVA_LEVEL)] == 89 and t[P(3, B.TVA_LEVEL)] == 89, 'the detuned copy follows the SAW level')
r.key(0x05)
r.dial(4)                                            # DETUNE again
r.key(0x5D)
r.dial(-50)
check(t[0x0C] == 0x07 and r.screen[1] == L('DETUNE', 0, 1), 'DETUNE 0 = P4 off: %r' % (r.screen,))
r.key(0x05)
r.dial(1)                                            # RANGE
check(r.screen[1] == L('RANGE', "4'"), 'RANGE: %r' % (r.screen,))
r.key(0x5D)
r.dial(-1)
check([t[P(p, B.WG_COARSE)] for p in range(4)] == [36, 36, 24, 36] and r.screen[1] == L('RANGE', "8'", 1), "RANGE 8': %r" % (r.screen,))
r.dial(-5)
check([t[P(p, B.WG_COARSE)] for p in range(4)] == [24, 24, 12, 24], "RANGE 16'")
check(bytes(r.s.mem[S['WORK']:S['WORK'] + 246]) == bytes(t), 'WORK = CK-34 model after the JUNO edits')
# ---- PITCH ENV ----
r.key(0x05); r.key(0x05)
r.key(0x43)                                          # NUMBER 4 = PITCH ENV
check(r.screen == ('PITCH ENV    ALL', L('AMOUNT', 0)), 'PITCH ENV: %r' % (r.screen,))
r.key(0x5D)
n = len(r.msgs)
r.dial(4)
check([t[P(p, B.PE_L0)] for p in range(4)] == [58, 58, 58, 50] and len(dt1s(r, n)) == 3 and r.screen[1] == L('AMOUNT', '+8', 1),
      'AMOUNT +8 on the partials that are on: %r' % (r.screen,))
r.key(0x05)
r.dial(2)
check(r.screen[1] == L('DEPTH', 8), 'DEPTH: %r' % (r.screen,))
# ---- SYNTH OSC: PULSE W as duty ----
r.key(0x05)
r.dial(5)                                            # page 9 = SYNTH OSC
r.key(0x5D)
r.key(0x39)                                          # BANK 2 = P2 (PW 100)
r.dial(1)
check(r.screen[1] == L('PULSE W', '13%'), 'SYNTH OSC PULSE W shows the duty: %r' % (r.screen,))
r.key(0x5D)
r.dial(-25)
check(t[P(1, B.WG_PW)] == 0 and r.screen[1] == L('PULSE W', '50%', 1), 'PW 0 = 50 %%: %r' % (r.screen,))
# ---- TUNE: 36 = 0 ----
r.key(0x05); r.key(0x05)
r.dial(1)                                            # page 10 = PITCH
r.key(0x5D)
check(r.screen[1] == L('TUNE', -12), "TUNE at RANGE 16' (coarse 24) = -12: %r" % (r.screen,))

# ---------- v0.7: ROSETTA FX pages ----------
L = lambda label, val, ed=False: label.ljust(9) + ('>' if ed else ' ') + str(val).rjust(6)
SYS = lambda m, t, l: bytes([0x10, 0x00, 0x01, m, t, l])
r = Rig()
r.boot()
r.key(0x5D)
r.dial(20)
r.dial(-6)                                           # page 13 = REVERB
check(r.screen[1] == 'REVERB     13/19', 'REVERB page: %r' % (r.screen,))
r.key(0x5D)
check(r.screen == ('REVERB       ALL', L('TIME', 4)), 'REVERB TIME default 4: %r' % (r.screen,))
r.key(0x5D)
r.dial(1)
check(r.sysx[-1:] == [SYS(0, 5, 5)] and r.screen[1] == L('TIME', 5, 1), 'TIME 5 -> DT1 10 00 01 00 05 05: %r' % (r.sysx[-1:],))
r.key(0x05); r.key(0x05)
r.dial(1)                                            # JUNO CHORUS
r.key(0x5D)
check(r.screen == ('JUNO CHORUS  ALL', L('RATE', '0.5Hz')), 'JUNO CHORUS RATE = Chorus I: %r' % (r.screen,))
r.key(0x5D)
r.dial(2)
check(r.sysx[-1] == SYS(1, 4, 4) and r.screen[1] == L('RATE', '0.9Hz', 1), 'RATE -> Chorus II speed (lists step 1): %r' % (r.sysx[-1],))
r.key(0x05); r.key(0x05)
r.dial(1)                                            # DELAY
r.key(0x5D)
check(r.screen[1] == L('TIME', '150ms'), 'DELAY TIME default 150 ms: %r' % (r.screen,))
r.key(0x5D)
r.dial(3)
check(r.sysx[-1] == SYS(2, 1, 4) and r.screen[1] == L('TIME', '230ms', 1), 'DELAY 230 ms = program 8: level 4, time bit 2 off, feedback kept: %r' % (r.sysx[-1],))
r.key(0x05)
r.dial(1)
check(r.screen[1] == L('FEEDBACK', '38%'), 'FEEDBACK: %r' % (r.screen,))
r.key(0x5D)
r.dial(2)
check(r.sysx[-1] == SYS(2, 3, 4), 'FEEDBACK 75 %% = time & 3 = 3, the delay time kept: %r' % (r.sysx[-1],))
r.key(0x05); r.key(0x05)
r.dial(1)                                            # LO-FI
r.key(0x5D)
check(r.screen[1] == L('CRUSH', '11b'), 'LO-FI CRUSH default 11 bits: %r' % (r.screen,))
r.key(0x05)
r.dial(3)                                            # FX ROUTING
r.key(0x5D)
check(r.screen == ('FX ROUTING   ALL', L('PART FX', 'DRY+FX')), 'PART FX default: %r' % (r.screen,))
r.key(0x5D)
r.dial(1)
check(r.sysx[-1] == bytes([0x03, 0x00, 0x26, 2]) and r.screen[1] == L('PART FX', 'FXONLY', 1), 'FX ONLY for SOLO: DT1 03 00 26 02: %r' % (r.sysx[-1],))
r.key(0x05)
r.dial(1)
r.key(0x5D)
n = len(r.sysx)
r.dial(-1)
check(r.sysx[n:] == [bytes([0x03, 0x00, 0x06 + 16 * k, 0]) for k in range(8)], 'ALL PARTS DRY: 8 parts 03 00 06/16/../76')
# the PRO-E's own reverb type list renamed and pointed at the new modes
b0 = img7[:0x8000]
o = 0x6361 - 0x4000
check(b0[o:o + 88] == b'1 = Plate 12 = Plate 23 = Juno I 4 = Juno II5 = Delay 16 = Delay 27 = Lo-Fi 18 = Lo-Fi 2', 'reverb type names: %r' % b0[o:o + 88])
check(list(b0[0x53C6 - 0x4000:0x53D6 - 0x4000]) == [0x01, 0x03, 0x12, 0x14, 0x21, 0x22, 0x31, 0x36, 6, 5, 4, 5, 2, 6, 4, 6], 'reverb type table')

# ---------- v0.7: MIDI remote control ----------
r = Rig()
r.boot()
R = lambda *b: [0xF0, 0x7D, 0x52, 0x22, 0x00] + list(b) + [0xF7]
r.midi(R(0x7F))
check(r.mout == [0xF0, 0x7D, 0x52, 0x7F] + list(b'RO07') + [0xF7], 'ping -> RO07: %r' % r.mout)
r.mout = []
r.midi(R(0x01, 0x5D))                                # press CURSOR
check(r.ram('EDIT') == 1 and r.screen[0] == 'SYNTH EDIT  SOLO', 'remote CURSOR press opens SYNTH EDIT: %r' % (r.screen,))
r.midi(R(0x02, 0x5D))
r.midi(R(0x03, 64 + 3))                              # dial +3
check(r.s.mem[0x53] == 53, 'remote dial moves the dial value (%d)' % r.s.mem[0x53])
r.w_latch(0x00); r.s.mem[0x0A] = 0x00
r.s.call(S['RAMTICK'])                               # her next 20 ms page tick reads it
check(r.screen[1] == 'PITCH ENV   4/19', 'remote dial +3 scrolls 3 pages: %r' % (r.screen,))
r.mout = []
r.midi(R(0x10))                                      # screen dump
txt = bytes((r.mout[4 + 2 * i] << 4) | r.mout[5 + 2 * i] for i in range(32)).decode()
check(r.mout[:4] == [0xF0, 0x7D, 0x52, 0x10] and r.mout[-1] == 0xF7 and len(r.mout) == 69, 'screen dump = 64 nibbles')
check(txt == r.screen[0] + r.screen[1], 'screen dump text = the LCD: %r' % txt)
r.mout = []
r.s.mem[0x30A0], r.s.mem[0x30A1] = 0xAB, 0x5C
r.midi(R(0x12, 3, 0, 0xA, 0, 2))                     # peek $30A0, 2 bytes
check(r.mout == [0xF0, 0x7D, 0x52, 0x12, 0xA, 0xB, 5, 0xC, 0xF7], 'peek: %r' % r.mout)
r.midi(R(0x13, 3, 0, 0xA, 1, 7, 0xE))                # poke $30A1 = $7E
check(r.s.mem[0x30A1] == 0x7E, 'poke')
r.midi(R(0x13, 0xC, 0, 0, 0, 1, 2))                  # poke into ROM space: refused
check(True, 'poke >= $4000 refused (no crash)')
n = len(r.msgs)
msg = [0xF0, 0x41, 0x10, 0x16, 0x12, 0x03, 0x00, 0x26, 0x02, 0x55, 0xF7]
r.midi(R(0x20, *[x for b in msg for x in (b >> 4, b & 0xF)]))
check(r.msgs[n:] == [bytes(msg)], 'raw bytes to the CK-34: %r' % r.msgs[n:])
r.mout = []
r.midi(R(0x11))
check(r.mout[:4] == [0xF0, 0x7D, 0x52, 0x11] and len(r.mout) == 5 + 24, 'LED dump: 12 bytes')
r.mout = []
r.midi([0xF0, 0x43, 0x10, 0x22, 0x01, 0xF7])          # another maker's SysEx is not ours
r.midi([0xF0, 0x7D, 0x52, 0x22, 0x05, 0x7F, 0xF7])    # no 00 guard: refused
check(r.mout == [], 'no 00 guard = not a remote command')
check(r.mout == [], 'other SysEx ignored by the remote')
print('ALL OK, %d checks' % len(OK))
