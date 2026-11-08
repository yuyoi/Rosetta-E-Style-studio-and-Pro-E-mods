"""Rosetta ROM Studio v0.3 - swap waves in a Roland D-110 (IC8 drums, IC7 instruments, IC12 names + pitch/loop table).
Pick a wave, drop in a WAV, set its root note / loop, rename, BUILD -> three patched ROM images (IC8, IC7, IC12). Hardware-untested.
File menu: import ROM dumps, import a folder of WAVs (named 003_..., or by wave name), export all originals,
save/open project, build. Look and feel follows U110 RomHex Studio."""
import os, sys, glob, wave, io, json, re, zipfile, tempfile, collections, hashlib, datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from rosetta_d110 import rom_to_log, log_to_rom, log_to_lin, lin_to_log, read_wav
try:
    import windnd
except ImportError:
    windnd = None
try:
    import winsound
except ImportError:
    winsound = None

HERE = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)); os.chdir(HERE)
APP = 'Rosetta ROM Studio'; EXT = '.rosetta'; CARD = '.rcard'; RPATCH = '.rpatch'; CFG = os.path.join(HERE, 'rosetta_config.json')
APP_VERSION = '0.4'
FULL = 2.0 ** (32766 / 2048); RATE = 32000; NW = 128
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def note_name(m):
    return '%s%d' % (NOTES[m % 12], m // 12 - 1)          # middle C = C4 = 60


def parse_note(t):
    t = t.strip().upper().replace('♯', '#')
    m = re.fullmatch(r'([A-G]#?)(-?\d)', t)
    if m:
        return (int(m.group(2)) + 1) * 12 + NOTES.index(m.group(1))
    return int(t) if t.isdigit() else None


def root_to_pitch(root):
    """IC12 PCM-table pitch field: u16, 4096 per octave, 0x5000 = stored 32 kHz plays 1:1 on key 60 (coarse 36).
    A WAV that sounds at note `root` is played 1:1 when that key is pressed."""
    return int(round(0x5000 - (root - 60) * 4096 / 12))


def pitch_to_root(p):
    return 60 - (p - 0x5000) * 12 / 4096
PANEL, PANEL_HI, RECESS, EDGE = '#1d2228', '#2a3038', '#12161a', '#0a0c0e'
TEXT, DIM, SILK = '#eef1f3', '#8a96a0', '#ffffff'
RED, AMBER, BLUE = '#c8322a', '#6ec8e8', '#6ec8e8'
LCD_A, LCD_B, LCD_CELL, LCD_INK = '#94ec44', '#5cc41c', '#80da32', '#10280a'
WAVE_BG, WAVE_FG, GRID, NEW_COL = '#0c0f0d', '#8fe05a', '#161d17', '#f0b12a'


def apply_theme(root):
    st = ttk.Style(root); st.theme_use('clam'); root.configure(bg=PANEL)
    st.configure('.', background=PANEL, foreground=TEXT, fieldbackground=RECESS, bordercolor=EDGE, lightcolor=PANEL_HI,
                 darkcolor=EDGE, troughcolor=RECESS, focuscolor=AMBER, selectbackground=AMBER, selectforeground='#111',
                 insertcolor=TEXT, arrowcolor=TEXT, font=('Segoe UI', 9))
    st.configure('TLabelframe', background=PANEL, bordercolor='#46494e')
    st.configure('TLabelframe.Label', background=PANEL, foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('TButton', background='#3a3f46', foreground=TEXT, bordercolor=EDGE, lightcolor='#50565e', darkcolor='#1a1d21',
                 padding=(9, 3), font=('Arial', 9, 'bold'))
    st.map('TButton', background=[('pressed', '#23272c'), ('active', '#474d55')])
    st.configure('Build.TButton', background='#3a4048', foreground=BLUE, font=('Bahnschrift', 13, 'bold'), padding=(20, 10),
                 lightcolor='#4d545d', darkcolor='#16191d', bordercolor=BLUE)
    st.map('Build.TButton', background=[('pressed', '#23272c'), ('active', '#454c55')])
    st.configure('Treeview', background=RECESS, fieldbackground=RECESS, foreground=TEXT, rowheight=21, bordercolor=EDGE)
    st.map('Treeview', background=[('selected', '#2f6f8a')], foreground=[('selected', '#ffffff')])
    st.configure('Treeview.Heading', background=PANEL_HI, foreground=SILK, font=('Segoe UI', 8, 'bold'), relief='flat')
    st.map('Treeview.Heading', background=[('active', '#44474c')])
    for w in ('TEntry', 'TCombobox'):
        st.configure(w, fieldbackground=RECESS, foreground=TEXT, background='#4a4d53', arrowcolor=TEXT)
    st.map('TCombobox', fieldbackground=[('readonly', RECESS)], foreground=[('readonly', TEXT)],
           selectbackground=[('readonly', RECESS)], selectforeground=[('readonly', TEXT)])
    st.configure('TCheckbutton', background=PANEL, foreground=TEXT, indicatorbackground=RECESS, indicatorforeground=AMBER)
    st.map('TCheckbutton', background=[('active', PANEL)])
    st.configure('TScrollbar', background='#4a4d53', troughcolor=RECESS, arrowcolor=TEXT)
    st.configure('Dim.TLabel', foreground=DIM); st.configure('Silk.TLabel', foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('Title.TLabel', foreground=BLUE, font=('Bahnschrift SemiLight SemiConde', 30))
    st.configure('Sub.TLabel', foreground=BLUE, font=('Bahnschrift', 10))
    st.configure('Status.TFrame', background=RECESS); st.configure('Status.TLabel', background=RECESS, foreground=DIM)


def dark_titlebar(win):
    try:
        import ctypes
        win.update_idletasks(); hwnd = ctypes.windll.user32.GetParent(win.winfo_id()); v = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0:
                break
    except Exception:
        pass


class LCD(tk.Canvas):
    CW, CH = 11, 20

    def __init__(self, master, cols=40):
        self.cols = cols
        super().__init__(master, width=cols * self.CW + 26, height=2 * self.CH + 22, bg=PANEL, highlightthickness=0)
        self.lines = ['', '']; self.text_ids = []; W, H = int(self['width']), int(self['height'])
        self.create_rectangle(0, 0, W, H, fill=EDGE, outline='#0b0b0c'); x0, y0, x1, y1 = 6, 6, W - 6, H - 6; n = y1 - y0
        a = [int(LCD_A[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(LCD_B[i:i + 2], 16) for i in (1, 3, 5)]
        for i in range(n):
            t = abs(i / n - 0.35) * 1.3
            self.create_line(x0, y0 + i, x1, y0 + i, fill='#%02x%02x%02x' % tuple(int(a[k] * (1 - t) + b[k] * t) for k in range(3)))
        for r in range(2):
            for c in range(cols):
                cx, cy = 13 + c * self.CW, 11 + r * self.CH
                self.create_rectangle(cx, cy, cx + self.CW - 2, cy + self.CH - 3, fill=LCD_CELL, outline='')

    def set(self, l1, l2):
        lines = [l1[:self.cols].ljust(self.cols), l2[:self.cols].ljust(self.cols)]
        if lines == self.lines:
            return
        self.lines = lines
        for i in self.text_ids:
            self.delete(i)
        self.text_ids = []
        for r, s in enumerate(lines):
            for c, ch in enumerate(s):
                if ch != ' ':
                    self.text_ids.append(self.create_text(13 + c * self.CW + (self.CW - 2) / 2, 11 + r * self.CH + (self.CH - 3) / 2,
                                                          text=ch, fill=LCD_INK, font=('Consolas', 12, 'bold')))


class LEDMeter(tk.Canvas):
    def __init__(self, master, segs=26):
        self.segs = segs
        super().__init__(master, width=segs * 8 + 4, height=18, bg=PANEL, highlightthickness=0); self.set(0)

    def set(self, frac, over=False):
        self.delete('all'); lit = int(round(frac * self.segs))
        for i in range(self.segs):
            p = i / self.segs; on = over or i < lit
            col = ('#ff3b30' if over or p >= 0.9 else '#f0b12a' if p >= 0.7 else '#6fd13a') if on else \
                  ('#3a1e1c' if p >= 0.9 else '#3a3218' if p >= 0.7 else '#1f3319')
            self.create_rectangle(2 + i * 8, 2, 2 + i * 8 + 6, 16, fill=col, outline='')


def load_cfg():
    try:
        return json.load(open(CFG))
    except Exception:
        return {}


class Rom:
    """wave space = IC8 (first 256K samples) then IC7; names + table come from IC12"""

    none = False

    def __init__(s, ic8=None, ic7=None, ic12=None):
        c = load_cfg()
        ic8 = ic8 or c.get('ic8') or 'dumps/r15179880.ic8.bin'
        ic7 = ic7 or c.get('ic7') or 'dumps/r15179878.ic7.bin'
        ic12 = ic12 or c.get('ic12') or (glob.glob('ctrl/**/r15179873*.bin', recursive=True) or ['ctrl/r15179873.ic12.bin'])[0]
        s.paths = {'ic8': ic8, 'ic7': ic7, 'ic12': ic12}
        s.real = {}      # optional sound_times.json next to IC12: real sound length (samples) of waves stored time-compressed (see gen_way_different 'longer')
        try:
            sc = os.path.join(os.path.dirname(os.path.abspath(ic12)), 'sound_times.json')
            if os.path.exists(sc):
                s.real = {int(k): int(v) for k, v in json.load(open(sc)).items()}
        except Exception:
            pass
        s.ic8 = np.fromfile(ic8, np.uint8); s.ic7 = np.fromfile(ic7, np.uint8); s.ctrl = np.fromfile(ic12, np.uint8)
        if len(s.ic8) != 524288 or len(s.ic7) != 524288 or len(s.ctrl) != 131072:
            raise ValueError('Expected IC8 and IC7 = 512 KB each, IC12 = 128 KB (got %d / %d / %d bytes)' % (len(s.ic8), len(s.ic7), len(s.ctrl)))
        s.wave = np.concatenate([log_to_lin(rom_to_log(s.ic8)), log_to_lin(rom_to_log(s.ic7))])
        s.names = [bytes(s.ctrl[0x100 + 8 * i:0x108 + 8 * i]).decode('latin1') for i in range(NW)]
        s.ent = [(int(s.ctrl[0x900 + 4 * i]) * 0x800, 0x800 << ((int(s.ctrl[0x901 + 4 * i]) >> 4) & 7),
                  bool(s.ctrl[0x901 + 4 * i] & 0x80)) for i in range(NW)]

        s.pos = [int(s.ctrl[0x900 + 4 * i]) for i in range(256)]
        s.lenb = [int(s.ctrl[0x901 + 4 * i]) for i in range(256)]
        s.pitch = [int(s.ctrl[0x902 + 4 * i]) | int(s.ctrl[0x903 + 4 * i]) << 8 for i in range(256)]

        # slots that sit inside another slot (e.g. 'Shot 1-9' = tail halves of drum samples) share its data
        s.parent = {}
        for i in range(NW):
            a, n, _ = s.ent[i]
            for j in range(NW):
                ja, jn, _ = s.ent[j]
                if j != i and ja <= a and a + n <= ja + jn and (jn > n or (jn == n and j < i)) and (a >= 0x40000) == (ja >= 0x40000):
                    s.parent[i] = j; break

    def orig(s, i):
        a, n, _ = s.ent[i]; return s.wave[a:a + n]

    def linked(s, i):
        """table entries (incl. the bank-2 drum aliases 128+) that point at the same wave data: pitch/loop edits apply to all of them"""
        return [j for j in range(256) if s.pos[j] == s.pos[i] and (s.lenb[j] >> 4) & 7 == (s.lenb[i] >> 4) & 7]

    def chip(s, i):
        return 'IC8' if s.ent[i][0] < 0x40000 else 'IC7'


class NoRom:
    """stand-in when no dumps are loaded, so the Studio still opens: empty wave list, BUILD off until File > Import ROM dumps"""

    none = True

    def __init__(s):
        s.paths = {}; s.real = {}
        s.ent = [(0, 0, False)] * NW; s.names = [''] * NW
        s.pos = [0] * 256; s.lenb = [0] * 256; s.pitch = [0] * 256; s.parent = {}

    def orig(s, i): return np.zeros(0)
    def linked(s, i): return []
    def chip(s, i): return 'IC8'


def fit(x, n, norm=True):
    x = np.asarray(x, float)[:n]; x = np.concatenate([x, np.zeros(n - len(x))])
    return x / (np.abs(x).max() + 1e-9) * 0.98 if norm else np.clip(x, -1, 1)


def write_wav(fn, x):
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    w = wave.open(fn, 'wb') if isinstance(fn, str) else wave.open(fn, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes((x * 32767).astype(np.int16).tobytes()); w.close()


def pcm16(x):
    b = io.BytesIO(); w = wave.open(b, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
    w.writeframes(np.clip(np.round(np.asarray(x) * 32768), -32768, 32767).astype(np.int16).tobytes()); w.close(); return b.getvalue()


def wav_bytes(x):
    b = io.BytesIO(); write_wav(b, x); return b.getvalue()


def slot_exp(n):
    """smallest length code e (slot = 0x800 << e samples, e = 0..7) holding n samples"""
    e = 0
    while (0x800 << e) < n and e < 7:
        e += 1
    return e


def plan_layout(rom, swaps, discard=(), sizes=None):
    """A WAV longer than its slot moves to a new, bigger slot (the table is just data in IC12).
    Rules seen on all 256 stock entries: start = pos * 0x800 samples, and every slot is aligned to its own length.
    Table entries that point at the same data (same pos + length code) move together; entries that only share part of the old
    data (sub-slots) keep it. `discard` = waves whose space may be reused: their table entries are parked on one silent unit.
    Returns (moves {wave: (pos, exp)}, errors, free-aligned-block text, park (unit, entries) or None)."""
    discard = set(discard) - set(swaps)
    sizes = sizes or {}
    need = {}
    for i in set(swaps) | set(sizes):          # a wave moves when its WAV or the SLOT you picked is bigger than the stock slot
        e = max(slot_exp(len(swaps[i])) if i in swaps else 0, sizes.get(i, 0))
        if (0x800 << e) > rom.ent[i][1]:
            need[i] = e
    moving = set(); free_up = set()
    for i in need:
        moving.update(rom.linked(i))
    for i in discard:
        free_up.update(rom.linked(i))
    used = bytearray(256)                      # 256 units of 0x800 samples = the whole 1 MB wave space
    span = lambda j: (rom.pos[j], rom.pos[j] + (1 << ((rom.lenb[j] >> 4) & 7)))
    freedu = bytearray(256)
    for j in (free_up | moving):
        for u in range(*span(j)):
            freedu[u] = 1
    for j in range(256):
        if j in moving or j in free_up:
            continue
        if j >= 128 and all(freedu[u] for u in range(*span(j))):
            continue                           # a sub-slice (loop slice / drum alias) lying wholly in space you freed goes with it
        p, e = rom.pos[j], (rom.lenb[j] >> 4) & 7
        for u in range(p, min(256, p + (1 << e))):
            used[u] = 1
    moves, errs = {}, []
    for i, e in sorted(need.items(), key=lambda kv: (-kv[1], kv[0])):
        size = 1 << e; got = None
        for st in range(0, 256, size):         # natural alignment, lowest address first
            if not any(used[st:st + size]):
                got = st; break
        if got is None:
            errs.append('#%d %s needs a free %.2f s block (aligned) and there is none' % (i, rom.names[i].strip(), (0x800 << e) / RATE))
        else:
            moves[i] = (got, e)
            for u in range(got, got + size):
                used[u] = 1
    park = {}
    parked = sorted((free_up - moving) | {j for j in range(128, 256) if j not in moving and j not in free_up and all(freedu[u] for u in range(*span(j)))})
    if parked:
        # Freed waves must still point somewhere legal, but they must NOT all end up on one unit. That is what
        # broke a real D-110: stock has 128 distinct (pos, exp) slots and the old single-park build had 6,
        # with 242 of the 256 entries sharing a single 0.06 s slot of silence. The machine still booted and
        # drew its screen, but the Edit button did nothing, because the Edit screen walks this table.
        #
        # Most freed waves do not need parking at all. Their old slot is theirs, nothing staying uses it,
        # and render() wipes the audio that was there - so leave the table entry exactly where it is and it
        # becomes a silent wave at its own original position. Only waves whose old slot is genuinely needed
        # by something else have to move, and they are rare. The wave space is genuinely full: after a
        # large relocation only ~4 units are free, so a fresh unit per freed wave is not an option.
        # One cap for everybody: stock shares a single slot between at most 5 of the 256 entries (measured
        # across the whole table), so 5 is as dense as factory ever gets. The old build put 242 waves on one
        # slot and that is what killed the Edit screen. A freed wave prefers its own old slot, because that
        # keeps its position in the table and keeps the table's spread; only if that space is genuinely
        # wanted by something else does it move to a shared one.
        load = {}
        for j in parked:
            e = (rom.lenb[j] >> 4) & 7; want = 1 << e; p = rom.pos[j]
            opts = ([p] if p % want == 0 and p + want <= 256
                    and not any(used[u] for u in range(p, p + want)) else [])
            opts += [u for u in range(256)
                     if u % want == 0 and u + want <= 256
                     and not any(used[u] for u in range(u, u + want))]
            pick = next((o for o in opts if all(load.get(u, 0) < 5 for u in range(o, o + want))), None)
            if pick is None:
                errs.append('wave #%d %s has nowhere to go: no free 0.06 s unit with room left for it '
                            '(%d units are free and no slot may hold more than 5 waves, like factory)'
                            % (j, rom.names[j].strip() if j < len(rom.names) else 'wave %d' % j,
                               sum(1 for u in range(256) if not used[u])))
                break
            park[j] = pick
            for u in range(pick, pick + want):
                load[u] = load.get(u, 0) + 1
    blocks = []
    for e in (7, 6, 5, 4):
        size = 1 << e; k = sum(1 for st in range(0, 256, size) if not any(used[st:st + size]))
        blocks.append('%d x %.2f s' % (k, (0x800 << e) / RATE))
    return moves, errs, 'free aligned blocks after this plan: ' + ', '.join(blocks), park


Render = collections.namedtuple('Render', 'ic8 ic7 ctrl moves park where fitted gone free_text')


ENFORCE_TABLE_SPREAD = True     # refuse a layout that collapses the PCM table and kills the Edit screen


def rs_total_samples():
    """total wave space in samples: 256 units of 0x800"""
    return UNIT_SAMPLES * UNITS


def check_table_spread(rom, ctrl):
    """see below. ENFORCE_TABLE_SPREAD = False turns it into a warning, for the tests that need the old
    behaviour on purpose."""
    """Refuse a layout that collapses the PCM table onto far fewer slots than the stock ROM has.

    This exists because it actually happened. A bank with one 8.19 s wave has to displace half the wave
    space, and plan_layout parks every freed wave in the same place: stock has 128 distinct (pos, exp)
    slots, that build had 6, with 242 of the 256 entries sharing one 0.064 s slot of silence. The D-110
    still booted and drew its screen, but the Edit button did nothing - the Edit screen walks the table
    and does not survive that. The old test suite was happy because every entry was individually legal.

    So: distinct slots may not drop below half of stock. A normal swap or a ~100-wave recorded bank keeps
    every slot distinct and sails through. Only the builds that park hundreds of waves get stopped, and
    those are exactly the ones that bricked the Edit screen.
    """
    d_stk = len(set((int(rom.ctrl[TABLE_AT + 4 * i]), (int(rom.ctrl[TABLE_AT + 4 * i + 1]) >> 4) & 7)
                    for i in range(256)))
    d_new = len(set((int(ctrl[TABLE_AT + 4 * i]), (int(ctrl[TABLE_AT + 4 * i + 1]) >> 4) & 7)
                    for i in range(256)))
    if d_new * 2 >= d_stk:
        return
    if not ENFORCE_TABLE_SPREAD:
        print('WARNING: table spread %d/%d distinct slots - this boots but kills the Edit screen'
              % (d_new, d_stk))
        return
    if True:
        biggest = 0x800 << max((int(ctrl[TABLE_AT + 4 * i + 1]) >> 4) & 7 for i in range(256))
        raise ValueError(
            'this layout would collapse the PCM table to %d distinct slots, down from %d in stock. '
            'The D-110 boots but its Edit screen stops working, because 200+ waves would share one '
            '0.06 s slot of silence. Its biggest slot is %d samples, which is %d%% of the whole wave '
            'space, so it cannot share a ROM with a full bank. Free fewer waves, or use a shorter '
            'length code (4 = 1.02 s, 5 = 2.05 s need far less room).'
            % (d_new, d_stk, biggest, 100 * biggest // (rs_total_samples() // 2)))


def render(rom, swaps, renames, norm=True, roots=None, loops=None, discard=(), pitches=None, sizes=None):
    """pure: returns the final IC8/IC7/IC12 images plus the frozen layout decision, writing nothing to disk"""
    roots, loops = roots or {}, loops or {}
    moves, errs, free_text, park = plan_layout(rom, swaps, discard, sizes)

    def audio(i):                              # the WAV, or (slot made bigger without a WAV) the wave's own audio: looped waves tile, hits pad with silence
        if i in swaps:
            return swaps[i]
        o = rom.orig(i)
        return np.tile(o, (0x800 << moves[i][1]) // len(o) + 1) if loops.get(i, rom.ent[i][2]) else o
    if errs:
        raise ValueError('; '.join(errs) + '. Mark waves you do not need as "free space" so a block opens up.')
    ic8, ic7, c = rom.ic8.copy(), rom.ic7.copy(), rom.ctrl.copy(); fitted = {}; where = {}
    gone = set(park) if park else set()                        # wipe the old audio of freed / moved waves (units no staying entry still uses)
    for i in moves:
        gone.update(rom.linked(i))
    if gone:
        sp_ = lambda j: range(rom.pos[j], rom.pos[j] + (1 << ((rom.lenb[j] >> 4) & 7)))
        keep = {u for j in range(256) if j not in gone for u in sp_(j)}
        for u in {u for j in gone for u in sp_(j)} - keep:
            r, base = (ic8, 0) if u * 0x800 < 0x40000 else (ic7, 0x40000)
            r[(u * 0x800 - base) * 2:(u * 0x800 - base + 0x800) * 2] = log_to_rom(np.zeros(0x800, np.uint32))
    for i in moves:                            # sub-slices that still point into the old slot (loop slices) play the head of the new audio, like an in-place swap
        a, n, _ = rom.ent[i]; r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
        r[(a - base) * 2:(a - base + n) * 2] = log_to_rom(lin_to_log(fit(audio(i), n, norm) * FULL))
    for i, x in sorted(swaps.items(), key=lambda kv: -rom.ent[kv[0]][1]):   # big slots first so a sub-slot you changed wins over its parent
        if i in moves:
            continue
        a, n, _ = rom.ent[i]; r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
        fitted[i] = fit(x, n, norm)
        r[(a - base) * 2:(a - base + n) * 2] = log_to_rom(lin_to_log(fitted[i] * FULL))
    for i, (pos, e) in moves.items():          # relocated waves: new slot, then every table entry that shared the old one follows
        a, n = pos * 0x800, 0x800 << e; r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
        fitted[i] = fit(audio(i), n, norm)
        r[(a - base) * 2:(a - base + n) * 2] = log_to_rom(lin_to_log(fitted[i] * FULL))
        for j in rom.linked(i):
            c[0x900 + 4 * j] = pos; c[0x901 + 4 * j] = (int(c[0x901 + 4 * j]) & 0x8F) | (e << 4)
        where[i] = (a, n)
    if park:                                   # freed waves -> their own silent unit each, so nothing plays
        for j, u in sorted(park.items()):  # leftovers of whatever now lives there, and the table keeps spread
            a = u * 0x800; r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
            r[(a - base) * 2:(a - base + 0x800) * 2] = log_to_rom(np.zeros(0x800, np.uint32))
            c[0x900 + 4 * j] = u; c[0x901 + 4 * j] = int(c[0x901 + 4 * j]) & 0x0F
    for i, nm in renames.items():
        c[0x100 + 8 * i:0x108 + 8 * i] = list(nm.encode('ascii', 'replace')[:8].ljust(8))
    for i, root in roots.items():
        p = max(0, min(0xFFFF, root_to_pitch(root)))
        for j in rom.linked(i):
            c[0x902 + 4 * j], c[0x903 + 4 * j] = p & 255, p >> 8
    for i, p in (pitches or {}).items():
        p = max(0, min(0xFFFF, int(p)))
        for j in rom.linked(i):
            c[0x902 + 4 * j], c[0x903 + 4 * j] = p & 255, p >> 8
    for i, lp in loops.items():
        for j in rom.linked(i):
            c[0x901 + 4 * j] = (int(c[0x901 + 4 * j]) & 0x7F) | (0x80 if lp else 0)
    check_table_spread(rom, c)
    return Render(ic8, ic7, c, moves, park, where, fitted, gone, free_text)


def report_lines(rd, rom, swaps, renames, roots=None, pitches=None, loops=None):
    """one line per touched wave, describing what the build did"""
    ic8, ic7, moves, park, where, fitted = rd.ic8, rd.ic7, rd.moves, rd.park, rd.where, rd.fitted
    lines = []
    for i in sorted(set(swaps) | set(moves) | set(renames) | set(roots or {}) | set(loops or {}) | set(pitches or {}) | (set(j for j in park if j < 128) if park else set())):
        bits = []
        if i in swaps or i in moves:
            a, n = where.get(i) or rom.ent[i][:2]; r = ic8 if a < 0x40000 else ic7; base = 0 if a < 0x40000 else 0x40000
            d = log_to_lin(rom_to_log(r[(a - base) * 2:(a - base + n) * 2]))
            cc = np.corrcoef(d, fitted[i] * FULL)[0, 1] if np.std(d) > 0 and np.std(fitted[i]) > 0 else 0.0
            # Pearson is blind to a constant offset and the codec has no exact zero (log_to_lin(0) == 1.0),
            # so silence/wipes/parking sit at +1.0 and still correlate perfectly. Print the bias too,
            # otherwise "decode check 1.0000" reads stronger than it is.
            bias = float(np.mean(d) - np.mean(fitted[i] * FULL))
            bits.append(('wave replaced (%s, decode check %.4f, bias %+.4f)' if i in swaps
                         else 'slot enlarged, own audio kept (%s, decode check %.4f, bias %+.4f)') % ('IC8' if a < 0x40000 else 'IC7', cc, bias))
            if i in moves:
                bits.append('MOVED to wave pos 0x%05X, slot %.2f s (was 0x%05X, %.2f s); table entries %s' % (a, n / RATE, rom.ent[i][0], rom.ent[i][1] / RATE, rom.linked(i)))
        if i in (roots or {}):
            p = max(0, min(0xFFFF, root_to_pitch(roots[i])))
            bits.append('root %s -> pitch 0x%04X (was 0x%04X) on table entries %s' % (note_name(int(round(roots[i]))), p, rom.pitch[i], rom.linked(i)))
        if i in (pitches or {}):
            bits.append('pitch field 0x%04X (was 0x%04X)' % (pitches[i], rom.pitch[i]))
        if i in (loops or {}):
            bits.append('loop ' + ('ON' if loops[i] else 'OFF'))
        if park and i in park:
            bits.append('FREED: now points at its own silent unit 0x%05X' % (park[i] * 0x800))
        lines.append('%3d %s -> %s  %s' % (i, rom.names[i], renames.get(i, rom.names[i]).ljust(8), '; '.join(bits)))
    return lines


def build(rom, swaps, renames, out='patched', norm=True, roots=None, loops=None, discard=(), pitches=None, sizes=None):
    """writes all three images: IC8 (drums), IC7 (instruments), IC12 (names + pitch/loop table). Returns (files, report lines)"""
    rd = render(rom, swaps, renames, norm, roots, loops, discard, pitches, sizes)
    os.makedirs(out, exist_ok=True)
    files = ['r15179880.ic8_patched.bin', 'r15179878.ic7_patched.bin', 'r15179873.ic12_patched.bin']
    for fn, arr in zip(files, (rd.ic8, rd.ic7, rd.ctrl)):
        arr.tofile(f'{out}/{fn}')
    lines = report_lines(rd, rom, swaps, renames, roots, pitches, loops)
    with open(f'{out}/report.txt', 'w') as f:
        f.write(chr(10).join(lines) + chr(10))
    return files, lines


# ---- .rpatch packs: only your own audio + table deltas, no Roland data, so a bank can be shared ----

UNIT_SAMPLES = 0x800            # one allocatable unit of wave space = 4096 bytes = 2048 samples
UNITS = 256                     # the whole 1 MB wave space: 256 units, unit < 128 in IC8, 128+ in IC7
NAMES_AT, NAMES_LEN = 0x100, 0x800      # 256 x 8 ASCII
TABLE_AT, TABLE_LEN = 0x900, 0x400      # 256 x 4 bytes {pos, len, pitch}
RPATCH_REGIONS = (('names', NAMES_AT, NAMES_LEN), ('table', TABLE_AT, TABLE_LEN))


def _md5(b):
    return hashlib.md5(bytes(b)).hexdigest()


SILENT_UNIT = bytes(log_to_rom(np.zeros(UNIT_SAMPLES, np.uint32)))    # what a wipe / park writes: one 4 KB block


def _runs(offs, maxlen=64):
    """[0,1,2,5,6] -> [(0,3),(5,2)] (offset, length), split so no run is longer than maxlen"""
    out = []
    for o in offs:
        if out and o == out[-1][0] + out[-1][1] and out[-1][1] < maxlen:
            out[-1][1] += 1
        else:
            out.append([int(o), 1])
    return [tuple(r) for r in out]


def build_patch(rom, swaps, renames, fn, norm=True, roots=None, loops=None, discard=(), pitches=None, sizes=None,
                name='patch', description='', allow_stock_audio=False, created=None, writes=None):
    """Writes a .rpatch pack (ZIP) holding ONLY user-authored content: the replacement audio as 4 KB blocks in
    final ROM byte order, the IC12 byte edits, and a manifest that pins the layout and the dump revision.
    No full chip image is written, so no factory audio rides along. Returns the manifest dict."""
    rd = render(rom, swaps, renames, norm, roots, loops, discard, pitches, sizes)
    swaps, roots, loops, pitches, sizes = swaps or {}, roots or {}, loops or {}, pitches or {}, sizes or {}

    # a wave made bigger without a WAV keeps its own (factory) audio - that must never end up in a shareable pack
    stock = [i for i in rd.moves if i not in swaps]
    if stock and not allow_stock_audio:
        raise ValueError('Wave%s %s would keep the factory audio in a bigger slot, which a shareable pack may not contain. '
                         'Load a WAV for %s, or pass allow_stock_audio=True.'
                         % ('s' if len(stock) > 1 else '', ', '.join('#%d %s' % (i, rom.names[i].strip()) for i in stock),
                            'it' if len(stock) == 1 else 'them'))

    # --- wave space: every 4 KB block that changed, shipped whole. Shipping whole blocks means a partial
    #     block write would still come out byte-exact, so no diff-boundary bug can corrupt a neighbour.
    stock_all = np.concatenate([rom.ic8, rom.ic7]); new_all = np.concatenate([rd.ic8, rd.ic7])
    ub = UNIT_SAMPLES * 2
    by_unit = {}                                                 # unit -> waves whose audio now sits there
    for i, (a, n) in rd.where.items():
        by_unit.setdefault(a // UNIT_SAMPLES, []).append(i)
    for i, (a, n, lp) in enumerate(rom.ent):
        if i in swaps and i not in by_unit.get(a // UNIT_SAMPLES, []):
            by_unit.setdefault(a // UNIT_SAMPLES, []).append(i)
    blobs, entries, by_md5 = {}, [], {}
    for u in range(UNITS):                      # every block that differs, not just the ones a wave can be named for:
        lo, hi = u * ub, (u + 1) * ub            # freed / moved / parked waves wipe whole blocks too
        if np.array_equal(stock_all[lo:hi], new_all[lo:hi]):
            continue
        raw = bytes(new_all[lo:hi]); h = _md5(raw)
        if h not in by_md5:
            nm = 'audio/a%04d.bin' % len(by_md5); blobs[nm] = raw; by_md5[h] = nm
        entries.append({'unit': u, 'blob': by_md5[h], 'chip': 'ic8' if u < 128 else 'ic7',
                        'why': ('waves ' + ' '.join('#%d' % i for i in sorted(by_unit[u]))) if u in by_unit
                               else ('silence (freed or parked)' if h == _md5(SILENT_UNIT) else 'cleared')})

    # --- control ROM: byte edits only, and only inside the regions a pack is allowed to touch
    d = np.nonzero(rd.ctrl != rom.ctrl)[0]
    outside = [int(o) for o in d if not any(at <= o < at + ln for _, at, ln in RPATCH_REGIONS)]
    if outside:
        raise ValueError('IC12 edit at 0x%X is outside the packed regions (names 0x%03X-0x%03X, table 0x%03X-0x%03X). '
                         'Add a region to RPATCH_REGIONS before patching there.' % (outside[0], NAMES_AT, NAMES_AT + NAMES_LEN, TABLE_AT, TABLE_AT + TABLE_LEN))
    edits = [{'off': o, 'len': n, 'hex': bytes(rd.ctrl[o:o + n]).hex()} for o, n in _runs(d)]

    # --- what a human wants to read, all derived from the frozen render
    touched = sorted({j for i in set(swaps) | set(rd.moves) | set(renames) for j in rom.linked(i)})
    # slot_exp() saturates at e=7 (8.19 s) and fit() truncates quietly, so a wave that did not fit says so here
    cut = [{'wave': i, 'src_samples': len(swaps[i]),
            'slot_samples': (rd.where.get(i) or rom.ent[i][:2])[1],
            'exp': (int(rd.ctrl[TABLE_AT + 4 * i + 1]) >> 4) & 7}
           for i in sorted(swaps) if len(swaps[i]) > (rd.where.get(i) or rom.ent[i][:2])[1]]
    man = {
        'format': 'rosetta-rpatch', 'version': 1,
        'name': name, 'description': description,
        'created': created or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'generator': {'tool': 'rosetta_studio.pyw', 'app_version': APP_VERSION},
        'basis': {'family': 'd110-lh5310', 'chips': {
            'ic8': {'size': 524288, 'md5': _md5(rom.ic8), 'label': 'IC8 drums, HN62304B'},
            'ic7': {'size': 524288, 'md5': _md5(rom.ic7), 'label': 'IC7 instruments, HN62304B'},
            'ic12': {'size': 131072, 'md5': _md5(rom.ctrl), 'label': 'IC15 control, LH5310 (called "ic12" in dump sets)',
                     'regions': [{'name': nm, 'off': at, 'len': ln, 'md5': _md5(rom.ctrl[at:at + ln])} for nm, at, ln in RPATCH_REGIONS]}}},
        'geometry': {'unit_samples': UNIT_SAMPLES, 'units': UNITS, 'rate': RATE, 'chip_switch_unit': 128, 'max_exp': 7},
        'layout': {'moves': {str(i): {'unit': p, 'exp': e} for i, (p, e) in rd.moves.items()},
                   'park': None if not rd.park else {'per_wave': {str(i): rd.park[i] for i in sorted(rd.park)}},
                   'free_text': rd.free_text},
        'units': entries,
        'ctrl_edits': edits,
        'ctrl': {'names': {str(i): n for i, n in renames.items()},
                 'roots': {str(i): int(r) for i, r in roots.items()},
                 'pitches': {str(i): int(p) for i, p in pitches.items()},
                 'loops': {str(i): bool(l) for i, l in loops.items()},
                 'table': {str(j): {'pos': int(rd.ctrl[TABLE_AT + 4 * j]), 'len_b': int(rd.ctrl[TABLE_AT + 4 * j + 1]),
                                    'exp': (int(rd.ctrl[TABLE_AT + 4 * j + 1]) >> 4) & 7,
                                    'pitch': int(rd.ctrl[TABLE_AT + 4 * j + 2]) | int(rd.ctrl[TABLE_AT + 4 * j + 3]) << 8,
                                    'loop': bool(int(rd.ctrl[TABLE_AT + 4 * j + 1]) & 0x80)} for j in touched}},
        'waves': {str(i): {'samples_in': len(swaps[i]), 'slot_samples': (rd.where.get(i) or rom.ent[i][:2])[1],
                           'truncated': len(swaps[i]) > (rd.where.get(i) or rom.ent[i][:2])[1],
                           'loop': bool(loops.get(i, rom.ent[i][2]))} for i in sorted(swaps)},
        # slot_exp() saturates at e=7 (8.19 s) and fit() pads/truncates silently, so say it out loud:
        # a wave longer than its slot loses its tail, and the LA32 has never been asked to play e=5..7.
        'truncation': cut,
        'expected': {'ic8': _md5(rd.ic8), 'ic7': _md5(rd.ic7), 'ic12': _md5(rd.ctrl),
                     'ic12_x4': _md5(np.tile(rd.ctrl, 4))},
        'report': report_lines(rd, rom, swaps, renames, roots, pitches, loops),
    }
    if writes:
        man['dumps'] = writes

    os.makedirs(os.path.dirname(os.path.abspath(fn)), exist_ok=True)
    with zipfile.ZipFile(fn, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for nm in sorted(blobs):                                    # fixed mtime + sorted members -> byte-reproducible pack
            zi = zipfile.ZipInfo(nm, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, blobs[nm])
        zi = zipfile.ZipInfo('manifest.json', date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(zi, json.dumps(man, indent=1, sort_keys=True))
    try:                                                          # sidecar: where this pack was built from (absolute paths, never shared)
        json.dump(rom.paths, open(os.path.splitext(fn)[0] + '.dumps.json', 'w'), indent=1)
    except Exception:
        pass
    return man


class WaveView(tk.Canvas):
    """original (green) with the replacement overlaid (amber); wheel = zoom, shift+wheel = pan, right-click = fit"""

    def __init__(s, master):
        super().__init__(master, bg=WAVE_BG, highlightthickness=1, highlightbackground=EDGE, height=200)
        s.o = s.n = None; s.z, s.p = 1.0, 0.0; s.loop = False
        s.bind('<Configure>', lambda e: s.draw()); s.bind('<MouseWheel>', s.wheel); s.bind('<Button-3>', s.fit_view)

    def fit_view(s, e=None):
        s.z, s.p = 1.0, 0.0; s.draw()

    def show(s, o, n, loop):
        s.o, s.n, s.loop = o, n, loop; s.fit_view()

    def wheel(s, e):
        if e.state & 1:
            s.p = min(max(s.p - np.sign(e.delta) * 0.1 / s.z, 0), 1 - 1 / s.z)
        else:
            s.z = min(max(s.z * (1.25 if e.delta > 0 else 0.8), 1.0), 64.0); s.p = min(s.p, 1 - 1 / s.z)
        s.draw()

    def trace(s, x, W, mid, amp, col, pk):
        n = len(x); seg = x[int(s.p * n):int((s.p + 1 / s.z) * n)]
        if len(seg) < 2:
            return
        for px in range(W):
            a = int(px * len(seg) / W); b = max(int((px + 1) * len(seg) / W), a + 1); c = seg[a:b]
            s.create_line(px, mid - c.max() / pk * amp, px, mid - c.min() / pk * amp + 1, fill=col)

    def draw(s):
        s.delete('all'); W, H = s.winfo_width(), s.winfo_height()
        if W < 10:
            return
        mid, amp = H / 2, H / 2 - 14
        for k in range(1, 8):
            s.create_line(k * W / 8, 0, k * W / 8, H, fill=GRID)
        s.create_line(0, mid, W, mid, fill='#24302a')
        if s.o is None:
            s.create_text(W / 2, H / 2, text='SELECT A WAVE', fill='#4d6b45', font=('Consolas', 12, 'bold')); return
        pk = np.abs(s.o).max() + 1e-9
        s.trace(s.o, W, mid, amp, WAVE_FG, pk)
        if s.n is not None:
            s.trace(s.n, W, mid, amp, NEW_COL, np.abs(s.n).max() + 1e-9)
        s.create_text(4, H - 4, anchor='sw', text='%.3fs' % (s.p * len(s.o) / RATE), fill='#5f7a58', font=('Consolas', 9))
        s.create_text(W - 4, H - 4, anchor='se', text='%.3fs' % ((s.p + 1 / s.z) * len(s.o) / RATE), fill='#5f7a58', font=('Consolas', 9))
        s.create_text(W - 6, 6, anchor='ne', text='ORIGINAL' + ('  (loops)' if s.loop else ''), fill=WAVE_FG, font=('Consolas', 9, 'bold'))
        if s.n is not None:
            s.create_text(W - 6, 20, anchor='ne', text='REPLACEMENT', fill=NEW_COL, font=('Consolas', 9, 'bold'))


class Studio(tk.Tk):
    def __init__(s):
        super().__init__(); s.geometry('1180x%d' % min(720, s.winfo_screenheight() - 140)); s.minsize(980, 560); s.title(APP)
        for base in (getattr(sys, '_MEIPASS', HERE), HERE):               # logo as the window icon; default= makes the pop-up windows use it too
            ico = next((p for p in (os.path.join(base, 'assets', n) for n in ('rosetta_dark15.ico', 'rosetta.ico')) if os.path.isfile(p)), '')
            if os.path.isfile(ico):
                try: s.iconbitmap(default=ico)
                except tk.TclError: pass
                s.exact_icons(ico)
                break
        apply_theme(s); dark_titlebar(s)
        s.rom = s.first_rom(); s.swaps = {}; s.src = {}; s.renames = {}; s.roots = {}; s.loops = {}; s.discard = set(); s.sizes = {}; s.path = None; s.dirty = False; s.pv = 0
        s.norm = tk.BooleanVar(value=True); s.filt = tk.StringVar(value='All')
        s.menu(); s.ui(); s.fill(); s.sel_first(); s.retitle()
        s.protocol('WM_DELETE_WINDOW', s.quit_app)
        if windnd:
            windnd.hook_dropfiles(s, func=lambda files: s.after(30, lambda: s.on_drop(files)))

    def first_rom(s):
        try:
            if '--roms' in sys.argv:        # --roms IC8 IC7 IC12 : open these images (e.g. a built set) without changing the remembered dumps
                a = [os.path.abspath(x) for x in sys.argv[sys.argv.index('--roms') + 1:sys.argv.index('--roms') + 4]]
                if len(a) == 3:
                    return Rom(*a)
            return Rom()
        except Exception:
            d = {}
            for key, title in (('ic8', 'IC8 drum ROM (512 KB, r15179880)'), ('ic7', 'IC7 instrument ROM (512 KB, r15179878)'), ('ic12', 'IC12 control ROM (128 KB, r15179873)')):
                fn = filedialog.askopenfilename(title='Select ' + title, filetypes=[('ROM dump', '*.bin;*.rom'), ('All', '*.*')])
                if not fn:
                    return NoRom()       # the program stays open on an empty wave list; File > Import ROM dumps loads a set later
                d[key] = fn
            try:
                r = Rom(**d)
            except Exception as e:
                messagebox.showerror(APP, str(e)); return NoRom()
            json.dump(d, open(CFG, 'w'), indent=1); return r

    def menu(s):
        mb = tk.Menu(s); f = tk.Menu(mb, tearoff=0)
        for l, c, a in (('New', s.new, 'Ctrl+N'), ('Open card / project...', s.open, 'Ctrl+O'), ('Save', s.save, 'Ctrl+S'), ('Save as...', lambda: s.save(True), 'Ctrl+Shift+S'), (None,) * 3,
                        ('Import WAV(s) into selected wave...', s.import_wavs, 'Ctrl+I'), ('Import WAV folder...', s.import_folder, ''),
                        ('Export all original waves to folder...', s.export_all, ''), ('Import ROM dumps (IC8, IC7, IC12)...', s.import_roms, ''), (None,) * 3,
                        ('Build ROM images...', s.build, 'Ctrl+B'),
                        ('Export .rpatch pack...', s.export_patch, 'Ctrl+P'), ('Apply .rpatch pack to my dumps...', s.apply_pack, 'Ctrl+Shift+P'),
                        ('Patch OS (no waves)...', s.patch_os, ''), (None,) * 3, ('Exit', s.quit_app, '')):
            f.add_separator() if l is None else f.add_command(label=l, command=c, accelerator=a)
        mb.add_cascade(label='File', menu=f)
        h = tk.Menu(mb, tearoff=0); h.add_command(label='How it works', command=s.help); mb.add_cascade(label='Help', menu=h); s.config(menu=mb)
        for k, fn in (('<Control-n>', s.new), ('<Control-o>', s.open), ('<Control-s>', s.save), ('<Control-S>', lambda: s.save(True)), ('<Control-b>', s.build),
                      ('<Control-i>', s.import_wavs), ('<Control-p>', s.export_patch), ('<Control-P>', s.apply_pack), ('<Delete>', s.undo)):
            s.bind(k, lambda e, fn=fn: fn())

    def ui(s):
        head = ttk.Frame(s, padding=(12, 10, 12, 4)); head.pack(fill='x'); plate = ttk.Frame(head); plate.pack(side='left', padx=(0, 16))
        ttk.Label(plate, text='D-110', style='Title.TLabel').pack(anchor='w'); ttk.Label(plate, text='ROSETTA ROM STUDIO', style='Sub.TLabel').pack(anchor='w')
        s.lcd = LCD(head, 40); s.lcd.pack(side='left'); mf = ttk.Frame(head); mf.pack(side='left', padx=16)
        ttk.Label(mf, text='WAVES CHANGED', style='Silk.TLabel').pack(anchor='w'); s.meter = LEDMeter(mf); s.meter.pack(anchor='w', pady=(2, 2))
        s.v_cnt = tk.StringVar(); ttk.Label(mf, textvariable=s.v_cnt, style='Dim.TLabel').pack(anchor='w')
        bf = ttk.Frame(head); bf.pack(side='right'); ttk.Label(bf, text='WRITE ROMS', style='Silk.TLabel').pack()
        ttk.Button(bf, text='BUILD', style='Build.TButton', command=s.build).pack(pady=(2, 0))
        stf = ttk.Frame(s, style='Status.TFrame'); stf.pack(fill='x', side='bottom')
        s.v_st = tk.StringVar(value='Hardware-untested. Each wave keeps its slot position and length. Root note and loop flag go into IC12. 32 kHz mono.')
        ttk.Label(stf, textvariable=s.v_st, style='Status.TLabel', padding=(8, 3)).pack(side='left')
        main = ttk.PanedWindow(s, orient='horizontal'); main.pack(fill='both', expand=True, padx=8, pady=(4, 4))
        lf = ttk.Labelframe(main, text=' WAVES ', padding=6); main.add(lf, weight=1)
        fb = ttk.Frame(lf); fb.pack(fill='x', pady=(0, 4)); ttk.Label(fb, text='SHOW', style='Silk.TLabel').pack(side='left')
        cb = ttk.Combobox(fb, textvariable=s.filt, values=['All', 'IC8 drums', 'IC7 instruments', 'Changed'], width=16, state='readonly')
        cb.pack(side='left', padx=6); cb.bind('<<ComboboxSelected>>', lambda e: s.fill())
        cols = (('n', '#', 36), ('name', 'Name', 90), ('chip', 'Chip', 44), ('sec', 'Time', 84), ('st', 'Edits', 110))
        s.tv = ttk.Treeview(lf, columns=[c[0] for c in cols], show='headings', selectmode='browse')
        s.cols = {c: t for c, t, w in cols}; s.sort = ('n', False)
        for c, t, w in cols:
            s.tv.heading(c, text=t, command=lambda c=c: s.sort_by(c)); s.tv.column(c, width=w, anchor='w' if c in ('name', 'st') else 'center')
        sb = ttk.Scrollbar(lf, command=s.tv.yview); s.tv.configure(yscrollcommand=sb.set); sb.pack(side='right', fill='y'); s.tv.pack(fill='both', expand=True)
        s.tv.bind('<<TreeviewSelect>>', lambda e: s.on_sel()); s.tv.bind('<Double-1>', lambda e: s.play_orig())
        rf = ttk.Labelframe(main, text=' WAVEFORM ', padding=6); main.add(rf, weight=3); s.wv = WaveView(rf); s.wv.pack(fill='both', expand=True)
        info = ttk.Frame(rf); info.pack(fill='x', pady=(6, 0)); s.v_info = tk.StringVar(); ttk.Label(info, textvariable=s.v_info, style='Dim.TLabel').pack(side='left')
        s.v_pitch = tk.StringVar(); ttk.Label(rf, textvariable=s.v_pitch, style='Dim.TLabel').pack(fill='x')
        row = ttk.Frame(rf); row.pack(fill='x', pady=(8, 0))
        for t, c in (('Play original', s.play_orig), ('Play replacement', s.play_new), ('Load WAV...', s.load), ('Undo', s.undo), ('Save original WAV...', s.save_orig)):
            ttk.Button(row, text=t, command=c).pack(side='left', padx=(0, 6))
        ttk.Checkbutton(row, text='Normalize', variable=s.norm, command=s.on_sel).pack(side='left', padx=8)
        nr = ttk.Frame(rf); nr.pack(fill='x', pady=(8, 0)); ttk.Label(nr, text='NAME (8)', style='Silk.TLabel').pack(side='left'); s.v_name = tk.StringVar()
        e = ttk.Entry(nr, textvariable=s.v_name, width=12, validate='key', validatecommand=(s.register(lambda v: len(v) <= 8 and v.isascii()), '%P'))
        e.pack(side='left', padx=6); ttk.Button(nr, text='Set name', command=s.set_name).pack(side='left'); e.bind('<Return>', lambda ev: s.set_name())
        pr = ttk.Frame(rf); pr.pack(fill='x', pady=(8, 0)); ttk.Label(pr, text='ROOT NOTE', style='Silk.TLabel').pack(side='left')
        s.v_root = tk.StringVar(); er = ttk.Entry(pr, textvariable=s.v_root, width=6); er.pack(side='left', padx=6)
        er.bind('<Return>', lambda ev: s.set_root()); ttk.Button(pr, text='Set root', command=s.set_root).pack(side='left')
        ttk.Label(pr, text='LOOP', style='Silk.TLabel').pack(side='left', padx=(16, 0)); s.v_loop = tk.StringVar(value='Keep')
        cl = ttk.Combobox(pr, textvariable=s.v_loop, values=['Keep', 'Loop', 'One-shot'], width=9, state='readonly'); cl.pack(side='left', padx=6)
        cl.bind('<<ComboboxSelected>>', lambda ev: s.set_loop())
        ttk.Label(pr, text='SLOT', style='Silk.TLabel').pack(side='left', padx=(16, 0)); s.v_slot = tk.StringVar(value='Keep')
        cs = ttk.Combobox(pr, textvariable=s.v_slot, values=['Keep'] + ['%.2f s' % ((0x800 << e) / RATE) for e in range(7, -1, -1)], width=7, state='readonly')
        cs.pack(side='left', padx=6); cs.bind('<<ComboboxSelected>>', lambda ev: s.set_slot())
        s.v_disc = tk.BooleanVar(); ttk.Checkbutton(pr, text='Free this wave\'s space', variable=s.v_disc, command=s.set_disc).pack(side='left', padx=(16, 0))

    # ---- list
    def state(s, i):
        return ('WAV ' if i in s.swaps else '') + ('NAME ' if i in s.renames else '') + (('ROOT %s ' % note_name(s.roots[i])) if i in s.roots else '') \
            + (('LOOP ' if s.loops[i] else '1SHOT ') if i in s.loops else '') + ('FREE ' if i in s.discard else '') + (('SLOT %.2fs ' % ((0x800 << s.sizes[i]) / RATE)) if i in s.sizes else '') + ('in #%d' % s.rom.parent[i] if i in s.rom.parent else '')

    def vis(s, i):
        f = s.filt.get()
        return f == 'All' or (f == 'IC8 drums' and s.rom.chip(i) == 'IC8') or (f == 'IC7 instruments' and s.rom.chip(i) == 'IC7') \
            or (f == 'Changed' and s.touched(i))

    def eff_n(s, i):
        """slot length a replacement will occupy: the original slot, or the bigger slot it moves to"""
        n = s.rom.ent[i][1]
        e = max(slot_exp(len(s.swaps[i])) if i in s.swaps and len(s.swaps[i]) > n else 0, s.sizes.get(i, 0))
        return max(n, 0x800 << e) if e else n

    def real_n(s, i):
        """how long the wave SOUNDS (samples): the slot, or more when the bank stores it time-compressed (pitch field lowered to play it back at real speed)"""
        n = s.eff_n(i)
        return n if (i in s.swaps or i in s.sizes) else max(n, s.rom.real.get(i, n))

    def layout_msg(s):
        if not (any(len(x) > s.rom.ent[i][1] for i, x in s.swaps.items()) or any((0x800 << e) > s.rom.ent[i][1] for i, e in s.sizes.items())):
            return ''
        mv, er, fr, _ = plan_layout(s.rom, s.swaps, s.discard, s.sizes)
        return ('LAYOUT: %d wave(s) move to bigger slots. %s' % (len(mv), fr)) if not er else ('LAYOUT PROBLEM: ' + '; '.join(er) + '. Tick "Free this wave\'s space" on waves you do not need.')

    def touched(s, i):
        return i in s.swaps or i in s.renames or i in s.roots or i in s.loops or i in s.discard or i in s.sizes

    def row_vals(s, i):
        n = s.eff_n(i); rn = s.real_n(i)      # Time = how long it sounds; + = a loaded WAV / SLOT moves it to a bigger slot; xN = stored N times compressed in its slot
        return (i, s.renames.get(i, s.rom.names[i]), s.rom.chip(i), '%.2f' % (rn / RATE) + ('+' if n > s.rom.ent[i][1] else '') + (' x%d' % (rn // n) if rn > n else '')
                + ('*' if s.loops.get(i, s.rom.ent[i][2]) else ''), s.state(i))

    def sort_key(s, col):
        r = s.rom
        return {'n': lambda i: i,
                'name': lambda i: (s.renames.get(i, r.names[i]).strip().lower(), i),
                'chip': lambda i: (r.chip(i), i),
                'sec': lambda i: (s.real_n(i), i),
                'st': lambda i: (s.state(i) == '', s.state(i), i)}[col]

    def sort_by(s, col):
        s.sort = (col, not s.sort[1] if s.sort[0] == col else False)
        s.fill()

    def fill(s):
        cur = s.cur(); s.tv.delete(*s.tv.get_children())
        col, rev = s.sort
        for c, t in s.cols.items():
            s.tv.heading(c, text=t + (' ▼' if rev else ' ▲') if c == col else t)
        for i in sorted((i for i in range(NW) if not s.rom.none and s.vis(i)), key=s.sort_key(col), reverse=rev):
            s.tv.insert('', 'end', iid=str(i), values=s.row_vals(i))
        if cur is not None and s.tv.exists(str(cur)):
            s.tv.selection_set(str(cur))
        s.update_head()

    def cur(s):
        x = s.tv.selection(); return int(x[0]) if x else None

    def sel_first(s):
        k = s.tv.get_children()
        if k:
            s.tv.selection_set(k[0])

    def refresh_row(s, i):
        if s.tv.exists(str(i)):
            s.tv.item(str(i), values=s.row_vals(i))

    def update_head(s):
        n = len(set(s.swaps) | set(s.renames) | set(s.roots) | set(s.loops) | set(s.discard) | set(s.sizes)); s.meter.set(n / NW); s.v_cnt.set('%d of %d' % (n, NW)); s.on_sel()

    def on_sel(s):
        i = s.cur()
        if i is None:
            s.lcd.set('', ''); return
        a, n, l = s.rom.ent[i]; nm = s.renames.get(i, s.rom.names[i]); l = s.loops.get(i, l)
        s.lcd.set('%03d %-8s %s %.2fs%s' % (i, nm, s.rom.chip(i), s.real_n(i) / RATE, ' LOOP' if l else ''),
                  ('NEW: ' + os.path.basename(s.src[i])) if i in s.src else 'ORIGINAL')
        s.v_name.set(nm.strip())
        s.v_root.set(note_name(s.roots[i]) if i in s.roots else '')
        s.v_loop.set('Keep' if i not in s.loops else ('Loop' if s.loops[i] else 'One-shot'))
        p0 = s.rom.pitch[i]; lk = [j for j in s.rom.linked(i) if j != i]
        s.v_pitch.set('table pitch 0x%04X = %+.2f st vs a 32 kHz 1:1 wave (key 60)%s%s' % (
            p0, 12 * (p0 / 4096 - 5), ('   |   set root: new pitch 0x%04X' % max(0, min(0xFFFF, root_to_pitch(s.roots[i])))) if i in s.roots else '',
            ('   |   also applies to table entries %s' % lk) if lk else ''))
        s.wv.show(s.rom.orig(i), fit(s.swaps[i], s.eff_n(i), s.norm.get()) if i in s.swaps else None, l)
        s.v_disc.set(i in s.discard)
        s.v_slot.set('%.2f s' % ((0x800 << s.sizes[i]) / RATE) if i in s.sizes else 'Keep')
        if i in s.swaps:
            ln = len(s.swaps[i]); en = s.eff_n(i)
            s.v_info.set('slot %d samples (%.2fs) at wave pos 0x%05X  |  replacement %.2fs%s' %
                         (n, n / RATE, a, ln / RATE, ('  -> MOVES to a %.2fs slot%s' % (en / RATE, ' (TRUNCATED, 8.19s max)' if ln > en else '')) if en > n else '  (padded with silence)'))
        else:
            s.v_info.set('slot %d samples (%.2fs)%s at wave pos 0x%05X%s' % (n, n / RATE, (' holds %.2fs of sound, stored %dx time-compressed (table pitch lowered to play it at real speed)' % (s.real_n(i) / RATE, s.real_n(i) // n)) if s.real_n(i) > n else '', a, ('   |   shares data with #%d %s (changing either changes the other)' % (s.rom.parent[i], s.rom.names[s.rom.parent[i]].strip())) if i in s.rom.parent else ''))

    # ---- play / edit
    def play(s, x):
        if winsound:   # async playback needs a file (SND_MEMORY can't be async)
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
                fn = os.path.join(tempfile.gettempdir(), 'rosetta_preview_%d.wav' % (s.pv % 2)); s.pv += 1
                open(fn, 'wb').write(wav_bytes(x)); winsound.PlaySound(fn, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception as e:
                s.v_st.set('Playback failed: %s' % e)

    def play_orig(s):
        i = s.cur()
        if i is not None:
            o = s.rom.orig(i); s.play(np.tile(o, 3) if s.rom.ent[i][2] else o)

    def play_new(s):
        i = s.cur()
        if i is None:
            return
        if i not in s.swaps:
            s.v_st.set('No replacement loaded for this wave.'); return
        x = fit(s.swaps[i], s.eff_n(i), s.norm.get()); s.play(np.tile(x, 3) if s.rom.ent[i][2] else x)

    def load(s):
        i = s.cur()
        if i is None:
            return
        fn = filedialog.askopenfilename(filetypes=[('WAV files', '*.wav')])
        if fn and s.set_wav(i, fn):
            s.update_head(); s.play_new()

    def set_wav(s, i, fn, quiet=False):
        try:
            x = read_wav(fn)
        except Exception as e:
            if not quiet:
                messagebox.showerror('WAV', '%s: %s' % (os.path.basename(fn), e))
            return False
        s.swaps[i] = x; s.src[i] = fn; n = s.rom.ent[i][1]; s.refresh_row(i); s.mark()
        s.v_st.set(('Loaded %s (%.2fs). Slot holds %.2fs.' % (os.path.basename(fn), len(x) / RATE, n / RATE)) + ('  ' + s.layout_msg() if len(x) > n else ''))
        return True

    def set_name(s):
        i = s.cur()
        if i is None:
            return
        v = s.v_name.get()
        if v.strip() == s.rom.names[i].strip():
            s.renames.pop(i, None)
        else:
            s.renames[i] = v
        s.refresh_row(i); s.update_head(); s.mark()

    def set_root(s):
        i = s.cur()
        if i is None:
            return
        t = s.v_root.get().strip()
        if not t:
            s.roots.pop(i, None)
        else:
            m = parse_note(t)
            if m is None or not 0 <= m <= 120:
                messagebox.showerror(APP, 'Root note: a name like C4 or F#3 (middle C = C4 = 60), or a MIDI number 0-120.'); return
            s.roots[i] = m
        s.refresh_row(i); s.update_head(); s.mark()

    def set_slot(s):
        i = s.cur()
        if i is None:
            return
        v = s.v_slot.get()
        if v == 'Keep':
            s.sizes.pop(i, None)
        else:
            e = next((e for e in range(8) if '%.2f s' % ((0x800 << e) / RATE) == v), None)
            if e is None:              # combobox was left holding text that is not one of our slot sizes
                s.v_slot.set('Keep'); s.sizes.pop(i, None); e = None
            elif (0x800 << e) > s.rom.ent[i][1]:
                s.sizes[i] = e
            else:
                s.sizes.pop(i, None); s.v_slot.set('Keep')          # only bigger than the stock slot is a change; smaller needs no table edit
        s.refresh_row(i); s.update_head(); s.mark(); s.v_st.set(s.layout_msg() or 'Slot kept as it is.')

    def set_disc(s):
        i = s.cur()
        if i is None:
            return
        (s.discard.add if s.v_disc.get() else s.discard.discard)(i)
        s.refresh_row(i); s.update_head(); s.mark(); s.v_st.set(s.layout_msg() or 'Space of #%d %s %s.' % (i, s.rom.names[i].strip(), 'is freed: it will play silence in the built ROM' if i in s.discard else 'is kept'))

    def set_loop(s):
        i = s.cur()
        if i is None:
            return
        v = s.v_loop.get()
        if v == 'Keep':
            s.loops.pop(i, None)
        else:
            s.loops[i] = (v == 'Loop')
        s.refresh_row(i); s.update_head(); s.mark()

    def undo(s):
        i = s.cur()
        if i is None:
            return
        for d in (s.swaps, s.src, s.renames, s.roots, s.loops):
            d.pop(i, None)
        s.discard.discard(i); s.sizes.pop(i, None)
        s.mark()
        if s.filt.get() == 'Changed':
            s.fill()
        else:
            s.refresh_row(i); s.update_head()

    def save_orig(s):
        i = s.cur()
        if i is None:
            return
        fn = filedialog.asksaveasfilename(defaultextension='.wav', initialfile='%03d_%s.wav' % (i, s.rom.names[i].strip()))
        if fn:
            write_wav(fn, s.rom.orig(i))

    # ---- import / export
    def import_roms(s):
        d = {}
        for key, title in (('ic8', 'IC8 drum ROM (512 KB, r15179880)'), ('ic7', 'IC7 instrument ROM (512 KB, r15179878)'), ('ic12', 'IC12 control ROM (128 KB, r15179873)')):
            p = s.rom.paths.get(key)
            fn = filedialog.askopenfilename(title='Select ' + title, initialdir=os.path.dirname(p) if p else HERE, filetypes=[('ROM dump', '*.bin;*.rom'), ('All', '*.*')])
            if not fn:
                return
            d[key] = fn
        try:
            new = Rom(**d)
        except Exception as e:
            messagebox.showerror(APP, str(e)); return
        pending = s.swaps or s.renames or s.roots or s.loops or s.sizes or s.discard
        if pending and not messagebox.askyesno(APP, 'Loading new ROM dumps discards the %d pending edit(s).\n\n'
                                                   'Wave numbers and slot sizes refer to the current dumps, so they cannot be kept.\n\nContinue?' % sum(len(x) for x in (s.swaps, s.renames, s.roots, s.loops, s.sizes)) + len(s.discard)):
            return
        if pending:
            s.swaps.clear(); s.src.clear(); s.renames.clear(); s.roots.clear(); s.loops.clear(); s.discard.clear(); s.sizes.clear()
        s.rom = new; json.dump(d, open(CFG, 'w'), indent=1); s.fill(); s.sel_first(); s.mark(False)
        s.v_st.set('Loaded ROM dumps (remembered for next time).' + ('  Pending edits were discarded.' if pending else ''))

    def import_wavs(s):
        fns = filedialog.askopenfilenames(title='WAV file(s): one goes into the selected wave, several are matched by number/name', filetypes=[('WAV files', '*.wav')])
        if fns:
            s.import_files(list(fns))

    def import_folder(s):
        d = filedialog.askdirectory(title='Folder of WAVs (named 003_..., or by wave name)')
        if d:
            s.import_files(sorted(glob.glob(os.path.join(d, '*.wav'))))

    def import_files(s, fns, target=None):
        """one WAV -> target (or selected) wave; several -> matched by leading number (003_x.wav) or by wave name"""
        if len(fns) == 1 and (target is not None or s.cur() is not None):
            i = target
            if i is None:       # not dropped on a row: a numbered or named file (003_kick.wav) goes to its own wave, else the selected one
                base = os.path.splitext(os.path.basename(fns[0]))[0]; m = re.match(r'^(\d{1,3})(?:\D|$)', base)
                i = int(m.group(1)) if m and int(m.group(1)) < NW else None
                if i is None:
                    i = next((k for k in range(NW) if re.sub(r'\W', '', s.rom.names[k]).lower() == re.sub(r'\W', '', base).lower()), s.cur())
            if s.set_wav(i, fns[0]):
                if s.tv.exists(str(i)):
                    s.tv.selection_set(str(i))
                s.update_head(); s.play_new()
            return
        byname = {}
        for i in range(NW):
            byname.setdefault(re.sub(r'\W', '', s.rom.names[i]).lower(), i)
        ok = skip = 0
        for fn in fns:
            base = os.path.splitext(os.path.basename(fn))[0]; m = re.match(r'^(\d{1,3})(?:\D|$)', base)
            i = int(m.group(1)) if m and int(m.group(1)) < NW else byname.get(re.sub(r'\W', '', base).lower())
            if i is not None and s.set_wav(i, fn, quiet=True):
                ok += 1
            else:
                skip += 1
        s.fill(); s.v_st.set('Imported %d WAVs, skipped %d (name them 003_x.wav or use the wave name).' % (ok, skip))

    def on_drop(s, files):
        names = []
        for f in files:
            try:
                names.append(f.decode('utf-8'))
            except UnicodeDecodeError:
                names.append(f.decode('mbcs'))
        cards = [f for f in names if f.lower().endswith((CARD, EXT))]
        if cards:
            s.open(cards[0]); return
        wavs = []
        for f in names:
            wavs += sorted(glob.glob(os.path.join(f, '*.wav'))) if os.path.isdir(f) else ([f] if f.lower().endswith('.wav') else [])
        if not wavs:
            s.v_st.set('Drop WAV files, a folder of WAVs, or a card/project.'); return
        x, y = s.winfo_pointerxy(); w = s.winfo_containing(x, y); target = None
        if w is s.tv:
            r = s.tv.identify_row(y - s.tv.winfo_rooty())
            target = int(r) if r else None
        s.import_files(wavs, target)

    def export_all(s):
        if s.rom.none:
            messagebox.showinfo(APP, 'No ROM dumps loaded, so there are no original waves to export. Use File > Import ROM dumps first.'); return
        d = filedialog.askdirectory(title='Folder for the original waves')
        if not d:
            return
        for i in range(NW):
            o = s.rom.orig(i); write_wav(os.path.join(d, '%03d_%s.wav' % (i, re.sub(r'[^\w-]', '_', s.rom.names[i].strip()))), o)
        s.v_st.set('Exported %d original waves to %s (re-import them as-is after editing).' % (NW, d))

    def build(s):
        if s.rom.none:
            messagebox.showinfo(APP, 'No ROM dumps loaded, so there is nothing to build.\n\nUse File > Import ROM dumps and pick your own IC8 (drums), IC7 (instruments) and IC12 (control).'); return
        if not (s.swaps or s.renames or s.roots or s.loops or s.discard or s.sizes):
            messagebox.showinfo(APP, 'Nothing changed yet: load a WAV, set a root note / loop or rename a wave first.'); return
        d = filedialog.askdirectory(title='Folder for the patched ROM images', initialdir=HERE)
        if not d:
            return
        try:
            files, lines = build(s.rom, s.swaps, s.renames, d, s.norm.get(), s.roots, s.loops, s.discard, None, s.sizes)
        except ValueError as e:
            messagebox.showerror(APP, str(e)); return
        s.v_st.set('Built: ' + ', '.join(files))
        messagebox.showinfo(APP, 'Wrote 3 images + report.txt to %s\n\nIC8 (drums):  %s\nIC7 (instruments):  %s\nIC12 (control):  %s\n\nProgram each image to its own chip. Images are in chip byte order, as dumped.' % ((d,) + tuple(files)))

    def export_patch(s):
        """write a .rpatch pack: your samples and table edits only, no factory audio, so it can be shared"""
        if s.rom.none:
            messagebox.showinfo(APP, 'No ROM dumps loaded, so there is nothing to pack.\n\nUse File > Import ROM dumps and pick your own IC8 (drums), IC7 (instruments) and IC12 (control).'); return
        if not (s.swaps or s.renames or s.roots or s.loops or s.discard or s.sizes):
            messagebox.showinfo(APP, 'Nothing changed yet: load a WAV, set a root note / loop or rename a wave first.'); return
        fn = filedialog.asksaveasfilename(title='Save .rpatch pack (shareable: your samples only)', initialdir=HERE,
                                          initialfile='my_bank' + RPATCH, defaultextension=RPATCH, filetypes=[('Rosetta pack', '*' + RPATCH)])
        if not fn:
            return
        if not fn.lower().endswith(RPATCH):
            fn += RPATCH
        try:
            man = build_patch(s.rom, s.swaps, s.renames, fn, s.norm.get(), s.roots, s.loops, s.discard, None, s.sizes,
                              name=os.path.splitext(os.path.basename(fn))[0])
        except ValueError as e:
            messagebox.showerror(APP, str(e)); return
        nb = sum(len(b) for b in [open(fn, 'rb').read()])
        s.v_st.set('Wrote pack %s (%d unit(s), %d IC12 edit(s), %d KB).' % (os.path.basename(fn), len(man['units']), len(man['ctrl_edits']), nb // 1024))
        messagebox.showinfo(APP, 'Pack written:\n%s\n\n%d wave block(s), %d IC12 edit(s), %d KB total.\n\nIt holds only your own audio and table changes, so it carries no factory data and can be shared.\n\nThe person it is for runs:  py -3.10 rosetta_inject.py %s'
                             % (os.path.basename(fn), len(man['units']), len(man['ctrl_edits']), nb // 1024, os.path.basename(fn)))

    def apply_pack(s):
        """open the Apply Pack window: a .rpatch + your own dumps -> new burn files in a new folder (never overwrites)"""
        try:
            from rosetta_apply_window import ApplyPackWindow
        except ImportError as e:
            messagebox.showerror(APP, 'Apply Pack window is missing: %s' % e); return
        ApplyPackWindow(s)

    def patch_os(s):
        """open the Patch OS window: your v1.10 IC19 + a mode -> a new patched IC19 in a new folder (no waves)"""
        try:
            from rosetta_os_window import PatchOSWindow
        except ImportError as e:
            messagebox.showerror(APP, 'Patch OS window is missing: %s' % e); return
        PatchOSWindow(s)

    # ---- cards (.rcard: self-contained, samples only, no Roland data) and projects (.rosetta: paths to WAVs)
    def mark(s, d=True):
        s.dirty = d; s.retitle()

    def exact_icons(s, ico):
        """Tk hands Windows only a 32 px and a 16 px icon, which Windows then stretches (blur on 125-200% screens).
        Ask for the exact sizes the taskbar (24 px x scale) and title bar (16 px x scale) use and set them ourselves."""
        try:
            import ctypes
            u = ctypes.windll.user32; s.update_idletasks()
            try: sc = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100.0
            except Exception: sc = 1.0
            hwnd = u.GetParent(s.winfo_id()) or s.winfo_id()
            for kind, px in ((1, int(round(24 * sc))), (0, int(round(16 * sc)))):       # 1 = taskbar/big, 0 = title bar/small
                h = u.LoadImageW(None, ico, 1, px, px, 0x10)                               # IMAGE_ICON, LR_LOADFROMFILE: picks that exact size from the .ico
                if h: u.SendMessageW(hwnd, 0x80, kind, h)                                  # WM_SETICON
        except Exception:
            pass

    def retitle(s):
        s.title('%s - %s%s' % (APP, os.path.basename(s.path) if s.path else 'untitled', ' *' if s.dirty else ''))

    def check_save(s):
        if not s.dirty:
            return True
        a = messagebox.askyesnocancel(APP, 'Save changes to %s?' % (os.path.basename(s.path) if s.path else 'untitled'))
        if a is None:
            return False
        return s.save() if a else True

    def new(s):
        if not s.check_save():
            return
        s.swaps.clear(); s.src.clear(); s.renames.clear(); s.roots.clear(); s.loops.clear(); s.discard.clear(); s.sizes.clear(); s.path = None; s.mark(False); s.fill()

    def quit_app(s):
        if s.check_save():
            s.destroy()

    def save(s, as_new=False):
        fn = None if as_new else s.path
        if not fn:
            fn = filedialog.asksaveasfilename(defaultextension=CARD, initialfile=os.path.basename(s.path or 'my_card' + CARD),
                                              filetypes=[('Rosetta card (self-contained, shareable)', '*' + CARD), ('Rosetta project (links to WAV files)', '*' + EXT)])
        if not fn:
            return False
        if fn.lower().endswith(EXT):
            card = [i for i, p in s.src.items() if str(p).startswith('card:')]
            if card and not messagebox.askyesno(APP, 'A project file only links to WAV files on disk, so these %d wave(s) came from a card '
                                                    'and would be left out:\n%s\n\nSave as a .rcard card instead, or continue?' % (len(card), ', '.join('#%d' % i for i in sorted(card)))):
                return False
            json.dump({'wavs': {str(i): p for i, p in s.src.items() if not str(p).startswith('card:')},
                       'names': {str(i): n for i, n in s.renames.items()},
                       'roots': {str(i): r for i, r in s.roots.items()}, 'loops': {str(i): bool(l) for i, l in s.loops.items()}, 'free': sorted(s.discard), 'slots': {str(i): e for i, e in s.sizes.items()}}, open(fn, 'w'), indent=1)
        else:
            if not fn.lower().endswith(CARD):
                fn += CARD
            meta = {'format': 'rosetta-card', 'version': 1, 'machine': 'D-110', 'name': os.path.splitext(os.path.basename(fn))[0],
                    'waves': {str(i): {'file': 'w%03d.wav' % i, 'src': os.path.basename(str(s.src.get(i, '')))} for i in s.swaps},
                    'names': {str(i): n for i, n in s.renames.items()},
                    'roots': {str(i): r for i, r in s.roots.items()}, 'loops': {str(i): bool(l) for i, l in s.loops.items()}, 'free': sorted(s.discard), 'slots': {str(i): e for i, e in s.sizes.items()}}
            with zipfile.ZipFile(fn, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('card.json', json.dumps(meta, indent=1))
                for i, x in s.swaps.items():
                    z.writestr('w%03d.wav' % i, pcm16(x))
        s.path = fn; s.mark(False); s.v_st.set('Saved ' + fn); return True

    def open(s, fn=None):
        if not s.check_save():
            return
        fn = fn or filedialog.askopenfilename(filetypes=[('Rosetta card or project', '*%s;*%s' % (CARD, EXT))])
        if not fn:
            return
        prev = (dict(s.swaps), dict(s.src), dict(s.renames), dict(s.roots), dict(s.loops), set(s.discard), dict(s.sizes))   # kept, so a failed open does not leave the app half-cleared
        s.swaps.clear(); s.src.clear(); s.renames.clear(); s.roots.clear(); s.loops.clear(); s.discard.clear(); s.sizes.clear()
        try:
            if fn.lower().endswith(CARD):
                with zipfile.ZipFile(fn) as z:
                    d = json.loads(z.read('card.json'))
                    if d.get('format') != 'rosetta-card':
                        raise ValueError('not a Rosetta card')
                    for i, w in d.get('waves', {}).items():
                        with wave.open(io.BytesIO(z.read(w['file']))) as wv:
                            x = np.frombuffer(wv.readframes(wv.getnframes()), np.int16).astype(np.float64) / 32768.0
                        s.swaps[int(i)] = x; s.src[int(i)] = 'card:' + (w.get('src') or w['file'])
            else:
                d = json.load(open(fn))
                for i, p in d.get('wavs', {}).items():
                    if not s.set_wav(int(i), p, quiet=True):
                        messagebox.showwarning(APP, 'Could not load ' + p)
            s.renames.update({int(i): n for i, n in d.get('names', {}).items()})
            s.roots.update({int(i): int(r) for i, r in d.get('roots', {}).items()}); s.loops.update({int(i): bool(l) for i, l in d.get('loops', {}).items()}); s.discard.update(int(i) for i in d.get('free', [])); s.sizes.update({int(i): int(e) for i, e in d.get('slots', {}).items()})
        except Exception as e:
            s.swaps.clear(); s.src.clear(); s.renames.clear(); s.roots.clear(); s.loops.clear(); s.discard.clear(); s.sizes.clear()
            s.swaps.update(prev[0]); s.src.update(prev[1]); s.renames.update(prev[2]); s.roots.update(prev[3]); s.loops.update(prev[4]); s.discard.update(prev[5]); s.sizes.update(prev[6])
            messagebox.showerror(APP, 'Could not open %s: %s' % (os.path.basename(fn), e)); return
        s.path = fn; s.fill(); s.mark(False); s.v_st.set('Opened ' + os.path.basename(fn))

    def help(s):
        messagebox.showinfo('How it works',
            'WAVES are the first 128 entries of the D-110 control ROM table (IC12).\n\n'
            'Pick a wave, Load WAV: it replaces that slot in IC8 (drums, #0-31) or IC7 (instruments, #32+).\n'
            'The slot keeps its position and length: longer WAVs are cut, shorter ones padded. 32 kHz mono.\n'
            'Rename edits the 8-character name in IC12 (IC12 must be reprogrammed too).\n'
            'ROOT NOTE (e.g. C4, middle C = 60) = the pitch your WAV sounds at: Studio writes the matching pitch into the IC12 table so that key plays it in tune (drum aliases of the same wave are updated too). LOOP flips the wave between looping the whole slot and one-shot.\n'
            'LONG SAMPLES: pick a SLOT length (up to 8.19 s) or load a WAV longer than the slot and the wave moves to a bigger slot (up to 8.19 s) and Studio rewrites the IC12 table to match. Slots are aligned to their own length, so the whole 16.4 s wave space holds four 4.10 s slots or two 8.19 s ones. Tick "Free this wave\'s space" on waves you do not need to open room: freed waves play silence. Untested on hardware.\n'
            'BUILD always writes all three images: IC8 (drums), IC7 (instruments), IC12 (control).\n\n'
            'Drag WAVs onto the list (onto a row = that wave), a folder, or a card. Save as .rcard = self-contained card, only your samples (shareable, no Roland data); .rosetta = project linking to your WAV files.\n'
            'File > Export all original waves, edit them, then Import WAV folder to swap them all back in.\n'
            'Wheel = zoom, Shift+wheel = pan, right-click = fit. Double-click a wave to hear the original.\n'
            'Looped waves (* in Time) preview 3x. BUILD writes patched .bin images. Hardware-untested.')


if __name__ == '__main__':
    try:                                                      # own taskbar identity, so Windows shows our icon and not the Python one
        import ctypes; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JSW.RosettaROMStudio')
    except Exception:
        pass
    Studio().mainloop()
