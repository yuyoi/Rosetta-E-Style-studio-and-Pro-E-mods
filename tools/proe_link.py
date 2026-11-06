"""PRO-E remote link (Rosetta OS v0.7): drive her over MIDI, read her screen, record her through the Focusrite.

  py -3.10 proe_link.py ping | screen | leds | key NAME|CODE | dial N | peek ADDR N | poke ADDR VAL | ck HEX..
  py -3.10 proe_link.py note NOTE [secs] [wav]     play SOLO through the CK-34 directly and record it
  py -3.10 proe_link.py lab                          run the FX lab tests (wet-only bit, 8 modes, moving chorus)
  py -3.10 proe_link.py chiplab                      IC13 mode 7 chip tests (filters that oscillate, read timing)

Wiring: Focusrite MIDI OUT -> PRO-E MIDI IN, PRO-E MIDI OUT -> Focusrite MIDI IN, PRO-E outputs -> Focusrite rear
line ins 3/4 (ASIO channels 2/3; WDM/MME only show inputs 1/2), the HR-GP5 recipe.
Protocol (synth_v07_fx.asm): F0 7D 52 00 00 cmd args F7. Her MIDI ISR overwrites the 3rd byte after F0 and her parser
reads the 4th as a Roland command, so both are 00 here. Replies: F0 7D 52 cmd nibbles F7.
"""
import os, sys, time
os.environ.setdefault('SD_ENABLE_ASIO', '1')
import mido

PORT = 'Focusrite USB MIDI'
KEYS = {'cursor': 0x5D, 'parameter': 0x05}
FS = 48000
CH = (0, 1)                 # ASIO inputs: she is on the front inputs 1/2 (measured 2026-11-05)


def ports():
    i = [n for n in mido.get_input_names() if PORT.lower() in n.lower()]
    o = [n for n in mido.get_output_names() if PORT.lower() in n.lower()]
    if not i or not o:
        sys.exit('no %r MIDI port (in %s, out %s)' % (PORT, mido.get_input_names(), mido.get_output_names()))
    return mido.open_input(i[0]), mido.open_output(o[0])


class Link:
    def __init__(self):
        self.i, self.o = ports()

    def send(self, cmd, *args):
        for _ in self.i.iter_pending():
            pass
        self.o.send(mido.Message('sysex', data=[0x7D, 0x52, 0x00, 0x00, cmd] + list(args)))

    def reply(self, cmd, timeout=1.0):
        t = time.time() + timeout
        while time.time() < t:
            for m in self.i.iter_pending():
                if m.type == 'sysex' and list(m.data[:3]) == [0x7D, 0x52, cmd]:
                    return list(m.data[3:])
            time.sleep(0.005)
        return None

    @staticmethod
    def bytes_of(nib):
        return bytes((nib[2 * k] << 4) | nib[2 * k + 1] for k in range(len(nib) // 2))

    def ping(self):
        self.send(0x7F)
        r = self.reply(0x7F)
        return bytes(r).decode() if r else None

    def screen(self):
        self.send(0x10)
        r = self.reply(0x10)
        if not r:
            return None
        t = self.bytes_of(r).decode('latin1')
        return t[:16], t[16:]

    def leds(self):
        self.send(0x11)
        r = self.reply(0x11)
        return self.bytes_of(r) if r else None

    def key(self, code, hold=0.05):
        self.send(0x01, code)
        time.sleep(hold)
        self.send(0x02, code)
        time.sleep(0.06)

    def dial(self, n):
        while n:
            d = max(-60, min(60, n))
            self.send(0x03, 64 + d)
            n -= d
            time.sleep(0.03)

    def peek(self, addr, n=1):
        self.send(0x12, addr >> 12 & 15, addr >> 8 & 15, addr >> 4 & 15, addr & 15, n)
        r = self.reply(0x12)
        return self.bytes_of(r) if r else None

    def poke(self, addr, v):
        self.send(0x13, addr >> 12 & 15, addr >> 8 & 15, addr >> 4 & 15, addr & 15, v >> 4, v & 15)

    def ck(self, data):
        """raw bytes to the CK-34 (MIDI or SysEx with F0/F7)"""
        self.send(0x20, *[x for b in data for x in (b >> 4, b & 15)])
        time.sleep(0.01 + len(data) * 0.0004)

    def dt1(self, addr, data):
        body = list(addr) + list(data)
        self.ck([0xF0, 0x41, 0x10, 0x16, 0x12] + body + [(-sum(body)) & 0x7F, 0xF7])

    def fx(self, mode, t, l):
        self.dt1([0x10, 0x00, 0x01], [mode, t, l])

    def part_fx(self, switch, part=0x26):          # 0x26 SOLO, 0x16 LOWER, 0x06 M.BASS
        self.dt1([0x03, 0x00, part], [switch])


def record(secs, play=None):
    """record the Focusrite rear ins 3/4 while play() runs; returns (L, R) numpy arrays"""
    import numpy as np, sounddevice as sd
    dev = [k for k, d in enumerate(sd.query_devices()) if 'focusrite' in d['name'].lower()
           and d['max_input_channels'] >= 4 and 'asio' in sd.query_hostapis(d['hostapi'])['name'].lower()]
    if not dev:
        sys.exit('no Focusrite ASIO input with 4+ channels')
    rec = sd.rec(int(secs * FS), samplerate=FS, channels=4, device=dev[0], dtype='float32')
    if play:
        play()
    sd.wait()
    return rec[:, CH[0]].copy(), rec[:, CH[1]].copy()


def wav(path, L, R):
    import numpy as np, struct
    x = np.stack([L, R], 1)
    pk = max(1e-9, float(np.abs(x).max()))
    d = (x / pk * 30000).astype('<i2').tobytes()
    with open(path, 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(d)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 2, FS, FS * 4, 4, 16)
                + b'data' + struct.pack('<I', len(d)) + d)


def note(lk, n=60, secs=0.4, vel=100, ch=3):
    lk.ck([0x90 | ch, n, vel])
    time.sleep(secs)
    lk.ck([0x80 | ch, n, 0])


def env(L, R, ms=10):
    import numpy as np
    x = np.abs(L) + np.abs(R)
    k = int(FS * ms / 1000)
    return np.array([x[i:i + k].mean() for i in range(0, len(x) - k, k)])


def lab(lk):
    """the tests that need her: wet-only bit, IC13 A14 (8 modes), moving chorus. Writes WAVs + a report."""
    import numpy as np
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'lab')
    os.makedirs(out, exist_ok=True)
    rep = []
    print('ping:', lk.ping())
    lk.fx(2, 2, 6)                                   # DELAY 375 ms, feedback 63 %
    res = {}
    for sw, name in ((1, 'dry+fx'), (2, 'fx only'), (0, 'dry'), (3, 'test3')):
        lk.part_fx(sw)
        time.sleep(0.2)
        L, R = record(1.5, lambda: note(lk, 60, 0.15))
        wav(os.path.join(out, 'wet_%d.wav' % sw), L, R)
        e = env(L, R)
        res[sw] = (e[:25].max(), e[34:45].max())     # 0-250 ms (dry note), 340-450 ms (first echo)
        rep.append('reverb switch %d (%s): note level %.4f, echo level %.4f' % (sw, name, *res[sw]))
    dry_on, fx_on = res[1]
    w_dry, w_fx = res[2]
    rep.append('WET ONLY WORKS' if w_dry < 0.15 * dry_on and w_fx > 0.5 * fx_on else 'wet-only: check the WAVs')
    lk.part_fx(1)
    for m in (6, 2):                                 # 6 = stock HALL in IC13's upper half, 2 = DELAY
        lk.fx(m, 4 if m == 6 else 2, 5 if m == 6 else 6)
        time.sleep(0.2)
        L, R = record(1.5, lambda: note(lk, 60, 0.15))
        wav(os.path.join(out, 'mode_%d.wav' % m), L, R)
        e = env(L, R)
        res['m%d' % m] = e
    e6, e2 = res['m6'], res['m2']
    corr = float(np.corrcoef(e6[:140], e2[:140])[0, 1])
    rep.append('mode 6 vs mode 2 envelope correlation %.2f: %s' % (corr, 'SAME = A14 not wired (4 modes)' if corr > 0.9
               else 'DIFFERENT = 8 modes work (IC13 A14 = mode bit 2)'))
    lk.fx(1, 2, 4)                                   # Chorus I
    time.sleep(0.2)
    L, R = record(4.0, lambda: note(lk, 57, 3.5))
    wav(os.path.join(out, 'chorus_I.wav'), L, R)
    lk.fx(1, 0, 4)                                   # level 4 + time 0: static (rate table 0.25 Hz, still moving)
    for line in rep:
        print(line)
    open(os.path.join(out, 'report.txt'), 'w').write('\n'.join(rep) + '\n')


CHIPLAB = ['OFF', 'REF line=input', 'lofi pole a1/2', 'lofi pole a3/4', 'pole state@0x2000', 'v2 filter (osc?)',
           'v2 stage1', 'same-frame read', 'e1 taps+load', '2 poles via shifter']


def chiplab(lk):
    """IC13 mode 7 tests (gen_fx.lab_block): idle (self-oscillation) + the 187 ms echo of a short note vs REF.
    A test that oscillates is cut after 0.4 s and she goes back to Plate."""
    import numpy as np
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'lab')
    os.makedirs(out, exist_ok=True)
    rep, ref = [], None
    lk.part_fx(1)
    for k, name in enumerate(CHIPLAB):
        lk.fx(7, (k & 1) * 4, k >> 1)
        time.sleep(0.4)
        L, R = record(0.4)
        idle = 20 * np.log10(np.concatenate([L, R]).std() + 1e-12)
        if idle > -60:
            lk.fx(0, 1, 6)
            X = np.abs(np.fft.rfft(L)); f = np.fft.rfftfreq(len(L), 1 / FS)
            rep.append('k%d %-20s OSCILLATES: idle %.1f dB at %.0f Hz' % (k, name, idle, f[np.argmax(X[1:]) + 1]))
            print(rep[-1]); time.sleep(1.0); continue
        L, R = record(0.9, lambda: (time.sleep(0.1), note(lk, 72, 0.06)))
        wav(os.path.join(out, 'chiplab_k%d.wav' % k), L, R)
        x = np.abs(L) + np.abs(R)
        on = int(np.argmax(x > 0.3 * x.max()))
        d0 = x[on:on + int(0.05 * FS)].mean()
        w = (L + R)[on + int(0.187 * FS) - 200:on + int(0.187 * FS) + int(0.05 * FS)]
        ech = np.abs(w).mean() * 0.5
        W = np.abs(np.fft.rfft(w * np.hanning(len(w)))) ** 2; f = np.fft.rfftfreq(len(w), 1 / FS)
        hf = 10 * np.log10(W[f > 4000].sum() / (W.sum() + 1e-20) + 1e-12)
        if k == 1:
            ref = ech
        rel = 20 * np.log10(ech / ref + 1e-12) if ref else 0
        rep.append('k%d %-20s idle %6.1f dB  echo %6.1f dB vs REF  (dry %.4f)  echo >4k %6.1f dB' % (k, name, idle, rel, d0, hf))
        print(rep[-1])
    lk.fx(0, 1, 6)
    open(os.path.join(out, 'chiplab.txt'), 'w').write('\n'.join(rep) + '\n')


CANCEL_G = [round(0.5 * 1.06 ** n, 4) for n in range(24)]        # = gen_fx.CANCEL_G (IC13 mode 7, k10-15)


def cancel(lk, n=57):
    """FULL WET test: SOLO on DRY+FX, IC13 mode 7 k10-15 play -g * input. The gain that nulls her dry sound deepest
    wins; low (<500 Hz) vs high (>3 kHz) null shows whether the chip output is a frame late."""
    import numpy as np
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'lab')
    os.makedirs(out, exist_ok=True)
    lk.part_fx(1)
    def take(t, l):
        lk.fx(7, t, l)
        time.sleep(0.3)
        L, R = record(1.3, lambda: (time.sleep(0.1), note(lk, n, 1.0)))
        x = np.concatenate([L[int(0.35 * FS):int(0.95 * FS)], R[int(0.35 * FS):int(0.95 * FS)]])
        X = np.abs(np.fft.rfft(L[int(0.35 * FS):int(0.95 * FS)] + R[int(0.35 * FS):int(0.95 * FS)])) ** 2
        f = np.fft.rfftfreq(int(0.6 * FS), 1 / FS)
        return x.std(), X[f < 500].sum(), X[f > 3000].sum()
    ref = [take(0, 0) for _ in range(2)]                 # mode 7 OFF = dry only
    r0, lo0, hi0 = [sum(v) / 2 for v in zip(*ref)]
    rep = ['dry reference rms %.5f' % r0]
    best = None
    for i, g in enumerate(CANCEL_G):
        k, sb = 10 + i // 4, i % 4
        rms, lo, hi = take((k & 1) * 4 + sb, k >> 1)
        db = 20 * np.log10(rms / r0 + 1e-12)
        rep.append('g %.3f  total %6.1f dB  <500Hz %6.1f dB  >3k %6.1f dB' % (g, db, 10 * np.log10(lo / lo0 + 1e-12),
                                                                            10 * np.log10(hi / hi0 + 1e-12)))
        print(rep[-1])
        if best is None or db < best[1]:
            best = (g, db)
    lk.fx(0, 1, 6)
    rep.append('BEST g %.3f: %.1f dB (0 dB = no cancel, -20 dB = usable, -40 dB = full wet)' % best)
    print(rep[-1])
    open(os.path.join(out, 'cancel.txt'), 'w').write('\n'.join(rep) + '\n')


CANCEL_G2 = [round(1.13 * 1.05 ** n, 4) for n in range(8)]      # = gen_fx.CANCEL_G2
CANCEL_T = ['now', 'x[n-1]', '2x[n]-x[n-1]']


def lab2(lk, n=57):
    """IC13 LAB round 2 (gen_fx.lab_block): k1/k2 fixed low-pass (stable?), k3 wet-path polarity, k4-15 cancel
    (timing x sign x 8 gains) with SOLO on DRY+FX. Oscillating tests are cut after 0.4 s. Report: build/lab/lab2.txt"""
    import numpy as np
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'lab')
    os.makedirs(out, exist_ok=True)
    rep = []
    lk.part_fx(1)

    def guard(t, l, name):
        lk.fx(7, t, l)
        time.sleep(0.35)
        L, R = record(0.3)
        idle = 20 * np.log10(np.concatenate([L, R]).std() + 1e-12)
        if idle > -60:
            lk.fx(0, 1, 6)
            X = np.abs(np.fft.rfft(L)); f = np.fft.rfftfreq(len(L), 1 / FS)
            rep.append('%-26s OSCILLATES: idle %.1f dB at %.0f Hz' % (name, idle, f[np.argmax(X[1:]) + 1]))
            print(rep[-1]); time.sleep(0.8)
            return False
        return True

    def held(t, l):
        lk.fx(7, t, l)
        time.sleep(0.3)
        L, R = record(1.3, lambda: (time.sleep(0.1), note(lk, n, 1.0)))
        a, b = int(0.35 * FS), int(0.95 * FS)
        x = L[a:b] + R[a:b]
        X = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / FS)
        return x.std(), X[f < 500].sum(), X[f > 3000].sum()
    # low-pass tests: echo of a short note 187 ms later
    for k, name in ((1, 'LP 2-pole (fixed)'), (2, 'LP 1-pole a3/4 (fixed)')):
        if not guard((k & 1) * 4, k >> 1, name):
            continue
        L, R = record(0.9, lambda: (time.sleep(0.1), note(lk, 72, 0.06)))
        wav(os.path.join(out, 'lab2_k%d.wav' % k), L, R)
        x = np.abs(L) + np.abs(R)
        on = int(np.argmax(x > 0.3 * x.max()))
        d0 = x[on:on + int(0.05 * FS)].mean()
        w = (L + R)[on + int(0.187 * FS) - 200:on + int(0.187 * FS) + int(0.05 * FS)]
        W = np.abs(np.fft.rfft(w * np.hanning(len(w)))) ** 2; f = np.fft.rfftfreq(len(w), 1 / FS)
        rep.append('%-26s STABLE  echo %.1f dB vs dry  echo >4k %.1f dB' % (
            name, 20 * np.log10(np.abs(w).mean() * 0.5 / d0 + 1e-12), 10 * np.log10(W[f > 4000].sum() / W.sum() + 1e-12)))
        print(rep[-1])
    # dry reference (mode 7 OFF)
    ref = [held(0, 0) for _ in range(2)]
    r0, lo0, hi0 = [sum(v) / 2 for v in zip(*ref)]
    db = lambda a, b: 10 * np.log10(a / b + 1e-12)
    if guard(4, 1, 'polarity +x'):
        r, lo, hi = held(4, 1)
        rep.append('polarity +x: %+.1f dB vs dry -> %s' % (2 * db(r, r0), 'wet path INVERTED (+x cancels)' if r < r0
                                                          else 'wet path in phase (+x adds)'))
        print(rep[-1])
    best = {}
    for t in range(3):
        for sg in '+-':
            for h in (0, 1):
                k = 4 + t * 4 + (0 if sg == '+' else 2) + h
                if not guard((k & 1) * 4, k >> 1, 'k%d' % k):
                    continue
                for sb in range(4):
                    g = CANCEL_G2[h * 4 + sb]
                    r, lo, hi = held((k & 1) * 4 + sb, k >> 1)
                    tot = 2 * db(r, r0)
                    line = '%s%-13s g %.3f  total %6.1f dB  <500Hz %6.1f dB  >3k %6.1f dB' % (
                        sg, CANCEL_T[t], g, tot, db(lo, lo0), db(hi, hi0))
                    rep.append(line); print(line)
                    key = sg + CANCEL_T[t]
                    if key not in best or tot < best[key][1]:
                        best[key] = (g, tot, db(hi, hi0))
    lk.fx(0, 1, 6)
    for key, (g, tot, hi) in best.items():
        rep.append('BEST %-15s g %.3f  total %.1f dB  highs %.1f dB' % (key, g, tot, hi))
        print(rep[-1])
    open(os.path.join(out, 'lab2.txt'), 'w').write('\n'.join(rep) + '\n')


LAB3 = [('OFF', None), ('REF acc = x/2', 1.0), ('h0 pure negate', -1.0), ('h1 pure negate', -1.0),
        ('h0 add x/4 + negate', -1.5), ('h1 add x/2 + negate', -2.0), ('h1 clear+add+negate (r1 cancel)', -1.0),
        ('h0 negate, then add x/2', 0.0), ('two h0 negates', 1.0), ('h0 negate, mask other saw', -1.0),
        ('doubled (x)', 2.0), ('h1 neg on add, h0 neg before', -1.0), ('add x/2 twice', 2.0)]   # = gen_fx.LAB3
CANCEL_G3 = [1.18, 1.24, 1.30, 1.37]
ECHO_LAG = 9000                                  # 6000 chip frames at 32 kHz = 9000 samples at 48 kHz


def lab3(lk):
    """IC13 LAB round 3: the real meaning of each accumulator op (k1-12, signed echo gain vs REF, emulator
    prediction next to it) + cancel (k13-15: now / one frame late / half a frame late, 4 gains). SOLO on DRY+FX.
    Report: build/lab/lab3.txt"""
    import numpy as np
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'build', 'lab')
    os.makedirs(out, exist_ok=True)
    rep = []
    lk.part_fx(1)

    def guard(t, l, name):
        lk.fx(7, t, l)
        time.sleep(0.35)
        L, R = record(0.3)
        idle = 20 * np.log10(np.concatenate([L, R]).std() + 1e-12)
        if idle > -60:
            lk.fx(0, 1, 6)
            rep.append('%-34s OSCILLATES / STUCK LOUD: idle %.1f dB' % (name, idle)); print(rep[-1]); time.sleep(0.8)
            return False
        return True

    def signed_echo(k):
        L, R = record(0.9, lambda: (time.sleep(0.1), note(lk, 72, 0.06)))
        wav(os.path.join(out, 'lab3_k%d.wav' % k), L, R)
        x = L + R
        on = int(np.argmax(np.abs(x) > 0.3 * np.abs(x).max()))
        d = x[on:on + int(0.05 * FS)]
        best = (0, 0)
        for lag in range(ECHO_LAG - 30, ECHO_LAG + 31):
            e = x[on + lag:on + lag + len(d)]
            c = float(np.dot(e, d) / np.dot(d, d))
            if abs(c) > abs(best[1]):
                best = (lag, c)
        return best
    ref = None
    for k in range(1, 13):
        name, pred = LAB3[k]
        if not guard((k & 1) * 4, k >> 1, 'k%d %s' % (k, name)):
            continue
        lag, c = signed_echo(k)
        if k == 1:
            ref = c
        rel = c / ref if ref else float('nan')
        rep.append('k%-2d %-34s %+6.2f x REF   (emulator %+.1f)   lag %d' % (k, name, rel, pred, lag - ECHO_LAG))
        print(rep[-1])

    def held(t, l):
        lk.fx(7, t, l)
        time.sleep(0.3)
        L, R = record(1.3, lambda: (time.sleep(0.1), note(lk, 57, 1.0)))
        a, b = int(0.35 * FS), int(0.95 * FS)
        res = []
        for x in (L[a:b], R[a:b]):
            X = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / FS)
            res.append((x.std() ** 2, X[f < 500].sum(), X[(f > 1000) & (f < 3000)].sum(), X[f > 3000].sum()))
        return res
    refs = [held(0, 0) for _ in range(2)]
    ref = [[(refs[0][c][i] + refs[1][c][i]) / 2 for i in range(4)] for c in range(2)]
    db = lambda a, b: 10 * np.log10(a / b + 1e-12)
    for k, name in ((13, 'cancel x[n]'), (14, 'cancel 1st-order lead'), (15, 'cancel 2nd-order lead')):
        if not guard((k & 1) * 4, k >> 1, name):
            continue
        for sb, g in enumerate(CANCEL_G3):
            res = held((k & 1) * 4 + sb, k >> 1)
            parts = []
            for c, nm in enumerate('LR'):
                parts.append('%s total %6.1f  <500 %6.1f  1-3k %6.1f  >3k %6.1f' % (nm, *[db(res[c][i], ref[c][i]) for i in range(4)]))
            rep.append('%-22s g %.2f | %s | %s' % (name, g, parts[0], parts[1]))
            print(rep[-1])
    lk.fx(0, 1, 6)
    open(os.path.join(out, 'lab3.txt'), 'w').write('\n'.join(rep) + '\n')


def flip(lk, secs=4.0, rounds=6, t=2, l=4):
    """listening A/B: JUNO CHORUS v4 (mode 1, 64 positions) <-> chorus B (mode 6, 128 positions, IC13 v5 + IC28 v3),
    same rate/depth (TIME t, LEVEL l), switching every secs while you play."""
    lk.part_fx(1)
    for r in range(rounds):
        for m, name in ((1, 'v4  (64 positions)'), (6, 'B   (128 positions)')):
            lk.fx(m, t, l)
            print('now: %s' % name)
            time.sleep(secs)
    lk.fx(1, t, l)


if __name__ == '__main__':
    a = sys.argv[1:] or ['ping']
    lk = Link()
    c = a[0]
    if c == 'ping':
        print(lk.ping())
    elif c == 'screen':
        print('\n'.join(lk.screen() or ['(no reply)']))
    elif c == 'leds':
        print((lk.leds() or b'').hex(' '))
    elif c == 'key':
        lk.key(KEYS.get(a[1].lower(), None) or int(a[1], 0))
        print('\n'.join(lk.screen() or []))
    elif c == 'dial':
        lk.dial(int(a[1]))
        time.sleep(0.1)
        print('\n'.join(lk.screen() or []))
    elif c == 'peek':
        print((lk.peek(int(a[1], 0), int(a[2]) if len(a) > 2 else 1) or b'').hex(' '))
    elif c == 'poke':
        lk.poke(int(a[1], 0), int(a[2], 0))
    elif c == 'ck':
        lk.ck(bytes.fromhex(''.join(a[1:])))
    elif c == 'note':
        L, R = record(float(a[2]) + 1 if len(a) > 2 else 2.0, lambda: note(lk, int(a[1]), float(a[2]) if len(a) > 2 else 1.0))
        wav(a[3] if len(a) > 3 else 'note.wav', L, R)
    elif c == 'lab':
        lab(lk)
    elif c == 'chiplab':
        chiplab(lk)
    elif c == 'cancel':
        cancel(lk)
    elif c == 'lab2':
        lab2(lk)
    elif c == 'lab3':
        lab3(lk)
    elif c == 'flip':
        flip(lk, float(a[1]) if len(a) > 1 else 4.0)
