"""A3_link_tables.py - dump the HC11 -> CK-34 link tables straight from the ROM image, as evidence
for A3_hc11_midi_and_ck34_link.md.

usage: python -I A3_link_tables.py [map_bank0.bin]
(map_bank0.bin = IC7 bank 0 + IC4 as one 48 KB image at $4000-$FFFF)
Read-only: prints only.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'map_bank0.bin')
d = open(IMG, 'rb').read()
assert len(d) == 0xC000, 'expected the 48 KB bank0+IC4 image'


def b(a):
    return d[a - 0x4000]


def imm(a, op):
    """byte after opcode `op` at address a (checks the opcode so a wrong address fails loudly)"""
    assert b(a) == op, f'${a:04X}: expected opcode {op:02X}, found {b(a):02X}'
    return b(a + 1)


PARTS = ['SOLO', 'LOWER', 'ACCOMP1', 'ACCOMP2', 'ACCOMP3', 'A.BASS', 'M.BASS', 'DRUMS', 'EFFECT',
         'RX ONLY', 'NOTE>ARR', '(11)']

print('== CK-34 note-on senders (ldaa #$9n inside each routine) ==')
for entry, at, gate in [(0xEBF1, 0xEBF3, 0x2400), (0xEC15, 0xEC17, 0x2401), (0xEC1E, 0xEC20, 0x2403),
                        (0xEC27, 0xEC29, 0x2402), (0xEC30, 0xEC32, 0x2406), (0xEC39, 0xEC3B, 0x2407),
                        (0xEC42, 0xEC44, 0x2408), (0xEC4B, 0xEC5F, 0x2404), (0xEC66, 0xEC76, None),
                        (0xEC7A, 0xEC8E, 0x2405), (0xEC96, 0xEC98, None)]:
    st = imm(at, 0x86)
    print(f'  ${entry:04X}: status ${st:02X} = note-on ch{(st & 15) + 1:2d}   gate/level byte {"$%04X" % gate if gate else "-"}')

print('== CK-34 program-change senders ==')
for entry, at, cache in [(0xEAEA, 0xEAFB, 0x2680), (0xEB27, 0xEB38, 0x267F), (0xEB3D, 0xEB4E, 0x267A),
                         (0xEB52, 0xEB5A, 0x267E), (0xEB65, 0xEB6D, 0x267D), (0xEB79, 0xEB81, 0x267C),
                         (0xEB8D, 0xEB95, 0x267B), (0xEADE, 0xEAE6, 0x2D66)]:
    st = imm(at, 0x86)
    print(f'  ${entry:04X}: ${st:02X} = PC ch{(st & 15) + 1:2d}  (last-program cache ${cache:04X})')

print('== CK-34 control-change senders (A=value, B=controller) ==')
for entry, at in [(0x4834, 0x4848), (0x4860, 0x4874), (0x4878, 0x488C), (0x4890, 0x4892), (0x4896, 0x4898),
                  (0x489C, 0x489E), (0x48A2, 0x48A4), (0x48A8, 0x48AA), (0x481C, 0x4830)]:
    st = imm(at, 0x86)
    print(f'  ${entry:04X}: ${st:02X} = CC ch{(st & 15) + 1:2d}')

print('== CK-34 pitch-bend senders ==')
for entry, at in [(0x4923, 0x4925), (0x4935, 0x4937), (0x493B, 0x493D), (0x4941, 0x4943), (0x4947, 0x4949),
                  (0x494D, 0x494F), (0x4953, 0x4955), (0x4959, 0x495B), (0x495F, 0x4961)]:
    st = imm(at, 0x86)
    print(f'  ${entry:04X}: ${st:02X} = PB ch{(st & 15) + 1:2d}')

print('== default part MIDI channels $243F-$244A (ROM $A40E..) bit7 = on ==')
for i in range(12):
    v = b(0xA3CF + 0x3F + i)
    print(f'  ${0x243F + i:04X} {PARTS[i]:9s} ${v:02X} -> {"on " if v & 0x80 else "off"} ch{(v & 15) + 1}')

print('== default part levels/tones ($2400-$240B from ROM $A3CF) ==')
print('  ' + ' '.join(f'{b(0xA3CF + i):02X}' for i in range(12)))

print('== MT-32 DT1 header used for the link ($53B2, $FF-terminated) ==')
a = 0x53B2
hdr = []
while b(a) != 0xFF:
    hdr.append(b(a))
    a += 1
print('  ' + ' '.join(f'{x:02X}' for x in hdr))
print('  bender-range table $53B8:', ' '.join(f'{b(0x53B8 + i):02X}' for i in range(8)))
print('  part address-low table $53C0 (SOLO,LOWER,M.BASS):', ' '.join(f'{b(0x53C0 + i):02X}' for i in range(3)))
print('  reverb mode<<4|time $53C6:', ' '.join(f'{b(0x53C6 + i):02X}' for i in range(8)))
print('  reverb level $53CE:', ' '.join(f'{b(0x53CE + i):02X}' for i in range(8)))

print('== tone volume trim $A601 (signed %, added to the part level before CC7) ==')
trim = [x - 256 if x > 127 else x for x in d[0xA601 - 0x4000:0xA601 - 0x4000 + 128]]
for i in range(0, 128, 16):
    print(f'  {i:3d}: ' + ' '.join(f'{t:4d}' for t in trim[i:i + 16]))


def cs(bs):
    return (-sum(bs)) & 0x7F


def cc7(level, tone=None):
    v = level + (trim[tone] if tone is not None else 0)
    return max(v, 0) * 127 // 100


print('== boot stream to the CK-34 as the code queues it (defaults, before the 20 ms SysEx tasks) ==')
pr = [0x10, 0x00, 0x04, 4, 4, 4, 0, 0, 4, 4, 0, 0x0C]
lvl = [b(0xA3CF + i) & 0x7F for i in range(9)]
tone = [b(0xA3CF + 9 + i) for i in range(3)]
s = hdr + pr + [cs(pr), 0xF7]
s += [0xB4, 7, cc7(lvl[2]), 0xB5, 7, cc7(lvl[6]), 0xB6, 7, cc7(lvl[7]), 0xB7, 7, cc7(lvl[8]), 0xB9, 7, cc7(100)]
for st in (0xB3, 0xB2, 0xB1, 0xB7, 0xB4, 0xB5, 0xB6, 0xB9, 0xB8):
    s += [st, 0x0A, 0x40]
s += [0xC3, tone[0], 0xB3, 7, cc7(lvl[0], tone[0])]
s += [0xC2, tone[1], 0xB2, 7, cc7(lvl[1], tone[1])]
s += [0xC1, tone[2], 0xB1, 7, cc7(lvl[3], tone[2])]
s += [0xC8, 3, 0xB8, 7, cc7(100, 3)]
print('  ' + ' '.join(f'{x:02X}' for x in s))
print('  (every status byte differs from the previous one here, so running status drops nothing)')
for nm, msg in [('bender SOLO', [3, 0, 0x24, b(0x53B8 + (b(0xA3CF + 0x4B) & 7))]),
                ('bender LOWER', [3, 0, 0x14, b(0x53B8 + (b(0xA3CF + 0x4B) & 7))]),
                ('bender M.BASS', [3, 0, 0x04, b(0x53B8 + (b(0xA3CF + 0x4B) & 7))])]:
    print(f'  {nm}: ' + ' '.join(f'{x:02X}' for x in hdr + msg + [cs(msg), 0xF7]))
rt = (b(0xA3CF + 0x4D) & 0x3F) >> 3
rv = [0x10, 0, 1, b(0x53C6 + rt) >> 4, b(0x53C6 + rt) & 15, b(0x53CE + rt)]
print(f'  reverb (type idx {rt}): ' + ' '.join(f'{x:02X}' for x in hdr + rv + [cs(rv), 0xF7]))
