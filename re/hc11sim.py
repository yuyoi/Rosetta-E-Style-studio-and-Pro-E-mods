"""Small 68HC11 simulator for unit-testing PRO-E patches (the instruction set the Rosetta code uses).

Decoding comes from hc11asm.TABLE (capstone's opcode map), so sizes and modes match the assembler.
Memory is a flat 64 KB array plus hooks:
  sim.read_hook[addr]  = fn() -> byte        (registers such as SCSR / SCDR)
  sim.write_hook[addr] = fn(byte)            (latches, PORTA)
  sim.stubs[addr]      = fn(sim)             (stock routines: run fn, then return as if by rts)
Unknown opcodes raise, so a test fails instead of running off into garbage.
"""
import hc11asm as A

DECODE = {}
for (mn, mode), (code, size) in A.TABLE.items():
    DECODE.setdefault(bytes(code), (mn, mode, size))


class Stop(Exception):
    pass


class Sim:
    def __init__(self):
        self.mem = bytearray(0x10000)
        self.read_hook, self.write_hook, self.stubs = {}, {}, {}
        self.a = self.b = 0
        self.x = self.y = 0
        self.sp = 0x00C7
        self.pc = 0
        self.n = self.z = self.v = self.c = 0
        self.i = 1
        self.stop_at = set()
        self.steps = 0

    # ---- memory ----
    def rd(self, a):
        a &= 0xFFFF
        if a in self.read_hook:
            return self.read_hook[a]() & 0xFF
        return self.mem[a]

    def wr(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if a in self.write_hook:
            self.write_hook[a](v)
        else:
            self.mem[a] = v

    def rd16(self, a):
        return self.rd(a) << 8 | self.rd(a + 1)

    def wr16(self, a, v):
        self.wr(a, v >> 8)
        self.wr(a + 1, v)

    def push(self, v):
        self.wr(self.sp, v)
        self.sp = (self.sp - 1) & 0xFFFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFFFF
        return self.rd(self.sp)

    def push16(self, v):
        self.push(v & 0xFF)
        self.push(v >> 8)

    def pull16(self):
        h = self.pull()
        return h << 8 | self.pull()

    @property
    def d(self):
        return self.a << 8 | self.b

    @d.setter
    def d(self, v):
        self.a, self.b = (v >> 8) & 0xFF, v & 0xFF

    # ---- flags ----
    def nz8(self, r):
        self.n, self.z = r >> 7 & 1, int(r & 0xFF == 0)

    def nz16(self, r):
        self.n, self.z = r >> 15 & 1, int(r & 0xFFFF == 0)

    def add8(self, x, y, c=0):
        r = x + y + c
        self.c = int(r > 0xFF)
        self.v = int(~(x ^ y) & (x ^ r) & 0x80 != 0)
        r &= 0xFF
        self.nz8(r)
        return r

    def sub8(self, x, y, c=0):
        r = x - y - c
        self.c = int(r < 0)
        self.v = int((x ^ y) & (x ^ r) & 0x80 != 0)
        r &= 0xFF
        self.nz8(r)
        return r

    def add16(self, x, y):
        r = x + y
        self.c = int(r > 0xFFFF)
        self.v = int(~(x ^ y) & (x ^ r) & 0x8000 != 0)
        r &= 0xFFFF
        self.nz16(r)
        return r

    def sub16(self, x, y):
        r = x - y
        self.c = int(r < 0)
        self.v = int((x ^ y) & (x ^ r) & 0x8000 != 0)
        r &= 0xFFFF
        self.nz16(r)
        return r

    def ccr(self):
        return (self.c | self.v << 1 | self.z << 2 | self.n << 3 | self.i << 4) | 0xC0

    def set_ccr(self, v):
        self.c, self.v, self.z, self.n, self.i = v & 1, v >> 1 & 1, v >> 2 & 1, v >> 3 & 1, v >> 4 & 1

    # ---- run ----
    def call(self, addr, ret=0xFFFE, limit=2_000_000):
        """jsr addr; run until it returns to `ret` (or hits a stop address)."""
        self.push16(ret)
        self.pc = addr
        return self.run(stop={ret} | self.stop_at, limit=limit)

    def run(self, stop, limit=2_000_000):
        n = 0
        while self.pc not in stop:
            if self.pc in self.stubs:
                self.stubs[self.pc](self)
                self.pc = self.pull16()
                continue
            self.step()
            n += 1
            if n > limit:
                raise Stop(f'step limit at ${self.pc:04X}')
        self.steps += n
        return self.pc

    def step(self):
        pc = self.pc
        op = bytes([self.rd(pc)])
        if op[0] in (0x18, 0x1A, 0xCD):
            op += bytes([self.rd(pc + 1)])
        if op not in DECODE:
            raise Stop(f'unknown opcode {op.hex()} at ${pc:04X}')
        mn, mode, size = DECODE[op]
        p = pc + len(op)
        self.pc = (pc + size) & 0xFFFF
        md, _, reg = mode.partition(':')
        ireg = self.y if reg == 'y' else self.x

        def ea():
            if md in ('dir', 'bit_dir', 'bit_dir_rel'):
                return self.rd(p)
            if md == 'ext':
                return self.rd16(p)
            if md in ('idx', 'bit_idx', 'bit_idx_rel'):
                return (ireg + self.rd(p)) & 0xFFFF
            raise Stop(f'no ea for {mn} {mode}')

        def opnd8():
            return self.rd(p) if md == 'imm8' else self.rd(ea())

        def opnd16():
            if md == 'imm16':
                return self.rd16(p)
            return self.rd16(ea())

        def rel(off_at):
            o = self.rd(off_at)
            return (self.pc + (o - 256 if o > 127 else o)) & 0xFFFF

        R8 = {'a': 'a', 'b': 'b'}
        # loads / stores
        if mn in ('ldaa', 'ldab'):
            v = opnd8(); setattr(self, mn[-1], v); self.nz8(v); self.v = 0
        elif mn in ('ldd', 'ldx', 'ldy', 'lds'):
            v = opnd16(); setattr(self, {'ldd': 'd', 'ldx': 'x', 'ldy': 'y', 'lds': 'sp'}[mn], v); self.nz16(v); self.v = 0
        elif mn in ('staa', 'stab'):
            v = getattr(self, mn[-1]); self.wr(ea(), v); self.nz8(v); self.v = 0
        elif mn in ('std', 'stx', 'sty', 'sts'):
            v = getattr(self, {'std': 'd', 'stx': 'x', 'sty': 'y', 'sts': 'sp'}[mn]); self.wr16(ea(), v); self.nz16(v); self.v = 0
        # arithmetic
        elif mn in ('adda', 'addb', 'adca', 'adcb'):
            r = mn[-1]; setattr(self, r, self.add8(getattr(self, r), opnd8(), self.c if mn.startswith('adc') else 0))
        elif mn in ('suba', 'subb', 'sbca', 'sbcb'):
            r = mn[-1]; setattr(self, r, self.sub8(getattr(self, r), opnd8(), self.c if mn.startswith('sbc') else 0))
        elif mn in ('cmpa', 'cmpb'):
            self.sub8(getattr(self, mn[-1]), opnd8())
        elif mn == 'addd':
            self.d = self.add16(self.d, opnd16())
        elif mn == 'subd':
            self.d = self.sub16(self.d, opnd16())
        elif mn in ('cpx', 'cpy', 'cpd'):
            self.sub16({'cpx': self.x, 'cpy': self.y, 'cpd': self.d}[mn], opnd16())
        elif mn in ('anda', 'andb', 'oraa', 'orab', 'eora', 'eorb', 'bita', 'bitb'):
            r = mn[-1]; x, y = getattr(self, r), opnd8()
            v = {'and': x & y, 'ora': x | y, 'eor': x ^ y, 'bit': x & y}[mn[:3]]
            if not mn.startswith('bit'):
                setattr(self, r, v)
            self.nz8(v); self.v = 0
        elif mn == 'aba':
            self.a = self.add8(self.a, self.b)
        elif mn == 'cba':
            self.sub8(self.a, self.b)
        elif mn == 'sba':
            self.a = self.sub8(self.a, self.b)
        elif mn == 'abx':
            self.x = (self.x + self.b) & 0xFFFF
        elif mn == 'aby':
            self.y = (self.y + self.b) & 0xFFFF
        elif mn == 'mul':
            self.d = self.a * self.b; self.c = self.b >> 7 & 1
        elif mn == 'idiv':
            if self.x == 0:
                self.x, self.c = 0xFFFF, 1
            else:
                q, r = divmod(self.d, self.x); self.x, self.d, self.c = q, r, 0
            self.z = int(self.x == 0); self.v = 0
        # single-operand (register and memory)
        elif mn[:-1] in ('clr', 'inc', 'dec', 'tst', 'neg', 'com', 'lsr', 'lsl', 'asl', 'asr', 'rol', 'ror') and mn[-1] in 'ab' \
                or mn in ('clr', 'inc', 'dec', 'tst', 'neg', 'com', 'lsr', 'lsl', 'asl', 'asr', 'rol', 'ror'):
            if mn[-1] in 'ab' and md == 'inh':
                base, get, put = mn[:-1], (lambda r=mn[-1]: getattr(self, r)), (lambda v, r=mn[-1]: setattr(self, r, v & 0xFF))
            else:
                e = ea(); base, get, put = mn, (lambda e=e: self.rd(e)), (lambda v, e=e: self.wr(e, v))
            x = get()
            if base == 'clr':
                put(0); self.n, self.z, self.v, self.c = 0, 1, 0, 0
            elif base == 'inc':
                r = (x + 1) & 0xFF; put(r); self.nz8(r); self.v = int(x == 0x7F)
            elif base == 'dec':
                r = (x - 1) & 0xFF; put(r); self.nz8(r); self.v = int(x == 0x80)
            elif base == 'tst':
                self.nz8(x); self.v = self.c = 0
            elif base == 'neg':
                r = (-x) & 0xFF; put(r); self.nz8(r); self.v = int(r == 0x80); self.c = int(r != 0)
            elif base == 'com':
                r = x ^ 0xFF; put(r); self.nz8(r); self.v = 0; self.c = 1
            elif base == 'lsr':
                self.c = x & 1; r = x >> 1; put(r); self.nz8(r); self.v = self.c
            elif base in ('lsl', 'asl'):
                self.c = x >> 7; r = (x << 1) & 0xFF; put(r); self.nz8(r); self.v = self.n ^ self.c
            elif base == 'asr':
                self.c = x & 1; r = (x >> 1) | (x & 0x80); put(r); self.nz8(r); self.v = self.n ^ self.c
            elif base == 'rol':
                r = ((x << 1) | self.c) & 0xFF; self.c = x >> 7; put(r); self.nz8(r); self.v = self.n ^ self.c
            elif base == 'ror':
                r = (x >> 1) | (self.c << 7); self.c = x & 1; put(r); self.nz8(r); self.v = self.n ^ self.c
        elif mn in ('asld', 'lsld'):
            v = self.d; self.c = v >> 15; v = (v << 1) & 0xFFFF; self.d = v; self.nz16(v); self.v = self.n ^ self.c
        elif mn == 'lsrd':
            v = self.d; self.c = v & 1; v >>= 1; self.d = v; self.nz16(v); self.v = self.c
        elif mn in ('inx', 'dex', 'iny', 'dey'):
            r = 'x' if mn[-1] == 'x' else 'y'
            v = (getattr(self, r) + (1 if mn[0] == 'i' else -1)) & 0xFFFF; setattr(self, r, v); self.z = int(v == 0)
        elif mn in ('ins', 'des'):
            self.sp = (self.sp + (1 if mn == 'ins' else -1)) & 0xFFFF
        # transfers / stack
        elif mn == 'tab':
            self.b = self.a; self.nz8(self.b); self.v = 0
        elif mn == 'tba':
            self.a = self.b; self.nz8(self.a); self.v = 0
        elif mn == 'xgdx':
            self.d, self.x = self.x, self.d
        elif mn == 'xgdy':
            self.d, self.y = self.y, self.d
        elif mn == 'tsx':
            self.x = (self.sp + 1) & 0xFFFF
        elif mn == 'tsy':
            self.y = (self.sp + 1) & 0xFFFF
        elif mn == 'txs':
            self.sp = (self.x - 1) & 0xFFFF
        elif mn == 'tpa':
            self.a = self.ccr()
        elif mn == 'tap':
            self.set_ccr(self.a)
        elif mn in ('psha', 'pshb'):
            self.push(getattr(self, mn[-1]))
        elif mn in ('pula', 'pulb'):
            setattr(self, mn[-1], self.pull())
        elif mn in ('pshx', 'pshy'):
            self.push16(getattr(self, mn[-1]))
        elif mn in ('pulx', 'puly'):
            setattr(self, mn[-1], self.pull16())
        elif mn in ('sec', 'clc', 'sei', 'cli', 'sev', 'clv'):
            setattr(self, mn[-1], int(mn[0] == 's'))
        elif mn == 'nop':
            pass
        # flow
        elif mn == 'jsr':
            t = ea(); self.push16(self.pc); self.pc = t
        elif mn == 'bsr':
            t = rel(p); self.push16(self.pc); self.pc = t
        elif mn == 'jmp':
            self.pc = ea()
        elif mn == 'rts':
            self.pc = self.pull16()
        elif mn in A.BRANCHES:
            c, z, n, v = self.c, self.z, self.n, self.v
            take = {'bra': 1, 'brn': 0, 'beq': z, 'bne': not z, 'bcc': not c, 'bhs': not c, 'bcs': c, 'blo': c,
                    'bpl': not n, 'bmi': n, 'bvc': not v, 'bvs': v, 'bhi': not (c or z), 'bls': c or z,
                    'bge': not (n ^ v), 'blt': n ^ v, 'bgt': not (z or (n ^ v)), 'ble': z or (n ^ v)}[mn]
            if take:
                self.pc = rel(p)
        elif mn in ('bset', 'bclr'):
            e = ea(); m = self.rd(p + 1)
            r = self.rd(e) | m if mn == 'bset' else self.rd(e) & ~m & 0xFF
            self.wr(e, r); self.nz8(r); self.v = 0
        elif mn in ('brset', 'brclr'):
            e = ea(); m = self.rd(p + 1); x = self.rd(e)
            if (x & m == m) if mn == 'brset' else (x & m == 0):
                self.pc = rel(p + 2)
        else:
            raise Stop(f'unhandled {mn} {mode} at ${pc:04X}')
