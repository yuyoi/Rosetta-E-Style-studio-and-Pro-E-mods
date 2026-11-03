import os
"""Recursive 68HC11 disassembler from given entry points, hex immediates.
usage: python a2_dis_entry.py <bank 0-7> <out.lst> <entry hex> [entry hex ...]
Image = IC7 bank N (32 KB at $4000) + IC4 (16 KB at $C000). Only follows code inside $4000-$BFFF
(this bank) unless --ic4 given; IC4 targets are only noted as calls."""
import sys, re, collections
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dumps') + '/'
ic7 = open(D + 'proe_ic7_R15179983_LH53234L_v2.00.bin', 'rb').read()
ic4 = open(D + 'proe_ic4_os_v2.00_051289_27c128.bin', 'rb').read()
bank = int(sys.argv[1]); out = sys.argv[2]
follow_ic4 = '--ic4' in sys.argv
ents = [int(a, 16) for a in sys.argv[3:] if not a.startswith('--')]
rom = ic7[bank * 0x8000:(bank + 1) * 0x8000] + ic4
BASE = 0x4000
md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
W16 = {'ldd','ldx','ldy','lds','cpd','cpx','cpy','addd','subd'}
code = {}; labels = collections.defaultdict(set); ext = collections.Counter()
for e in ents: labels[e].add('entry')
todo = list(ents)
STOP = {'rts', 'rti', 'jmp', 'bra', 'stop', 'wai', 'swi', 'test'}
lim = 0x10000 if follow_ic4 else 0xC000
while todo:
    a = todo.pop()
    while BASE <= a < lim and a not in code:
        ins = next(md.disasm(rom[a - BASE:a - BASE + 6], a), None)
        if ins is None: break
        code[a] = ins
        m = ins.mnemonic
        mt = re.search(r'\$([0-9a-f]{4})$', ins.op_str)
        is_br = (m.startswith('b') and m not in ('bit','bita','bitb','bset','bclr')) or m.startswith('brset') or m.startswith('brclr') or m in ('jsr','jmp','bsr','lbra')
        if is_br and mt and ',x' not in ins.op_str and ',y' not in ins.op_str:
            t = int(mt.group(1), 16)
            if BASE <= t < lim:
                labels[t].add('sub' if m in ('jsr','bsr') else 'L'); todo.append(t)
            else:
                ext[(m, t)] += 1
        if m in STOP: break
        a += ins.size
def fmt(ins):
    mn = ins.mnemonic
    ops = re.sub(r'#(-?\d+)', lambda mm: ('#$%04X' % (int(mm.group(1)) & 0xFFFF)) if mn in W16 else ('#$%02X' % (int(mm.group(1)) & 0xFF)), ins.op_str)
    return f'{mn:6s} {ops}'
with open(out, 'w', encoding='utf-8') as f:
    f.write(f'; IC7 bank {bank} at $4000-$BFFF + IC4; entries {" ".join("$%04X"%e for e in ents)}\n')
    for a in sorted(code):
        if a in labels: f.write(f'\nL{a:04X}:  ; {",".join(sorted(labels[a]))}\n')
        f.write(f'  {a:04X}  {code[a].bytes.hex():10s} {fmt(code[a])}\n')
print('insns', len(code), 'ext calls', len(ext))
print(sorted(set('%s $%04X' % k for k in ext))[:80])
