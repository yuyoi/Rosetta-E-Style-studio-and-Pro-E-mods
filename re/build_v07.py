"""Build Rosetta OS PRO-E v0.7: ROSETTA FX pages (IC13 FX + IC28 LAB) + MIDI remote control, on top of v0.6: SYNTH EDIT + JUNO page (saw / pulse / sub / detune / range, PW modes, pitch env) (+ NUMBER 1-5 partial select / on-off on the tempo LEDs, VOICE page) (Juno-style macro editing) on top of your own build, for the pin-31 mod
(IC7 A18 = HC11 PA6, see docs/PIN31_MOD.md).

  python -I build_v07.py [IC7_base.bin IC4_base.bin]   -> ../build/IC7_v0.7_W27C040.bin (IC4 = the v0.5b one, unchanged)

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
           JOP=0x2E2D, JV=0x2E2E, JC=0x2E2F,
           FXT=0x3050, FXL=0x3058, FXM=0x3060, FXF=0x3061, FXLV=0x3062, TXN=0x3063, TXB=0x3064, WETP=0x306C,
           WETA=0x306F, RACT=0x3070, RCNT=0x3071, MBYTE=0x3072, PKF=0x3073, PKEY=0x3074, PKB=0x3075, RADR=0x3076,
           RBUF=0x3078, BMODE=0x309A, BSKIP=0x309B, BLAST=0x309C,   # v0.10 bender (RBUF 40 -> 34 bytes)
           PEND=0x309D, PCNT=0x309E, UPG=0x309F, UIDX=0x30A0,     # v0.13 USER PROGRAM tones
           LINE1=0x2E30, LINE2=0x2E40, WORK=0x2E50, HOOKBASE=0x2F50,
           # v0.14 ARPEGGIATOR: held notes + settings after the trampoline ($2DF0-$2DFF), runtime after WORK ($2F46-$2F4F)
           ARPN=0x2DF0, ARPM=0x2DF8, ARPR=0x2DF9, ARPO=0x2DFA, ARPL=0x2DFB, ARPC=0x2DFC, ARPT=0x2DFD, ARPI=0x2DFE,
           ARPS=0x2DFF, ARPK=0x2F46, ARPVL=0x2F48, ARPG=0x2F49, ARPQ=0x2F4A, ARPRN=0x2F4B, ARPX=0x2F4C, ARPP=0x2F4D,
           ARPY=0x2F4E)
assert RAM['WORK'] + 246 <= RAM['ARPK'] and RAM['ARPY'] + 2 <= RAM['HOOKBASE']
RBUFN = 34
assert RAM['RBUF'] + RBUFN <= 0x30A2
HW = dict(SHADOW=0x0A, LATCH=0x180D, PORTA=0x1000, BANKSEL=BANKSEL, ENTRY=CODE, BEAT=0x10, BEAT2=0x16,
          MIDIOUT=0xE84D, LCDWAIT=0xD5E9, LCDCMD=0xD611, LCDDATA=0x160E, RBUFN=RBUFN)
FXSEG, FXSEG_END = 0x6800, 0xA000                 # v0.7: second code segment, free in both halves of bank 5

# ---- menu data ----
T_NUM, T_SGN, T_LIST, T_PCM, T_WAVE, T_PART, T_CLIST, T_RING, T_JUNO, T_PW, T_FX, T_WET, T_BEND, T_ARP = range(14)
ARP_TICKS = [24, 12, 8, 6, 4, 3]                     # v0.14 RATE list -> 24 PPQN ticks per step (must match arptk)
F_T, F_L, F_K, F_S = range(4)                     # FX fields: time, level, level*2 + time>>2, time & 3
F_ABS, F_FIXP = 1, 2
def _duty(pw):
    """LA32 square duty in % for PW 0-100 (Munt LA32WaveGenerator: 0-50 = 50 %, then 2^-((PW*2.55-128)/64) / 2)"""
    v = int(pw * 255 / 100 + 0.5)
    return 50 * 2 ** (-((v - 128) * 64 if v > 128 else 0) / 4096)


DUTY = [_duty(pw) for pw in range(50, 101)]
PWTAB = [0, 58, 65, 75, 87, 100]                     # must match pwtab in synth_v06.asm
LISTS = {
    'offon': ['OFF', 'ON'],
    'wave': ['SQUARE', 'SAW'],
    'part': ['SOLO', 'LOWER', 'BASS'],
    'struct': ['S+S', 'S&S', 'P+S', 'P&S', 'S&P', 'P+P', 'P&P', 'S/S', 'P/P', 'S*S', 'P*S', 'S*P', 'P*P'],
    'go': ['TURN >'],
    'rate': ['0.25Hz', '0.4Hz', '0.5Hz', '0.7Hz', '0.9Hz', '1.5Hz', '3Hz', '6Hz'],
    'dms': ['%dms' % t for t in (40, 60, 80, 100, 120, 150, 180, 200, 230, 260, 300, 333, 375, 420, 460, 495)],
    'fb': ['0%', '38%', '63%', '75%'],
    # v0.9: IC13 v8 mode 0 = RESONANT FILTER (gen_filter.py; Plate dropped): program = cutoff (16), sawBits = output + reso
    'cut': [('%dHz' % f) if f < 1000 else ('%.1fk' % (f / 1000)) for f in [round(110 * 2 ** (k * 6.0 / 15)) for k in range(16)]],
    'fres': ['LP', 'LP RES', 'BP', 'BP RES'],
    'bendm': ['PITCH', 'CUTOFF', 'RESO'],         # v0.10: what the bender moves (CUTOFF / RESO = the DSP filter)
    'tone': ['OPEN', 'SOFT', 'DARK', 'DULL'],
    # v0.8: IC13 v7 mode 3 = LO-FI (programs 0-7 = gen_fx.LOFI_PICK, plain crush) + DRIVE (8-15 = DRIVE_PICK, x4 .. x512)
    'crush': ['%db' % (16 - c) for c in (0, 2, 3, 4, 5, 6, 7, 8)] + ['DRIVE%d' % n for n in range(1, 9)],
    'wet': ['DRY', 'DRY+FX', 'FXONLY', 'TEST 3'],
    'pwmode': ['SQUARE'] + ['%d%%' % round(DUTY[pw - 50]) for pw in PWTAB[1:]],
    'range': ["16'", "8'", "4'", "2'"],
    'keyf': ['-1', '-1/2', '-1/4', '0', '1/8', '1/4', '3/8', '1/2', '5/8', '3/4', '7/8', '1', '5/4', '3/2', '2',
             'S1', 'S2'],
    'arpm': ['OFF', 'UP', 'DOWN', 'UPDOWN', 'RANDOM'],    # v0.14 ARPEGGIATOR
    'arpr': ['1/4', '1/8', '1/8T', '1/16', '1/16T', '1/32'],
    'arpo': ['1 OCT', '2 OCT', '3 OCT'],
}
LIST_IDS = {k: i for i, k in enumerate(LISTS)}
# partial offsets (MT-32 timbre layout, max values from the CK-34's own clamp table)
WG_COARSE, WG_FINE, WG_KEYF, WG_BEND, WG_WAVE, WG_PCM, WG_PW, WG_PWV = range(8)
PE_DEPTH, PE_VELO, PE_T1, PE_L0 = 8, 9, 11, 15
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
    'pw':      it('PULSE W', T_PW, [WG_PW]),
    'pwv':     it('PW VELO', T_SGN, [WG_PWV], aux=7),
    'tune':    it('TUNE', T_SGN, [WG_COARSE], aux=36),   # v0.6: 36 = C4 = normal pitch (Munt coarseToPitch)
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
    # v0.6 JUNO page: fixed roles P1 SAW, P2 PULSE, P3 SUB, P4 DETUNE (offs = [list id] or [255] = a number)
    'jmake':   it('MAKE JUNO', T_JUNO, [LIST_IDS['go']], 0, 0),
    'jsaw':    it('SAW', T_JUNO, [255], 100, 1),
    'jpulse':  it('PULSE', T_JUNO, [255], 100, 2),
    'jpw':     it('PULSE W', T_JUNO, [LIST_IDS['pwmode']], len(PWTAB) - 1, 4),
    'jsub':    it('SUB OSC', T_JUNO, [255], 100, 3),
    'jdet':    it('DETUNE', T_JUNO, [255], 50, 5),
    'jpwm':    it('PWM', T_JUNO, [255], 10, 7),          # v0.11: fake PWM = 2nd pulse 3 cents off, depth 0-10
    'jrange':  it('RANGE', T_JUNO, [LIST_IDS['range']], 3, 6),
    'pedepth': it('DEPTH', T_NUM, [PE_DEPTH]),
    'peamt':   it('AMOUNT', T_SGN, [PE_L0], aux=50),
    'petime':  it('TIME', T_NUM, [PE_T1]),
    'pevelo':  it('VELOCITY', T_NUM, [PE_VELO]),
    # v0.7 ROSETTA FX (IC13 modes; aux = mode, offs = [field, list id or 255])
    'rvt':     it('TIME', T_FX, [F_T, 255], 7, 1),          # v0.8: IC13 mode 1 = Roland's HALL
    'rvl':     it('LEVEL', T_FX, [F_L, 255], 7, 1),
    'chr':     it('RATE', T_FX, [F_T, LIST_IDS['rate']], 7, 6),   # v0.8: chorus B = IC13 mode 6 (IC28 v6, no redirect)
    'chd':     it('DEPTH', T_FX, [F_L, 255], 7, 6),
    'dlt':     it('TIME', T_FX, [F_K, LIST_IDS['dms']], 15, 2),
    'dlf':     it('FEEDBACK', T_FX, [F_S, LIST_IDS['fb']], 3, 2),
    'fxc':     it('FX CUTOFF', T_FX, [F_K, LIST_IDS['cut']], 15, 0),     # v0.9: IC13 mode 0 = RESONANT FILTER
    'fxq':     it('FX RESO', T_FX, [F_S, LIST_IDS['fres']], 3, 0),
    'bend':    it('BENDER', T_BEND, [LIST_IDS['bendm']], 2, 0),
    'lfc':     it('AMOUNT', T_FX, [F_K, LIST_IDS['crush']], 15, 3),
    'lft':     it('TONE', T_FX, [F_S, LIST_IDS['tone']], 3, 3),
    'flr':     it('RATE', T_FX, [F_T, LIST_IDS['rate']], 7, 4),
    'fld':     it('DEPTH', T_FX, [F_L, 255], 7, 4),
    'drg':     it('RATE', T_FX, [F_T, LIST_IDS['rate']], 7, 5),   # v0.8: IC13 mode 5 = JUNO + REVERB (keys kept)
    'drt':     it('DEPTH', T_FX, [F_L, 255], 7, 5),
    'wet':     it('PART FX', T_WET, [LIST_IDS['wet']], 3, 0),
    'weta':    it('ALL PARTS', T_WET, [LIST_IDS['wet']], 3, 1),
    # v0.14 ARPEGGIATOR (RAM settings ARPM + aux: 0 mode, 1 rate, 2 range, 3 latch)
    'arpm':    it('MODE', T_ARP, [LIST_IDS['arpm']], 4, 0),
    'arpr':    it('RATE', T_ARP, [LIST_IDS['arpr']], 5, 1),
    'arpo':    it('RANGE', T_ARP, [LIST_IDS['arpo']], 2, 2),
    'arpl':    it('LATCH', T_ARP, [LIST_IDS['offon']], 1, 3),
}
PG_ROWS = 10                         # page record = title 11 + live + count + 10 item indices + pad = 24 bytes
PAGES = [  # (title, live, items): order = scroll order; BANK 1-8 jump to the first eight
    ('JUNO', 0, ['jmake', 'jsaw', 'jpulse', 'jpw', 'jpwm', 'jsub', 'jdet', 'jrange']),   # v0.6: Juno order, DCO first
    ('FILTER', 0, ['cutoff', 'reso', 'envamt', 'fkeyf', 'fvelo']),
    ('ENVELOPE', 0, ['attack', 'decay', 'sustain', 'release']),
    ('PITCH ENV', 0, ['peamt', 'petime', 'pedepth', 'pevelo']),
    ('LFO', 0, ['lrate', 'ldepth', 'lmod']),
    ('VOICE', 0, ['st12', 'st34', 'ring12', 'ring34', 'lvl1', 'lvl2', 'lvl3', 'lvl4']),
    ('PCM WAVE', 0, ['pcm']),
    ('LIVE FILTER', 1, ['cutoff', 'reso', 'fxc', 'fxq', 'bend']),   # stays on NUMBER 8; v0.9: + the DSP filter (PCM tones too)
    ('SYNTH OSC', 0, ['osc', 'pw', 'pwv']),
    ('PITCH', 0, ['tune', 'fine', 'wkeyf', 'bend']),
    ('AMP', 0, ['level', 'avelo']),
    ('PART', 0, ['part']),
    ('HALL', 0, ['rvt', 'rvl']),                     # v0.7 ROSETTA FX: one page per IC13 effect (v0.8: SUPER FX)
    ('JUNO CHORUS', 0, ['chr', 'chd']),
    ('DELAY', 0, ['dlt', 'dlf']),
    ('LOFI+DRIVE', 0, ['lfc', 'lft']),
    ('FLANGER', 0, ['flr', 'fld']),
    ('JUNO+REV', 0, ['drg', 'drt']),
    ('FX ROUTING', 0, ['wet', 'weta']),
    ('ARPEGGIO', 0, ['arpm', 'arpr', 'arpo', 'arpl']),   # v0.14: last page = dial all the way right
]
# FX defaults per mode (time, level): filter 1.3 kHz BP RES, hall, 150 ms 38 %, 11 bits soft, flanger, Juno+rev full, Chorus I, -
FXDEF = [(7, 4), (4, 5), (5, 2), (1, 2), (1, 6), (2, 7), (2, 4), (3, 4)]
# the PRO-E's own 8 reverb types (IC7 bank 0: names $6361, 11 bytes each; mode<<4|time $53C6, level $53CE)
REV_TYPES = [('Filter ', 0, 7, 4), ('Hall   ', 1, 5, 5), ('Juno   ', 6, 2, 4), ('Drive  ', 3, 1, 6),   # v0.8 SUPER FX
             ('Delay  ', 2, 1, 2), ('Lo-Fi  ', 3, 1, 2), ('Flanger', 4, 1, 7), ('JunoRev', 5, 2, 7)]
ITEM_KEYS = list(ITEMS)
assert len(PAGES) <= 29                             # v0.14: the "nn/NN" page counter handles 2-digit page numbers


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
    out.append('dutytab: db ' + ','.join(str(round(d)) for d in DUTY))
    out.append('fxdef: db ' + ','.join(str(t) for t, l in FXDEF) + ',' + ','.join(str(l) for t, l in FXDEF))
    out.append('DEFTONE: db ' + ','.join(map(str, dtone)))
    return '\n'.join(out) + '\n'


def lists_asm():
    """v0.9: the list strings live in the FX segment (same bank 5 window as the menu code): CODE is full"""
    out = []
    for k, names in LISTS.items():
        out.append('list_%s:' % k)
        assert all(len(n) <= 6 for n in names), (k, names)
        out += ['        ' + 'db "%s"' % n.rjust(6) for n in names]
    return '\n'.join(out) + '\n'


def patch(img, base, addr, old, new, what):
    o = addr - base
    if bytes(img[o:o + len(old)]) != old:
        sys.exit(f'{what}: stock bytes at ${addr:04X} are {bytes(img[o:o + len(old)]).hex()}, expected {old.hex()}')
    img[o:o + len(new)] = new
    print(f'  patched ${addr:04X} {what}: {old.hex()} -> {new.hex()}')


OS_VERSION = 'v0.14'


def build(ic7_base=None, ic4_base=None, banner=None, version=None):
    """banner / version: 32-byte boot banner (IC7) and version screen (IC4); None = the Rosetta OS defaults."""
    lower = bytearray(open(ic7_base or os.path.join(BUILD, 'IC7_v0.3b_W27C040.bin'), 'rb').read()[:0x40000])
    ic4 = bytearray(open(ic4_base or os.path.join(BUILD, 'IC4_v0.3b_W27C512.bin'), 'rb').read()[:0x4000])
    b5 = BANK * 0x8000
    assert all(x == 0xFF for x in lower[b5 + CODE - 0x4000:b5 + CODE_END - 0x4000]), 'IC7 base: bank 5 $A000-$B668 is not free ($FF). Use a ROM Studio build, not the stock dump'

    syms = dict(RAM, **HW)
    ram_segs, ram_syms = A.assemble(open(os.path.join(HERE, 'synth_v07_ram.asm')).read(), dict(syms))
    tramp = bytes(ram_segs[RAM['RAMBASE']])
    hooks = bytes(ram_segs[RAM['HOOKBASE']])
    assert ram_syms['HOOK_END'] <= RAM['FXT'], 'hooks run into the FX variables at $%04X' % ram_syms['HOOK_END']
    assert ram_syms['TRAMP_END'] <= RAM['ARPN'], 'trampoline runs into the variables'
    syms.update({k: ram_syms[k] for k in ('RAMKEY', 'RAMTICK', 'BOOTRET', 'HB1', 'HB2', 'HB3', 'HB4', 'HB5', 'HMS', 'HMD', 'HBD',
                                         'HST', 'HRC', 'HTK', 'HAR', 'ATK')})
    syms.update(HOOK_LEN=len(hooks), TRAMP_LEN=len(tramp), CODE=CODE, NPAGES=len(PAGES), PGSIZE=24)
    src = (open(os.path.join(HERE, 'synth_v07.asm')).read() + tables_asm(ic28_partial_max(), deftone(lower))
           + 'TRAMP_IMG: db ' + ','.join(map(str, tramp)) + '\n' + 'HOOK_IMG: db ' + ','.join(map(str, hooks)) + '\n')
    src += '        org %d\n' % FXSEG + open(os.path.join(HERE, 'synth_v07_fx.asm')).read() + lists_asm()
    segs, csyms = A.assemble(src, syms)
    code = bytes(segs[CODE])
    fxcode = bytes(segs[FXSEG])
    assert FXSEG + len(fxcode) <= FXSEG_END, 'FX segment too long'
    assert all(x == 0xFF for x in lower[BANK * 0x8000 + FXSEG - 0x4000:BANK * 0x8000 + FXSEG - 0x4000 + len(fxcode)]), 'FX segment not free'
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
    hm, hd = syms['HMS'], syms['HMD']
    patch(lower, 0x4000, 0x9703, bytes.fromhex('f6268a'), bytes([0xBD, hm >> 8, hm & 0xFF]), 'MIDI IN status -> HMS')
    patch(lower, 0x4000, 0x9745, bytes.fromhex('145b40'), bytes([0xBD, hd >> 8, hd & 0xFF]), 'MIDI IN data -> HMD')
    hb = syms['HBD']                                     # v0.10: bender A/D (B = raw) -> HBD, can skip the pitch bend
    patch(lower, 0x4000, 0x551D, bytes.fromhex('f7266c'), bytes([0xBD, hb >> 8, hb & 0xFF]), 'bender -> HBD')
    # v0.13: USER PROGRAM tones (store / recall in IC4, link-idle send in IC7 bank 0)
    hs, hr, ht = syms['HST'], syms['HRC'], syms['HTK']
    patch(ic4, 0xC000, 0xF4DD, bytes.fromhex('7e9419'), bytes([0x7E, hs >> 8, hs & 0xFF]), 'WRITE + USER store end -> HST')
    patch(ic4, 0xC000, 0xF57E, bytes.fromhex('7efc67'), bytes([0x7E, hr >> 8, hr & 0xFF]), 'USER recall end -> HRC')
    patch(lower, 0x4000, 0x51C4, bytes.fromhex('b62673'), bytes([0xBD, ht >> 8, ht & 0xFF]), 'link scheduler idle -> HTK')
    # v0.14 ARPEGGIATOR: the SOLO note send and the 24 PPQN arranger tick go through the SYNTH code
    har, atk = syms['HAR'], syms['ATK']
    patch(lower, 0x4000, 0x42CB, bytes.fromhex('bdebf1'), bytes([0xBD, har >> 8, har & 0xFF]), 'SOLO note -> HAR')
    patch(lower, 0x4000, 0xA118, bytes.fromhex('13104048'), bytes([0xBD, atk >> 8, atk & 0xFF, 0x01]), 'tick -> ATK')
    # v0.13: composer gone (user 2026-11-08: never used), so nothing stock writes the tone pages 2-3
    # (map: fw_map agent report 2026-11-08). Demo songs keep working (they never touch pages 1-3).
    patch(lower, 0x4000, 0x9057, bytes.fromhex('1210402d'), bytes.fromhex('135d802c'), 'PLAY outside demo -> rts')
    patch(ic4, 0xC000, 0xF7A8, bytes.fromhex('7efc90'), bytes.fromhex('7efc88'), 'REC / PUNCH key -> rts')
    patch(ic4, 0xC000, 0xF908, bytes.fromhex('7ee522'), bytes.fromhex('7ef8d4'), 'footswitch PUNCH -> rts')
    patch(lower, 0x4000, 0x92CF, bytes.fromhex('1f0b08ad'), bytes.fromhex('20af0101'), 'TRACK ERASE mode off')
    patch(ic4, 0xC000, 0xD8D0, bytes.fromhex('13104075'), bytes.fromhex('135d8075'), 'song tick: demo only')
    patch(ic4, 0xC000, 0xD7F5, bytes.fromhex('130e8034'), bytes.fromhex('20360101'), 'no song recording (1)')
    patch(ic4, 0xC000, 0xD832, bytes.fromhex('130e80f7'), bytes.fromhex('20f90101'), 'no song recording (2)')
    patch(ic4, 0xC000, 0xE544, bytes.fromhex('18'), bytes.fromhex('39'), 'no punch')
    patch(ic4, 0xC000, 0xDA34, bytes.fromhex('c6'), bytes.fromhex('39'), 'factory reset keeps the tone pages')
    for a in (0x9398, 0x93CE):
        patch(lower, 0x4000, a, bytes.fromhex('bdd3c8'), bytes.fromhex('010101'), 'card song load off')
    patch(lower, 0x4000, 0x93C9, bytes.fromhex('bdd30f'), bytes.fromhex('010101'), 'card single-song load off')
    patch(lower, 0x4000 - 0x8000, 0xB62C, bytes.fromhex('c603'), bytes.fromhex('c600'), 'test-mode RAM test: page 0 only')
    o = 0x6361 - 0x4000
    assert lower[o:o + 11] == b'1 = Room 1 ', lower[o:o + 11]
    for n, (name, m, t, l) in enumerate(REV_TYPES):
        assert len(name) == 7
        lower[o + 11 * n:o + 11 * n + 11] = ('%d = %s' % (n + 1, name)).ljust(11).encode()
        lower[0x53C6 - 0x4000 + n] = m << 4 | t
        lower[0x53CE - 0x4000 + n] = l
    assert ic4[0x2D48] == 0x00
    banner = banner or b' ROSETTA  PRO-E ' + b' OS v0.14  ARP  '
    version = version or b'ROSETTA OS PRO-E' + b'VER 00.51 110326'
    assert len(banner) == 32 and len(version) == 32, 'banner / version must be 2 x 16 characters'
    lower[0x19E1:0x19E1 + 32] = banner
    ic4[0x2DA8:0x2DA8 + 32] = version
    rs.bank_fix(lower)

    up = bytearray(lower)
    up[b5 + CODE - 0x4000:b5 + CODE - 0x4000 + len(code)] = code
    up[b5 + FXSEG - 0x4000:b5 + FXSEG - 0x4000 + len(fxcode)] = fxcode
    rs.bank_fix(up)
    img7 = bytes(lower) + bytes(up)
    return img7, bytes(ic4) * 4, dict(csyms, **syms), code + b'', tramp, bootcopy


if __name__ == '__main__':
    img7, img4, syms, code, tramp, bootcopy = build(*sys.argv[1:3])
    print('SYNTH code + tables: %d bytes at $%04X-$%04X (bank %d, upper half), trampoline %d bytes, BOOTCOPY %d bytes'
          % (len(code), CODE, CODE + len(code) - 1, BANK, len(tramp), len(bootcopy)))
    for name, data in (('IC7_v0.7_W27C040.bin', img7), ('IC4_v0.7_W27C512.bin', img4)):
        p = os.path.join(BUILD, name)
        open(p + '.tmp', 'wb').write(data)
        os.replace(p + '.tmp', p)
        print(f'{name}  md5 {hashlib.md5(data).hexdigest()}')
    lst = '\n'.join(f'{a:04X} {raw.hex():10s} {mn:6s} {ops}' for a, mn, ops, raw in A.disasm(code[:syms['rq1'] - CODE], CODE))
    open(os.path.join(BUILD, 'v0.7_synth.lst'), 'w').write(lst)
