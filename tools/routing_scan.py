"""D-70-style knockout scan for the PRO-E: which LA32 routing entry gives WET ONLY (send on, dry off)?

  py -3.10 routing_scan.py [key]      (default key 38 = snare, rhythm part ch 10)

The CK-34 routes every partial through table 0x39C2 (8 entries) indexed by the part's / rhythm key's reverb switch.
Melodic parts can only pick 0/1 (LAB build: 2/3), rhythm keys 0-7 (clamp 0x483F). Entries 4-7 are the D-110
multi-out groups (07 0F 00 08), never tested here. For each switch value: Delay at 150 ms, no feedback, hit the
key, record, then dry = energy before the echo, wet = energy of the echo. Restores the switch to 1 at the end.
"""
import sys, time
import numpy as np
import proe_link as P

KEY = int(sys.argv[1]) if len(sys.argv) > 1 else 38
ADDR = 0x90 + (KEY - 24) * 4 + 3                     # 03 xx xx: patch temp x 9, then rhythm setup (4 bytes/key)
DELAY_MS = 150


def db(x):
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9)


lk = P.Link()
print(lk.ping())
lk.fx(2, 4, 2)                                       # DELAY: program 5 = 150 ms, sawBits 0 = no feedback
time.sleep(0.3)
rows = []
for v in range(8):
    lk.dt1([0x03, ADDR >> 7, ADDR & 0x7F], [v])
    time.sleep(0.15)
    hit = lambda: (lk.ck([0x99, KEY, 127]), time.sleep(0.05), lk.ck([0x89, KEY, 0]))
    L, R = P.record(0.7, hit)
    x = (L + R) / 2
    on = int(np.argmax(np.abs(x) > 0.02)) if (np.abs(x) > 0.02).any() else 0
    d0, d1 = on, on + int(0.10 * P.FS)               # dry: 100 ms from the onset (echo comes at 150 ms)
    w0, w1 = on + int(DELAY_MS / 1000 * P.FS), on + int((DELAY_MS + 100) / 1000 * P.FS)
    rows.append((v, db(x[d0:d1]), db(x[w0:w1]), db(x[-int(0.1 * P.FS):])))
    print('switch %d: dry %6.1f dB   echo %6.1f dB   floor %6.1f dB' % rows[-1])
    time.sleep(0.2)
lk.dt1([0x03, ADDR >> 7, ADDR & 0x7F], [1])
print('restored key %d reverb switch = 1' % KEY)
best = [r for r in rows if r[2] - r[3] > 6 and r[1] - r[2] < 3]
print('WET-ONLY candidates (echo present, dry not louder than the echo):', [r[0] for r in best] or 'none')
