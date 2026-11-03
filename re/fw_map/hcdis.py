"""Linear 68HC11 disassembly of a 48 KB $4000-$FFFF image (bank N + IC4), hex immediates.
usage: python dis.py ADDR COUNT [bank]   (bank default 0)"""
import sys, re, os
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', '..', 'dumps')
ic7 = open(os.path.join(D, 'proe_ic7_R15179983_LH53234L_v2.00.bin'), 'rb').read()
ic4 = open(os.path.join(D, 'proe_ic4_os_v2.00_051289_27c128.bin'), 'rb').read()
bank = int(sys.argv[3]) if len(sys.argv) > 3 else 0
img = ic7[bank * 0x8000:(bank + 1) * 0x8000] + ic4
md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
W16 = {'ldx','ldy','ldd','lds','cpx','cpy','cpd','addd','subd'}
a = int(sys.argv[1], 16); n = int(sys.argv[2])
while n > 0 and a < 0x10000:
    ins = next(md.disasm(img[a - 0x4000:a - 0x4000 + 6], a), None)
    if ins is None:
        print(f'  {a:04X}  {img[a-0x4000]:02x}         db'); a += 1; n -= 1; continue
    ops = ins.op_str
    ops = re.sub(r'#(-?\d+)', lambda x: ('#$%04X' if ins.mnemonic in W16 else '#$%02X') % (int(x.group(1)) & (0xFFFF if ins.mnemonic in W16 else 0xFF)), ops)
    ops = re.sub(r'(?<![\$\w])(-?\d+), ([xy])', lambda x: '$%02X,%s' % (int(x.group(1)) & 0xFF, x.group(2)), ops)
    print(f'  {a:04X}  {ins.bytes.hex():10s} {ins.mnemonic:6s} {ops}')
    a += ins.size; n -= 1
