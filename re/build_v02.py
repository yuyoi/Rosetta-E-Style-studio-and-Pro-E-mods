"""Rosetta OS PRO-E v0.2: the MSL-15's two hidden cards (Turkey + Asia) replace styles 16-23 (panel BANK 3, buttons 1-8).

  python -I build_v02.py      -> ../build/IC7_v0.2_W27C040.bin (IC4 stays the v0.1 chip)

Only patterns used by styles 16-23 (and by no other style) are freed. Card patterns are relocated into those gaps
(each pattern pointer carries its own bank nibble, so a style may spread over banks). Baroque (24) is locked: the build
stops if any Baroque byte changes. Every other style must decode to exactly its stock events.
"""
import hashlib, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('rs', os.path.join(HERE, 'rosetta_style.py'))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

CARDS = os.path.join(HERE, '..', 'dumps_ext', 'msl15')
BUILD = os.path.join(HERE, '..', 'build')
# (card file, card style index 0-3) -> internal slot. Slots 16-23 = panel BANK 3, number 1-8.
IMPORT = [('card15_TN-SC1-01_turkey.bin', i, 16 + i) for i in range(4)] + \
         [('card14_TN-SC1-01_asia.bin', i, 20 + i) for i in range(4)]
DROP = {slot for _, _, slot in IMPORT}
BANNER = (0x19E1, b'  ROLAND PRO-E  INTELL. ARRANGER', b' ROSETTA  PRO-E   OS v0.2 2026  ')


def set_ref(rec, p, k, c, bank, ptr):
    if p == 0:
        i = k // 2
        rec[i] = (rec[i] & 0x0F) | bank << 4 if k & 1 else (rec[i] & 0xF0) | bank
        rec[3 + 2*k], rec[4 + 2*k] = ptr >> 8, ptr & 0xFF
        return
    o = rs.PART_OFF[p]
    nib = rs.bank_nibbles(rec, o)
    nib[(k, c)] = bank
    rs.put_bank_nibbles(rec, o, nib)
    j = o + 9 + 2 * (3*k + c)
    rec[j], rec[j + 1] = ptr >> 8, ptr & 0xFF


def merged(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def main():
    stock = open(rs.STOCK, 'rb').read()
    doc = rs.decode(stock)
    # sanity: the record writer reproduces every stock record
    for s in doc['styles']:
        rec = bytearray.fromhex(s['record_hex'])
        for (p, k, c), (bank, ptr) in rs.pattern_refs(bytes(rec)).items():
            set_ref(rec, p, k, c, bank, ptr)
        assert rec.hex() == s['record_hex'], f'record writer broken on style {s["n"]}'

    # 1. free the patterns only the dropped styles use
    kept = {v for s in doc['styles'] if s['n'] not in DROP for v in s['slots'].values()}
    freed = sorted({v for s in doc['styles'] if s['n'] in DROP for v in s['slots'].values()
                    if not v.startswith('ic4') and v not in kept})
    img = bytearray(stock)
    free = {}
    for key in freed:
        p = doc['patterns'][key]
        o = rs.off(p['bank'], p['addr'])
        img[o:o + p['size']] = b'\xff' * p['size']
        free.setdefault(p['bank'], []).append((p['addr'], p['addr'] + p['size']))
    holes = [[b, s, e] for b in sorted(free) for s, e in merged(free[b])]
    print(f'freed {len(freed)} patterns, {sum(e - s for _, s, e in holes)} bytes in {len(holes)} gaps, banks {sorted(free)}')

    # 2. relocate card patterns into the gaps (first fit, biggest first)
    expected = {}
    for fname, idx, slot in IMPORT:
        card = open(os.path.join(CARDS, fname), 'rb').read()
        cimg = bytearray(0x40000)
        cimg[:0x8000] = card
        rec = bytearray(card[0xB0 + 197 * idx:0xB0 + 197 * (idx + 1)])
        refs = rs.pattern_refs(bytes(rec))
        pats = {}
        for (bank, ptr) in refs.values():
            if ptr < 0xC000 and ptr not in pats:
                assert bank == 8, f'{fname}: unexpected card bank nibble {bank}'
                ev, _ = rs.decode_events(bytes(cimg), 0, ptr)
                pats[ptr] = (ev, rs.encode_events(ev))
        where = {}
        for ptr, (ev, data) in sorted(pats.items(), key=lambda t: -len(t[1][1])):
            for h in holes:
                if h[2] - h[1] >= len(data):
                    where[ptr] = (h[0], h[1])
                    o = rs.off(h[0], h[1])
                    img[o:o + len(data)] = data
                    h[1] += len(data)
                    break
            else:
                sys.exit(f'out of space placing a {len(data)}-byte pattern from {fname}')
        for (p, k, c), (bank, ptr) in refs.items():
            if ptr < 0xC000:
                nb, na = where[ptr]
                set_ref(rec, p, k, c, nb, na)
                expected[(slot, p, k, c)] = pats[ptr][0]
            else:
                set_ref(rec, p, k, c, 0, ptr)
                expected[(slot, p, k, c)] = None
        o = rs.DIR_AT - 0x4000 + rs.REC_LEN * slot
        img[o:o + rs.REC_LEN] = rec
        name = card[0x30 + 16 * idx:0x40 + 16 * idx].decode('latin1').strip()[:8].ljust(8)
        o = rs.NAMES_AT - 0x4000 + 8 * slot
        img[o:o + 8] = name.encode('latin1')
        print(f'  slot {slot} (BANK 3 no.{slot - 15}) <- {name.strip():8s} {len(pats)} patterns, tempo {rec[0x10]}, {rec[0x0F]} ticks/bar')

    # 3. banner + checksums
    off, old, new = BANNER
    assert img[off:off + len(old)] == old
    img[off:off + len(new)] = new
    rs.bank_fix(img)

    # 4. verify
    for (o, n), want in rs.baroque_bytes(stock).items():
        assert bytes(img[o:o + n]) == want, f'BAROQUE changed at {o:#x}: REFUSED'
    new_doc = rs.decode(bytes(img))
    for s_old, s_new in zip(doc['styles'], new_doc['styles']):
        if s_old['n'] in DROP:
            continue
        for slot_name, key in s_old['slots'].items():
            k2 = s_new['slots'][slot_name]
            if key.startswith('ic4'):
                assert k2 == key
            else:
                assert doc['patterns'][key]['events'] == new_doc['patterns'][k2]['events'], f'style {s_old["n"]} changed'
    for s in new_doc['styles']:
        if s['n'] not in DROP:
            continue
        rec = bytes.fromhex(s['record_hex'])
        for (p, k, c), (bank, ptr) in rs.pattern_refs(rec).items():
            want = expected[(s['n'], p, k, c)]
            if want is not None:
                got, _ = rs.decode_events(bytes(img), bank, ptr)
                assert got == want, f'imported style {s["n"]} pattern mismatch'
    for k in range(8):
        b0 = k * 0x8000
        assert ((img[b0] << 8 | img[b0 + 1]) + sum(img[b0 + 2:b0 + 0x8000])) & 0xFFFF == 0
    print('verified: 24 stock styles identical (Baroque byte-locked), 8 imported styles match the cards, bank sums OK')

    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, 'IC7_v0.2_W27C040.bin')
    data = bytes(img) * 2
    open(out + '.tmp', 'wb').write(data)
    os.replace(out + '.tmp', out)
    print(f'{out}  md5 {hashlib.md5(data).hexdigest()}')


if __name__ == '__main__':
    main()
