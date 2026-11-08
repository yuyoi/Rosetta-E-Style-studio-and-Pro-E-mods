"""Techno lead loop into SOLO so the user can play with the filter / bender / PWM while it runs.

  py -3.10 arp_loop.py [minutes] [bpm]      (default 10 min, 128 BPM; stop early: create build/lab/STOP_ARP)

16 sixteenth steps in A minor, 4-bar phrase that moves the root (A A F G), accents on the off-beats, gate 55 %.
"""
import os, sys, time
import proe_link as P

HERE = os.path.dirname(os.path.abspath(__file__))
STOP = os.path.join(HERE, '..', 'build', 'lab', 'STOP_ARP')
MINUTES = float(sys.argv[1]) if len(sys.argv) > 1 else 10
BPM = float(sys.argv[2]) if len(sys.argv) > 2 else 128
CH = 3                                               # SOLO
STEP = 60 / BPM / 4
# offsets from the bar root, None = rest
PAT = [0, 12, 7, 12, 3, 12, 7, 15, 0, 12, 7, 12, 10, 12, 7, 19]
VEL = [100, 70, 90, 70, 100, 70, 90, 115, 100, 70, 90, 70, 100, 70, 90, 120]
ROOTS = [45, 45, 41, 43]                             # A2 A2 F2 G2

if os.path.exists(STOP):
    os.remove(STOP)
lk = P.Link()
print(lk.ping(), 'arp: %.0f BPM, %.0f min, stop file %s' % (BPM, MINUTES, os.path.abspath(STOP)))
t0 = time.perf_counter()
end = t0 + MINUTES * 60
k = 0
try:
    while time.perf_counter() < end and not os.path.exists(STOP):
        root = ROOTS[(k // 16) % 4]
        n = PAT[k % 16]
        due = t0 + k * STEP
        while time.perf_counter() < due:
            time.sleep(0.001)
        if n is not None:
            note = root + n
            lk.ck([0x90 | CH, note, VEL[k % 16]])
            off = due + STEP * 0.55
            while time.perf_counter() < off:
                time.sleep(0.001)
            lk.ck([0x80 | CH, note, 0])
        k += 1
finally:
    lk.ck([0xB0 | CH, 123, 0])                       # all notes off
    print('arp stopped after %d steps' % k)
