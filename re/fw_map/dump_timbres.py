#!/usr/bin/env python3
"""List the CK-34 (IC28 v2.06) preset timbre tables, decoded the way the 8098 code reads them.

Tables (file offset = CPU address with bank 2 at 0x8000; pointers resolved like sub_4eea @0x4eea):
  0x8000  timbre A map: 64 LE words; ptr -> bank 2 + (ptr >> 14), CPU 0x8000 + (ptr & 0x3FFF),
          i.e. file = 0x8000 + ptr ("Munt offset 0x8000"). Timbres 0-63.
  0x8080  timbre B map: same, timbres 64-127.
  0x8500  rhythm timbre map ("R"): 64 LE words, CPU address in bank 2 (bit 14 set = bank 3; code 0x262f / 0x2632).
  0x8580  rhythm setup: 85 x 4 bytes (keys 24..108): timbre (0x40+n = R timbre n, <0x40 = memory M n), level, pan, reverb switch
All timbres are "compressed" (Munt initCompressedTimbre; code 0x4e8e-0x4eb9): 14-byte common + only the partials whose mute
bit is set; a muted partial reuses the previous stored partial.

usage: python dump_timbres.py [IC28.bin] [--mt32 IC26.bin IC27.bin]   (compare A/B params with MT-32 1.0.x presets)
"""
import argparse, os

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_ROM = os.path.join(HERE, '..', '..', 'dumps', 'ck34_ic28_control_R15179974_CK-34_v2.06.bin')
# Munt PartialStruct/PartialMixStruct; '+' mix, '&' ring mod + mix, '*' ring mod only, '/' stereo pair
STRUCT = ['S+S', 'S&S', 'P+S', 'P&S', 'S&P', 'P+P', 'P&P', 'S/S', 'P/P', 'S*S', 'P*S', 'S*P', 'P*P']


def w(rom, a):
    return rom[a] | (rom[a + 1] << 8)


def timbre(rom, a):
    """expand a compressed timbre at file address a -> (name, common14, [4 x 58-byte partials])"""
    common = rom[a:a + 14]
    mute = common[12]
    parts, src = [], a + 14
    for t in range(4):
        if t != 0 and not (mute >> t) & 1:
            src -= 58
        parts.append(rom[src:src + 58])
        src += 58
    return common[:10].decode('ascii', 'replace'), common, parts


def mt32_image(ic26, ic27):
    a, b = open(ic27, 'rb').read(), open(ic26, 'rb').read()
    img = bytearray(0x10000)
    img[0::2], img[1::2] = a, b
    return bytes(img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', nargs='?', default=DEF_ROM)
    ap.add_argument('--mt32', nargs=2, metavar=('IC26', 'IC27'))
    a = ap.parse_args()
    rom = open(a.rom, 'rb').read()
    mt = mt32_image(*a.mt32) if a.mt32 else None

    print('== Preset timbres (A = 0x8000 map, B = 0x8080 map) ==')
    same = 0
    for i in range(128):
        ptr = w(rom, 0x8000 + 2 * i)
        fa = 0x8000 + ptr
        name, com, parts = timbre(rom, fa)
        s12, s34, mute, nosus = com[10], com[11], com[12], com[13]
        waves = []
        for k in range(4):
            if k and not (mute >> k) & 1:
                waves.append('--')
                continue
            st = STRUCT[s12 if k < 2 else s34] if (s12 if k < 2 else s34) < 13 else '???'
            is_pcm = st[0 if k % 2 == 0 else 2] == 'P'
            p = parts[k]
            # PCM index as the code builds it @0x34c3: (waveform bit1) * 128 + pcmWave (table 0x8100)
            waves.append(('PCM%d' % (((p[4] >> 1) & 1) * 128 + p[5])) if is_pcm else ('SAW' if p[4] & 1 else 'SQU'))
        line = '%3d %s ptr %04X file %05X bank %d cpu %04X  "%s"  struct %d:%-3s %d:%-3s mute %X  %-27s%s' % (
            i, 'AB'[i // 64], ptr, fa, 2 + (ptr >> 14), 0x8000 + (ptr & 0x3FFF), name,
            s12 + 1, STRUCT[s12] if s12 < 13 else '?', s34 + 1, STRUCT[s34] if s34 < 13 else '?', mute,
            ' '.join(waves), ' nosus' if nosus else '')
        if mt:
            # MT-32 1.0.x: A map 0x8000 offset 0, B map 0xC000 offset 0x4000, uncompressed 246-byte timbres
            mp = (w(mt, 0x8000 + 2 * i) if i < 64 else w(mt, 0xC000 + 2 * (i - 64)) + 0x4000)
            mname = mt[mp:mp + 10].decode('ascii', 'replace')
            mcom, mparts = mt[mp:mp + 14], [mt[mp + 14 + 58 * k: mp + 72 + 58 * k] for k in range(4)]
            used = [k for k in range(4) if k == 0 or (mute >> k) & 1]
            eq = mcom == com and all(mparts[k] == parts[k] for k in used)
            same += eq
            line += '  | MT-32: %s' % ('same' if eq else 'DIFF ("%s")' % mname)
        print(line)
    if mt:
        print('identical to MT-32 1.0.x preset (common + unmuted partials): %d/128' % same)

    print('\n== Rhythm timbres (R map 0x8500, 64 entries) ==')
    rnames = []
    for i in range(64):
        ptr = w(rom, 0x8500 + 2 * i)
        bank = 3 if ptr & 0x4000 else 2
        fa = (ptr & ~0x4000) + (0x4000 if bank == 3 else 0)
        if ptr == 0xFFFF:
            rnames.append('-')
            continue
        name = rom[fa:fa + 10].decode('ascii', 'replace')
        rnames.append(name.strip())
        print('R%02d ptr %04X -> bank %d cpu %04X file %05X  "%s"' % (i, ptr, bank, ptr & 0xBFFF, fa, name))

    print('\n== Rhythm setup (0x8580, keys 24-108: timbre, level, pan, reverb) ==')
    for k in range(85):
        t, lv, pan, rev = rom[0x8580 + 4 * k: 0x8584 + 4 * k]
        if t == 0x7F:
            continue  # 0x7F = off
        tn = ('R%02d %s' % (t - 0x40, rnames[t - 0x40])) if t >= 0x40 else 'M%02d' % t
        print('key %3d  timbre %02X %-16s level %3d pan %2d rev %d' % (k + 24, t, tn, lv, pan, rev))


if __name__ == '__main__':
    main()
