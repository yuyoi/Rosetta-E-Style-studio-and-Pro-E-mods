"""PA6 -> IC7 pin 31 (A18) mod test: v0.3b IC4 that flips PA6 during the boot banner.

  python -I build_pa6test.py   -> ../build/IC4_pa6test_W27C512.bin

Use with the halftest IC7 (LOWER/UPPER banners). The stock banner wait at $C199 (ldy #5 / jsr $ED35) becomes
jsr FLIP: 6 x (wait, toggle PA6, redraw the banner from IC7). A working mod shows
LOWER -> UPPER -> LOWER -> UPPER -> LOWER -> UPPER -> LOWER, then a normal boot with PA6 low (stock state).
Interrupts are not on yet at that point ($C236 sets TMSK1 later), so nothing else touches PORTA meanwhile.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc11asm as A

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, '..', 'build')
ic4 = bytearray(open(os.path.join(BUILD, 'IC4_v0.3b_W27C512.bin'), 'rb').read()[:0x4000])

segs, _ = A.assemble('''
        org $FFB1
FLIP:   ldab #6
fl_lp:  pshb
        ldy #5
        jsr $ED35               ; stock banner wait
        ldaa $1000
        eora #$40               ; toggle PA6 = IC7 A18
        staa $1000
        jsr $D5AB               ; redraw both lines from $59E1 / $59F1 (now read from the other half)
        pulb
        decb
        bne fl_lp
        rts                     ; even count: PA6 is low again, like stock
''')
flip = bytes(segs[0xFFB1])
assert len(flip) <= 37, len(flip)


def patch(addr, old, new, what):
    o = addr - 0xC000
    if bytes(ic4[o:o + len(old)]) != old:
        sys.exit(f'{what}: ${addr:04X} is {bytes(ic4[o:o + len(old)]).hex()}, expected {old.hex()}')
    ic4[o:o + len(new)] = new
    print(f'  patched ${addr:04X} {what}: {old.hex()} -> {new.hex()}')


patch(0xC199, bytes.fromhex('18ce0005bded35'), bytes.fromhex('bdffb1') + b'\x01' * 4, 'banner wait -> FLIP')
patch(0xFFB1, b'\xff' * len(flip), flip, 'FLIP')
for a, mn, ops, raw in A.disasm(flip, 0xFFB1):
    print(f'   {a:04X} {raw.hex():10s} {mn:6s} {ops}')
data = bytes(ic4) * 4
p = os.path.join(BUILD, 'IC4_pa6test_W27C512.bin')
open(p + '.tmp', 'wb').write(data)
os.replace(p + '.tmp', p)
print(f'IC4_pa6test_W27C512.bin  md5 {hashlib.md5(data).hexdigest()}')
