"""One-off: turn a copy of the D-110 Rosetta ROM Studio (rosetta_rom/rosetta_studio.pyw) into the PRO-E wave studio.

  python -I port_from_d110.py rosetta_studio.pyw -> rosetta_wave_proe.pyw

Every replacement must match exactly the expected number of times, so a changed D-110 source fails loudly.
Internally the lower / upper wave chips keep the D-110 attribute names (rom.ic8 = IC37, rom.ic7 = IC38, rom.ctrl = IC28).
"""
import sys

src = open(sys.argv[1], encoding='utf-8').read()


def rep(old, new, count=1):
    global src
    n = src.count(old)
    if n != count:
        sys.exit(f'expected {count} x {old!r}, found {n}')
    src = src.replace(old, new)


# header, identity, geometry
rep('"""Rosetta ROM Studio v0.3 - swap waves in a Roland D-110 (IC8 drums, IC7 instruments, IC12 names + pitch/loop table).\n'
    'Pick a wave, drop in a WAV, set its root note / loop, rename, BUILD -> three patched ROM images (IC8, IC7, IC12). Hardware-untested.',
    '"""Rosetta Wave Studio for the Roland PRO-E (CK-34 voice board = CM-32L hardware), ported from the D-110 Rosetta ROM Studio.\n'
    'IC37 = lower 512 KB (MT-32 set), IC38 = upper 512 KB (CM-32L effects), IC28 = control ROM (wave table 0x8100, tones).\n'
    'Pick a wave, drop in a WAV, set its root note / loop, BUILD -> IC37 + IC38 (+ IC28 when the table changes). Hardware-untested.\n'
    'Names are not in the ROM: each wave is named after the first PRO-E tone that plays it (project-only, never written).')
rep("from rosetta_d110 import rom_to_log, log_to_rom, log_to_lin, lin_to_log, read_wav",
    "from rosetta_d110 import rom_to_log, log_to_rom, log_to_lin, lin_to_log, read_wav\nimport proe_profile as PROE")
rep("APP = 'Rosetta ROM Studio'; EXT = '.rosetta'", "APP = 'Rosetta Wave PRO-E'; EXT = '.rwproe'")
rep("CFG = os.path.join(HERE, 'rosetta_config.json')", "CFG = os.path.join(HERE, 'proe_wave_config.json')")
rep("APP_VERSION = '0.4'", "APP_VERSION = '0.1-proe'")
rep("RATE = 32000; NW = 128", "RATE = 32000; NW = 256\nLO, HI, CT = PROE.LO, PROE.HI, PROE.CT")
rep('    """IC12 PCM-table pitch field', '    """IC28 PCM-table pitch field')

# the ROM model
a = src.index('class Rom:')
b = src.index('    def orig(s, i):', a)
src = src[:a] + '''class Rom:
    """wave space = IC37 (first 256K samples) then IC38; the table comes from IC28, names from the PRO-E tone list (IC7)"""

    none = False

    def __init__(s, ic8=None, ic7=None, ic12=None, tones=None):
        c = load_cfg()
        d = os.path.join(HERE, '..', 'dumps')
        ic8 = ic8 or c.get('ic8') or os.path.join(d, 'ck34_ic37_wave_R15449121_TC534000P.bin')
        ic7 = ic7 or c.get('ic7') or os.path.join(d, 'ck34_ic38_wave_R15179945_HN62304.bin')
        ic12 = ic12 or c.get('ic12') or os.path.join(d, 'ck34_ic28_control_R15179974_CK-34_v2.06.bin')
        tones = tones or c.get('tones') or os.path.join(d, 'proe_ic7_R15179983_LH53234L_v2.00.bin')
        s.paths = {'ic8': ic8, 'ic7': ic7, 'ic12': ic12, 'tones': tones}
        s.real = {}
        s.ic8 = np.fromfile(ic8, np.uint8); s.ic7 = np.fromfile(ic7, np.uint8); s.ctrl = np.fromfile(ic12, np.uint8)
        if len(s.ic8) != 524288 or len(s.ic7) != 524288 or len(s.ctrl) != 65536:
            raise ValueError('Expected IC37 and IC38 = 512 KB each, IC28 = 64 KB (got %d / %d / %d bytes)' % (len(s.ic8), len(s.ic7), len(s.ctrl)))
        if bytes(s.ctrl[TABLE_AT:TABLE_AT + 4]) == b'\\xff' * 4:
            raise ValueError('IC28 has no wave table at 0x%04X: is this the CK-34 v2.06 control ROM?' % TABLE_AT)
        s.wave = np.concatenate([log_to_lin(rom_to_log(s.ic8)), log_to_lin(rom_to_log(s.ic7))])
        ic7img = np.fromfile(tones, np.uint8) if os.path.isfile(tones) else None
        s.names, s.used = PROE.wave_names(s.ctrl, ic7img)
        s.ent = [(int(s.ctrl[TABLE_AT + 4 * i]) * 0x800, 0x800 << ((int(s.ctrl[TABLE_AT + 1 + 4 * i]) >> 4) & 7),
                  bool(s.ctrl[TABLE_AT + 1 + 4 * i] & 0x80)) for i in range(NW)]

        s.pos = [int(s.ctrl[TABLE_AT + 4 * i]) for i in range(256)]
        s.lenb = [int(s.ctrl[TABLE_AT + 1 + 4 * i]) for i in range(256)]
        s.pitch = [int(s.ctrl[TABLE_AT + 2 + 4 * i]) | int(s.ctrl[TABLE_AT + 3 + 4 * i]) << 8 for i in range(256)]

        # slots that sit inside another slot (loop slices of a longer wave, the same wave twice) share its data
        s.parent = {}
        for i in range(NW):
            a, n, _ = s.ent[i]
            for j in range(NW):
                ja, jn, _ = s.ent[j]
                if j != i and ja <= a and a + n <= ja + jn and (jn > n or (jn == n and j < i)) and (a >= 0x40000) == (ja >= 0x40000):
                    s.parent[i] = j; break

''' + src[b:]
rep("""        return [j for j in range(256) if s.pos[j] == s.pos[i] and (s.lenb[j] >> 4) & 7 == (s.lenb[i] >> 4) & 7]

    def chip(s, i):
        return 'IC8' if s.ent[i][0] < 0x40000 else 'IC7'""",
    """        return [j for j in range(256) if s.pos[j] == s.pos[i] and (s.lenb[j] >> 4) & 7 == (s.lenb[i] >> 4) & 7]

    def chip(s, i):
        return LO if s.ent[i][0] < 0x40000 else HI""")
rep("        s.ent = [(0, 0, False)] * NW; s.names = [''] * NW", "        s.ent = [(0, 0, False)] * NW; s.names = [''] * NW; s.used = [''] * NW")
rep("    def chip(s, i): return 'IC8'", "    def chip(s, i): return LO")

# layout: on the PRO-E every entry is a real wave; the D-110's "aliases 128+" become "sub-slots of another entry"
# PRO-E: no automatic "sub-slices go with a freed parent". On the D-110 those were aliases (128+); here the waves inside
# the big whole-region loops (#119-127) are the drum kit itself. A wave is only freed when it is asked for by name.
rep("        if j >= 128 and all(freedu[u] for u in range(*span(j))):", "        if False:")
rep("    parked = sorted((free_up - moving) | {j for j in range(128, 256) if j not in moving and j not in free_up and all(freedu[u] for u in range(*span(j)))})",
    "    parked = sorted(free_up - moving)")
rep("(set(j for j in park if j < 128) if park else set())", "(set(park) if park else set())")

# table offsets + names (the PRO-E keeps names in the project only: IC28 0x100 is code)
for k in range(4):
    lit = '0x90%d + 4' % k
    new = 'TABLE_AT + 4' if k == 0 else 'TABLE_AT + %d + 4' % k
    src = src.replace(lit, new)
rep("    for i, nm in renames.items():\n        c[0x100 + 8 * i:0x108 + 8 * i] = list(nm.encode('ascii', 'replace')[:8].ljust(8))\n",
    "    # names: project only on the PRO-E (no name table in IC28)\n")
rep("NAMES_AT, NAMES_LEN = 0x100, 0x800      # 256 x 8 ASCII\nTABLE_AT, TABLE_LEN = 0x900, 0x400      # 256 x 4 bytes {pos, len, pitch}\n"
    "RPATCH_REGIONS = (('names', NAMES_AT, NAMES_LEN), ('table', TABLE_AT, TABLE_LEN))",
    "TABLE_AT, TABLE_LEN = PROE.TABLE_AT, 0x400      # IC28: 256 x 4 bytes {pos, len, pitch}\n"
    "RPATCH_REGIONS = (('table', TABLE_AT, TABLE_LEN),)")
rep("'IC12 edit at 0x%X is outside the packed regions (names 0x%03X-0x%03X, table 0x%03X-0x%03X). '\n"
    "                         'Add a region to RPATCH_REGIONS before patching there.' % (outside[0], NAMES_AT, NAMES_AT + NAMES_LEN, TABLE_AT, TABLE_AT + TABLE_LEN))",
    "'IC28 edit at 0x%X is outside the wave table 0x%04X-0x%04X. '\n"
    "                         'Add a region to RPATCH_REGIONS before patching there.' % (outside[0], TABLE_AT, TABLE_AT + TABLE_LEN))")

# chip labels, files, manifest
rep("('IC8' if a < 0x40000 else 'IC7', cc, bias)", "(LO if a < 0x40000 else HI, cc, bias)")
rep('    """writes all three images: IC8 (drums), IC7 (instruments), IC12 (names + pitch/loop table). Returns (files, report lines)"""',
    '    """writes IC37 + IC38 (waves) and IC28 (table). Returns (files, report lines); IC28 only needs burning if it changed"""')
rep("    files = ['r15179880.ic8_patched.bin', 'r15179878.ic7_patched.bin', 'r15179873.ic12_patched.bin']",
    "    files = ['IC37_R15449121_patched.bin', 'IC38_R15179945_patched.bin', 'IC28_R15179974_patched.bin']")
rep("""    with open(f'{out}/report.txt', 'w') as f:""",
    """    lines.append('IC28: ' + ('CHANGED (new lengths / positions / pitch / loop): burn IC28 too' if not np.array_equal(rd.ctrl, rom.ctrl)
                                else 'unchanged: burn only IC37 / IC38'))
    with open(f'{out}/report.txt', 'w') as f:""")
rep("UNITS = 256                     # the whole 1 MB wave space: 256 units, unit < 128 in IC8, 128+ in IC7",
    "UNITS = 256                     # the whole 1 MB wave space: 256 units, unit < 128 in IC37, 128+ in IC38")
rep("'chip': 'ic8' if u < 128 else 'ic7',", "'chip': 'ic37' if u < 128 else 'ic38',")
rep("""        'basis': {'family': 'd110-lh5310', 'chips': {
            'ic8': {'size': 524288, 'md5': _md5(rom.ic8), 'label': 'IC8 drums, HN62304B'},
            'ic7': {'size': 524288, 'md5': _md5(rom.ic7), 'label': 'IC7 instruments, HN62304B'},
            'ic12': {'size': 131072, 'md5': _md5(rom.ctrl), 'label': 'IC15 control, LH5310 (called "ic12" in dump sets)',""",
    """        'basis': {'family': 'proe-ck34', 'chips': {
            'ic8': {'size': 524288, 'md5': _md5(rom.ic8), 'label': 'IC37 R15449121 (lower half, MT-32 set)'},
            'ic7': {'size': 524288, 'md5': _md5(rom.ic7), 'label': 'IC38 R15179945 (upper half, CM-32L effects)'},
            'ic12': {'size': 65536, 'md5': _md5(rom.ctrl), 'label': 'IC28 R15179974 CK-34 v2.06 control',""")
rep("""        'expected': {'ic8': _md5(rd.ic8), 'ic7': _md5(rd.ic7), 'ic12': _md5(rd.ctrl),
                     'ic12_x4': _md5(np.tile(rd.ctrl, 4))},""",
    """        'expected': {'ic8': _md5(rd.ic8), 'ic7': _md5(rd.ic7), 'ic12': _md5(rd.ctrl)},""")

# UI text
rep("            if '--roms' in sys.argv:        # --roms IC8 IC7 IC12", "            if '--roms' in sys.argv:        # --roms IC37 IC38 IC28")
rep("(('ic8', 'IC8 drum ROM (512 KB, r15179880)'), ('ic7', 'IC7 instrument ROM (512 KB, r15179878)'), ('ic12', 'IC12 control ROM (128 KB, r15179873)'))",
    "(('ic8', 'IC37 wave ROM, lower half (512 KB, R15449121)'), ('ic7', 'IC38 wave ROM, upper half (512 KB, R15179945)'), ('ic12', 'IC28 control ROM (64 KB, R15179974)'))",
    count=2)
rep("('Import ROM dumps (IC8, IC7, IC12)...'", "('Import ROM dumps (IC37, IC38, IC28)...'")
rep("text='D-110', style='Title.TLabel'", "text='PRO-E', style='Title.TLabel'")
rep("text='ROSETTA ROM STUDIO', style='Sub.TLabel'", "text='ROSETTA WAVE STUDIO', style='Sub.TLabel'")
rep("value='Hardware-untested. Each wave keeps its slot position and length. Root note and loop flag go into IC12. 32 kHz mono.'",
    "value='Hardware-untested. Same-slot swaps need only IC37/IC38. Root note, loop flag and bigger slots go into IC28. 32 kHz mono.'")
rep("values=['All', 'IC8 drums', 'IC7 instruments', 'Changed']", "values=['All', 'IC37 MT-32 set', 'IC38 effects', 'Used by tones', 'Changed']")
rep("(f == 'IC8 drums' and s.rom.chip(i) == 'IC8') or (f == 'IC7 instruments' and s.rom.chip(i) == 'IC7')",
    "(f == 'IC37 MT-32 set' and s.rom.chip(i) == LO) or (f == 'IC38 effects' and s.rom.chip(i) == HI) or (f == 'Used by tones' and s.rom.used[i].startswith('used'))")
rep("'machine': 'D-110'", "'machine': 'PRO-E'")

# menu: the D-110 pack / OS tools don't apply here
rep("""                        ('Build ROM images...', s.build, 'Ctrl+B'),
                        ('Export .rpatch pack...', s.export_patch, 'Ctrl+P'), ('Apply .rpatch pack to my dumps...', s.apply_pack, 'Ctrl+Shift+P'),
                        ('Patch OS (no waves)...', s.patch_os, ''), (None,) * 3, ('Exit', s.quit_app, '')):""",
    """                        ('Build ROM images...', s.build, 'Ctrl+B'), (None,) * 3, ('Exit', s.quit_app, '')):""")
rep("""('<Control-i>', s.import_wavs), ('<Control-p>', s.export_patch), ('<Control-P>', s.apply_pack), ('<Delete>', s.undo)):""",
    """('<Control-i>', s.import_wavs), ('<Delete>', s.undo)):""")
rep("pick your own IC8 (drums), IC7 (instruments) and IC12 (control).'); return", "pick your own IC37, IC38 and IC28 dumps.'); return", count=2)
rep(r"""        messagebox.showinfo(APP, 'Wrote 3 images + report.txt to %s\n\nIC8 (drums):  %s\nIC7 (instruments):  %s\nIC12 (control):  %s\n\nProgram each image to its own chip. Images are in chip byte order, as dumped.' % ((d,) + tuple(files)))""",
    r"""        messagebox.showinfo(APP, 'Wrote 3 images + report.txt to %s\n\nIC37 (W27C040):  %s\nIC38 (W27C040):  %s\nIC28 (64 KB):  %s\n\n%s\nImages are in chip byte order, as dumped.' % ((d,) + tuple(files) + (lines[-1],)))""")
rep("""            ('   |   also applies to table entries %s' % lk) if lk else ''))""",
    r"""            ('   |   also applies to table entries %s' % lk) if lk else '') + '\n' + s.rom.used[i])""")
rep("ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JSW.RosettaROMStudio')", "ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JSW.RosettaWaveProE')")
a = src.index("    def help(s):")
b = src.index("\n\nif __name__ == '__main__':")
src = src[:a] + r"""    def help(s):
        messagebox.showinfo('How it works',
            'WAVES = all 256 entries of the CK-34 wave table (IC28 0x8100). #0-127 = PCM bank 1, #128-255 = bank 2.\n'
            'Each name is the first PRO-E tone (or rhythm sound) that plays the wave; the line under the waveform lists all of them.\n\n'
            'Pick a wave, Load WAV: it replaces that slot in IC37 (lower half, MT-32 set) or IC38 (upper half, CM-32L effects).\n'
            'The slot keeps its position and length: longer WAVs are cut, shorter ones padded. 32 kHz mono.\n'
            'A same-slot swap only needs new IC37 / IC38 chips (W27C040 drop-ins). IC28 stays stock.\n'
            'ROOT NOTE / LOOP / bigger SLOT lengths go into the IC28 table, so IC28 must be burned too (report.txt says which).\n'
            'Names stay in the project: the PRO-E has no wave names in ROM.\n\n'
            'Drag WAVs onto the list (onto a row = that wave) or a folder. File > Export all original waves, edit, Import WAV folder.\n'
            'Wheel = zoom, Shift+wheel = pan, right-click = fit. Double-click a wave to hear the original. Hardware-untested.')""" + src[b:]

rep("'The D-110 boots but its Edit screen stops working, because 200+ waves would share one '",
    "'On the D-110 such a build booted but its Edit screen stopped working, because 200+ waves shared one '")
# a parked wave is written with length code 0 (one unit, see render), so plan one unit for it, not its old length
rep("            e = (rom.lenb[j] >> 4) & 7; want = 1 << e; p = rom.pos[j]",
    "            want = 1; p = rom.pos[j]          # render() parks it with length code 0 = one unit")
open(sys.argv[2], 'w', encoding='utf-8').write(src)
print('ported ->', sys.argv[2])
