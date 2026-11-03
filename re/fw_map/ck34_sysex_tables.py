import os
#!/usr/bin/env python3
"""Print the CK-34 (IC28 v2.06) MIDI/SysEx tables straight from the ROM, so B2_ck34_midi_sysex.md can be re-checked.

  python -I ck34_sysex_tables.py [path/to/ck34_ic28_control_R15179974_CK-34_v2.06.bin]

File offset == CPU address for 0x1000-0x7FFF (8098 control ROM).
"""
import sys

ROM = sys.argv[1] if len(sys.argv) > 1 else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'dumps', 'ck34_ic28_control_R15179974_CK-34_v2.06.bin')
d = open(ROM, 'rb').read()
w = lambda a: d[a] | d[a + 1] << 8

print('== Channel-message jump table 0x2466 (index = (status & 0x70) >> 3) ==')
for i, name in enumerate(['8x note off', '9x note on', 'Ax poly AT', 'Bx control', 'Cx program',
                          'Dx chan AT', 'Ex bend', 'Fx']):
    print('  %-12s -> 0x%04x' % (name, w(0x2466 + 2 * i)))

print('\n== Control-change jump table 0x39de (CC -> handler, 0 = ignored) ==')
for cc in range(128):
    h = w(0x39de + 2 * cc)
    if h:
        print('  CC%-3d -> 0x%04x' % (cc, h))

print('\n== SysEx command table 0x45ea / dispatch 0x45c0 ==')
names = {0x42: 'DAT', 0x40: 'WSD', 0x41: 'RQD', 0x12: 'DT1', 0x11: 'RQ1', 0x43: 'ACK', 0x4e: 'ERR',
         0x45: 'EOD', 0x4f: 'RJC'}
i = 0
while d[0x45ea + i]:
    c = d[0x45ea + i]
    print('  [%d] cmd 0x%02x %-3s -> 0x%04x%s' % (i, c, names.get(c, '?'), w(0x45c0 + 2 * i),
                                                  '  (checksum checked)' if i < 5 else ''))
    i += 1

print('\n== Address-hi list 0x4502 + (length, RAM base) table 0x450e (4 bytes per entry) ==')
i = 0
while d[0x4502 + i] != 0xff:
    hi = d[0x4502 + i]
    ln, base = w(0x450e + 4 * i), w(0x4510 + 4 * i)
    print('  %02x xx xx : %5d bytes (0x%04x) at RAM 0x%04x-0x%04x' % (hi, ln, ln, base, base + ln - 1))
    i += 1

print('\n== Post-write action list 0x3e71 -> 0x3e7a ==')
for i in range(8):
    print('  addr-hi %02x -> 0x%04x' % (d[0x3e71 + i], w(0x3e7a + 2 * i)))

print('\n== Max-value (clamp) tables; 0 = byte not writable ==')
for name, a, n in [('rhythm setup   d_483f', 0x483f, 4), ('patch temp     d_4843', 0x4843, 16),
                   ('system 10 00 xx d_485c', 0x485c, 0x21), ('timbre common  d_4873', 0x4873, 14),
                   ('timbre partial d_4873+14', 0x4873 + 14, 58)]:
    print('  %-24s @0x%04x: %s' % (name, a, d[a:a + n].hex(' ')))

print('\n== D-50 (model 0x14) source ranges 0x4bd6 (start,end) ==')
for k, label in enumerate(['lower partial-1 -> LA partial 1', 'lower partial-2 -> LA partial 2',
                           'upper partial-1 -> LA partial 3', 'upper partial-2 -> LA partial 4',
                           'lower common (after name)', 'upper common (after name)']):
    print('  D-50 0x%03x-0x%03x  %s' % (w(0x4bd6 + 4 * k), w(0x4bd8 + 4 * k) - 1, label))
print('  partial map d_4b79:', d[0x4b79:0x4baf].hex(' '))
print('  common  map d_4baf:', d[0x4baf:0x4bd6].hex(' '))

print('\n== Messages ==')
for a in (0x3ffd, 0x4013, 0x4029, 0x403f):
    e = d.index(b'\0', a)
    print('  0x%04x "%s"' % (a, d[a:e].decode('ascii')))
