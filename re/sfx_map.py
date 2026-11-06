"""PRO-E SOUND EFFECTS, end to end: pad -> SFX sequence (IC7) -> rhythm key on CK-34 ch 10 -> rhythm timbre -> PCM wave.

  python -I sfx_map.py

HC11 side (traced in the IC4 + IC7 bank 0 code):
  pads a-l (key codes $48-$4D, $50-$55) -> $7095: pad 0-11 -> note from RAM $240D[pad] (hold a key + press a pad
  stores that key's note) -> $407A: 4 SFX voices ($3E+v note, $42+v flags); note >= 109 = stop all.
  note 76..108: sequence pointer = word at bank 0 $BFA1 + 2*(note-76), bank = nibble of $BFEB[(note-76)/2]
  (low nibble for even notes) -> $ED48[bank] latch value. The IC4 player $C612 steps it (style event format);
  each note event = rhythm key (field + 60) -> $EC7A = note-on $99 (CK-34 channel 10, the rhythm part), velocity
  scaled by the SOUND EFFECTS volume $2405. A copy goes to MIDI OUT on the EFFECT channel ($2447, $EBEA).
CK-34 side: rhythm setup IC28 0x8580 (key 24-108: timbre, level, pan, reverb), R timbre map 0x8500,
  partial WG waveform/PCM -> wave table 0x8100 -> IC37 (pos < 0x80) / IC38.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rosetta_style as rs

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, '..', 'dumps')
ic7 = open(os.path.join(D, 'proe_ic7_R15179983_LH53234L_v2.00.bin'), 'rb').read()
ic28 = open(os.path.join(D, 'ck34_ic28_control_R15179974_CK-34_v2.06.bin'), 'rb').read()
STRUCT = ['S+S', 'S&S', 'P+S', 'P&S', 'S&P', 'P+P', 'P&P', 'S/S', 'P/P', 'S*S', 'P*S', 'S*P', 'P*P']
NOTES = 'C C# D D# E F F# G G# A A# B'.split()


def b0(cpu):
    return ic7[cpu - 0x4000]


def w(a):
    return ic28[a] | ic28[a + 1] << 8


def rtimbre(n):
    ptr = w(0x8500 + 2 * n)
    fa = (ptr & ~0x4000) + (0x4000 if ptr & 0x4000 else 0)
    common = ic28[fa:fa + 14]
    mute, parts, src = common[12], [], fa + 14
    for t in range(4):
        if t and not (mute >> t) & 1:
            src -= 58
        parts.append(ic28[src:src + 58])
        src += 58
    return common[:10].decode('ascii', 'replace').strip(), common, parts


def waves_of(common, parts):
    out = []
    kinds = STRUCT[common[10]] + STRUCT[common[11]]          # e.g. 'P+S' 'S+S' -> partials 1..4 = P,S,S,S
    pk = [kinds[0], kinds[2], kinds[3], kinds[5]]
    for p in range(4):
        if not (common[12] >> p) & 1 or pk[p] != 'P':
            continue
        idx = (parts[p][4] & 2) * 64 + parts[p][5]
        pos, ln = ic28[0x8100 + 4 * idx], ic28[0x8101 + 4 * idx]
        n = 0x800 << ((ln >> 4) & 7)
        out.append((idx, pos, n, bool(ln & 0x80)))
    return out


def key_info(key):
    t, lv, pan, rev = ic28[0x8580 + 4 * (key - 24):0x8584 + 4 * (key - 24)]
    if t < 0x40:
        return f'memory timbre M{t}', []
    name, common, parts = rtimbre(t - 0x40)
    return name, waves_of(common, parts)


def main():
    print('SFX note | bank ptr  | events | rhythm keys played -> timbre: wave (chip, pos, length, loop)')
    longest = []
    for note in range(76, 109):
        i = note - 76
        ptr = b0(0xBFA1 + 2 * i) << 8 | b0(0xBFA2 + 2 * i)
        nib = b0(0xBFEB + i // 2)
        bank = (nib >> 4 if note & 1 else nib) & 0x0F
        latch = b0(0xED48 + bank)
        b = (latch >> 4) & 7
        try:
            ev, size = rs.decode_events(ic7, b, ptr)
        except Exception as e:
            print(f'{note:3d} {NOTES[note % 12]}{note // 12 - 1:<2} | bank {b} ${ptr:04X} | ?? {e}')
            continue
        keys = []
        for e in ev:
            if 'end' in e or e['pc'] or e['field'] >= 0x3D or not e['hi']:
                continue
            k = e['field'] + 60
            if k not in keys:
                keys.append(k)
        desc = []
        for k in keys:
            name, wv = key_info(k) if 24 <= k <= 108 else ('(off the rhythm map)', [])
            ws = ', '.join(f"#{x[0]} {'IC37' if x[1] < 0x80 else 'IC38'} {x[1]:02X} {x[2] / 32000:.2f}s{' loop' if x[3] else ''}"
                           for x in wv)
            desc.append(f'key {k} {name}: {ws}')
            longest += [(x[2] / 32000, name, k, x) for x in wv]
        print(f'{note:3d} {NOTES[note % 12]}{note // 12 - 1:<2} | bank {b} ${ptr:04X} | {len(ev):5d}  | ' + ('; '.join(desc) or '-'))
    print('\nlongest waves behind the SFX:')
    for s, name, k, x in sorted(set(longest), reverse=True)[:12]:
        print(f'  {s:5.2f} s  {name:10s} key {k}  wave #{x[0]} {"IC37" if x[1] < 0x80 else "IC38"} pos {x[1]:02X} {"loop" if x[3] else "one-shot"}')


if __name__ == '__main__':
    main()
