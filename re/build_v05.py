"""Build Rosetta OS PRO-E v0.5: SYNTH EDIT (+ NUMBER 1-5 partial select / on-off on the tempo LEDs, VOICE page) (Juno-style macro editing) on top of your own build, for the pin-31 mod
(IC7 A18 = HC11 PA6, see docs/PIN31_MOD.md).

  python -I build_v05.py [IC7_base.bin IC4_base.bin]   -> ../build/IC7_v0.5_W27C040.bin, IC4_v0.5_W27C512.bin

The bases default to ../build/IC7_v0.3b_W27C040.bin and IC4_v0.3b_W27C512.bin (a ROM Studio build). The IC7 base must
have bank 5 $A000-$B668 free ($FF); stock IC7 doesn't, ROM Studio builds that relocate patterns usually do. The
build stops if it isn't. Needs dumps/ (IC28 for the CK-34 clamp table).

Layout:
  lower half = v0.3b + the key hooks in bank 0 (the OS she boots, PA6 low)
  upper half = a mirror of the lower half, plus the SYNTH code + tables in bank 5 at CODE. Lower bank 5 is free ($FF)
               there and stays reserved, so an interrupt that banks in bank 5 while PA6 is high reads nothing it needs.
Menus are data, like the D-70 Rosetta OS (PAGES / items): edit the tables below, rebuild.
"""
import hashlib, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hc11asm as A
import rosetta_style as rs

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, '..', 'build')
DUMPS = os.path.join(HERE, '..', 'dumps')
BANK, CODE, CODE_END = 5, 0xA000, 0xB668          # free run in lower bank 5: $6734-$B668
BANKSEL = BANK << 4

# ---- RAM (SRAM page 0 gap $2DA6-$30A2, no stock references) ----
RAM = dict(RAMBASE=0x2DA6, EDIT=0x2E00, LVL=0x2E01, SEL=0x2E02, ROW=0x2E03, PARTIX=0x2E04, VALID=0x2E05,
           OLDSH=0x2E06, DEV=0x2E07, DELTA=0x2E08, MAXV=0x2E09, SUM=0x2E0A, TMP=0x2E0B, VAL=0x2E0C, NEWV=0x2E0D,
           MASK=0x2E0E, REFP=0x2E0F, PNUM=0x2E10, KIX=0x2E11, OFFS=0x2E12, SIGN=0x2E13, MAGN=0x2E14,
           T16=0x2E16, IT=0x2E18, IDXB=0x2E1A, IDX=0x2E1C, PB=0x2E1E, PB2=0x2E20, VPTR=0x2E22, QT=0x2E24,
           SELP=0x2E26, SAV10=0x2E27, SAV16=0x2E28, LF1=0x2E29, LF2=0x2E2A, LB=0x2E2B, ACC=0x2E2C,
           LINE1=0x2E30, LINE2=0x2E40, WORK=0x2E50, HOOKBASE=0x2F50)
assert RAM['WORK'] + 246 <= RAM['HOOKBASE']
HW = dict(SHADOW=0x0A, LATCH=0x180D, PORTA=0x1000, BANKSEL=BANKSEL, ENTRY=CODE, BEAT=0x10, BEAT2=0x16)

# ---- menu data ----
T_NUM, T_SGN, T_LIST, T_PCM, T_WAVE, T_PART, T_CLIST, T_RING = range(8)
F_ABS, F_FIXP = 1, 2
LISTS = {
    'offon': ['OFF', 'ON'],
    'wave': ['SQUARE', 'SAW'],
    'part': ['SOLO', 'LOWER', 'BASS'],
    'struct': ['S+S', 'S&S', 'P+S', 'P&S', 'S&P', 'P+P', 'P&P', 'S/S', 'P/P', 'S*S', 'P*S', 'S*P', 'P*P'],
    'keyf': ['-1', '-1/2', '-1/4', '0', '1/8', '1/4', '3/8', '1/2', '5/8', '3/4', '7/8', '1', '5/4', '3/2', '2',
             'S1', 'S2'],
}
LIST_IDS = {k: i for i, k in enumerate(LISTS)}
# partial offsets (MT-32 timbre layout, max values from the CK-34's own clamp table)
WG_COARSE, WG_FINE, WG_KEYF, WG_BEND, WG_WAVE, WG_PCM, WG_PW, WG_PWV = range(8)
LFO_RATE, LFO_DEPTH, LFO_MOD = 20, 21, 22
TVF_CUT, TVF_RESO, TVF_KEYF, TVF_DEPTH, TVF_VELO = 23, 24, 25, 28, 29
TVF_T = [32, 33, 34, 35, 36]
TVF_SUS = 40
TVA_LEVEL, TVA_VELO = 41, 42
TVA_T = [49, 50, 51, 52, 53]
TVA_SUS = 57


def it(label, typ, offs, mx=0, aux=0, flags=0):
    return (label, typ, offs, mx, aux, flags)


ITEMS = {
    'st12':    it('STRUCT1-2', T_CLIST, [0x0A], 12, LIST_IDS['struct']),          # common bytes: offsets into the timbre
    'st34':    it('STRUCT3-4', T_CLIST, [0x0B], 12, LIST_IDS['struct']),
    'ring12':  it('RING 1-2', T_RING, [0x0A], 1, LIST_IDS['offon']),
    'ring34':  it('RING 3-4', T_RING, [0x0B], 1, LIST_IDS['offon']),
    'lvl1':    it('LEVEL P1', T_NUM, [TVA_LEVEL], aux=1, flags=F_FIXP),
    'lvl2':    it('LEVEL P2', T_NUM, [TVA_LEVEL], aux=2, flags=F_FIXP),
    'lvl3':    it('LEVEL P3', T_NUM, [TVA_LEVEL], aux=3, flags=F_FIXP),
    'lvl4':    it('LEVEL P4', T_NUM, [TVA_LEVEL], aux=4, flags=F_FIXP),
    'pcm':     it('WAVE', T_PCM, [WG_PCM], 255, flags=F_ABS),
    'osc':     it('WAVE', T_WAVE, [WG_WAVE], 1, LIST_IDS['wave'], F_ABS),
    'pw':      it('PULSE W', T_NUM, [WG_PW]),
    'pwv':     it('PW VELO', T_SGN, [WG_PWV], aux=7),
    'tune':    it('TUNE', T_SGN, [WG_COARSE], aux=48),
    'fine':    it('FINE', T_SGN, [WG_FINE], aux=50),
    'wkeyf':   it('KEY FOLLW', T_LIST, [WG_KEYF], 16, LIST_IDS['keyf'], F_ABS),
    'bend':    it('BENDER', T_LIST, [WG_BEND], 1, LIST_IDS['offon'], F_ABS),
    'cutoff':  it('CUTOFF', T_NUM, [TVF_CUT]),
    'reso':    it('RESO', T_NUM, [TVF_RESO]),
    'envamt':  it('ENV AMT', T_NUM, [TVF_DEPTH]),
    'fkeyf':   it('KEY TRACK', T_LIST, [TVF_KEYF], 14, LIST_IDS['keyf'], F_ABS),
    'fvelo':   it('VELOCITY', T_NUM, [TVF_VELO]),
    'attack':  it('ATTACK', T_NUM, [TVA_T[0], TVF_T[0]]),                       # one ENV for VCA + VCF, Juno style
    'decay':   it('DECAY', T_NUM, TVA_T[1:4] + TVF_T[1:4]),
    'sustain': it('SUSTAIN', T_NUM, [TVA_SUS, TVF_SUS]),
    'release': it('RELEASE', T_NUM, [TVA_T[4], TVF_T[4]]),
    'level':   it('LEVEL', T_NUM, [TVA_LEVEL]),
    'avelo':   it('VELOCITY', T_SGN, [TVA_VELO], aux=50),
    'lrate':   it('RATE', T_NUM, [LFO_RATE]),
    'ldepth':  it('DEPTH', T_NUM, [LFO_DEPTH]),
    'lmod':    it('MOD WHEEL', T_NUM, [LFO_MOD]),
    'part':    it('PART', T_PART, [], 2, LIST_IDS['part'], F_ABS),
}
PG_ROWS = 10                         # page record = title 11 + live + count + 10 item indices + pad = 24 bytes
PAGES = [  # (title, live, items): order = scroll order; BANK 1-8 jump to the first eight
    ('VOICE', 0, ['st12', 'st34', 'ring12', 'ring34', 'lvl1', 'lvl2', 'lvl3', 'lvl4']),
    ('PCM WAVE', 0, ['pcm']),
    ('SYNTH OSC', 0, ['osc', 'pw', 'pwv']),
    ('PITCH', 0, ['tune', 'fine', 'wkeyf', 'bend']),
    ('FILTER', 0, ['cutoff', 'reso', 'envamt', 'fkeyf', 'fvelo']),
    ('ENVELOPE', 0, ['attack', 'decay', 'sustain', 'release']),
    ('AMP', 0, ['level', 'avelo']),
    ('LIVE FILTER', 1, ['cutoff', 'reso']),          # stays on BANK 8
    ('LFO', 0, ['lrate', 'ldepth', 'lmod']),
    ('PART', 0, ['part']),
]
ITEM_KEYS = list(ITEMS)
assert len(PAGES) <= 19


def ic28_partial_max():
    d = open(os.path.join(DUMPS, 'ck34_ic28_control_R15179974_CK-34_v2.06.bin'), 'rb').read()
    t = d[0x4873:0x4873 + 72]                          # CK-34 timbre clamp table: 14 common + 58 partial
    assert list(t[:14]) == [127] * 10 + [12, 12, 15, 1], 'IC28 clamp table not where expected'
    assert t[14 + WG_PCM] == 127 and t[14 + TVF_RESO] == 30
    return bytes(t[14:])


def deftone(ic7):
    """Fallback tone when the CK-34 does not answer: the PRO-E's own AUDIO TEST timbre (bank 1 $BBBA)."""
    o = 1 * 0x8000 + (0xBBBA - 0x4000)
    hdr = bytes(ic7[o:o + 8])
    assert hdr == bytes.fromhex('f041011612020000'), hdr.hex()
    t = bytearray(ic7[o + 8:o + 8 + 130])              # name, common, partials 1-2
    t += t[14 + 58:14 + 116] * 2                       # partials 3-4 = partial 2
    assert len(t) == 246
    return bytes(t)


def tables_asm(pmax, dtone):
    def text(s, n):
        assert len(s) <= n, s
        return 'db "%s"' % s.ljust(n)
    out = ['PAGES:']
    for title, live, keys in PAGES:
        idx = [ITEM_KEYS.index(k) for k in keys] + [0] * (PG_ROWS - len(keys))
        assert len(keys) <= PG_ROWS, title
        out += ['        ' + text(title, 11), '        db %d,%d,%s,0' % (live, len(keys), ','.join(map(str, idx)))]
    out.append('ITEMS:')
    for k in ITEM_KEYS:
        label, typ, offs, mx, aux, flags = ITEMS[k]
        assert len(offs) <= 6
        out += ['        db %d,%d,%d,%d,%d,%s' % (typ, mx, aux, flags, len(offs),
                                                 ','.join(map(str, offs + [255] * (6 - len(offs))))),
                '        ' + text(label, 9)]
    out.append('PMAX:   db ' + ','.join(map(str, pmax)))
    out.append('listtab: dw ' + ','.join('list_%s' % k for k in LISTS))
    for k, names in LISTS.items():
        out.append('list_%s:' % k)
        out += ['        ' + 'db "%s"' % n.rjust(6) for n in names]
    out.append('DEFTONE: db ' + ','.join(map(str, dtone)))
    return '\n'.join(out) + '\n'


def patch(img, base, addr, old, new, what):
    o = addr - base
    if bytes(img[o:o + len(old)]) != old:
        sys.exit(f'{what}: stock bytes at ${addr:04X} are {bytes(img[o:o + len(old)]).hex()}, expected {old.hex()}')
    img[o:o + len(new)] = new
    print(f'  patched ${addr:04X} {what}: {old.hex()} -> {new.hex()}')


def build(ic7_base=None, ic4_base=None):
    lower = bytearray(open(ic7_base or os.path.join(BUILD, 'IC7_v0.3b_W27C040.bin'), 'rb').read()[:0x40000])
    ic4 = bytearray(open(ic4_base or os.path.join(BUILD, 'IC4_v0.3b_W27C512.bin'), 'rb').read()[:0x4000])
    b5 = BANK * 0x8000
    assert all(x == 0xFF for x in lower[b5 + CODE - 0x4000:b5 + CODE_END - 0x4000]), 'IC7 base: bank 5 $A000-$B668 is not free ($FF). Use a ROM Studio build, not the stock dump'

    syms = dict(RAM, **HW)
    ram_segs, ram_syms = A.assemble(open(os.path.join(HERE, 'synth_v05_ram.asm')).read(), dict(syms))
    tramp = bytes(ram_segs[RAM['RAMBASE']])
    hooks = bytes(ram_segs[RAM['HOOKBASE']])
    assert ram_syms['HOOK_END'] <= 0x30A2, 'hooks run past the free RAM gap'
    assert ram_syms['TRAMP_END'] <= RAM['EDIT'], 'trampoline runs into the variables'
    syms.update({k: ram_syms[k] for k in ('RAMKEY', 'RAMTICK', 'BOOTRET', 'HB1', 'HB2', 'HB3', 'HB4', 'HB5')})
    syms.update(HOOK_LEN=len(hooks), TRAMP_LEN=len(tramp), CODE=CODE, NPAGES=len(PAGES), PGSIZE=24)
    src = (open(os.path.join(HERE, 'synth_v05.asm')).read() + tables_asm(ic28_partial_max(), deftone(lower))
           + 'TRAMP_IMG: db ' + ','.join(map(str, tramp)) + '\n' + 'HOOK_IMG: db ' + ','.join(map(str, hooks)) + '\n')
    segs, csyms = A.assemble(src, syms)
    code = bytes(segs[CODE])
    assert CODE + len(code) <= CODE_END, f'SYNTH code is {len(code)} bytes, past ${CODE_END:04X}'

    # IC4 BOOTCOPY at $FFB1 (37 free bytes): page 0 + bank 5 + PA6 high, jsr boot8, which returns through BOOTRET
    boot_segs, _ = A.assemble(f'''
        org $FFB1
        pshx
        pshy
        psha
        pshb
        ldab $0A
        ldaa #{BANKSEL}
        staa $0A
        staa $180D
        stab {RAM['OLDSH']}
        ldx #$1000
        bset 0,x,#$40
        jsr {CODE + 3}
        pulb
        pula
        puly
        pulx
        rts
''')
    bootcopy = bytes(boot_segs[0xFFB1])
    assert len(bootcopy) <= 37, f'BOOTCOPY is {len(bootcopy)} bytes'

    rk, rt = syms['RAMKEY'], syms['RAMTICK']
    patch(lower, 0x4000, 0x4CF7, bytes.fromhex('bd4d32'), bytes([0xBD, rk >> 8, rk & 0xFF]), 'key release -> RAMKEY')
    patch(lower, 0x4000, 0x4D01, bytes.fromhex('bd4d32'), bytes([0xBD, rk >> 8, rk & 0xFF]), 'key press -> RAMKEY')
    patch(ic4, 0xC000, 0xFA7B, bytes.fromhex('7e83ff'), bytes([0x7E, rt >> 8, rt & 0xFF]), 'page $0D tick -> RAMTICK')
    patch(ic4, 0xC000, 0xE625, bytes.fromhex('010101'), bytes.fromhex('bdffb1'), 'boot hook -> BOOTCOPY')
    # v0.5: the 5 tempo-LED writers -> RAM hooks that skip the write while SYNTH EDIT is open (no IC4 free space needed)
    for addr, old, hook in ((0xC490, '15100f15160f141008141608', 'HB1'), (0xC4A7, '9610bdd2d897109616bdd2d89716', 'HB2'),
                            (0xC4C7, '15100f15160f', 'HB3'), (0xC4D5, '151007151607141008141608', 'HB4'),
                            (0xC859, '961084f01b9710961684f01b9716', 'HB5')):
        o = bytes.fromhex(old); h = syms[hook]
        patch(ic4, 0xC000, addr, o, bytes([0xBD, h >> 8, h & 0xFF]) + b'\x01' * (len(o) - 3), 'tempo LEDs -> ' + hook)
    patch(ic4, 0xC000, 0xFFB1, b'\xff' * len(bootcopy), bootcopy, 'BOOTCOPY')
    assert ic4[0x2D48] == 0x00
    lower[0x19E1:0x19E1 + 32] = b' ROSETTA  PRO-E ' + b' OS v0.5c SYNTH '
    ic4[0x2DA8:0x2DA8 + 32] = b'ROSETTA OS PRO-E' + b'VER 00.51 110326'
    rs.bank_fix(lower)

    up = bytearray(lower)
    up[b5 + CODE - 0x4000:b5 + CODE - 0x4000 + len(code)] = code
    rs.bank_fix(up)
    img7 = bytes(lower) + bytes(up)
    return img7, bytes(ic4) * 4, dict(csyms, **syms), code, tramp, bootcopy


if __name__ == '__main__':
    img7, img4, syms, code, tramp, bootcopy = build(*sys.argv[1:3])
    print('SYNTH code + tables: %d bytes at $%04X-$%04X (bank %d, upper half), trampoline %d bytes, BOOTCOPY %d bytes'
          % (len(code), CODE, CODE + len(code) - 1, BANK, len(tramp), len(bootcopy)))
    for name, data in (('IC7_v0.5c_W27C040.bin', img7), ('IC4_v0.5c_W27C512.bin', img4)):
        p = os.path.join(BUILD, name)
        open(p + '.tmp', 'wb').write(data)
        os.replace(p + '.tmp', p)
        print(f'{name}  md5 {hashlib.md5(data).hexdigest()}')
    lst = '\n'.join(f'{a:04X} {raw.hex():10s} {mn:6s} {ops}' for a, mn, ops, raw in A.disasm(code[:syms['rq1'] - CODE], CODE))
    open(os.path.join(BUILD, 'v0.5_synth.lst'), 'w').write(lst)
