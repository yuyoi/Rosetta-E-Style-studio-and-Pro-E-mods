#!/usr/bin/env python3
"""Decode the LA32 PCM wave table in the CK-34 control ROM (IC28, R15179974, v2.06).

Table: file 0x8100 (= CPU 0x8100 with bank 0x0100 = 2), 256 entries x 4 bytes, Munt ControlROMPCMStruct:
  byte 0 pos   : start = pos * 0x800 samples (2048-sample granularity, 1 sample = 2 bytes in the wave ROM)
  byte 1 len   : bit 7 = loop, bits 4-6 = n (length = 0x800 << n samples), bit 0 = 1 -> NOT affected by
                 master tune (CK-34 code 0x2cb4-0x2cc4 adds master tune 0xF4A0 only when this bit is 0),
                 bit 3 is forced to 1 by the code before the byte goes to LA32 reg 0x0D01 (0x34e9)
  byte 2/3     : pitch LSB/MSB, added to the partial base pitch (code 0x363b), 4096 units per octave
Index used by the code (0x34c3-0x34df): (waveform bit1) * 128 + pcmWave, i.e. entries 0-127 = PCM bank 1
(waveform SQU/1, SAW/1 = MT-32 set), 128-255 = bank 2 (waveform SQU/2, SAW/2 = CM-32L extra set).

The wave ROM byte address of an entry = pos * 0x1000 (IC37 = 0x00000-0x7FFFF, IC38 = 0x80000-0xFFFFF).

usage: python dump_pcm_table.py [IC28.bin] [--csv] [--mt32 IC26.bin IC27.bin] [--ic38 IC38.bin]
  --mt32 : compare entries 0-127 with the MT-32 1.0.x control ROM table at 0x3000 (old-gen, ic27 = even bytes)
  --ic38 : for entries in the IC38 half, print the max log code (bits 0-14, 0x7FFF = loudest) of the
           first 256 samples after Munt's bit unscramble (sanity check: the wave is not silent)
"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_ROM = os.path.join(HERE, '..', '..', 'dumps', 'ck34_ic28_control_R15179974_CK-34_v2.06.bin')
TABLE, COUNT = 0x8100, 256


def decode(rom, base=TABLE, count=COUNT):
    out = []
    for i in range(count):
        pos, ln, plo, phi = rom[base + 4 * i: base + 4 * i + 4]
        n = (ln >> 4) & 7
        out.append(dict(idx=i, pos=pos, lenb=ln, start=pos * 0x800, length=0x800 << n,
                        loop=bool(ln & 0x80), fixed=bool(ln & 1), other=ln & 0x0e,
                        pitch=(phi << 8) | plo))
    return out


def unscramble(s, c):
    # Munt Synth::loadPCMROM bit order; returns the 16-bit log sample (sign in bit 15)
    order = (0, 9, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 8)
    word = (s << 8) | c
    v = 0
    for u in range(16):
        if word & (0x8000 >> order[u]):
            v |= 0x8000 >> u
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', nargs='?', default=DEF_ROM)
    ap.add_argument('--csv', action='store_true')
    ap.add_argument('--mt32', nargs=2, metavar=('IC26', 'IC27'))
    ap.add_argument('--ic38')
    a = ap.parse_args()
    rom = open(a.rom, 'rb').read()
    if len(rom) != 0x10000:
        sys.exit('expected the 64 KB IC28 image')
    ents = decode(rom)

    mt = None
    if a.mt32:
        b26, b27 = open(a.mt32[0], 'rb').read(), open(a.mt32[1], 'rb').read()
        img = bytearray(0x10000)
        img[0::2], img[1::2] = b27, b26
        mt = decode(img, 0x3000, 128)
    ic38 = open(a.ic38, 'rb').read() if a.ic38 else None

    if a.csv:
        print('idx,bank,wave,pos,lenbyte,start_sample,length_samples,loop,fixed_pitch,pitch_hex,rom_byte_addr')
    else:
        print('IC28 PCM table @0x%04X, %d entries' % (TABLE, COUNT))
        print(' idx bk wv | pos len  | start    length  loop fix | pitch   (semis vs 0x5000) | ROM byte addr' +
              ('  | MT-32 1.0x' if mt else '') + ('  | IC38 max log code' if ic38 else ''))
    overlaps = 0
    for e in ents:
        bank, wave = e['idx'] // 128 + 1, e['idx'] % 128 + 1
        addr = e['start'] * 2
        end = e['start'] + e['length']
        if end > 0x80000:
            overlaps += 1
        if a.csv:
            print('%d,%d,%d,0x%02X,0x%02X,0x%05X,%d,%d,%d,0x%04X,0x%05X' % (
                e['idx'], bank, wave, e['pos'], e['lenb'], e['start'], e['length'], e['loop'], e['fixed'],
                e['pitch'], addr))
            continue
        semis = (e['pitch'] - 0x5000) * 12 / 4096.0
        line = '%4d %d %3d | %02X  %02X   | %05X  %6d  %-4s %-3s | %04X (%+6.2f)          | %05X%s' % (
            e['idx'], bank, wave, e['pos'], e['lenb'], e['start'], e['length'],
            'loop' if e['loop'] else '-', 'fix' if e['fixed'] else '-', e['pitch'], semis,
            addr, ' IC38' if addr >= 0x80000 else ' IC37')
        if e['other']:
            line += ' [len bits1-3=%X]' % e['other']
        if mt and e['idx'] < 128:
            m = mt[e['idx']]
            same = (m['pos'], m['lenb'], m['pitch']) == (e['pos'], e['lenb'], e['pitch'])
            line += '  | %s' % ('same' if same else 'DIFF %02X %02X %04X' % (m['pos'], m['lenb'], m['pitch']))
        if ic38 is not None and addr >= 0x80000:
            off = addr - 0x80000
            pk = 0
            for k in range(256):
                v = unscramble(ic38[off + 2 * k], ic38[off + 2 * k + 1])
                pk = max(pk, v & 0x7FFF)  # Munt: log attenuation = 32787 - (v & 0x7FFF), so larger = louder
            line += '  | max log code %04X' % pk
        print(line)
    if not a.csv:
        uniq = len({(e['pos'], e['lenb'] & 0xF0) for e in ents})
        print('\n%d entries, %d distinct (pos,len) regions, %d loop, %d fixed-pitch, %d exceed 1 MB' % (
            len(ents), uniq, sum(e['loop'] for e in ents), sum(e['fixed'] for e in ents), overlaps))
        if mt:
            print('entries 0-127 identical to MT-32 table: %d/128' % sum(
                (mt[i]['pos'], mt[i]['lenb'], mt[i]['pitch']) == (ents[i]['pos'], ents[i]['lenb'], ents[i]['pitch'])
                for i in range(128)))


if __name__ == '__main__':
    main()
