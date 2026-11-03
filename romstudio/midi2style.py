"""Style Maker: MIDI -> PRO-E style, packed as a TN-SC1-format card image (loads in ROM Studio's library).

A song spec says which MIDI bars become which section and which channels become which part. Notes are kept as
they are: quantized to the PRO-E's 24 PPQN (16ths, 8th triplets, 32nds exact; anything else is reported), and the
whole song is transposed so the given root becomes C (the arranger stores patterns in C and moves them to the held root).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proe_rom as pr
import smf

rs = pr.rs
PPQN, TPB = 24, 96
OFFSET = {'drums': 36, 'bass': 24, 'acc': 36}
VEL_TABLE_IC4 = 0x2D5A          # $ED5A: velocity index -> velocity (index 0 = note off)
NOP, END = 0x3D, 0x3F
# TN-SC1 card header the OS checks ($D4A3): signature, type byte 'N' + complement pairs, card id, then
# the record table at $40B0 and pattern data from $46D8 (0x30 00 B0 06 D8). The card id is overwritten per style.
CARD_HEADER = bytes.fromhex('526f6c616e6420452d3230204eb151ae544e2d5343312d303100000000000000003000b006d800000000000000000000')


def vel_index(v, table):
    return min(range(1, 16), key=lambda i: abs(table[i] - v))


def bar_starts(song):
    """MIDI tick of every bar start, following the song's time-signature changes."""
    ms = sorted(song.meters) or [(0, 4, 4)]
    end = max(n.off for n in song.notes)
    out, t, i = [], 0, 0
    while t <= end:
        while i + 1 < len(ms) and ms[i + 1][0] <= t:
            i += 1
        out.append(t)
        t += song.ppq * 4 * ms[i][1] // ms[i][2]
    out.append(t)
    return out


def part_events(song, chans, t0, t1, kind, shift, program, table, report):
    """MIDI notes in MIDI ticks [t0, t1) on chans -> pattern events (incl. END)."""
    mt = song.ppq / PPQN                        # MIDI ticks per style tick
    length = round((t1 - t0) / mt)
    drum_map = report.get('drum_map', {})
    raw = []
    for n in song.notes:
        if n.ch not in chans or not t0 <= n.on < t1:
            continue
        on = (n.on - t0) / mt
        off = (min(n.off, t1) - t0) / mt
        q_on, q_off = round(on), max(round(off), round(on) + 1)
        if abs(on - q_on) > 0.05:
            report['moved'] += 1
        key = n.key if kind == 'drums' else n.key + shift
        if kind == 'drums':
            key = drum_map.get((n.ch, n.key), drum_map.get(n.ch, key))
            if key == 35:
                key = 36
        f = key - OFFSET[kind]
        while f < 0:
            f += 12
            report['octave_up'] += 1
        while f > 60:
            f -= 12
            report['octave_down'] += 1
        raw.append((min(q_on, length - 1), 1, f, vel_index(n.vel, table)))
        raw.append((min(q_off, length), 0, f, 0))
    raw.sort(key=lambda e: (e[0], e[1]))      # note-offs before note-ons at the same tick
    # voice check
    live, peak = set(), 0
    for t, is_on, f, _ in raw:
        (live.add if is_on else live.discard)(f)
        peak = max(peak, len(live))
    report.setdefault('peak', {})[kind] = max(report.get('peak', {}).get(kind, 0), peak)
    ev = []
    if program is not None:
        ev.append([0, {'pc': True, 'field': program & 0x3F, 'hi': (program & 0x40) >> 4, 'dt': 0}])
    for t, is_on, f, vi in raw:
        ev.append([t, {'pc': False, 'field': f, 'hi': vi if is_on else 0, 'dt': 0}])
    if not ev or ev[-1][0] < length and not raw:
        ev.append([0, {'pc': False, 'field': NOP, 'hi': 0, 'dt': 0}])
    for i in range(len(ev)):
        nxt = ev[i + 1][0] if i + 1 < len(ev) else length
        ev[i][1]['dt'] = nxt - ev[i][0]
    out = [e for _, e in ev]
    for e in out:
        while e['dt'] > 0xFFF:
            raise ValueError('gap longer than 4095 ticks inside one pattern')
    out.append({'end': END})
    return out


def make_card(spec, midi_path, out_path):
    song = smf.read(midi_path)
    ic4 = open(pr.STOCK_IC4, 'rb').read()
    table = list(ic4[VEL_TABLE_IC4:VEL_TABLE_IC4 + 16])
    shift = (-spec['root']) % 12
    if shift > 6:
        shift -= 12
    report = {'moved': 0, 'octave_up': 0, 'octave_down': 0, 'drum_map': spec.get('drum_map', {})}
    tpb = spec.get('ticks_per_bar', TPB)
    bars = bar_starts(song)
    if not spec['tempo']:                       # live tempo map: use the median over the song
        ts = sorted(song.tempos) + [(bars[-1], 0)]
        spans = sorted((ts[i][1], ts[i + 1][0] - ts[i][0]) for i in range(len(ts) - 1))
        half, acc = sum(d for _, d in spans) / 2, 0
        for bpm, d in spans:
            acc += d
            if acc >= half:
                spec = dict(spec, tempo=round(bpm))
                break
        report['tempo_from_median'] = spec['tempo']
    card = bytearray(b'\xff' * pr.CARD_SIZE)
    card[:0x30] = CARD_HEADER
    card[0x10:0x1A] = spec['card_id'].encode('latin1')[:9].ljust(9, b'\0') + b'\0'
    pat_at = 0xB0 + 8 * rs.REC_LEN           # patterns start at card offset 0x6D8 ($46D8), as on Roland's cards
    parts_map = spec['parts']                # part name -> (channels, program)
    rec = bytearray(rs.REC_LEN)
    rec[0x0F], rec[0x10] = tpb, spec['tempo']
    cache = {}

    def place(events):
        nonlocal pat_at
        data = rs.encode_events(events)
        if data in cache:
            return cache[data]
        if pat_at + len(data) > pr.CARD_SIZE:
            raise RuntimeError('style does not fit in a 32 KB card')
        card[pat_at:pat_at + len(data)] = data
        cache[data] = 0x4000 + pat_at
        pat_at += len(data)
        return cache[data]

    for k, sect in enumerate(rs.SECT):
        bar0, nbars = spec['sections'][sect]
        t0, t1 = bars[bar0], bars[bar0 + nbars]
        if round((t1 - t0) / (song.ppq / PPQN)) % tpb:
            raise ValueError(f'{sect}: bars {bar0}-{bar0 + nbars - 1} are not whole {tpb}-tick bars (odd meter inside?)')
        chans, _ = parts_map['DRUMS']
        ptr = place(part_events(song, chans, t0, t1, 'drums', 0, None, table, report))
        pr._set_ref(rec, 0, k, 0, 8, ptr)
        for p, pname in enumerate(rs.PARTS[1:], start=1):
            chans, program = parts_map[pname]
            kind = 'bass' if pname == 'A.BASS' else 'acc'
            ptr = place(part_events(song, chans, t0, t1, kind, shift, program, table, report))
            for c in range(3):                # Ma / mi / 7 share the pattern (a riff has no chord 3rd to swap)
                pr._set_ref(rec, p, k, c, 8, ptr)
    for i in range(8):
        card[0xB0 + rs.REC_LEN * i:0xB0 + rs.REC_LEN * (i + 1)] = rec
        card[0x30 + 16 * i:0x40 + 16 * i] = spec['name'].encode('latin1')[:16].ljust(16)
    open(out_path, 'wb').write(card)
    report['bytes'] = pat_at - (0xB0 + 8 * rs.REC_LEN)
    report['shift'] = shift
    report.pop('drum_map', None)
    return report


def tone(name):
    ic7 = open(pr.STOCK_IC7, 'rb').read()
    names = [ic7[0x24D9 + 12 * i:0x24D9 + 12 * i + 12].decode('latin1').strip() for i in range(128)]
    return names.index(name)


IRON = {
    'name': 'IRONMAN', 'card_id': 'ROSETTA01', 'tempo': 85, 'root': 10,   # riff on Bb (tuned down a half step)
    'sections': {'BASIC': (12, 2), 'VARIATION': (22, 4), 'FILL>ORIG': (27, 1), 'FILL>VAR': (21, 1),
                 'INTRO': (0, 10), 'ENDING': (119, 2)},
    'parts': {'DRUMS': ({9}, None), 'A.BASS': ({1}, 66),       # ELEC BASS1
              'ACC1': ({0}, 62), 'ACC2': ({2}, 61), 'ACC3': ({0}, 62)},   # ELEC GUITAR2 riff, ELEC GUITAR1 harmony
}

ARMY = {
    'name': 'ARMYDRMS', 'card_id': 'ROSETTA02', 'tempo': 67, 'root': 11, 'ticks_per_bar': 72,   # 6/8 in B
    'sections': {'BASIC': (2, 4), 'VARIATION': (18, 4), 'FILL>ORIG': (27, 1), 'FILL>VAR': (17, 1),
                 'INTRO': (2, 2), 'ENDING': (76, 2)},
    'parts': {'DRUMS': ({9, 8}, None), 'A.BASS': ({7}, tone('ACOU BASS1')),
              'ACC1': ({3}, tone('GUITAR1')), 'ACC2': ({5}, tone('STRING SECT1')), 'ACC3': ({3}, tone('GUITAR1'))},
    'drum_map': {8: 36},                # the TAIKO track (ch9, melodic) -> kick
}

FUNERAL = {
    'name': 'FUNERAL', 'card_id': 'ROSETTA03', 'tempo': 0, 'root': 11, 'ticks_per_bar': 72,   # 12/8 bar = 2 x 72, in B
    'sections': {'BASIC': (25, 4), 'VARIATION': (60, 4), 'FILL>ORIG': (32, 1), 'FILL>VAR': (48, 1),
                 'INTRO': (0, 5), 'ENDING': (184, 2)},
    'parts': {'DRUMS': ({9}, None), 'A.BASS': ({0}, tone('ELEC BASS1')),
              'ACC1': ({1}, tone('ELEC GUITAR2')), 'ACC2': ({2, 3}, tone('ELEC GUITAR1')), 'ACC3': ({1}, tone('ELEC GUITAR2'))},
}

SONGS = {'IRONMAN': (IRON, 'Black_Sabbath_-_Iron_Man.mid'), 'ARMYDRMS': (ARMY, 'Army-Dreamers.mid'),
         'FUNERAL': (FUNERAL, 'funeralopolis.mid')}

if __name__ == '__main__':
    for key in (sys.argv[1:] or SONGS):
        spec, mid = SONGS[key]
        src = os.path.join(pr.ROOT, 'midi_in', mid)
        out = os.path.join(pr.ROOT, 'midi_in', f'{key}_card.bin')
        rep = make_card(spec, src, out)
        print(out, rep)
