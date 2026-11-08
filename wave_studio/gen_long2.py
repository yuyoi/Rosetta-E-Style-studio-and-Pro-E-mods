"""LONG2 test bank: as many long sounds as fit, drum kit kept stock. Output ../build/waves_long2/ (git-ignored, private audio).

  python -I gen_long2.py

- Kept: every wave the rhythm kit uses (keys < 76), with the stock audio. Everything else is freed.
- Each sound goes on a PCM bank-2 entry (#128, #129, ...), so SYNTH EDIT > PCM WAVE "2- 1", "2- 2", ... plays them in order.
- RATE: a sound longer than 4.10 s is stored at half (or quarter) rate and its table pitch is lowered one (two) octaves,
  so it plays back at real speed with less top end (16 kHz -> 8 kHz -> 4 kHz). The slot length codes are the v13 ones (5/6).
- key.txt = what is where; preview.wav = decoded back out of the images and played at the speed the pitch field gives.
"""
import os, sys, glob, re, importlib.util, hashlib
import numpy as np
from scipy.signal import resample_poly
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location('ws', os.path.join(HERE, 'rosetta_wave_proe.pyw'))
ws = importlib.util.module_from_spec(spec)
sys.argv = ['x']
spec.loader.exec_module(ws)
import proe_profile as P
R = ws.RATE
SRC = os.environ.get('PROE_WAV_DIR', 'wavs')                 # your WAVs
D10 = os.environ.get('D10_DIR', '')
OUT = os.path.join(HERE, '..', 'build', 'waves_long2')
MAXSLOT = 0x800 << 6                      # 4.10 s: the longest code the D-110 proved (8.19 s = half the wave space)


def take(f):
    x = ws.read_wav(f)
    x = x - np.mean(x)
    return x / (np.abs(x).max() + 1e-9)


def root_of(name):                       # "Arr1C5" -> C5 = 72, else C4
    m = re.search(r'([A-G]#?)(\d)(?!.*[A-G]#?\d)', os.path.splitext(name)[0])
    return ws.parse_note(m.group(1) + m.group(2)) if m else 60


def main():
    rom = ws.Rom()
    sounds = [(os.path.basename(f), take(f)) for f in glob.glob(SRC + '/Recording*.wav')]
    if D10:
        sounds += [(os.path.basename(f), take(f)) for f in glob.glob(D10 + '/*.wav')]
    sounds.sort(key=lambda s: -len(s[1]))

    # keep the rhythm kit (keys < 76) exactly as stock
    use = P.usage(rom.ctrl, np.fromfile(rom.paths['tones'], np.uint8))
    kit = set()
    for i, u in use.items():
        if any(int(m.group(1)) < 76 for w, _ in u for m in [re.search(r'\(key (\d+)\)', w)] if m):
            kit |= set(rom.linked(i))
    hosts = [i for i in range(128, 256) if i not in kit and i not in rom.parent]

    # fixed layout: the kit owns units 0x00-0x33. Long slots: 2 x 4.10 s = all of IC38, 2 x 1.02 s at 0x40-0x5F.
    # Every other wave above the kit is freed; 0x34-0x3F + 0x60-0x7F hold the parked (silent) table entries.
    by = {n: x for n, x in sounds}
    want = [('m6.wav', 2), ('Recording (214).wav', 2), ('Recording (226).wav', 4), ('Recording (228).wav', 4)]
    plan, key = [], []
    for (name, S), host in zip([w for w in want if w[0] in by], hosts):
        x = by[name]
        plan.append((host, name, x, (resample_poly(x, 1, S) if S > 1 else x)[:MAXSLOT], S))
    swaps = {h: y for h, _, _, y, _ in plan}
    pitches = {h: int(round(ws.root_to_pitch(root_of(n)) - 4096 * np.log2(S))) for h, n, _, _, S in plan}
    keep = kit | {j for h in swaps for j in rom.linked(h)}
    span = lambda j: range(rom.pos[j], rom.pos[j] + (1 << ((rom.lenb[j] >> 4) & 7)))
    free = {i for i in range(256) if i not in keep and any(u >= 0x34 for u in span(i))}
    files, lines = ws.build(rom, swaps, {}, OUT, True, None, {h: False for h in swaps}, free, pitches)
    ic37, ic38, c = (np.fromfile(os.path.join(OUT, f), np.uint8) for f in files)
    T = ws.TABLE_AT
    # the drum kit must come out untouched: its table entries and every byte of its audio
    for j in kit:
        assert bytes(c[T + 4 * j:T + 4 * j + 4]) == bytes(rom.ctrl[T + 4 * j:T + 4 * j + 4]), 'kit entry %d changed' % j
    ku = sorted({u for j in kit for u in span(j)})
    assert all(np.array_equal(ic37[u * 4096:(u + 1) * 4096], rom.ic8[u * 4096:(u + 1) * 4096]) for u in ku if u < 128), 'kit audio changed'
    print('drum kit: %d table entries + %d units of audio identical to stock' % (len(kit), len(ku)))
    prev, total = [], 0.0
    for h, n, x, y, S in plan:
        pos, e = int(c[T + 4 * h]), (int(c[T + 1 + 4 * h]) >> 4) & 7
        a, slot = pos * 0x800, 0x800 << e
        chip = ic37 if a < 0x40000 else ic38
        d = ws.log_to_lin(ws.rom_to_log(chip[(a % 0x40000) * 2:(a % 0x40000 + min(len(y), slot)) * 2])) / ws.FULL
        prev += [resample_poly(d, S, 1) if S > 1 else d, np.zeros(R // 3)]
        real = min(len(x), slot * S) / R
        total += real
        key.append('PCM WAVE 2-%3d  (#%d)  %-22s %5.2f s of sound, slot %.2f s at 0x%05X (%s), rate %s, root %s'
                   % (h - 127, h, n, real, slot / R, a, 'IC37' if a < 0x40000 else 'IC38',
                      {1: 'full 32 kHz', 2: 'half (16 kHz)', 4: 'quarter (8 kHz)'}[S], ws.note_name(root_of(n))))
    ws.write_wav(os.path.join(OUT, 'preview.wav'), np.concatenate(prev))
    open(os.path.join(OUT, 'key.txt'), 'w').write(
        'LONG2: %d sounds, %.1f s of sound in all. Drum kit = stock. Everything else freed (silent).\n'
        'Play: a PCM tone (XYLOPHONE) -> SYNTH EDIT -> PCM WAVE 2-n, ENVELOPE SUSTAIN up, hold the root key.\n\n'
        % (len(plan), total) + '\n'.join(key) + '\n\n' + '\n'.join(lines) + '\n')
    print('\n'.join(key))
    print('total %.1f s of sound' % total)
    for f in files:
        print('  %-28s md5 %s' % (f, hashlib.md5(open(os.path.join(OUT, f), 'rb').read()).hexdigest()))


if __name__ == '__main__':
    main()
