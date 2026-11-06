"""JUNO CHORUS for the CK-34 reverb chip: replaces reverb mode 3 (TAP DELAY) in IC13 with 64 chorus positions.

  python -I gen_chorus.py     -> ../build/chorus/IC13_chorus_W27C256.bin + preview WAVs (your ears decide)

The chip has no LFO and fixed delay offsets (see boss_reverb.py), so the sweep is done by switching programs:
  position p (0-63) = program p // 4 (via LEVEL + TIME bit 2) and sawBits p % 4 (TIME bits 0-1), each holding a
  right tap of D(p) and a left tap of D(63 - p) frames (opposite sweeps, like the Juno's stereo chorus).
  Juno-60 chorus BBD delay range is about 1.7-5.3 ms = 53-171 frames at 32 kHz.
Stock IC28: any TAP DELAY panel setting picks a fixed position = a static stereo chorus (no movement).
A later IC28 patch steps the position from the 10 ms tick = the moving chorus. Previews render both, plus a smooth
float reference, so the cost of 10 ms stepping can be heard before anything is burned.
"""
import math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import boss_reverb as BR

OUT = os.path.join(HERE, '..', 'build', 'chorus')
FS = 32000
D_MIN, D_MAX = 53, 171
NPOS = 64


def snake(c):
    """latch combination c (0x0800 bits 0-1 = c >> 4, 0x0400 bits 0-3 = c & 15) -> sweep position. Rows of 16 run
    forwards then backwards, so every one-position step changes one latch only (the IC28 stepper writes them one
    after the other: with plain binary order the chip saw position 0 / 31 for an instant at 15<->16 = a click)."""
    return (c & ~15) | ((c & 15) ^ (15 if c & 16 else 0))      # any number of rows (v5: 8 rows = 128)


def delay(p):
    return D_MIN + round((D_MAX - D_MIN) * p / (NPOS - 1))


def chorus_programs():
    progs = []
    for k in range(16):
        st = {0: BR.step_write_input(0), 32: BR.step_write_input(0x2000)}    # R buffer at 0, L buffer at 0x2000
        for s in range(4):
            p = k * 4 + s
            st[40 + s] = BR.step_tap(delay(p), 1 << s, clear=(s == 0))                    # out R (latched at 47)
            st[48 + s] = BR.step_tap(delay(NPOS - 1 - p) + 0x2000, 1 << s, clear=(s == 0))  # out L (latched at 56)
        progs.append(BR.program(st))
    return progs


def params(p):
    """position -> (mode, time, level) the CK-34 has to set"""
    k, s = divmod(p, 4)
    return 3, (k & 1) * 4 + s, k >> 1


def build_rom(stock):
    rom = bytearray(stock)
    blob = b''.join(chorus_programs())
    assert len(blob) == 0x1000
    rom[0x3000:0x4000] = blob
    if len(rom) == 0x8000:
        rom[0x7000:0x8000] = blob                     # the mirror
    return bytes(rom)


def test_signal(secs=5.0):
    """C minor 9 pad: band-limited saws, slightly detuned pair per note (like JUNO DETUNE)."""
    notes = [130.81, 155.56, 196.00, 233.08, 293.66]
    n = int(FS * secs)
    out = [0.0] * n                                   # polyBLEP saws
    for f0 in notes:
        for det in (1.0, 1.0035):
            f, ph = f0 * det / FS, 0.0
            for i in range(n):
                t = ph
                v = 2 * t - 1
                if t < f:
                    x = t / f; v -= x + x - x * x - 1
                elif t > 1 - f:
                    x = (t - 1) / f; v -= x * x + x + x + 1
                out[i] += v
                ph += f
                if ph >= 1:
                    ph -= 1
    env = [min(1, i / (0.3 * FS)) * min(1, (n - i) / (0.5 * FS)) for i in range(n)]
    peak = max(abs(x) for x in out)
    return [int(18000 * out[i] / peak * env[i]) for i in range(n)]


def render_chip(rom, sig, lfo_hz=None, step_ms=10.0, fixed=32):
    c = BR.Chip(rom)
    c.set_params(*params(fixed))
    tick = int(FS * step_ms / 1000)
    L, R = [], []
    for i, x in enumerate(sig):
        if lfo_hz and i % tick == 0:
            ph = (i / FS * lfo_hz) % 1.0
            tri = 2 * ph if ph < 0.5 else 2 - 2 * ph
            c.set_params(*params(round(tri * (NPOS - 1))))
        l, r = c.frame(x, x)
        L.append(x + 2 * l)                           # dry + wet (the chip halves its input)
        R.append(x + 2 * r)
    return L, R


def render_float(sig, lfo_hz):
    """reference: smooth, interpolated chorus with the same range"""
    L, R = [], []
    buf = sig
    for i, x in enumerate(sig):
        ph = (i / FS * lfo_hz) % 1.0
        tri = 2 * ph if ph < 0.5 else 2 - 2 * ph
        out = []
        for d in (D_MIN + (D_MAX - D_MIN) * tri, D_MAX - (D_MAX - D_MIN) * tri):
            j = i - d
            j0 = math.floor(j)
            a = j - j0
            y = (buf[j0] * (1 - a) + buf[j0 + 1] * a) if j0 >= 0 else 0
            out.append(y)
        R.append(x + out[0]); L.append(x + out[1])
    return L, R


def wav(path, L, R):
    peak = max(max(abs(v) for v in L), max(abs(v) for v in R), 1)
    g = min(1.0, 30000 / peak)
    data = b''.join(struct.pack('<hh', int(l * g), int(r * g)) for l, r in zip(L, R))
    hdr = b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 2, FS, FS * 4, 4, 16)
    with open(path + '.tmp', 'wb') as f:
        f.write(hdr + b'data' + struct.pack('<I', len(data)) + data)
    os.replace(path + '.tmp', path)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    stock = open(os.path.join(HERE, '..', 'dumps', 'ck34_ic13_reverb_R15179917_HN623257.bin'), 'rb').read()
    rom = build_rom(stock)
    p = os.path.join(OUT, 'IC13_chorus_W27C256.bin')
    open(p + '.tmp', 'wb').write(rom); os.replace(p + '.tmp', p)
    import hashlib
    print('IC13_chorus_W27C256.bin md5', hashlib.md5(rom).hexdigest(), '(modes 0-2 stock, mode 3 = chorus)')
    assert rom[:0x3000] == stock[:0x3000]
    # sanity: an impulse at a fixed position comes back on the right frames
    c = BR.Chip(rom); c.set_params(*params(10))
    resp = [c.frame(16000, 16000) if i == 0 else c.frame(0, 0) for i in range(400)]
    hits = [(i, l, r) for i, (l, r) in enumerate(resp) if l or r]
    print('position 10: R tap at', delay(10), 'L tap at', delay(53), '-> chip:', hits)
    sig = test_signal()
    wav(os.path.join(OUT, '1_dry.wav'), sig, sig)
    wav(os.path.join(OUT, '2_static_stock_ic28.wav'), *render_chip(rom, sig, None))
    wav(os.path.join(OUT, '3_chorus_I_0.5Hz_chip_10ms_steps.wav'), *render_chip(rom, sig, 0.513))
    wav(os.path.join(OUT, '4_chorus_II_0.86Hz_chip_10ms_steps.wav'), *render_chip(rom, sig, 0.863))
    wav(os.path.join(OUT, '5_chorus_I_smooth_reference.wav'), *render_float(sig, 0.513))
    print('previews in', os.path.abspath(OUT))
