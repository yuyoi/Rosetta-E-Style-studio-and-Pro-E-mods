import os
"""Fuller recursive disasm of IC7 bank N + IC4: vectors + jmp-tables (runs of >=4 '7E hi lo') + extra entries.
usage: python a2_dis_full.py <bank> <out.lst> [extra entry hex ...]"""
import sys, re, collections
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dumps') + '/'
ic7 = open(D + 'proe_ic7_R15179983_LH53234L_v2.00.bin', 'rb').read()
ic4 = open(D + 'proe_ic4_os_v2.00_051289_27c128.bin', 'rb').read()
bank = int(sys.argv[1]); out = sys.argv[2]
rom = ic7[bank * 0x8000:(bank + 1) * 0x8000] + ic4
BASE = 0x4000
def rd(a): return rom[a - BASE]
md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
W16 = {'ldd','ldx','ldy','lds','cpd','cpx','cpy','addd','subd'}
VEC = ['SCI','SPI','PAI','PAOV','TOF','TOC5','TOC4','TOC3','TOC2','TOC1','TIC3','TIC2','TIC1','RTI','IRQ','XIRQ','SWI','ILLOP','COP','CLKMON','RESET']
labels = collections.defaultdict(set)
ents = []
for i, n in enumerate(VEC):
    a = 0xFFD6 + 2 * i; t = (rd(a) << 8) | rd(a + 1); labels[t].add(n); ents.append(t)
for a in sys.argv[3:]:
    t = int(a, 16); labels[t].add('entry'); ents.append(t)
# jmp tables
tables = []
a = BASE
while a < 0xFFD0:
    n = 0
    while a + 3 * n + 2 < 0xFFD6 and rd(a + 3 * n) == 0x7E and 0x4000 <= ((rd(a + 3 * n + 1) << 8) | rd(a + 3 * n + 2)) < 0xFFD6:
        n += 1
    if n >= 4:
        tables.append((a, n))
        for k in range(n):
            labels[a + 3 * k].add('jtab'); ents.append(a + 3 * k)
        a += 3 * n
    else:
        a += 1
code = {}; ext = collections.Counter()
todo = list(ents)
STOP = {'rts', 'rti', 'jmp', 'bra', 'stop', 'wai', 'swi', 'test'}
while todo:
    a = todo.pop()
    while BASE <= a < 0xFFD6 and a not in code:
        ins = next(md.disasm(rom[a - BASE:a - BASE + 6], a), None)
        if ins is None: break
        code[a] = ins
        m = ins.mnemonic
        mt = re.search(r'\$([0-9a-f]{4})$', ins.op_str)
        is_br = (m.startswith('b') and m not in ('bit','bita','bitb','bset','bclr')) or m.startswith('brset') or m.startswith('brclr') or m in ('jsr','jmp','bsr','lbra')
        if is_br and mt and ',x' not in ins.op_str and ',y' not in ins.op_str:
            t = int(mt.group(1), 16)
            if BASE <= t < 0xFFD6:
                labels[t].add('sub' if m in ('jsr','bsr') else 'L'); todo.append(t)
            else: ext[(m, t)] += 1
        if m in STOP: break
        a += ins.size
def fmt(ins):
    mn = ins.mnemonic
    ops = re.sub(r'#(-?\d+)', lambda mm: ('#$%04X' % (int(mm.group(1)) & 0xFFFF)) if mn in W16 else ('#$%02X' % (int(mm.group(1)) & 0xFF)), ins.op_str)
    return f'{mn:6s} {ops}'
with open(out, 'w', encoding='utf-8') as f:
    f.write(f'; IC7 bank {bank} at $4000-$BFFF + IC4 at $C000; jmp tables: ' + ' '.join('$%04X x%d' % t for t in tables) + '\n')
    for a in sorted(code):
        if a in labels: f.write(f'\nL{a:04X}:  ; {",".join(sorted(labels[a]))}\n')
        f.write(f'  {a:04X}  {code[a].bytes.hex():10s} {fmt(code[a])}\n')
print('insns', len(code), 'bytes', sum(c.size for c in code.values()), 'tables', ['$%04X x%d' % t for t in tables])
print('ext', ext.most_common(10))
