"""Rewrite a capstone M680X listing so immediates/offsets are hex.
16-bit immediate for ldx/ldy/ldd/lds/cpx/cpy/cpd/addd/subd; others 8-bit."""
import sys, re
W16 = {'ldx','ldy','ldd','lds','cpx','cpy','cpd','addd','subd'}
def imm(m, mn):
    v = int(m.group(1))
    if mn in W16: return '#$%04X' % (v & 0xFFFF)
    return '#$%02X' % (v & 0xFF)
out = open(sys.argv[2], 'w', encoding='utf-8')
for l in open(sys.argv[1], encoding='utf-8'):
    m = re.match(r'^(\s+[0-9A-F]{4}\s+\S+\s+)(\w+)(\s+)(.*)$', l.rstrip('\n'))
    if m:
        mn, ops = m.group(2), m.group(4)
        ops = re.sub(r'#(-?\d+)', lambda x: imm(x, mn), ops)
        ops = re.sub(r'(?<![\$\w])(-?\d+), ([xy])', lambda x: '$%02X,%s' % (int(x.group(1)) & 0xFF, x.group(2)), ops)
        l = m.group(1) + mn + m.group(3) + ops + '\n'
    out.write(l)
