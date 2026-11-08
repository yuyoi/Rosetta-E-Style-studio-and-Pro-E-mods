"""PRO-E wave studio test on the real dumps: same-slot swap, bigger slot (table rewrite), root/loop, nothing else damaged.

  python -I test_proe_wave.py
"""
import os, sys, importlib.util, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location('ws', os.path.join(HERE, 'rosetta_wave_proe.pyw'))
ws = importlib.util.module_from_spec(spec)
sys.argv = ['x']
spec.loader.exec_module(ws)

OK = []


def check(c, what):
    assert c, what
    OK.append(what)


rom = ws.Rom(); R = ws.RATE; T = ws.TABLE_AT
tone = lambda s, f=440: np.sin(2 * np.pi * f * np.arange(int(s * R)) / R) * 0.7
check(rom.names[128].strip() == 'Laughing' and rom.chip(128) == 'IC38', 'wave #128 = Laughing in IC38')
check(rom.chip(0) == 'IC37' and 'used by' in rom.used[40], 'IC37 lower half, tone usage listed')

# decode of the stock dumps = the D-110 codec, bit exact round trip
for chip in (rom.ic8, rom.ic7):
    check(np.array_equal(ws.log_to_rom(ws.rom_to_log(chip)), chip), 'codec round trip is bit exact')


def load(d, f):
    return np.fromfile(os.path.join(d, f), np.uint8)


# 1) same-slot swap of Laughing: only IC38 changes, only inside its slot, IC28 untouched
with tempfile.TemporaryDirectory() as d:
    files, lines = ws.build(rom, {128: tone(0.3)}, {}, d)
    ic37, ic38, ic28 = (load(d, f) for f in files)
    a, n, _ = rom.ent[128]
    lo, hi = (a - 0x40000) * 2, (a - 0x40000 + n) * 2
    check(np.array_equal(ic37, rom.ic8), 'IC37 untouched')
    check(np.array_equal(ic28, rom.ctrl), 'IC28 untouched by a same-slot swap')
    check(np.array_equal(ic38[:lo], rom.ic7[:lo]) and np.array_equal(ic38[hi:], rom.ic7[hi:]), 'IC38 changed only inside the slot')
    dec = ws.log_to_lin(ws.rom_to_log(ic38[lo:hi]))
    ref = ws.fit(tone(0.3), n) * ws.FULL
    check(np.corrcoef(dec, ref)[0, 1] > 0.999, 'decoded swap matches the WAV')
    check(lines[-1].startswith('IC28: unchanged'), 'report says burn only IC37/IC38')

# 2) root note + loop: IC28 changes only inside the wave table, on the linked entries
with tempfile.TemporaryDirectory() as d:
    files, lines = ws.build(rom, {128: tone(0.3)}, {}, d, True, {128: 60}, {128: True})
    ic28 = load(d, files[2])
    diff = np.nonzero(ic28 != rom.ctrl)[0]
    check(len(diff) and all(T <= o < T + 0x400 for o in diff), 'root/loop edits stay inside IC28 0x8100-0x84FF')
    for j in rom.linked(128):
        check(ic28[T + 1 + 4 * j] & 0x80 and (int(ic28[T + 2 + 4 * j]) | int(ic28[T + 3 + 4 * j]) << 8) == ws.root_to_pitch(60),
              'linked entry %d: loop on, pitch for root C4' % j)
    check(lines[-1].startswith('IC28: CHANGED'), 'report says burn IC28 too')

# 3) a 2 s WAV moves to a bigger slot when waves are freed; every table entry stays legal
free = {i for i in range(256) if rom.pos[i] >= 0x80 and i not in rom.linked(140)}
with tempfile.TemporaryDirectory() as d:
    files, lines = ws.build(rom, {140: tone(2.0, 220)}, {}, d, True, None, None, free)
    ic37, ic38, ic28 = (load(d, f) for f in files)
    check(np.array_equal(ic37, rom.ic8), 'IC37 untouched when only IC38 waves move')
    for i in range(256):                      # stock itself has 4 unaligned entries (#252-255); moved ones must be aligned
        pos, e = int(ic28[T + 4 * i]), (int(ic28[T + 1 + 4 * i]) >> 4) & 7
        if bytes(ic28[T + 4 * i:T + 4 * i + 2]) != bytes(rom.ctrl[T + 4 * i:T + 4 * i + 2]):
            assert pos + (1 << e) <= 256 and pos % (1 << e) == 0, ('illegal entry', i, pos, e)
    check(True, 'every moved / parked entry aligned and in range after the repack')
    pos, e = int(ic28[T + 4 * 140]), (int(ic28[T + 1 + 4 * 140]) >> 4) & 7
    check((0x800 << e) >= 2.0 * R and pos >= 0x80, 'Door moved to a >= 2 s slot inside IC38 (%d samples)' % (0x800 << e))
    a, n = pos * 0x800, 0x800 << e
    dec = ws.log_to_lin(ws.rom_to_log(ic38[(a - 0x40000) * 2:(a - 0x40000) * 2 + int(2.0 * R) * 2]))
    check(np.corrcoef(dec, ws.fit(tone(2.0, 220), n)[:int(2.0 * R)] * ws.FULL)[0, 1] > 0.999, 'moved wave decodes back')
    diff = np.nonzero(ic28 != rom.ctrl)[0]
    check(all(T <= o < T + 0x400 for o in diff), 'repack touches only the IC28 wave table')
print('ALL OK, %d checks' % len(OK))
