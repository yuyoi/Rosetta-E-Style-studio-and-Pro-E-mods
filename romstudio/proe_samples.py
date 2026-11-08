"""Long samples for the PRO-E (CK-34 voice board): your WAVs -> IC37 / IC38 wave ROMs + the IC28 wave table.

Same method as wave_studio/gen_long2.py (the bank in her since 2026-11-07):
- the rhythm kit (every wave a key < 76 plays) keeps its stock audio and table entries, byte for byte;
- LONG mode frees every other wave, so a few long sounds fit (up to 4.10 s per slot, about 12 s in all);
- a sound longer than its slot is stored at half (16 kHz) or quarter (8 kHz) rate and its table pitch goes down one
  (two) octaves, so it plays at real speed and pitch with less top end;
- each sound replaces one wave: an SFX pad wave (#128 = Laughing = SFX key 76) or a PCM WAVE 2-n you pick in SYNTH EDIT.
The GUI (romstudio.pyw, SAMPLES tab) only calls this module.
"""
import importlib.util, os, re, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
WS_DIR = os.path.join(ROOT, 'wave_studio')
MAXSLOT = 0x800 << 6                 # 131072 samples = 4.10 s at 32 kHz: the longest slot code the D-110 proved
RATES = {1: 'full 32 kHz', 2: 'half 16 kHz', 4: 'quarter 8 kHz'}
_ws = None


def ws():
    """the Rosetta Wave PRO-E module (codec, table layout, build), loaded once"""
    global _ws
    if _ws is None:
        sys.path.insert(0, WS_DIR)
        spec = importlib.util.spec_from_file_location('rosetta_wave_proe', os.path.join(WS_DIR, 'rosetta_wave_proe.pyw'))
        m = importlib.util.module_from_spec(spec)
        argv, cwd = sys.argv, os.getcwd()
        sys.argv = ['x']
        try:
            spec.loader.exec_module(m)
        finally:
            sys.argv = argv
            os.chdir(cwd)                # the module chdirs to its own folder
        _ws = m
    return _ws


def load(path):
    """WAV -> mono float at 32 kHz, DC removed, peak 1.0"""
    x = ws().read_wav(path)
    x = x - np.mean(x)
    return x / (np.abs(x).max() + 1e-9)


def root_of(name):
    """'Arr1C5.wav' -> 72; no note in the name -> C4 = 60"""
    m = re.search(r'([A-G]#?)(\d)(?!.*[A-G]#?\d)', os.path.splitext(os.path.basename(name))[0])
    return ws().parse_note(m.group(1) + m.group(2)) if m else 60


def auto_rate(n):
    """smallest rate divider (1, 2, 4) that fits n samples into one 4.10 s slot"""
    for s in (1, 2, 4):
        if n <= MAXSLOT * s:
            return s
    return 4


class Sampler:
    def __init__(self):
        W = ws()
        self.rom = W.Rom()
        self.R = W.RATE
        use = W.PROE.usage(self.rom.ctrl, np.fromfile(self.rom.paths['tones'], np.uint8))
        self.usage = use
        kit = set()
        for i, u in use.items():
            if any(int(m.group(1)) < 76 for w, _ in u for m in [re.search(r'\(key (\d+)\)', w)] if m):
                kit |= set(self.rom.linked(i))
        self.kit = kit
        self.hosts = [i for i in range(128, 256) if i not in kit and i not in self.rom.parent]

    def host_label(self, i):
        sfx = sorted({int(m.group(1)) for w, _ in self.usage.get(i, []) for m in [re.search(r'\(key (\d+)\)', w)] if m})
        name = (self.rom.names[i] or 'WAVE%03d' % i).strip()
        where = ('SFX key %s' % '/'.join(map(str, sfx))) if sfx else 'tone wave'
        return 'PCM WAVE 2-%-3d #%d  %s  (%s)' % (i - 127, i, name, where)

    def span(self, j):
        return range(self.rom.pos[j], self.rom.pos[j] + (1 << ((self.rom.lenb[j] >> 4) & 7)))

    def plan(self, slots):
        """slots: [{'wav', 'host', 'rate' (0 = auto), 'root' (None = from the file name)}] ->
        [(host, name, x, y, S, root)]: y = what goes into the ROM (resampled, cut to one slot)"""
        from scipy.signal import resample_poly
        out, used = [], set()
        for s in slots:
            h = s['host']
            if h in used:
                raise ValueError('two sounds on wave #%d' % h)
            if h in self.kit:
                raise ValueError('wave #%d belongs to the drum kit (kept stock)' % h)
            used.add(h)
            x = load(s['wav'])
            S = s.get('rate') or auto_rate(len(x))
            y = (resample_poly(x, 1, S) if S > 1 else x)[:MAXSLOT]
            root = s.get('root')
            out.append((h, os.path.basename(s['wav']), x, y, S, root_of(s['wav']) if root is None else root))
        return out

    def build(self, slots, out, long_mode=True, log=print):
        """-> (files {chip: path}, key lines, preview wav path). Checks: the kit comes out byte-identical."""
        W, rom = ws(), self.rom
        plan = self.plan(slots)
        swaps = {h: y for h, _, _, y, _, _ in plan}
        pitches = {h: int(round(W.root_to_pitch(r) - 4096 * np.log2(S))) for h, _, _, _, S, r in plan}
        keep = self.kit | {j for h in swaps for j in rom.linked(h)}
        free = {i for i in range(256) if i not in keep and any(u >= 0x34 for u in self.span(i))} if long_mode else set()
        files, lines = W.build(rom, swaps, {}, out, True, None, {h: False for h in swaps}, free, pitches)
        ic37, ic38, c = (np.fromfile(os.path.join(out, f), np.uint8) for f in files)
        T = W.TABLE_AT
        for j in self.kit:
            assert bytes(c[T + 4 * j:T + 4 * j + 4]) == bytes(rom.ctrl[T + 4 * j:T + 4 * j + 4]), 'kit entry %d changed' % j
        ku = sorted({u for j in self.kit for u in self.span(j)})
        assert all(np.array_equal(ic37[u * 4096:(u + 1) * 4096], rom.ic8[u * 4096:(u + 1) * 4096]) for u in ku if u < 128), \
            'kit audio changed'
        log('drum kit: %d table entries + %d units of audio identical to stock' % (len(self.kit), len(ku)))
        from scipy.signal import resample_poly
        prev, key, total = [], [], 0.0
        for h, n, x, y, S, r in plan:
            pos, e = int(c[T + 4 * h]), (int(c[T + 1 + 4 * h]) >> 4) & 7
            a, slot = pos * 0x800, 0x800 << e
            chip = ic37 if a < 0x40000 else ic38
            d = W.log_to_lin(W.rom_to_log(chip[(a % 0x40000) * 2:(a % 0x40000 + min(len(y), slot)) * 2])) / W.FULL
            prev += [resample_poly(d, S, 1) if S > 1 else d, np.zeros(self.R // 3)]
            real = min(len(x), slot * S) / self.R
            total += real
            key.append('PCM WAVE 2-%3d  (#%d)  %-22s %5.2f s of sound, slot %.2f s at 0x%05X (%s), rate %s, root %s'
                       % (h - 127, h, n, real, slot / self.R, a, 'IC37' if a < 0x40000 else 'IC38', RATES[S], W.note_name(r)))
        pv = os.path.join(out, 'preview.wav')
        if prev:
            W.write_wav(pv, np.concatenate(prev))
        with open(os.path.join(out, 'key.txt'), 'w') as f:
            f.write('%d sounds, %.1f s of sound in all. Drum kit = stock.%s\n'
                    'Play: SFX pad, or a PCM tone -> SYNTH EDIT -> PCM WAVE 2-n, ENVELOPE SUSTAIN up, hold the root key.\n\n'
                    % (len(plan), total, ' Every other wave freed (silent).' if long_mode else '')
                    + '\n'.join(key) + '\n\n' + '\n'.join(lines) + '\n')
        return dict(zip(('IC37', 'IC38', 'IC28'), (os.path.join(out, f) for f in files))), key, pv
