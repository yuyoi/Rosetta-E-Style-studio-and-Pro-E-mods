"""Rosetta PRO-E ROM Studio engine: style slots, card import, OS text, image build, T48 burn.

The GUI only calls this module. Everything here is checked by test_proe_rom.py.
Format notes: ../re/fw_map/A4_hc11_arranger_styles.md; style codec: ../re/rosetta_style.py.
"""
import hashlib, importlib.util, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
_spec = importlib.util.spec_from_file_location('rosetta_style', os.path.join(ROOT, 're', 'rosetta_style.py'))
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

STOCK_IC7 = os.path.join(ROOT, 'dumps', 'proe_ic7_R15179983_LH53234L_v2.00.bin')
STOCK_IC4 = os.path.join(ROOT, 'dumps', 'proe_ic4_os_v2.00_051289_27c128.bin')
def _find_minipro():
    """$PROE_MINIPRO, then Documents/tools/minipro_win/minipro.exe, then minipro on PATH."""
    import shutil
    env = os.environ.get('PROE_MINIPRO')
    if env:
        return env
    local = os.path.join(os.path.expanduser('~'), 'Documents', 'tools', 'minipro_win', 'minipro.exe')
    return local if os.path.exists(local) else (shutil.which('minipro') or 'minipro')


MINIPRO = _find_minipro()

BAROQUE = rs.BAROQUE
CARD_SIZE = 0x8000
# IC7 bank 5 areas the Rosetta OS needs (re/build_v07.py): FX segment $6800 (2.3 KB used in v0.13, room to grow) and the
# SYNTH code $A000-$B668. Stock BIG BAND, COUNTRY and WALTZ1 sit there.
SYNTH_RESERVE = ((5, 0x6800, 0x7400), (5, 0xA000, 0xB668))
BANNER_OFF, BANNER_STOCK = 0x19E1, b'  ROLAND PRO-E  INTELL. ARRANGER'       # IC7 bank 0, 2 x 16 chars
VERSION_OFF, VERSION_STOCK = 0x2DA8, b'  ROLAND PRO E  VER 02.00 051289'      # IC4, 2 x 16 chars


def meter(ticks):
    """ticks per bar (24 ppqn) -> '4/4', '9/8', ..."""
    if ticks % 24 == 0:
        return f'{ticks // 24}/4'
    if ticks % 12 == 0:
        return f'{ticks // 12}/8'
    return f'{ticks}t'


class Style:
    """One style as it sits in a source: record bytes + the image to read its patterns from."""

    def __init__(self, source, index, name, record, image, bank_map):
        self.source, self.index, self.name = source, index, name
        self.record = bytes(record)
        self.image = image          # bytes the patterns are read from (IC7, or a card mapped as bank 0)
        self.bank_map = bank_map    # record bank nibble -> bank in self.image
        self.tempo, self.ticks = record[0x10], record[0x0F]

    @property
    def key(self):
        return (self.source, self.index)

    def refs(self):
        return rs.pattern_refs(self.record)

    def patterns(self):
        """{(bank_nibble, ptr): events} for every ROM pattern (IC4 silent ones excluded)."""
        out = {}
        for bank, ptr in self.refs().values():
            if ptr < 0xC000 and (bank, ptr) not in out:
                out[(bank, ptr)], _ = rs.decode_events(self.image, self.bank_map[bank], ptr)
        return out

    def size(self):
        return sum(len(rs.encode_events(ev)) for ev in self.patterns().values())


def stock_styles(ic7=None):
    ic7 = ic7 or open(STOCK_IC7, 'rb').read()
    out = []
    for n in range(rs.N_STYLES):
        rec = ic7[rs.DIR_AT - 0x4000 + rs.REC_LEN * n:][:rs.REC_LEN]
        name = ic7[rs.NAMES_AT - 0x4000 + 8 * n:][:8].decode('latin1').strip()
        out.append(Style('stock', n, name, rec, ic7, {b: b for b in range(8)}))
    return out


def load_cards(path):
    """A 32 KB TN-SC1 card or a multi-card dump (e.g. MSL-15, 16 x 32 KB). Returns [(card_label, [Style])]."""
    data = open(path, 'rb').read()
    if len(data) % CARD_SIZE:
        raise ValueError(f'{os.path.basename(path)}: size {len(data)} is not a multiple of 32 KB')
    cards = []
    for c in range(len(data) // CARD_SIZE):
        card = data[c * CARD_SIZE:(c + 1) * CARD_SIZE]
        if not card.startswith(b'Roland E-20'):
            continue
        cid = card[0x10:0x1A].split(b'\0')[0].decode('latin1')
        img = bytearray(0x40000)
        img[:CARD_SIZE] = card
        img = bytes(img)
        styles, seen = [], []
        for i in range(8):
            rec = card[0xB0 + rs.REC_LEN * i:0xB0 + rs.REC_LEN * (i + 1)]
            if rec in seen:
                continue
            seen.append(rec)
            name = card[0x30 + 16 * i:0x40 + 16 * i].decode('latin1').strip()
            src = f'{os.path.basename(path)}#{c}'
            styles.append(Style(src, i, name, rec, img, {8: 0, 9: 0}))
        label = f'{cid}  ({os.path.basename(path)} card {c + 1})' if len(data) > CARD_SIZE else cid
        cards.append((label, styles))
    return cards


def fit16(text):
    return text.encode('latin1', 'replace')[:16].ljust(16)


class Project:
    """32 slots -> Style, plus names/tempos and OS text. build() turns it into ROM images."""

    def __init__(self):
        self.stock_ic7 = open(STOCK_IC7, 'rb').read()
        self.stock_ic4 = open(STOCK_IC4, 'rb').read()
        self.stock = stock_styles(self.stock_ic7)
        self.slots = list(self.stock)                    # slot n -> Style
        self.names = [s.name for s in self.stock]
        self.tempos = [s.tempo for s in self.stock]
        self.banner = [' ROSETTA  PRO-E ', '  OS v0.3 2026  ']
        self.version = ['ROSETTA OS PRO-E', 'VER 00.30 110326']
        self.reserve = False             # True = keep bank 5 $A000-$B668 free for the Rosetta OS (SYNTH) code

    def synth_blockers(self):
        """slots whose stock patterns sit in the Rosetta OS code area (stock: COUNTRY + WALTZ1). Put other styles
        there and the area is freed."""
        doc = rs.decode(self.stock_ic7)
        inside = {k for k, p in doc['patterns'].items() for rb, ra, re_ in SYNTH_RESERVE
                  if p['bank'] == rb and p['addr'] < re_ and p['addr'] + p['size'] > ra}
        return [n for n, s in enumerate(self.slots) if s.source == 'stock'
                and {f'{b}:{p:04X}' for b, p in s.refs().values() if p < 0xC000} & inside]

    # ---- edits (Baroque is locked) ----
    def assign(self, slot, style):
        if slot == BAROQUE:
            raise PermissionError('BAROQUE is locked')
        self.slots[slot] = style
        self.names[slot] = style.name[:8]
        self.tempos[slot] = style.tempo

    def restore(self, slot):
        if slot == BAROQUE:
            return
        self.assign(slot, self.stock[slot])

    def rename(self, slot, name):
        if slot == BAROQUE:
            raise PermissionError('BAROQUE is locked')
        self.names[slot] = name[:8]

    def set_tempo(self, slot, bpm):
        if slot == BAROQUE:
            raise PermissionError('BAROQUE is locked')
        if not 20 <= bpm <= 250:
            raise ValueError('tempo 20-250')
        self.tempos[slot] = bpm

    def changed(self, slot):
        s = self.slots[slot]
        return s.key != ('stock', slot) or self.names[slot] != self.stock[slot].name or self.tempos[slot] != self.stock[slot].tempo

    # ---- space ----
    def space(self):
        """(bytes needed by non-stock patterns, bytes available after freeing unused stock patterns)."""
        _, holes, need = self._plan()
        return need, sum(e - s for _, s, e in holes)

    def _plan(self):
        doc = rs.decode(self.stock_ic7)
        kept = set()
        for s in self.slots:
            if s.source == 'stock':
                kept |= {f'{b}:{p:04X}' for b, p in s.refs().values() if p < 0xC000}
        free = {}
        freed = []
        for key, p in doc['patterns'].items():
            if key not in kept:
                freed.append(key)
                free.setdefault(p['bank'], []).append((p['addr'], p['addr'] + p['size']))
        holes = []
        for b in sorted(free):
            for s, e in _merge(free[b]):
                parts = [(s, e)]
                for rb, ra, re_ in (SYNTH_RESERVE if self.reserve else ()):     # keep the Rosetta OS code areas empty
                    if b == rb:
                        parts = [(x, y) for s2, e2 in parts for x, y in ((s2, min(e2, ra)), (max(s2, re_), e2)) if y > x]
                holes += [[b, x, y] for x, y in parts]
        need = sum(s.size() for s in {x.key: x for x in self.slots if x.source != 'stock'}.values())
        return freed, holes, need

    # ---- build ----
    def build(self):
        """-> (ic7_256k, ic4_16k, report lines). Raises on any check failure."""
        doc = rs.decode(self.stock_ic7)
        freed, holes, need = self._plan()
        img = bytearray(self.stock_ic7)
        for key in freed:
            p = doc['patterns'][key]
            o = rs.off(p['bank'], p['addr'])
            img[o:o + p['size']] = b'\xff' * p['size']
        placed = {}                      # (style key, bank nibble, ptr) -> (bank, addr)
        report = []
        for slot, s in enumerate(self.slots):
            rec = bytearray(s.record)
            if s.source != 'stock':
                pats = s.patterns()
                for (bn, ptr), ev in sorted(pats.items(), key=lambda t: -len(rs.encode_events(t[1]))):
                    k = (s.key, bn, ptr)
                    if k in placed:
                        continue
                    data = rs.encode_events(ev)
                    for h in holes:
                        if h[2] - h[1] >= len(data):
                            placed[k] = (h[0], h[1])
                            o = rs.off(h[0], h[1])
                            img[o:o + len(data)] = data
                            h[1] += len(data)
                            break
                    else:
                        raise RuntimeError(f'out of space: needs {need} bytes, {sum(e - s for _, s, e in holes)} left')
                for (p, kk, c), (bn, ptr) in s.refs().items():
                    if ptr < 0xC000:
                        _set_ref(rec, p, kk, c, *placed[(s.key, bn, ptr)])
                    else:
                        _set_ref(rec, p, kk, c, 0, ptr)
            rec[0x10] = self.tempos[slot]
            o = rs.DIR_AT - 0x4000 + rs.REC_LEN * slot
            img[o:o + rs.REC_LEN] = rec
            o = rs.NAMES_AT - 0x4000 + 8 * slot
            img[o:o + 8] = self.names[slot].encode('latin1', 'replace')[:8].ljust(8)
            if self.changed(slot):
                report.append(f'slot {slot:2d} (BANK {slot // 8 + 1} no.{slot % 8 + 1}) = {self.names[slot]:8s} '
                              f'{self.tempos[slot]} BPM {meter(s.ticks)}  from {s.source}')
        assert img[BANNER_OFF:BANNER_OFF + 32] == BANNER_STOCK
        img[BANNER_OFF:BANNER_OFF + 32] = fit16(self.banner[0]) + fit16(self.banner[1])
        rs.bank_fix(img)
        if self.reserve:
            for rb, ra, re_ in SYNTH_RESERVE:
                o = rb * 0x8000 + ra - 0x4000
                if any(x != 0xFF for x in img[o:o + re_ - ra]):
                    names = ', '.join(f'BANK {n // 8 + 1} no.{n % 8 + 1} {self.names[n]}' for n in self.synth_blockers())
                    raise RuntimeError(f'Rosetta OS needs IC7 bank 5 ${ra:04X}-${re_:04X} free. Put other styles into: {names}')
        ic4 = bytearray(self.stock_ic4)
        assert ic4[VERSION_OFF:VERSION_OFF + 32] == VERSION_STOCK
        ic4[VERSION_OFF:VERSION_OFF + 32] = fit16(self.version[0]) + fit16(self.version[1])
        self._verify(bytes(img))
        return bytes(img), bytes(ic4), report

    def _verify(self, img):
        for (o, n), want in rs.baroque_bytes(self.stock_ic7).items():
            if img[o:o + n] != want:
                raise RuntimeError(f'BAROQUE changed at IC7 {o:#x}: refused')
        for slot, s in enumerate(self.slots):
            rec = img[rs.DIR_AT - 0x4000 + rs.REC_LEN * slot:][:rs.REC_LEN]
            got = rs.pattern_refs(rec)
            for key, (bn, ptr) in s.refs().items():
                b2, p2 = got[key]
                if ptr >= 0xC000:
                    assert p2 == ptr
                    continue
                want, _ = rs.decode_events(s.image, s.bank_map[bn], ptr)
                have, _ = rs.decode_events(img, b2, p2)
                if want != have:
                    raise RuntimeError(f'slot {slot} {key}: pattern mismatch after build')
        for k in range(8):
            b0 = k * 0x8000
            assert ((img[b0] << 8 | img[b0 + 1]) + sum(img[b0 + 2:b0 + 0x8000])) & 0xFFFF == 0

    # ---- save / load (JSON-able dict) ----
    def to_dict(self, card_paths):
        return {'format': 'proe-romstudio-1', 'cards': card_paths,
                'slots': [list(s.key) for s in self.slots], 'names': self.names, 'tempos': self.tempos,
                'banner': self.banner, 'version': self.version}

    def from_dict(self, d, styles_by_key):
        for n, key in enumerate(d['slots']):
            key = tuple(key)
            if n == BAROQUE:
                continue
            self.slots[n] = styles_by_key[key] if key[0] != 'stock' else self.stock[key[1]]
        self.names = [self.stock[BAROQUE].name if n == BAROQUE else x for n, x in enumerate(d['names'])]
        self.tempos = [self.stock[BAROQUE].tempo if n == BAROQUE else x for n, x in enumerate(d['tempos'])]
        self.banner, self.version = d['banner'], d['version']


def _merge(ranges):
    out = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def _set_ref(rec, p, k, c, bank, ptr):
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


def write_images(ic7, ic4, out_dir, tag):
    """W27C040 (IC7 x2) + W27C512 (IC4 x4) burn images. Returns {name: (path, md5)}."""
    os.makedirs(out_dir, exist_ok=True)
    res = {}
    for name, data in ((f'IC7_{tag}_W27C040.bin', ic7 * 2), (f'IC4_{tag}_W27C512.bin', ic4 * 4)):
        p = os.path.join(out_dir, name)
        open(p + '.tmp', 'wb').write(data)
        os.replace(p + '.tmp', p)
        res[name] = (p, hashlib.md5(data).hexdigest())
    return res


# ---- T48 via minipro ----
CHIPS = {'IC7': ('W27C040', 0xDA86), 'IC4': ('W27C512@DIP28', 0xDA08), 'IC28': ('W27C512@DIP28', 0xDA08),
         'IC13': ('W27C512@DIP28', 0xDA08), 'IC37': ('W27C040', 0xDA86), 'IC38': ('W27C040', 0xDA86)}
BURN_MIN = {'W27C040': 3.5, 'W27C512@DIP28': 1}


def _minipro(args, timeout=600):
    r = subprocess.run([MINIPRO] + args, capture_output=True, text=True, timeout=timeout,
                       cwd=os.path.dirname(MINIPRO), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return r.returncode, r.stdout + r.stderr


def chip_id(which):
    dev, want = CHIPS[which]
    code, out = _minipro(['-p', dev, '-D'], timeout=30)
    m = re.search(r'Chip ID: 0x([0-9A-Fa-f]+)', out)
    got = int(m.group(1), 16) if m else None
    return got, got == want, out


def burn(which, image_path, log=print, backup_dir=None):
    """ID check -> backup read of what's on the chip -> erase/write/verify -> readback compare.
    Returns True only if the chip == image."""
    dev, want = CHIPS[which]
    got, ok, out = chip_id(which)
    if not ok:
        log(f'chip ID {got and hex(got)} is not {want:#x} ({dev}): not burning.\n{out}')
        return False
    if backup_dir:
        import time
        os.makedirs(backup_dir, exist_ok=True)
        bk = os.path.join(backup_dir, f'{which}_before_{time.strftime("%Y%m%d_%H%M%S")}.bin')
        _minipro(['-p', dev, '-r', bk])
        if os.path.exists(bk):
            log(f'{which}: old chip content saved to {bk} (md5 {hashlib.md5(open(bk, "rb").read()).hexdigest()[:8]})')
        else:
            log(f'{which}: backup read FAILED: not burning.')
            return False
    log(f'{which}: {dev} found (ID {got:#x}). Writing, ~{BURN_MIN.get(dev, 3)} min, don\'t pull the chip...')
    code, out = _minipro(['-p', dev, '-w', image_path])
    if 'Verification OK' not in out:
        keep = [l for l in out.splitlines() if not re.search(r'Writing\s+Code\.\.\.\s+\d+%|Reading\s+Code\.\.\.\s+\d+%', l)]
        log('write/verify FAILED:\n' + '\n'.join(keep[-6:]))
        return False
    rb = image_path + '.readback'
    _minipro(['-p', dev, '-r', rb])
    same = os.path.exists(rb) and open(rb, 'rb').read() == open(image_path, 'rb').read()
    log(f'{which}: verify OK, readback {"identical" if same else "DIFFERENT"}')
    return same
