# SPDX-License-Identifier: LGPL-2.1-or-later (port of Sergey V. Mikayev's MT-32 reverb interpreter)
"""CK-34 reverb chip (Boss HG61H20R36F / BOS-007) in Python: runs IC13 programs, assembles new ones.

  python -I boss_reverb.py            -> self-test on the stock IC13 dump (Tap Delay impulse response)

Port of Sergey V. Mikayev's interpreter (LGPL-2.1+, via gearmulator source/ronaldo/custom_chips/mt32reverb). Facts it gives:
  - IC13 = 256-byte programs, 64 steps x 4 bytes, one step per chip cycle, 64 steps per sample (32 kHz frames).
  - program index = mode*16 + level*2 + (time >> 2); time & 3 picks sawBits = 1 << (time & 3), which gates each
    half-step's add, so one program holds 4 coefficient sets.
  - step bytes: b0 + (b2 & 0x3F) << 8 = RAM offset (14 bits) from the frame position (+1 per frame, so an offset of
    0x4000 - D reads what was written D frames ago). b1 / b3 = control for half-step 0 / 1:
      bit0 the RAM write takes the input (else the accumulator), bit1 = 0 write RAM, bit2 = 0 load the shifter,
      bit3 invert the accumulator AFTER the add, only when the add fires (measured on hw), bit4 = 0 clear the accumulator first, bits5-7 = mask bits 1-3.
    mask bit 0 = b2 bit 7 (half-step 0) / b2 bit 6 (half-step 1). Add = accumulator + shifter + carry when mask & sawBits.
    The shifter halves every half-step: a load followed by adds = a shift-and-add multiply.
  - steps < 32 see the right input, steps >= 32 the left. Out R = accumulator before step 47, out L = before step 56.
  - No LFO and no address modulation: offsets are fixed in ROM.
"""
import os

RAM_MASK = 0x3FFF
OUT_R, OUT_L, SPLIT = 47, 56, 32


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Chip:
    def __init__(self, rom):
        self.rom = bytes(rom)
        self.ram = [0] * 0x4000
        self.pos = self.acc = self.sh = self.carry = 0
        self.saw = 0
        self.base = 0

    def set_params(self, mode, time, level):
        mode &= 7 if len(self.rom) == 0x8000 else 3
        base = (mode << 12) | ((level & 7) << 9) | ((time & 4) << 6)
        self.base, self.saw = (base, 1 << (time & 3)) if base < len(self.rom) else (0, 0)

    def _update(self, ctrl, mask):
        if not ctrl & 0x10:
            self.acc = 0
        if mask & self.saw:
            self.acc = max(-0x8000, min(0x7FFF, self.acc + self.sh + self.carry))
            if ctrl & 8:
                self.acc = s16(~self.acc)
        # MEASURED on the PRO-E 2026-11-06 (proe_link.py lab3, 12 single-op tests): the invert bit only acts in a
        # half-step whose add fires (mask & sawBits), after the add. On its own it does nothing, in either half-step.
        # (Mikayev's interpreter inverts unconditionally; every filter built on that squealed or stuck on her.)

    def frame(self, in_l, in_r):
        in_l = s16(max(-32768, min(32767, in_l)) >> 1)
        in_r = s16(max(-32768, min(32767, in_r)) >> 1)
        out_l = out_r = 0
        rom = self.rom
        for step in range(64):
            if step == OUT_R:
                out_r = self.acc
            elif step == OUT_L:
                out_l = self.acc
            b0, b1, b2, b3 = rom[self.base + step * 4:self.base + step * 4 + 4]
            addr = (self.pos + (b0 | (b2 << 8))) & RAM_MASK
            nsh = self.sh >> 1
            ncarry = self.sh & 1 if self.sh < 0 else 0
            if not b1 & 2:
                v = (in_r if step < SPLIT else in_l) if b1 & 1 else self.acc
                self.ram[addr] = v
                if not b1 & 4:
                    nsh, self.carry, ncarry = v, 0, 0
            elif not b1 & 4:
                nsh, self.carry, ncarry = self.ram[addr], 0, 0
            self._update(b1, ((b1 >> 4) & 0x0E) | (b2 >> 7))
            self.carry, self.sh = ncarry, nsh
            self._update(b3, ((b3 >> 4) & 0x0E) | ((b2 >> 6) & 1))
            self.carry = self.sh & 1 if self.sh < 0 else 0
            self.sh >>= 1
        self.pos = (self.pos + 1) & RAM_MASK
        return out_l, out_r


# ---- assembling new programs ----
NOP = bytes([0x00, 0x17, 0x00, 0x17])


def step_write_input(offset):
    """RAM[pos + offset] = input (right for steps < 32, left after)."""
    return bytes([offset & 0xFF, 0x15, (offset >> 8) & 0x3F, 0x17])


def step_tap(delay, sawmask, clear):
    """Read RAM written `delay` frames ago into the shifter, add it (x1) in half-step 1 when sawBits & sawmask.
    clear = zero the accumulator first (half-step 0)."""
    off = (0x4000 - delay) & RAM_MASK
    b1 = 0x02 | (0 if clear else 0x10)                  # no write, load, (no) clear, half-step 0 adds nothing
    b3 = 0x10 | ((sawmask & 0x0E) << 4)                 # keep the accumulator, mask bits 1-3
    b2 = ((off >> 8) & 0x3F) | ((sawmask & 1) << 6)     # mask bit 0 of half-step 1
    return bytes([off & 0xFF, b1, b2, b3])


def program(steps):
    """steps = {index: 4 bytes}; the rest are NOPs."""
    out = bytearray(NOP * 64)
    for i, s in steps.items():
        assert 0 <= i < 64 and len(s) == 4
        out[i * 4:i * 4 + 4] = s
    return bytes(out)


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    rom = open(os.path.join(here, '..', 'dumps', 'ck34_ic13_reverb_R15179917_HN623257.bin'), 'rb').read()
    for mode, name in enumerate(('ROOM', 'HALL', 'PLATE', 'TAP DELAY')):
        c = Chip(rom)
        c.set_params(mode, 4, 7)
        resp = [c.frame(16000, 16000) if i == 0 else c.frame(0, 0) for i in range(32000)]
        peaks = [(i, l, r) for i, (l, r) in enumerate(resp) if abs(l) > 600 or abs(r) > 600]
        energy = sum(abs(l) + abs(r) for l, r in resp)
        print('%-9s first taps (frame, L, R): %s  ... energy %d, last loud frame %s' %
              (name, peaks[:6], energy, peaks[-1][0] if peaks else '-'))
