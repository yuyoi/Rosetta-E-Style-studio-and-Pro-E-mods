"""hc11x.py - 68HC11 disassembler for the PRO-E (IC7 bank N + IC4 as one 48 KB image at $4000).

Improvements over ../hc11dis.py: hex immediates, HC11 register + PRO-E I/O names, xrefs (code and data),
linear dump of any range, RAM access tally.

usage:
  python -I hc11x.py full  <img48k> <out.lst> [entry_hex ...] [-target_hex ...]  recursive listing with xrefs
                          (-XXXX = never follow a jump to XXXX, e.g. bank-1 entry points seen from bank 0)
  python -I hc11x.py at    <img48k> <addr_hex> <n_insns>               linear dump
  python -I hc11x.py xref  <img48k> <addr_hex> [addr_hex ...]          who touches these addresses
  python -I hc11x.py ram   <img48k> <out.txt> [same entry args]        RAM/IO access tally
  python -I hc11x.py ff    <img48k>                                    runs of $FF / $00 >= 32 bytes
"""
import sys, re, collections
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811

REG = {0x00: 'PORTA', 0x02: 'PIOC', 0x03: 'PORTC', 0x04: 'PORTB', 0x05: 'PORTCL', 0x07: 'DDRC', 0x08: 'PORTD',
       0x09: 'DDRD', 0x0A: 'PORTE', 0x0B: 'CFORC', 0x0C: 'OC1M', 0x0D: 'OC1D', 0x0E: 'TCNT', 0x0F: 'TCNT+1',
       0x10: 'TIC1', 0x12: 'TIC2', 0x14: 'TIC3', 0x16: 'TOC1', 0x17: 'TOC1+1', 0x18: 'TOC2', 0x19: 'TOC2+1',
       0x1A: 'TOC3', 0x1B: 'TOC3+1', 0x1C: 'TOC4', 0x1D: 'TOC4+1', 0x1E: 'TOC5', 0x20: 'TCTL1', 0x21: 'TCTL2',
       0x22: 'TMSK1', 0x23: 'TFLG1', 0x24: 'TMSK2', 0x25: 'TFLG2', 0x26: 'PACTL', 0x27: 'PACNT', 0x28: 'SPCR',
       0x29: 'SPSR', 0x2A: 'SPDR', 0x2B: 'BAUD', 0x2C: 'SCCR1', 0x2D: 'SCCR2', 0x2E: 'SCSR', 0x2F: 'SCDR',
       0x30: 'ADCTL', 0x31: 'ADR1', 0x32: 'ADR2', 0x33: 'ADR3', 0x34: 'ADR4', 0x39: 'OPTION', 0x3A: 'COPRST',
       0x3B: 'PPROG', 0x3C: 'HPRIO', 0x3D: 'INIT', 0x3E: 'TEST1', 0x3F: 'CONFIG'}
IO = {0x1200: 'SWMATRIX', 0x1400: 'ACIA_CR/SR', 0x1401: 'ACIA_DATA', 0x160D: 'LCD_?D', 0x160E: 'LCD_?E',
      0x180D: 'GA_BANK', 0x180E: 'GA_180E'}

md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
VEC = ['SCI', 'SPI', 'PAI', 'PAOV', 'TOF', 'TOC5', 'TOC4', 'TOC3', 'TOC2', 'TOC1',
       'TIC3', 'TIC2', 'TIC1', 'RTI', 'IRQ', 'XIRQ', 'SWI', 'ILLOP', 'COP', 'CLKMON', 'RESET']
IMM16 = {'ldd', 'ldx', 'ldy', 'lds', 'cpd', 'cpx', 'cpy', 'addd', 'subd'}


class Img:
    def __init__(self, path):
        self.rom = open(path, 'rb').read()
        self.base = 0x10000 - len(self.rom)

    def rd(self, a):
        return self.rom[a - self.base] if self.base <= a < 0x10000 else None

    def w(self, a):
        return (self.rd(a) << 8) | self.rd(a + 1)

    def dis(self, a):
        if not (self.base <= a < 0x10000):
            return None
        return next(md.disasm(self.rom[a - self.base:a - self.base + 6], a), None)


def name(a):
    if 0x1000 <= a < 0x1040:
        return REG.get(a - 0x1000, f'REG{a-0x1000:02X}')
    return IO.get(a)


def fmt(ins):
    m, op = ins.mnemonic, ins.op_str

    def imm(mt):
        v = int(mt.group(1))
        if m in IMM16:
            return f'#${v & 0xFFFF:04X}'
        return f'#${v & 0xFF:02X}'
    op = re.sub(r'#(-?\d+)', imm, op)
    # indexed offsets in decimal -> hex
    op = re.sub(r'\b(\d+), ([xy])\b', lambda mt: f'${int(mt.group(1)):02X},{mt.group(2)}', op)
    cm = ''
    for mt in re.finditer(r'\$([0-9a-f]{2,4})\b', op):
        h = mt.group(1)
        a = int(h, 16)
        if len(h) == 4:
            n = name(a)
            if n:
                cm = n
    return f'{m:6s} {op}', cm


def target(ins):
    mt = re.findall(r'\$([0-9a-f]{4})\b', ins.op_str)
    return int(mt[-1], 16) if mt else None


def operand_addr(ins):
    """data address referenced (direct or extended), or None"""
    op = ins.op_str
    if op.startswith('#') or ',' in op and (', x' in op or ', y' in op) and '$' not in op.split(',')[0]:
        pass
    mt = re.match(r'\$([0-9a-f]{2,4})\b', op)
    if mt and not op.startswith('#'):
        return int(mt.group(1), 16)
    return None


BRANCH = lambda m: (m.startswith('b') and m not in ('bit', 'bita', 'bitb', 'bset', 'bclr')) or m.startswith('brset') \
    or m.startswith('brclr') or m in ('jsr', 'jmp', 'bsr')
STOP = {'rts', 'rti', 'jmp', 'bra', 'stop', 'wai', 'swi', 'test'}


def recurse(img, extra=(), nofollow=()):
    vectors = {n: img.w(0xFFD6 + 2 * i) for i, n in enumerate(VEC)}
    code = {}
    labels = collections.defaultdict(set)
    xref = collections.defaultdict(list)       # target -> [(from, mnem)]
    for n, a in vectors.items():
        labels[a].add(n)
    todo = list(set(vectors.values())) + list(extra)
    # jump tables: runs of >= 3 consecutive 'jmp $xxxx' (7E hi lo) -> every entry is code
    jt = []
    a = img.base
    while a < 0xFFD0:
        n = 0
        while img.rd(a + 3 * n) == 0x7E and 0x4000 <= img.w(a + 3 * n + 1) < 0xFFD6:
            n += 1
        if n >= 3:
            jt.extend(a + 3 * i for i in range(n))
            a += 3 * n
        else:
            a += 1
    for e in jt:
        labels[e].add('jt')
    todo += jt
    for e in extra:
        labels[e].add('entry')
    while todo:
        a = todo.pop()
        while img.base <= a < 0xFFD6 and a not in code:
            ins = img.dis(a)
            if ins is None:
                break
            code[a] = ins
            m = ins.mnemonic
            if BRANCH(m):
                t = target(ins)
                if t is not None:
                    xref[t].append((a, m))
                    if img.base <= t < 0x10000 and t not in nofollow:
                        labels[t].add('sub' if m in ('jsr', 'bsr') else 'L')
                        todo.append(t)
                    elif t in nofollow:
                        labels[t].add('OTHER-BANK')
            else:
                d = operand_addr(ins)
                if d is not None:
                    xref[d].append((a, m))
                for mt in re.finditer(r'#(-?\d+)', ins.op_str):
                    if m in IMM16:
                        v = int(mt.group(1)) & 0xFFFF
                        xref[v].append((a, m + '#'))
            if m in STOP:
                break
            a += ins.size
    return vectors, code, labels, xref


def main():
    mode = sys.argv[1]
    img = Img(sys.argv[2])
    if mode == 'at':
        a = int(sys.argv[3], 16)
        n = int(sys.argv[4])
        for _ in range(n):
            ins = img.dis(a)
            if ins is None:
                print(f'  {a:04X}  {img.rd(a):02x}         db'); a += 1; continue
            s, cm = fmt(ins)
            print(f'  {a:04X}  {ins.bytes.hex():10s} {s:28s} {";" + cm if cm else ""}')
            a += ins.size
        return
    extra, nofollow = [], set()
    args = sys.argv[4:] if mode in ('full', 'ram') else []
    for x in args:
        (nofollow.add(int(x[1:], 16)) if x.startswith('-') else extra.append(int(x, 16)))
    vectors, code, labels, xref = recurse(img, extra, nofollow)
    if mode == 'full':
        with open(sys.argv[3], 'w', encoding='utf-8') as f:
            f.write('; vectors\n')
            for n, a in vectors.items():
                f.write(f';  {n:7s} ${a:04X}\n')
            prev_end = None
            for a in sorted(code):
                ins = code[a]
                if prev_end is not None and a != prev_end:
                    f.write(f'  ; ---- gap ${prev_end:04X}-${a-1:04X} ({a-prev_end} bytes not reached)\n')
                if a in labels:
                    xr = xref.get(a, [])
                    xs = ' '.join(f'{fa:04X}' for fa, _ in xr[:12]) + (' ...' if len(xr) > 12 else '')
                    f.write(f'\nL{a:04X}:  ; {",".join(sorted(labels[a]))}  <- {xs}\n')
                s, cm = fmt(ins)
                f.write(f'  {a:04X}  {ins.bytes.hex():10s} {s:28s} {";" + cm if cm else ""}\n')
                prev_end = a + ins.size
        print('insns', len(code), 'bytes', sum(i.size for i in code.values()))
    elif mode == 'xref':
        for h in sys.argv[3:]:
            t = int(h, 16)
            print(f'${t:04X}:', ' '.join(f'{fa:04X}:{m}' for fa, m in sorted(xref.get(t, []))))
    elif mode == 'ram':
        with open(sys.argv[3], 'w', encoding='utf-8') as f:
            for t in sorted(xref):
                if t < 0x4000:
                    rs = xref[t]
                    f.write(f'${t:04X} {len(rs):4d}  ' + ' '.join(f'{fa:04X}:{m}' for fa, m in sorted(rs)[:24]) + '\n')
    elif mode == 'ff':
        for fill in (0xFF, 0x00):
            a = img.base
            while a < 0x10000:
                if img.rd(a) == fill:
                    b = a
                    while b < 0x10000 and img.rd(b) == fill:
                        b += 1
                    if b - a >= 32:
                        print(f'fill ${fill:02X}: ${a:04X}-${b-1:04X}  {b-a} bytes')
                    a = b
                else:
                    a += 1


if __name__ == '__main__':
    main()
