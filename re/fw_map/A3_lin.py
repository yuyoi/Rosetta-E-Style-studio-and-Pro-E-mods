"""A3_lin.py - linear 68HC11 disassembly with hex immediates (capstone M680X 6811).

usage: python -I A3_lin.py <48KB image at $4000> <addr_hex> <n_insns>
e.g.   python -I A3_lin.py ../map_bank0.bin E82E 20      (CK-34 link send routine)
"""
import re, sys
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811

W16 = {'ldx', 'ldy', 'ldd', 'lds', 'cpx', 'cpy', 'cpd', 'addd', 'subd'}


def fixops(mn, ops):
    ops = re.sub(r'#(-?\d+)', lambda m: ('#$%04X' if mn in W16 else '#$%02X') % (int(m.group(1)) & (0xFFFF if mn in W16 else 0xFF)), ops)
    ops = re.sub(r'(?<![\$\w])(\d+), ([xy])', lambda m: '$%02X,%s' % (int(m.group(1)), m.group(2)), ops)
    return re.sub(r'\$([0-9a-f]{2,4})\b', lambda m: '$' + m.group(1).upper(), ops)


rom = open(sys.argv[1], 'rb').read()
B = 0x10000 - len(rom)
a, n = int(sys.argv[2], 16), int(sys.argv[3])
md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
for _ in range(n):
    ins = next(md.disasm(rom[a - B:a - B + 6], a), None)
    if ins is None:
        print('  %04X  %02x         db' % (a, rom[a - B]))
        a += 1
        continue
    print('  %04X  %-10s %-6s %s' % (a, ins.bytes.hex(), ins.mnemonic, fixops(ins.mnemonic, ins.op_str)))
    a += ins.size
