"""Recursive-descent 68HC11 disassembler for the Pro-E IC4 dump (mapped at $C000)."""
import sys, re, collections
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811

rom = open(sys.argv[1], 'rb').read()
out = sys.argv[2]
BASE = 0x10000 - len(rom)
md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)

VEC = ['SCI', 'SPI', 'PAI', 'PAOV', 'TOF', 'TOC5', 'TOC4', 'TOC3', 'TOC2', 'TOC1',
       'TIC3', 'TIC2', 'TIC1', 'RTI', 'IRQ', 'XIRQ', 'SWI', 'ILLOP', 'COP', 'CLKMON', 'RESET']
vectors = {}
for i, name in enumerate(VEC):
    a = 0xFFD6 + 2 * i
    vectors[name] = (rom[a - BASE] << 8) | rom[a - BASE + 1]

def rd(a):
    return rom[a - BASE] if BASE <= a < 0x10000 else None

code = {}            # addr -> insn
labels = collections.defaultdict(set)
for n, a in vectors.items():
    labels[a].add(n)
todo = list(set(vectors.values()))
ext_refs = collections.Counter()
STOP = {'rts', 'rti', 'jmp', 'bra', 'stop', 'wai', 'swi', 'test'}
while todo:
    a = todo.pop()
    while BASE <= a < 0xFFD6 and a not in code:
        ins = next(md.disasm(rom[a - BASE:a - BASE + 6], a), None)
        if ins is None:
            break
        code[a] = ins
        m = ins.mnemonic
        tgt = None
        mt = re.search(r'\$([0-9a-f]{4})', ins.op_str)
        if mt:
            tgt = int(mt.group(1), 16)
        is_branch = m.startswith('b') and m not in ('bit', 'bita', 'bitb', 'bset', 'bclr') or m.startswith('brset') or m.startswith('brclr') or m in ('jsr', 'jmp', 'bsr', 'lbra')
        if is_branch and tgt is not None and ',x' not in ins.op_str and ',y' not in ins.op_str:
            if BASE <= tgt < 0x10000:
                labels[tgt].add('sub' if m in ('jsr', 'bsr') else 'L')
                todo.append(tgt)
            else:
                ext_refs[(m, tgt)] += 1
        if m in STOP:
            break
        a += ins.size

with open(out, 'w', encoding='utf-8') as f:
    f.write('; vectors\n')
    for n, a in vectors.items():
        f.write(f';  {n:7s} ${a:04X}\n')
    for a in sorted(code):
        ins = code[a]
        if a in labels:
            f.write(f'\nL{a:04X}:  ; {",".join(sorted(labels[a]))}\n')
        f.write(f'  {a:04X}  {ins.bytes.hex():10s} {ins.mnemonic:6s} {ins.op_str}\n')

covered = sum(code[a].size for a in code)
print('base', hex(BASE), 'insns', len(code), 'bytes covered', covered, 'of', len(rom))
print('vectors', {k: hex(v) for k, v in vectors.items()})
print('calls/jumps outside ROM', [(m, hex(t), c) for (m, t), c in ext_refs.most_common(30)])
