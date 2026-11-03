"""Minimal Standard MIDI File reader (format 0/1): notes, programs, tempo, meter, names, markers."""
import struct


class Note:
    __slots__ = ('ch', 'key', 'vel', 'on', 'off', 'track')

    def __init__(self, ch, key, vel, on, off, track):
        self.ch, self.key, self.vel, self.on, self.off, self.track = ch, key, vel, on, off, track


class Song:
    def __init__(self):
        self.ppq = 480
        self.notes, self.programs, self.tempos, self.meters = [], [], [], []
        self.names, self.markers = {}, []


def _vlq(d, i):
    v = 0
    while True:
        b = d[i]
        i += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, i


def read(path):
    d = open(path, 'rb').read()
    if d[:4] != b'MThd':
        raise ValueError('not a MIDI file')
    hl, fmt, ntrk, div = struct.unpack('>IHHH', d[4:14])
    if div & 0x8000:
        raise ValueError('SMPTE timing not supported')
    s = Song()
    s.ppq = div
    i = 8 + hl
    for t in range(ntrk):
        assert d[i:i + 4] == b'MTrk', 'bad track chunk'
        ln = struct.unpack('>I', d[i + 4:i + 8])[0]
        j, end = i + 8, i + 8 + ln
        i = end
        tick, status, hanging = 0, 0, {}
        while j < end:
            dt, j = _vlq(d, j)
            tick += dt
            b = d[j]
            if b == 0xFF:
                typ = d[j + 1]
                ln2, k = _vlq(d, j + 2)
                data = d[k:k + ln2]
                j = k + ln2
                if typ == 0x51:
                    s.tempos.append((tick, 60_000_000 / int.from_bytes(data, 'big')))
                elif typ == 0x58:
                    s.meters.append((tick, data[0], 2 ** data[1]))
                elif typ == 0x03:
                    s.names[t] = data.decode('latin1', 'replace')
                elif typ in (0x06, 0x01):
                    s.markers.append((tick, data.decode('latin1', 'replace')))
                continue
            if b in (0xF0, 0xF7):
                ln2, k = _vlq(d, j + 1)
                j = k + ln2
                continue
            if b & 0x80:
                status = b
                j += 1
            hi, ch = status & 0xF0, status & 0x0F
            if hi in (0xC0, 0xD0):
                a = d[j]
                j += 1
                if hi == 0xC0:
                    s.programs.append((tick, ch, a, t))
                continue
            a, v = d[j], d[j + 1]
            j += 2
            if hi == 0x90 and v:
                hanging.setdefault((ch, a), []).append((tick, v))
            elif hi == 0x80 or (hi == 0x90 and not v):
                lst = hanging.get((ch, a))
                if lst:
                    on, vel = lst.pop(0)
                    s.notes.append(Note(ch, a, vel, on, tick, t))
        for (ch, a), lst in hanging.items():
            for on, vel in lst:
                s.notes.append(Note(ch, a, vel, on, on + s.ppq // 4, t))
    s.notes.sort(key=lambda n: (n.on, n.ch, n.key))
    return s
