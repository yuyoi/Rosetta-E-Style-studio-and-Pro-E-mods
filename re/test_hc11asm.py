"""Re-assemble the PRO-E OS (IC4 + IC7 bank 0) from capstone's disassembly and require identical bytes.

Walks every instruction the recursive tracer found, turns capstone's text into assembler syntax, assembles it at the
same address and compares. Run: python -I test_hc11asm.py
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc11asm as A

HERE = os.path.dirname(os.path.abspath(__file__))
img = open(os.path.join(HERE, 'map_bank0.bin'), 'rb').read()      # IC7 bank 0 + IC4 at $4000-$FFFF
BASE = 0x4000


def to_src(mn, ops):
    ops = ops.replace('; ', ', ')
    ops = re.sub(r'\s*,\s*', ',', ops)
    return f'{mn} {ops}'.strip()


addrs = set()
for line in open(os.path.join(HERE, 'bank0_ic4.lst'), encoding='utf-8'):
    m = re.match(r'^\s+([0-9A-F]{4})\s', line)
    if m:
        addrs.add(int(m.group(1), 16))

ok = bad = 0
fails = []
for a in sorted(addrs):
    ins = A.disasm(img[a - BASE:a - BASE + 6], a)
    if not ins:
        continue
    addr, mn, ops, raw = ins[0]
    src = f'org ${a:04X}\n' + to_src(mn, ops)
    try:
        segs, _ = A.assemble(src)
        got = bytes(segs[a])
    except A.AsmError as e:
        got = str(e).encode()
    if got == raw:
        ok += 1
    else:
        bad += 1
        if len(fails) < 15:
            fails.append(f'${a:04X} {to_src(mn, ops):28s} want {raw.hex()} got {got.hex() if isinstance(got, bytes) else got}')
print(f'{len(A.TABLE)} opcode forms in the table')
print(f're-assembled {ok} instructions identical, {bad} different')
for f in fails:
    print('  ', f)
# a few hand-written forms
segs, syms = A.assemble('''
org $C000
start: ldaa #$12
  ldd #$1234
  staa $1D
  staa >$1D
  staa $180D
  ldaa 5,x
  ldaa 7,y
  bset $59,#$10
  bclr 0,x,#$80
  brclr $5f,#$01,start
  brset 11,y,#4,next
next: bra start
  jsr far
  rts
far = $FC97
  db "AB", 0, -1
  dw start, $ABCD
''')
print('hand test:', segs[0xC000].hex())
for x in A.disasm(segs[0xC000][:40], 0xC000):
    print(f'   {x[0]:04X} {x[1]:6s} {x[2]}')
sys.exit(0 if bad == 0 else 1)
