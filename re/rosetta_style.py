"""Rosetta Style: decode / encode the Roland PRO-E style data in IC7 (R15179983, OS v2.00).

  python -I rosetta_style.py decode  [ic7.bin] [styles.json]   IC7 -> JSON (records + patterns)
  python -I rosetta_style.py encode  styles.json [out.bin]      JSON -> IC7 image (patterns at their JSON addresses)
  python -I rosetta_style.py roundtrip                          decode the stock dump, encode, require byte-identical

Format (re/fw_map/A4_hc11_arranger_styles.md sec. 3):
  directory: 32 records x 197 B at bank 0 $A701; names 8 B at bank 0 $63D9
  record: +00 drum bank nibbles (3 B), +03 6 drum ptrs, +0F ticks/bar, +10 tempo,
          +11/+3E/+6B/+98 parts A.BASS/ACC1/ACC2/ACC3: 9 bank-nibble bytes + 18 ptrs [section][Ma/mi/7]
  event:  b0 b7 = program change, b6 = long (3-byte) delta, b5-0 = field ($3D no-op, $3E/$3F = END, 1 byte)
          b1 hi nibble = velocity index (raw, also carries prog bit 6), lo nibble = delta (hi bits if long)
  pointers >= $C000 = IC4 silent patterns (left alone).
Every IC7 bank has a header checksum (word at bank offset 0, see build_fw.py); encode re-fixes it.

HARD RULE: style 24 BAROQUE is never changed. Encode refuses to write if any byte of its record or patterns differs.
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DUMPS = os.path.join(HERE, '..', 'dumps')
STOCK = os.path.join(DUMPS, 'proe_ic7_R15179983_LH53234L_v2.00.bin')

DIR_AT, REC_LEN, N_STYLES, NAMES_AT = 0xA701, 197, 32, 0x63D9
SECT = ['BASIC', 'VARIATION', 'FILL>ORIG', 'FILL>VAR', 'INTRO', 'ENDING']
PARTS = ['DRUMS', 'A.BASS', 'ACC1', 'ACC2', 'ACC3']
PART_OFF = [None, 0x11, 0x3E, 0x6B, 0x98]
CLS = ['Ma', 'mi', '7']
BAROQUE = 24


def off(bank, cpu):
    """IC7 file offset of CPU address $4000-$BFFF in a bank."""
    assert 0x4000 <= cpu < 0xC000, hex(cpu)
    return bank * 0x8000 + cpu - 0x4000


def bank_nibbles(rec, o):
    """per (section, class) bank nibbles of a part block starting at record offset o."""
    b = rec[o:o + 9]
    out = {}
    for k in range(6):
        m = k // 2
        if k % 2 == 0:
            bk = [b[3*m] & 15, b[3*m] >> 4, b[3*m+1] & 15]
        else:
            bk = [b[3*m+2] & 15, b[3*m+2] >> 4, b[3*m+1] >> 4]
        for c in range(3):
            out[(k, c)] = bk[c]
    return out


def put_bank_nibbles(rec, o, nib):
    b = [0] * 9
    for k in range(6):
        m = k // 2
        c0, c1, c2 = (nib[(k, c)] for c in range(3))
        if k % 2 == 0:
            b[3*m] = (b[3*m] & 0xF0) | c0
            b[3*m] = (b[3*m] & 0x0F) | c1 << 4
            b[3*m+1] = (b[3*m+1] & 0xF0) | c2
        else:
            b[3*m+2] = c0 | c1 << 4
            b[3*m+1] = (b[3*m+1] & 0x0F) | c2 << 4
    rec[o:o + 9] = bytes(b)


def pattern_refs(rec):
    """{(part, section, class): (bank, ptr)}; drums use class 0 only."""
    refs = {}
    for k in range(6):
        nib = (rec[k // 2] >> 4) if k & 1 else (rec[k // 2] & 15)
        refs[(0, k, 0)] = (nib, rec[3 + 2*k] << 8 | rec[4 + 2*k])
    for p in range(1, 5):
        o = PART_OFF[p]
        nib = bank_nibbles(rec, o)
        for k in range(6):
            for c in range(3):
                j = o + 9 + 2 * (3*k + c)
                refs[(p, k, c)] = (nib[(k, c)], rec[j] << 8 | rec[j + 1])
    return refs


def decode_events(ic7, bank, ptr, limit=8000):
    """bit-exact event list up to and including END; returns (events, size)."""
    a = off(bank, ptr)
    start = a
    ev = []
    for _ in range(limit):
        b0 = ic7[a]
        if not b0 & 0x80 and (b0 & 0x3F) >= 0x3E:
            ev.append({'end': b0})
            return ev, a - start + 1
        b1 = ic7[a + 1]
        e = {'pc': bool(b0 & 0x80), 'field': b0 & 0x3F, 'hi': b1 >> 4}
        if b0 & 0x40:
            e['dt'] = (b1 & 15) << 8 | ic7[a + 2]
            e['long'] = True
            a += 3
        else:
            e['dt'] = b1 & 15
            a += 2
        ev.append(e)
    raise ValueError(f'no END in pattern bank {bank} ${ptr:04X}')


def encode_events(ev):
    out = bytearray()
    for e in ev:
        if 'end' in e:
            out.append(e['end'])
            continue
        long = e.get('long', False) or e['dt'] > 15
        if e['dt'] > 0xFFF or not 0 <= e['field'] <= 0x3F or not 0 <= e['hi'] <= 15:
            raise ValueError(f'event out of range: {e}')
        b0 = (0x80 if e['pc'] else 0) | (0x40 if long else 0) | e['field']
        if long:
            out += bytes([b0, e['hi'] << 4 | e['dt'] >> 8, e['dt'] & 0xFF])
        else:
            out += bytes([b0, e['hi'] << 4 | e['dt']])
    return bytes(out)


def decode(ic7):
    styles, patterns = [], {}
    for i in range(N_STYLES):
        rec = ic7[DIR_AT - 0x4000 + REC_LEN * i:][:REC_LEN]
        name = ic7[NAMES_AT - 0x4000 + 8 * i:][:8].decode('latin1')
        refs = pattern_refs(rec)
        slots = {}
        for (p, k, c), (bank, ptr) in refs.items():
            key = f'{bank}:{ptr:04X}' if ptr < 0xC000 else f'ic4:{ptr:04X}'
            slots[f'{PARTS[p]}/{SECT[k]}/{CLS[c]}'] = key
            if ptr < 0xC000 and key not in patterns:
                ev, size = decode_events(ic7, bank, ptr)
                patterns[key] = {'bank': bank, 'addr': ptr, 'size': size, 'events': ev}
        styles.append({'n': i, 'name': name, 'ticks_per_bar': rec[0x0F], 'tempo': rec[0x10],
                       'slots': slots, 'record_hex': rec.hex()})
    return {'format': 'rosetta-style-1', 'source_sha1': hashlib.sha1(ic7).hexdigest(),
            'styles': styles, 'patterns': patterns}


def bank_fix(img):
    for k in range(8):
        b0 = k * 0x8000
        w = -sum(img[b0 + 2:b0 + 0x8000]) & 0xFFFF
        img[b0], img[b0 + 1] = w >> 8, w & 0xFF


def baroque_bytes(ic7):
    """every byte that belongs to BAROQUE: its record, its name, all its patterns."""
    rec = ic7[DIR_AT - 0x4000 + REC_LEN * BAROQUE:][:REC_LEN]
    chunks = [('record', DIR_AT - 0x4000 + REC_LEN * BAROQUE, REC_LEN),
              ('name', NAMES_AT - 0x4000 + 8 * BAROQUE, 8)]
    for (p, k, c), (bank, ptr) in pattern_refs(rec).items():
        if ptr < 0xC000:
            _, size = decode_events(ic7, bank, ptr)
            chunks.append((f'{PARTS[p]}/{SECT[k]}/{CLS[c]}', off(bank, ptr), size))
    return {(o, n): ic7[o:o + n] for _, o, n in chunks}


def encode(doc, base):
    img = bytearray(base)
    for key, pat in doc['patterns'].items():
        data = encode_events(pat['events'])
        o = off(pat['bank'], pat['addr'])
        if o // 0x8000 != (o + len(data) - 1) // 0x8000:
            raise ValueError(f'pattern {key} crosses a bank end')
        img[o:o + len(data)] = data
    for s in doc['styles']:
        rec = bytes.fromhex(s['record_hex'])
        assert len(rec) == REC_LEN
        rec = bytearray(rec)
        rec[0x0F], rec[0x10] = s['ticks_per_bar'], s['tempo']
        o = DIR_AT - 0x4000 + REC_LEN * s['n']
        img[o:o + REC_LEN] = rec
        name = s['name'].encode('latin1')[:8].ljust(8)
        o = NAMES_AT - 0x4000 + 8 * s['n']
        img[o:o + 8] = name
    bank_fix(img)
    stock = open(STOCK, 'rb').read()
    for (o, n), want in baroque_bytes(stock).items():
        if bytes(img[o:o + n]) != want:
            sys.exit(f'REFUSED: BAROQUE (style 24) changed at IC7 offset {o:#x}. Baroque is never touched.')
    return bytes(img)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'roundtrip'
    if cmd == 'decode':
        src = sys.argv[2] if len(sys.argv) > 2 else STOCK
        dst = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, 'styles.json')
        doc = decode(open(src, 'rb').read())
        json.dump(doc, open(dst, 'w', encoding='utf-8'), indent=1)
        print(f'{len(doc["styles"])} styles, {len(doc["patterns"])} distinct patterns -> {dst}')
    elif cmd == 'encode':
        doc = json.load(open(sys.argv[2], encoding='utf-8'))
        dst = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, '..', 'build', 'IC7_styles.bin')
        img = encode(doc, open(STOCK, 'rb').read())
        open(dst, 'wb').write(img)
        print(f'{dst}  md5 {hashlib.md5(img).hexdigest()}')
    elif cmd == 'roundtrip':
        stock = open(STOCK, 'rb').read()
        doc = decode(stock)
        doc = json.loads(json.dumps(doc))          # go through JSON exactly like a saved file
        blank = bytearray(stock)
        for pat in doc['patterns'].values():      # wipe every pattern first, so encode must rebuild them
            o = off(pat['bank'], pat['addr'])
            blank[o:o + pat['size']] = b'\xff' * pat['size']
        for s in doc['styles']:
            o = DIR_AT - 0x4000 + REC_LEN * s['n']
            blank[o:o + REC_LEN] = b'\xff' * REC_LEN
        img = encode(doc, bytes(blank))
        n_ev = sum(len(p['events']) for p in doc['patterns'].values())
        n_bytes = sum(p['size'] for p in doc['patterns'].values())
        print(f'{len(doc["styles"])} styles, {len(doc["patterns"])} distinct patterns, {n_ev} events, {n_bytes} bytes')
        if img == stock:
            print('ROUND TRIP OK: rebuilt IC7 is byte-identical to the stock dump')
        else:
            d = [i for i in range(len(img)) if img[i] != stock[i]]
            sys.exit(f'ROUND TRIP FAILED: {len(d)} bytes differ, first at {[hex(x) for x in d[:8]]}')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
