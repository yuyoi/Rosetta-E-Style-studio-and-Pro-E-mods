"""Rosetta OS // PRO-E Studio v0.2: styles, OS text, long samples and the Rosetta firmware, built from your own dumps
and burned on a T48.
Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).

  STYLES    32 style slots: stock, MSL-15 / TN-SC1 cards, your MIDI songs
  OS TEXT   boot banner + version screen
  SAMPLES   your WAVs as long samples on the voice board (IC37 / IC38 + the IC28 wave table), up to 4.10 s a slot
  FIRMWARE  your dumps -> Rosetta OS (IC7 + IC4), CK-34 v8.1 (IC28), ROSETTA FX (IC13)
BUILD ALL makes every image, BURN writes one chip (ID check, backup read of the old chip, write, verify, readback).
"""
import json, os, sys, traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
                               QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QHeaderView,
                               QAbstractItemView)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proe_rom as pr
import proe_fw as fw

APP = 'Rosetta OS // PRO-E Studio'
VERSION = '0.2'
FORMAT = 'proe-romstudio-2'
_SONG_DIR = os.path.join(pr.ROOT, 'midi_in')
DEFAULT_CARDS = [os.path.join(pr.ROOT, 'dumps_ext', 'msl15', 'msl15_read2.bin')] + \
    sorted(os.path.join(_SONG_DIR, f) for f in (os.listdir(_SONG_DIR) if os.path.isdir(_SONG_DIR) else [])
           if f.endswith('_card.bin'))
BUILD_DIR = os.path.join(pr.ROOT, 'build', 'studio')
ASSETS = os.path.join(HERE, 'assets')

# SK-1 Studio colours
BG, PANEL, BLUE, GREEN, TXT, DIM, EDGE = '#05080c', '#0d141c', '#2ec4ff', '#39ff88', '#cfeee0', '#4f6b7a', '#1b2a36'
LCD_BG, LCD_INK = '#0b1a10', GREEN
STYLE = f"""
QWidget {{ background: {BG}; color: {TXT}; font-family: Consolas; font-size: 10pt; }}
QLabel {{ color: {BLUE}; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#warn {{ color: #ffb347; }}
QTabWidget::pane {{ border: 1px solid {EDGE}; }}
QTabBar::tab {{ background: {PANEL}; color: {DIM}; padding: 6px 16px; font-weight: bold; }}
QTabBar::tab:selected {{ background: {BG}; color: {GREEN}; border: 1px solid {EDGE}; border-bottom: none; }}
QPushButton {{ background: {PANEL}; color: {GREEN}; border: 1px solid {EDGE}; padding: 5px 10px; font-weight: bold; }}
QPushButton:hover {{ background: {BLUE}; color: {BG}; }}
QPushButton:checked {{ background: {GREEN}; color: {BG}; }}
QPushButton:disabled {{ color: #2c3b45; }}
QPushButton#burn {{ color: #ff6b6b; }}
QPushButton#burn:hover {{ background: #ff6b6b; color: {BG}; }}
QPushButton#build {{ background: {GREEN}; color: {BG}; }}
QPushButton#build:hover {{ background: {BLUE}; }}
QTreeWidget, QPlainTextEdit, QLineEdit, QSpinBox, QComboBox {{ background: {PANEL}; color: {TXT}; border: 1px solid {EDGE};
    selection-background-color: {BLUE}; selection-color: {BG}; }}
QPlainTextEdit {{ color: {GREEN}; }}
QHeaderView::section {{ background: {PANEL}; color: {DIM}; border: none; padding: 3px; }}
QCheckBox {{ color: {BLUE}; spacing: 8px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {EDGE}; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {GREEN}; }}
QProgressBar {{ background: {PANEL}; border: 1px solid {EDGE}; text-align: center; height: 16px; color: {TXT}; }}
QProgressBar::chunk {{ background: #1f6b45; }}
QMenuBar, QMenu {{ background: {PANEL}; color: {TXT}; }}
QMenu::item:selected {{ background: {BLUE}; color: {BG}; }}
"""
RATE_CHOICES = [('auto', 0), ('full 32 kHz', 1), ('half 16 kHz', 2), ('quarter 8 kHz', 4)]
FW_OPTS = (('os', 'Rosetta OS v0.14  (IC7 + IC4)',
            'SYNTH EDIT, JUNO mode, ARPEGGIATOR, ROSETTA FX pages, USER PROGRAM tones, bender CUTOFF/RESO, MIDI remote. '
            'Needs the pin-31 mod (docs/PIN31_MOD.md).'),
           ('ck34', 'CK-34 v8.1  (IC28)',
            'live filter on held notes, PWM LFO, moving Juno chorus, 8 FX modes, wet-only routing. Your samples go here too.'),
           ('fx', 'ROSETTA FX v8.2c  (IC13)',
            'Juno chorus, delay, lo-fi, drive, flanger, Juno chorus + reverb, resonant filter, hall.'))


def dim(text):
    l = QLabel(text)
    l.setObjectName('dim')
    l.setWordWrap(True)
    return l


class Lcd(QLabel):
    """16 x 2 LCD, green on black like the Rosetta screens."""

    def __init__(self):
        super().__init__()
        f = QFont('Consolas', 15)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setStyleSheet(f'background: {LCD_BG}; color: {LCD_INK}; border: 2px solid {EDGE}; padding: 6px 10px;')
        self.show_text('', '')

    def show_text(self, l1, l2):
        self.setText(f'{l1[:16]:<16}\n{l2[:16]:<16}')


class SlotButton(QPushButton):
    def __init__(self, slot):
        super().__init__()
        self.slot = slot
        self.setCheckable(True)
        self.setMinimumSize(92, 54)


class Worker(QThread):
    done = Signal(object, object)
    log = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.log.emit), None)
        except BaseException as e:          # build scripts sys.exit() on a failed stock-byte check
            self.done.emit(None, f'{e}\n{traceback.format_exc()}')


class SampleTree(QTreeWidget):
    """the sample list; WAV files can be dropped on it"""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        self.dropped.emit([u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile().lower().endswith('.wav')])


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP} v{VERSION}')
        ico = os.path.join(ASSETS, 'rosetta_proe.ico')
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))
        self.p = pr.Project()
        self.card_paths, self.lib = [], {}
        self.sel, self.worker, self.last = 0, None, {}
        self.samples = []                   # [{'wav', 'host', 'rate', 'root'}]
        self.sampler = None                 # proe_samples.Sampler, made on first use (loads the wave ROMs)
        self.fw_on = {'os': True, 'ck34': True, 'fx': True}
        self.long_mode = True
        self.out_dir = BUILD_DIR
        self.setStyleSheet(STYLE)
        self._ui()
        for path in DEFAULT_CARDS:
            if os.path.exists(path):
                self.add_cards(path)
        self.refresh()
        self.refresh_fw()

    # ---------- layout ----------
    def _ui(self):
        root = QWidget()
        v = QVBoxLayout(root)
        head = QHBoxLayout()
        png = os.path.join(ASSETS, 'hexgirl_icon.png')
        if os.path.exists(png):
            pic = QLabel()
            pic.setPixmap(QPixmap(png).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            head.addWidget(pic)
        logo = QLabel(f'<span style="font-size:17pt; font-weight:700; color:{GREEN}">ROSETTA OS&nbsp;&nbsp;//&nbsp;&nbsp;PRO-E STUDIO</span>'
                      f'<br><span style="color:{DIM}">styles · samples · firmware · T48 burn&nbsp;&nbsp;v{VERSION}</span>')
        head.addWidget(logo)
        head.addStretch()
        self.lcd = Lcd()
        head.addWidget(self.lcd)
        v.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._styles_tab(), 'STYLES')
        self.tabs.addTab(self._os_tab(), 'OS TEXT')
        self.tabs.addTab(self._samples_tab(), 'SAMPLES')
        self.tabs.addTab(self._fw_tab(), 'FIRMWARE')
        v.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        self.space = QProgressBar()
        bar.addWidget(QLabel('Style ROM space'))
        bar.addWidget(self.space, 1)
        self.b_build = QPushButton('BUILD ALL')
        self.b_build.setObjectName('build')
        self.b_build.clicked.connect(self.on_build)
        bar.addWidget(self.b_build)
        v.addLayout(bar)
        burn = QHBoxLayout()
        burn.addWidget(QLabel('BURN'))
        self.b_burn = {}
        for chip in ('IC7', 'IC4', 'IC28', 'IC13', 'IC37', 'IC38'):
            b = QPushButton(chip)
            b.setObjectName('burn')
            b.setToolTip(f'{pr.CHIPS[chip][0]}: {fw.CHIPS[chip][2]}')
            b.clicked.connect(lambda _=False, c=chip: self.on_burn(c))
            burn.addWidget(b)
            self.b_burn[chip] = b
        burn.addStretch()
        self.burn_info = dim('BUILD ALL first. Every burn reads the old chip into a backup before it writes.')
        burn.addWidget(self.burn_info)
        v.addLayout(burn)
        self.logw = QPlainTextEdit()
        self.logw.setReadOnly(True)
        self.logw.setMaximumHeight(140)
        v.addWidget(self.logw)
        self.setCentralWidget(root)

        m = self.menuBar().addMenu('File')
        for text, fn in (('Import ROM dumps...', self.on_import_dumps), ('Load card / MSL-15 dump...', self.on_load_cards),
                         ('Open project...', self.on_open), ('Save project...', self.on_save),
                         ('Output folder...', self.on_out_dir)):
            a = QAction(text, self)
            a.triggered.connect(fn)
            m.addAction(a)

    def _styles_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        left = QVBoxLayout()
        grid = QGridLayout()
        grid.setSpacing(5)
        grid.addWidget(QLabel('MUSIC STYLE'), 0, 0)
        for m in range(8):
            l = dim(f'NUMBER {m + 1}')
            l.setAlignment(Qt.AlignCenter)
            grid.addWidget(l, 0, m + 1)
        self.slot_btns = []
        for b in range(4):
            grid.addWidget(dim(f'BANK {b + 1}'), b + 1, 0)
            for m in range(8):
                btn = SlotButton(b * 8 + m)
                btn.clicked.connect(lambda _=False, s=b * 8 + m: self.select(s))
                grid.addWidget(btn, b + 1, m + 1)
                self.slot_btns.append(btn)
        left.addLayout(grid)

        ed = QHBoxLayout()
        ed.addWidget(QLabel('Name'))
        self.e_name = QLineEdit()
        self.e_name.setMaxLength(8)
        self.e_name.editingFinished.connect(self.on_rename)
        ed.addWidget(self.e_name)
        ed.addWidget(QLabel('Tempo'))
        self.e_tempo = QSpinBox()
        self.e_tempo.setRange(20, 250)
        self.e_tempo.valueChanged.connect(self.on_tempo)
        ed.addWidget(self.e_tempo)
        self.b_restore = QPushButton('Restore stock')
        self.b_restore.clicked.connect(self.on_restore)
        ed.addWidget(self.b_restore)
        self.info = dim('')
        left.addLayout(ed)
        left.addWidget(self.info)
        self.os_room = QLabel()
        self.os_room.setObjectName('warn')
        self.os_room.setWordWrap(True)
        left.addWidget(self.os_room)
        left.addStretch()
        h.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(QLabel('STYLE LIBRARY  (double-click = put into the selected slot)'))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Style', 'Tempo', 'Meter', 'Bytes'])
        self.tree.setColumnWidth(0, 230)
        self.tree.itemDoubleClicked.connect(self.on_lib_pick)
        right.addWidget(self.tree, 1)
        row = QHBoxLayout()
        b = QPushButton('Load card / MSL-15...')
        b.clicked.connect(self.on_load_cards)
        row.addWidget(b)
        self.b_put = QPushButton('Put into slot  >')
        self.b_put.clicked.connect(lambda: self.on_lib_pick(self.tree.currentItem()))
        row.addWidget(self.b_put)
        right.addLayout(row)
        h.addLayout(right, 2)
        self._fill_stock()
        return w

    def _os_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        self.os_edits = []
        for row, (title, attr, chip) in enumerate((('Boot banner (power on)', 'banner', 'IC7'),
                                                   ('Version screen (hold REVERB ON/OFF at power on)', 'version', 'IC4'))):
            g.addWidget(QLabel(f'{title}  ->  {chip}'), row * 3, 0, 1, 2)
            prev = Lcd()
            for i in range(2):
                e = QLineEdit(getattr(self.p, attr)[i])
                e.setMaxLength(16)
                e.setFont(QFont('Consolas', 12))
                e.textChanged.connect(lambda _t, a=attr, pv=prev: self.on_os_text(a, pv))
                g.addWidget(e, row * 3 + 1 + i, 0)
                self.os_edits.append((attr, i, e))
            g.addWidget(prev, row * 3 + 1, 1, 2, 1)
            self.on_os_text(attr, prev)
        self.os_text_note = dim('')
        g.addWidget(self.os_text_note, 6, 0, 1, 2)
        g.setRowStretch(7, 1)
        return w

    def _samples_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(dim('Drop WAVs here. Each sound replaces one wave: #128 is the SFX pad that played "Laughing" (key 76), '
                        'the others are PCM WAVE 2-n in SYNTH EDIT. Longer than 4.10 s = stored at half (16 kHz) or quarter '
                        '(8 kHz) rate and pitched back, so it plays at real speed. The drum kit always stays stock.'))
        self.s_tree = SampleTree()
        self.s_tree.setHeaderLabels(['#', 'WAV', 'Plays as', 'Rate', 'Root', 'Length', 'Stored'])
        self.s_tree.setRootIsDecorated(False)
        self.s_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        for c, wd in ((0, 30), (2, 330), (3, 120), (4, 60), (5, 70), (6, 150)):
            self.s_tree.setColumnWidth(c, wd)
        self.s_tree.dropped.connect(self.add_wavs)
        v.addWidget(self.s_tree, 1)
        row = QHBoxLayout()
        for text, fn in (('Add WAV...', self.on_add_wav), ('Remove', self.on_remove_wav), ('Play original', self.on_play_orig),
                         ('Play as she will', self.on_play_built), ('Stop', self.on_stop)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
            if text == 'Play as she will':
                self.b_play_built = b
        row.addStretch()
        self.c_long = QCheckBox('LONG mode: free every non-drum wave for space')
        self.c_long.setChecked(True)
        self.c_long.toggled.connect(lambda on: setattr(self, 'long_mode', on))
        row.addWidget(self.c_long)
        v.addLayout(row)
        self.s_info = dim('')
        v.addWidget(self.s_info)
        return w

    def _fw_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel('YOUR DUMPS  (../dumps, checked by SHA-1 against a PRO-E v2.00)'))
        self.d_tree = QTreeWidget()
        self.d_tree.setHeaderLabels(['Chip', 'Status', 'File'])
        self.d_tree.setRootIsDecorated(False)
        self.d_tree.setColumnWidth(0, 70)
        self.d_tree.setColumnWidth(1, 110)
        self.d_tree.setMaximumHeight(170)
        v.addWidget(self.d_tree)
        row = QHBoxLayout()
        b = QPushButton('Import ROM dumps...')
        b.clicked.connect(self.on_import_dumps)
        row.addWidget(b)
        row.addWidget(dim('Pick any files: the ones that are PRO-E v2.00 chips are copied in under their standard names.'))
        v.addLayout(row)
        v.addSpacing(8)
        v.addWidget(QLabel('PATCH WITH'))
        self.fw_checks = {}
        for key, title, desc in FW_OPTS:
            c = QCheckBox(title)
            c.setChecked(self.fw_on[key])
            c.toggled.connect(lambda on, k=key: self.on_fw_toggle(k, on))
            v.addWidget(c)
            l = dim(desc)
            l.setContentsMargins(26, 0, 0, 4)
            v.addWidget(l)
            self.fw_checks[key] = c
        self.fw_room = QLabel()
        self.fw_room.setObjectName('warn')
        self.fw_room.setWordWrap(True)
        v.addWidget(self.fw_room)
        row = QHBoxLayout()
        self.b_room = QPushButton('Make room for the OS')
        self.b_room.setToolTip('BANK 3 no.2 / no.4 / no.5 get copies of 8BEAT2 / 8BEAT1 / 16BEAT1, so BIG BAND, COUNTRY '
                               'and WALTZ1 leave bank 5. Better: put MSL-15 or MIDI styles there in STYLES.')
        self.b_room.clicked.connect(self.on_make_room)
        row.addWidget(self.b_room)
        row.addStretch()
        v.addLayout(row)
        self.out_label = dim('')
        v.addWidget(self.out_label)
        v.addStretch()
        return w

    # ---------- library ----------
    def _fill_stock(self):
        top = QTreeWidgetItem(['Her stock styles (v2.00)'])
        self.tree.addTopLevelItem(top)
        for s in self.p.stock:
            it = QTreeWidgetItem([f'{s.index + 1:2d}  {s.name}', str(s.tempo), pr.meter(s.ticks), ''])
            it.setData(0, Qt.UserRole, s.key)
            self.lib[s.key] = s
            top.addChild(it)

    def add_cards(self, path):
        try:
            cards = pr.load_cards(path)
        except Exception as e:
            QMessageBox.warning(self, APP, str(e))
            return
        if path not in self.card_paths:
            self.card_paths.append(path)
        for label, styles in cards:
            top = QTreeWidgetItem([label])
            self.tree.addTopLevelItem(top)
            for s in styles:
                it = QTreeWidgetItem([s.name, str(s.tempo), pr.meter(s.ticks), str(s.size())])
                it.setData(0, Qt.UserRole, s.key)
                self.lib[s.key] = s
                top.addChild(it)
        self.log(f'loaded {len(cards)} card(s) from {os.path.basename(path)}')

    # ---------- state -> view ----------
    def refresh(self):
        for btn in self.slot_btns:
            n = btn.slot
            mark = '  LOCK' if n == pr.BAROQUE else ('  NEW' if self.p.changed(n) else '')
            btn.setText(f'{n % 8 + 1}{mark}\n{self.p.names[n]}')
            btn.setChecked(n == self.sel)
            col = '#2a2410' if n == pr.BAROQUE else ('#0f2a1c' if self.p.changed(n) else PANEL)
            if n == self.sel:
                col = '#123a52'
            btn.setStyleSheet(f'background:{col}; color:{TXT}; text-align:center;')
        n = self.sel
        s = self.p.slots[n]
        locked = n == pr.BAROQUE
        self.e_name.blockSignals(True)
        self.e_tempo.blockSignals(True)
        self.e_name.setText(self.p.names[n])
        self.e_tempo.setValue(self.p.tempos[n])
        self.e_name.blockSignals(False)
        self.e_tempo.blockSignals(False)
        for w in (self.e_name, self.e_tempo, self.b_restore, self.b_put):
            w.setEnabled(not locked)
        src = 'stock' if s.source == 'stock' else s.source
        self.info.setText(f'BANK {n // 8 + 1} no.{n % 8 + 1}  ·  {pr.meter(s.ticks)}  ·  from {src}'
                          + ('  ·  BAROQUE is locked (never changed)' if locked else ''))
        self.lcd.show_text(f'{self.p.names[n]:<8} {self.p.tempos[n]:>3}BPM', f'B{n // 8 + 1}-{n % 8 + 1}  {pr.meter(s.ticks):<5}'
                           + ('LOCK' if locked else ('NEW' if self.p.changed(n) else '')))
        self.p.reserve = self.fw_on['os']
        need, have = self.p.space()
        self.space.setMaximum(max(have, 1))
        self.space.setValue(min(need, have))
        self.space.setFormat(f'{need} / {have} bytes' + ('  (TOO BIG)' if need > have else ''))
        self.b_build.setEnabled(need <= have)
        block = self.p.synth_blockers() if self.fw_on['os'] else []
        msg = ('Rosetta OS needs the bank 5 area these styles use: ' + ', '.join(
            f'BANK {n // 8 + 1} no.{n % 8 + 1} {self.p.names[n]}' for n in block)
            + '. Put other styles there, or FIRMWARE > Make room for the OS.') if block else ''
        self.os_room.setText(msg)
        if hasattr(self, 'fw_room'):
            self.fw_room.setText(msg)
            self.b_room.setVisible(bool(block))
        for chip, b in self.b_burn.items():
            b.setEnabled(chip in self.last)

    def refresh_fw(self):
        self.d_tree.clear()
        for chip, (path, st) in fw.check_dumps().items():
            it = QTreeWidgetItem([chip, {'ok': 'OK v2.00', 'missing': 'MISSING', 'different': 'NOT v2.00'}[st],
                                  os.path.basename(path) if path else fw.STOCK[chip][0]])
            it.setForeground(1, Qt.green if st == 'ok' else Qt.red)
            self.d_tree.addTopLevelItem(it)
        self.out_label.setText(f'Output: {self.out_dir}   (File > Output folder)')
        if self.fw_on['os']:
            self.os_text_note.setText('Rosetta OS is on: the version screen shows the OS version, and a banner left as it is '
                                      'becomes the OS banner (" ROSETTA  PRO-E " / " OS v0.14  ARP  ").')
        else:
            self.os_text_note.setText('')

    def refresh_samples(self, built=None):
        self.s_tree.clear()
        for n, s in enumerate(self.samples):
            it = QTreeWidgetItem([str(n + 1), os.path.basename(s['wav']), '', '', '', s.get('len', ''), (built or {}).get(n, '')])
            it.setToolTip(1, s['wav'])
            self.s_tree.addTopLevelItem(it)
            hosts = QComboBox()
            for h in self.sampler.hosts:
                hosts.addItem(self.sampler.host_label(h), h)
            hosts.setCurrentIndex(max(0, hosts.findData(s['host'])))
            hosts.currentIndexChanged.connect(lambda _i, c=hosts, k=n: self._set_sample(k, 'host', c.currentData()))
            self.s_tree.setItemWidget(it, 2, hosts)
            rate = QComboBox()
            for label, val in RATE_CHOICES:
                rate.addItem(label, val)
            rate.setCurrentIndex(max(0, rate.findData(s['rate'])))
            rate.currentIndexChanged.connect(lambda _i, c=rate, k=n: self._set_sample(k, 'rate', c.currentData()))
            self.s_tree.setItemWidget(it, 3, rate)
            root = QLineEdit(self.sampler_note(s['root']))
            root.editingFinished.connect(lambda e=root, k=n: self._set_root(k, e))
            self.s_tree.setItemWidget(it, 4, root)
        total = sum(s.get('secs', 0) for s in self.samples)
        self.s_info.setText(f'{len(self.samples)} sound(s), {total:.1f} s of audio. Room in LONG mode: about 12 s stored '
                            f'(4.10 s slots; half rate doubles the time a slot holds, quarter rate x4).')

    def sampler_note(self, m):
        import proe_samples as ps
        return ps.ws().note_name(m)

    def select(self, n):
        self.sel = n
        self.refresh()

    def log(self, msg):
        self.logw.appendPlainText(msg)

    # ---------- styles / OS text ----------
    def on_lib_pick(self, item):
        if not item or item.data(0, Qt.UserRole) is None:
            return
        s = self.lib[tuple(item.data(0, Qt.UserRole))]
        try:
            self.p.assign(self.sel, s)
        except PermissionError as e:
            self.log(str(e))
            return
        self.log(f'BANK {self.sel // 8 + 1} no.{self.sel % 8 + 1} <- {s.name} ({s.source})')
        self.refresh()

    def on_rename(self):
        if self.sel != pr.BAROQUE:
            self.p.rename(self.sel, self.e_name.text().upper())
            self.refresh()

    def on_tempo(self, v):
        if self.sel != pr.BAROQUE:
            self.p.set_tempo(self.sel, v)
            self.refresh()

    def on_restore(self):
        self.p.restore(self.sel)
        self.refresh()

    def on_os_text(self, attr, preview):
        lines = [e.text() for a, i, e in self.os_edits if a == attr]
        if len(lines) == 2:
            setattr(self.p, attr, [lines[0].ljust(16)[:16], lines[1].ljust(16)[:16]])
            preview.show_text(*lines)
            if hasattr(self, 'out_label'):
                self.refresh_fw()

    def on_load_cards(self):
        path, _ = QFileDialog.getOpenFileName(self, 'TN-SC1 card or MSL-15 dump', pr.ROOT, 'ROM images (*.bin *.rom);;All (*)')
        if path:
            self.add_cards(path)

    # ---------- samples ----------
    def _need_sampler(self):
        if self.sampler is None:
            import proe_samples as ps
            try:
                self.sampler = ps.Sampler()
            except Exception as e:
                QMessageBox.warning(self, APP, f'Samples need your IC37, IC38, IC28 and IC7 dumps in dumps/.\n\n{e}')
                return False
        return True

    def add_wavs(self, paths):
        if not paths or not self._need_sampler():
            return
        import proe_samples as ps
        free = [h for h in self.sampler.hosts if h not in {s['host'] for s in self.samples}]
        for p in paths:
            if not free:
                self.log('no free wave left for ' + os.path.basename(p))
                break
            try:
                x = ps.load(p)
            except Exception as e:
                self.log(f'{os.path.basename(p)}: {e}')
                continue
            secs = len(x) / 32000
            self.samples.append({'wav': p, 'host': free.pop(0), 'rate': 0, 'root': ps.root_of(p),
                                 'secs': secs, 'len': f'{secs:.2f} s'})
            self.log(f'sample {len(self.samples)}: {os.path.basename(p)} ({secs:.2f} s, auto rate: '
                     f'{ps.RATES[ps.auto_rate(len(x))]})')
        self.refresh_samples()

    def _set_sample(self, k, key, val):
        if k < len(self.samples):
            self.samples[k][key] = val

    def _set_root(self, k, e):
        import proe_samples as ps
        m = ps.ws().parse_note(e.text())
        if m is None or not 0 <= m <= 127:
            e.setText(self.sampler_note(self.samples[k]['root']))
            return
        self.samples[k]['root'] = m
        e.setText(ps.ws().note_name(m))

    def on_add_wav(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'WAV files', os.path.expanduser('~'), 'WAV (*.wav)')
        self.add_wavs(paths)

    def on_remove_wav(self):
        it = self.s_tree.currentItem()
        if it:
            del self.samples[self.s_tree.indexOfTopLevelItem(it)]
            self.refresh_samples()

    def _play(self, path):
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            self.log(f'play: {e}')

    def on_play_orig(self):
        it = self.s_tree.currentItem()
        if it:
            self._play(self.samples[self.s_tree.indexOfTopLevelItem(it)]['wav'])

    def on_play_built(self):
        pv = os.path.join(self.out_dir, 'samples', 'preview.wav')
        if os.path.exists(pv):
            self._play(pv)
        else:
            self.log('BUILD ALL first: the preview is decoded back out of the built wave ROMs.')

    def on_stop(self):
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    # ---------- firmware ----------
    def on_fw_toggle(self, key, on):
        self.fw_on[key] = on
        self.refresh()
        self.refresh_fw()

    def on_make_room(self):
        for slot, src in ((17, 9), (19, 8), (20, 10)):
            if slot in self.p.synth_blockers():
                self.p.assign(slot, self.p.stock[src])
                self.log(f'BANK {slot // 8 + 1} no.{slot % 8 + 1} <- copy of {self.p.stock[src].name} (room for the OS)')
        self.refresh()

    def on_import_dumps(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Your PRO-E ROM dumps', os.path.expanduser('~'), 'ROM images (*.bin *.rom);;All (*)')
        for p in paths:
            chip = fw.import_dump(p)
            self.log(f'{os.path.basename(p)}: ' + (f'{chip} v2.00, copied to dumps/' if chip else 'not a known PRO-E v2.00 chip, skipped'))
        self.refresh_fw()

    def on_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, 'Output folder', self.out_dir)
        if d:
            self.out_dir = d
            self.refresh_fw()

    # ---------- project ----------
    def on_save(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save project', pr.ROOT, 'PRO-E project (*.proe.json)')
        if path:
            d = self.p.to_dict(self.card_paths)
            d.update(format=FORMAT, firmware=self.fw_on, long_mode=self.long_mode,
                     samples=[{k: s[k] for k in ('wav', 'host', 'rate', 'root')} for s in self.samples])
            json.dump(d, open(path, 'w', encoding='utf-8'), indent=1)
            self.log(f'saved {path}')

    def on_open(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, 'Open project', pr.ROOT, 'PRO-E project (*.proe.json)')
        if not path:
            return
        d = json.load(open(path, encoding='utf-8'))
        for c in d['cards']:
            if c not in self.card_paths and os.path.exists(c):
                self.add_cards(c)
        self.p.from_dict(d, self.lib)
        for a, i, e in self.os_edits:
            e.setText(getattr(self.p, a)[i])
        for k, on in d.get('firmware', {}).items():
            if k in self.fw_checks:
                self.fw_checks[k].setChecked(on)
        self.c_long.setChecked(d.get('long_mode', True))
        self.samples = []
        if d.get('samples') and self._need_sampler():
            import proe_samples as ps
            for s in d['samples']:
                secs = len(ps.load(s['wav'])) / 32000 if os.path.exists(s['wav']) else 0
                self.samples.append(dict(s, secs=secs, len=f'{secs:.2f} s' if secs else 'MISSING'))
        if self.sampler:
            self.refresh_samples()
        self.refresh()
        self.log(f'opened {path}')

    # ---------- build / burn ----------
    def run(self, fn, after):
        if self.worker and self.worker.isRunning():
            return
        for b in [self.b_build] + list(self.b_burn.values()):
            b.setEnabled(False)
        self.worker = Worker(fn)
        self.worker.log.connect(self.log)
        self.worker.done.connect(lambda res, err: self._done(res, err, after))
        self.worker.start()

    def _done(self, res, err, after):
        if err:
            self.log('ERROR: ' + err)
            QMessageBox.critical(self, APP, err.splitlines()[0])
        else:
            after(res)
        self.refresh()

    def on_build(self):
        samples = list(self.samples)
        opts = dict(self.fw_on)
        # Rosetta OS on: the version screen is the OS's, the banner too unless you changed it
        banner = None if self.p.banner == pr.Project().banner else pr.fit16(self.p.banner[0]) + pr.fit16(self.p.banner[1])
        version = None
        out, long_mode, sampler = self.out_dir, self.long_mode, self.sampler

        def job(log):
            sfiles, key = None, []
            if samples:
                sfiles, key, _ = sampler.build(samples, os.path.join(out, 'samples'), long_mode, log)
            files = fw.build(self.p, out, opts['os'], opts['ck34'], opts['fx'], sfiles, banner, version, log)
            return files, key

        def after(res):
            files, key = res
            self.last = files
            self.log('BUILD OK' + ('' if self.p.reserve else '  (24 stock styles verified, Baroque locked, bank sums OK)'))
            for k in key:
                self.log('  ' + k)
            for chip, (path, md5) in files.items():
                self.log(f'  {chip:4s} {os.path.basename(path)}  md5 {md5}')
            if key:
                import re
                st = {}
                for n, k in enumerate(key):
                    m = re.search(r'slot ([\d.]+ s).*rate (\w+)', k)
                    st[n] = f'{m.group(1)} slot, {m.group(2)}' if m else ''
                self.refresh_samples(st)
        self.log('building...')
        self.run(job, after)

    def on_burn(self, which):
        if which not in self.last:
            QMessageBox.information(self, APP, 'BUILD ALL first.')
            return
        path = self.last[which][0]
        dev = pr.CHIPS[which][0].split('@')[0]
        note = {'IC28': '\n\nIC28 is a 28-pin chip: pin 20 = enable, pin 22 = A16. Check your socket wiring first.',
                'IC7': '\n\nThe Rosetta OS needs the pin-31 mod (docs/PIN31_MOD.md).'}.get(which, '')
        if QMessageBox.question(self, APP, f'Put a {dev} for {which} ({fw.CHIPS[which][2]}) in the T48, then Yes.\n\n'
                                           f'The old content is read into a backup first, then the chip is erased and '
                                           f'{os.path.basename(path)} is written.{note}') != QMessageBox.Yes:
            return
        self.run(lambda log: pr.burn(which, path, log, os.path.join(self.out_dir, 'backups')),
                 lambda ok: self.log(f'{which} BURN {"DONE: chip == image" if ok else "FAILED"}'))


def first_run():
    """no IC7 / IC4 dump yet (fresh clone): ask for the dump files once, file them in dumps/. False = give up."""
    def missing():
        return [c for c in ('IC7', 'IC4') if fw.check_dumps()[c][1] != 'ok']
    while missing():
        QMessageBox.information(None, APP, 'Welcome! The Studio builds everything from your own PRO-E v2.00 chip dumps.\n\n'
                                f'Missing: {", ".join(missing())}. Pick your dump files next (IC28, IC13, IC37, IC38 '
                                'too if you have them). They are checked by SHA-1 and copied into dumps/.')
        paths, _ = QFileDialog.getOpenFileNames(None, 'Your PRO-E ROM dumps', os.path.expanduser('~'),
                                                'ROM images (*.bin *.rom);;All (*)')
        if not paths:
            return False
        for p in paths:
            fw.import_dump(p)
    return True


def main():
    app = QApplication(sys.argv)
    if not first_run():
        sys.exit(0)
    w = Studio()
    w.resize(1320, 820)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
