"""Two hardware test banks from JSW's own recordings (never shipped: output goes to ../build/, which git ignores).

  python -I gen_test_banks.py

FILL  (../build/waves_fill/)  every wave slot of IC37 + IC38 gets one of your takes, same slot, same length.
       IC28 stays stock, so this needs only the two W27C040s. Every PRO-E tone and drum now plays your sounds.
LONG  (../build/waves_long/)  the FILL bank plus two long waves in bigger slots (new IC28 table entries, the D-110 v13 way):
         #128 (PCM bank 2 wave 1, rhythm key 76)  <- Recording (226), 3.99 s, slot 4.10 s (length code 6)
         #161 (PCM bank 2 wave 34, rhythm key 92) <- Recording (227), first 2.04 s, slot 2.05 s (code 5)
       IC38 = 8.19 s in all: 4.10 + 2.05 leaves 2.05 s for the freed effect waves (two 4.10 s slots leave none).
       Stock never uses more than 1.02 s. To make room, the other IC38 waves (the sound effects) are freed.
Each folder gets key.txt (wave -> take) and preview.wav (decoded back out of the built images, not the source).
"""
import os, sys, glob, importlib.util
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location('ws', os.path.join(HERE, 'rosetta_wave_proe.pyw'))
ws = importlib.util.module_from_spec(spec)
sys.argv = ['x']
spec.loader.exec_module(ws)
R = ws.RATE
SRC = os.environ.get('PROE_WAV_DIR', 'wavs')                 # your WAVs
SNAPS = sorted(glob.glob(SRC + '/rosetta_rom/recordings/*.wav'))
INST = sorted(glob.glob(SRC + '/recordings_wav/sound samples inst/*.wav'))
LONGS = {os.path.basename(f): f for f in glob.glob(SRC + '/recordings_wav/Recording*.wav')}
BUILD = os.path.join(HERE, '..', 'build')


def take(f):
    x = ws.read_wav(f)
    x = x - np.mean(x)
    return x / (np.abs(x).max() + 1e-9)


def decoded(chip, a, n):
    lo = (a % 0x40000) * 2
    return ws.log_to_lin(ws.rom_to_log(chip[lo:lo + n * 2])) / ws.FULL


def preview(out, rom7, rom8, picks):
    """decode every changed wave back out of the built images, 0.25 s gaps"""
    parts = []
    for i, (a, n) in picks:
        chip = rom8 if a < 0x40000 else rom7
        parts += [decoded(chip, a, n), np.zeros(R // 4)]
    ws.write_wav(os.path.join(out, 'preview.wav'), np.concatenate(parts))


def fill_bank():
    rom = ws.Rom()
    snaps = [take(f) for f in SNAPS]
    tonal = [take(f) for f in INST] + [take(f) for f in sorted(LONGS.values())]
    names = [os.path.basename(f) for f in SNAPS], [os.path.basename(f) for f in INST] + sorted(LONGS)
    # one take per distinct wave start: the big whole-region loops (#119-127) contain most other waves, and render()
    # writes big slots first, so every smaller wave inside ends up with its own take
    primaries = sorted({min(rom.linked(i)) for i in range(256)})
    swaps, key, k1, k2 = {}, [], 0, 0
    for i in primaries:
        a, n, loop = rom.ent[i]
        if loop:                                # looped slots: a steady piece of a tonal take (the slot loops as a whole)
            x = tonal[k2 % len(tonal)]; src = names[1][k2 % len(tonal)]; k2 += 1
            mid = max(0, len(x) // 3 - n // 2)
            seg = x[mid:mid + n]
            fade = min(256, n // 8)             # soft seam so the whole-slot loop doesn't click
            seg = np.concatenate([seg, np.zeros(max(0, n - len(seg)))])
            seg[:fade] *= np.linspace(0, 1, fade); seg[-fade:] *= np.linspace(1, 0, fade)
            swaps[i] = seg
        else:
            x = snaps[k1 % len(snaps)][:n].copy(); src = names[0][k1 % len(snaps)]; k1 += 1
            if len(x) == n:                     # same slot: a take longer than the slot is cut, with a short fade
                f = min(512, n // 8); x[-f:] *= np.linspace(1, 0, f)
            swaps[i] = x
        key.append('%3d %-8s %s %5.2fs %-4s <- %s   (%s)' % (i, rom.names[i], rom.chip(i), n / R, 'loop' if loop else '', src, rom.used[i]))
    out = os.path.join(BUILD, 'waves_fill')
    files, lines = ws.build(rom, swaps, {}, out)
    open(os.path.join(out, 'key.txt'), 'w').write('FILL bank: every slot = your own take, IC28 stock\n\n' + '\n'.join(key) + '\n')
    ic8, ic7 = (np.fromfile(os.path.join(out, f), np.uint8) for f in files[:2])
    preview(out, ic7, ic8, [(i, rom.ent[i][:2]) for i in primaries[:40:3]])
    return out, files, lines, len(primaries)


def long_bank(fill_dir, fill_files):
    rom = ws.Rom(ic8=os.path.join(fill_dir, fill_files[0]), ic7=os.path.join(fill_dir, fill_files[1]))
    l1 = take(LONGS['Recording (226).wav'])                  # 3.99 s -> 4.10 s slot (code 6)
    l2 = take(LONGS['Recording (227).wav'])[:int(2.04 * R)]  # first 2.04 s of 2.62 s -> 2.05 s slot (code 5)
    f = 2048; l2[-f:] *= np.linspace(1, 0, f)
    swaps = {128: l1, 161: l2}
    keep = set(rom.linked(128)) | set(rom.linked(161))
    free = {i for i in range(256) if rom.pos[i] >= 0x80 and i not in keep}
    out = os.path.join(BUILD, 'waves_long')
    files, lines = ws.build(rom, swaps, {}, out, True, {128: 60, 161: 60}, None, free)
    ic8, ic7, c = (np.fromfile(os.path.join(out, f), np.uint8) for f in files)
    T = ws.TABLE_AT
    ent = {i: (int(c[T + 4 * i]) * 0x800, 0x800 << ((int(c[T + 1 + 4 * i]) >> 4) & 7)) for i in (128, 161)}
    open(os.path.join(out, 'key.txt'), 'w').write(
        'LONG bank = FILL bank + two long waves (IC28 table changed: burn IC28 on the pin-22 adapter)\n\n'
        + '\n'.join('#%d -> wave pos 0x%05X, slot %.2f s, root C4' % (i, a, n / R) for i, (a, n) in ent.items())
        + '\n\nThe other IC38 waves (sound effects) are freed = silent in this test bank.\n\n' + '\n'.join(lines) + '\n')
    preview(out, ic7, ic8, [(i, ent[i]) for i in (128, 161)])
    return out, files, lines, ent


if __name__ == '__main__':
    fd, ff, fl, n = fill_bank()
    print('FILL: %d slots filled -> %s' % (n, fd)); print('  ' + fl[-1])
    ld, lf, ll, ent = long_bank(fd, ff)
    print('LONG ->', ld)
    for i, (a, n) in ent.items():
        print('  #%d at 0x%05X, %.2f s' % (i, a, n / R))
    print('  ' + ll[-1])
    import hashlib
    for d, fs in ((fd, ff), (ld, lf)):
        for f in fs:
            print('  %-28s md5 %s' % (f, hashlib.md5(open(os.path.join(d, f), 'rb').read()).hexdigest()))
