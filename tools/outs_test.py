"""Extra-outs proof (2026-11-07): main outs on Focusrite ASIO in 1/2, the SYN1 taps (IC18 pin 1 / IC2 pin 7 via 10 uF)
on in 3/4. Plays SOLO with part FX on (dry -> SYN1 -> outs 3/4) and LOWER with part FX off (dry -> SYN2 -> main),
effect OFF so only dry paths speak, records all 4 inputs, reports levels and the hash above 16 kHz on 3/4.

  py -3.10 outs_test.py
"""
import time
import numpy as np
import sounddevice as sd
import proe_link as P

FS = P.FS


def rec4(secs, play):
    dev = [k for k, d in enumerate(sd.query_devices()) if 'focusrite' in d['name'].lower()
           and d['max_input_channels'] >= 4 and 'asio' in sd.query_hostapis(d['hostapi'])['name'].lower()]
    if not dev:
        raise SystemExit('no Focusrite ASIO input with 4+ channels')
    r = sd.rec(int(secs * FS), samplerate=FS, channels=4, device=dev[0], dtype='float32')
    play()
    sd.wait()
    return r


def db(x):
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)


def hf(x):
    X = np.fft.rfft(x * np.hanning(len(x)))
    f = np.fft.rfftfreq(len(x), 1 / FS)
    tot = (np.abs(X) ** 2).sum() + 1e-30
    return 10 * np.log10((np.abs(X[f > 16000]) ** 2).sum() / tot + 1e-30)


lk = P.Link()
print(lk.ping())
lk.fx(2, 4, 0)                                   # DELAY level 0: no echo audible, routing untouched
lk.dt1([0x03, 0x00, 0x26], [1])                  # SOLO part FX on  -> SYN1 (outs 3/4)
lk.dt1([0x03, 0x00, 0x16], [0])                  # LOWER part FX off -> SYN2 (main)
time.sleep(0.2)
for name, ch in (('SOLO (FX on)', 3), ('LOWER (FX off)', 2)):
    r = rec4(1.6, lambda: (lk.ck([0x90 | ch, 60, 110]), time.sleep(1.0), lk.ck([0x80 | ch, 60, 0])))
    seg = r[int(0.2 * FS):int(1.0 * FS)]
    lv = [db(seg[:, k]) for k in range(4)]
    print('%-15s in1 %6.1f  in2 %6.1f  in3 %6.1f  in4 %6.1f dB   | hash >16k on in3/in4: %6.1f %6.1f dB'
          % ((name,) + tuple(lv) + (hf(seg[:, 2]), hf(seg[:, 3]))))
    time.sleep(0.3)
lk.dt1([0x03, 0x00, 0x16], [1])                  # LOWER back to dry + FX
