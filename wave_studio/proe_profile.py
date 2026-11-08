"""PRO-E (CK-34 voice board) machine profile for Rosetta Wave Studio.

  wave space = IC37 (R15449121, lower 512 KB: the MT-32 set) + IC38 (R15179945, upper 512 KB: CM-32L effects)
  control    = IC28 (R15179974, 64 KB): PCM wave table 0x8100 (256 x 4, the D-110 IC12 struct), 128 preset timbres
               (A map 0x8000, B map 0x8080, compressed), rhythm timbres (R map 0x8500) + rhythm setup 0x8580 (keys 24-108)
  tone names = IC7 (PRO-E style/OS ROM) bank 0 file 0x24D9, 12 chars x 128, same order as the CK-34 timbres
               (PRO-E tone n = program change n = timbre n)
IC28 has no wave names, so every wave is named after the first PRO-E tone (or rhythm sound) that plays it.
"""
STRUCT = ['S+S', 'S&S', 'P+S', 'P&S', 'S&P', 'P+P', 'P&P', 'S/S', 'P/P', 'S*S', 'P*S', 'S*P', 'P*P']
TABLE_AT = 0x8100
TONE_NAMES_AT = 0x24D9
LO, HI, CT = 'IC37', 'IC38', 'IC28'


def _w(rom, a):
    return int(rom[a]) | int(rom[a + 1]) << 8


def _timbre(rom, fa):
    """expand a compressed timbre at file address fa -> (name, common14, [4 x 58-byte partials])"""
    common = bytes(rom[fa:fa + 14])
    mute, parts, src = common[12], [], fa + 14
    for t in range(4):
        if t and not (mute >> t) & 1:
            src -= 58
        parts.append(bytes(rom[src:src + 58]))
        src += 58
    return common[:10].decode('latin1', 'replace').strip(), common, parts


def pcm_waves(common, parts):
    """table indices of the PCM partials that sound (mute bit set and the structure says PCM)"""
    s1, s2 = STRUCT[min(common[10], 12)], STRUCT[min(common[11], 12)]
    kinds = [s1[0], s1[2], s2[0], s2[2]]
    return [((parts[p][4] & 2) * 64 + parts[p][5], p + 1)
            for p in range(4) if (common[12] >> p) & 1 and kinds[p] == 'P']


def tone_names(ic7):
    if ic7 is None or len(ic7) < TONE_NAMES_AT + 12 * 128:
        return ['TONE %03d' % i for i in range(128)]
    return [bytes(ic7[TONE_NAMES_AT + 12 * i:TONE_NAMES_AT + 12 * i + 12]).decode('latin1', 'replace').strip()
            for i in range(128)]


def usage(ctrl, ic7=None):
    """-> {wave index: [(who, partial), ...]} for every preset tone and rhythm key"""
    names = tone_names(ic7)
    use = {}
    for t in range(128):
        mp = 0x8000 if t < 64 else 0x8080
        fa = 0x8000 + _w(ctrl, mp + 2 * (t % 64))
        if fa + 14 > len(ctrl):
            continue
        _, common, parts = _timbre(ctrl, fa)
        for idx, p in pcm_waves(common, parts):
            use.setdefault(idx, []).append((names[t], p))
    for k in range(85):
        tn = int(ctrl[0x8580 + 4 * k])
        if tn < 0x40:
            continue
        ptr = _w(ctrl, 0x8500 + 2 * (tn - 0x40))
        fa = (ptr & ~0x4000) + (0x4000 if ptr & 0x4000 else 0)
        nm, common, parts = _timbre(ctrl, fa)
        for idx, p in pcm_waves(common, parts):
            use.setdefault(idx, []).append(('%s (key %d)' % (nm, k + 24), p))
    return use


def wave_names(ctrl, ic7=None):
    """8-char name per table entry + a one-line 'used by' text"""
    use = usage(ctrl, ic7)
    names, used = [], []
    for i in range(256):
        u = use.get(i, [])
        if u:
            who = u[0][0].split(' (key')[0]
            names.append(who.replace('  ', ' ')[:8].ljust(8))
            more = len({w for w, _ in u}) - 1
            used.append('used by ' + ', '.join(sorted({w for w, _ in u}))[:140] + ('' if more < 1 else ''))
        else:
            names.append(('WAVE%03d' % i).ljust(8))
            used.append('no preset tone uses it (reachable by editing a tone in SYNTH EDIT)')
    return names, used
