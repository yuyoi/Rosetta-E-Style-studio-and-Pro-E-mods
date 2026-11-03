"""Rosetta PRO-E ROM Studio v0.1: style slots, card import, OS text, build + burn (T48).
Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).
"""
import json, os, sys, traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QColor
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QFrame)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proe_rom as pr

APP = 'Rosetta PRO-E ROM Studio'
VERSION = '0.1'
_SONG_DIR = os.path.join(pr.ROOT, 'midi_in')
DEFAULT_CARDS = [os.path.join(pr.ROOT, 'dumps_ext', 'msl15', 'msl15_read2.bin')] + \
    sorted(os.path.join(_SONG_DIR, f) for f in (os.listdir(_SONG_DIR) if os.path.isdir(_SONG_DIR) else [])
           if f.endswith('_card.bin'))
BUILD_DIR = os.path.join(pr.ROOT, 'build')

PANEL, PANEL2, INK, DIM, BLUE = '#26272b', '#1c1d20', '#e8e8e8', '#8a8d93', '#7ec8f0'
LCD_BG, LCD_INK = '#a9d46a', '#1d2b10'
STYLE = f"""
QWidget {{ background: {PANEL}; color: {INK}; font-family: 'Segoe UI'; font-size: 10pt; }}
QTabWidget::pane {{ border: 1px solid #3a3c41; }}
QTabBar::tab {{ background: {PANEL2}; color: {DIM}; padding: 6px 14px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {INK}; }}
QTabBar::tab:disabled {{ color: #55585e; }}
QPushButton {{ background: #3a3c41; border: 1px solid #50535a; border-radius: 3px; padding: 5px 10px; }}
QPushButton:hover {{ background: #464950; }}
QPushButton:disabled {{ color: #6b6e74; }}
QPushButton#burn {{ background: #6b2222; border-color: #8a3030; }}
QPushButton#build {{ background: #24506b; border-color: #2f6a8c; }}
QTreeWidget, QPlainTextEdit, QLineEdit, QSpinBox {{ background: {PANEL2}; border: 1px solid #3a3c41; }}
QHeaderView::section {{ background: {PANEL2}; color: {DIM}; border: none; padding: 3px; }}
QProgressBar {{ background: {PANEL2}; border: 1px solid #3a3c41; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: #3f7a3a; }}
"""


class Lcd(QLabel):
    """16 x 2 backlit LCD."""

    def __init__(self):
        super().__init__()
        f = QFont('Consolas', 15)
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setStyleSheet(f'background: {LCD_BG}; color: {LCD_INK}; border: 6px solid #111; '
                           f'border-radius: 4px; padding: 6px 10px;')
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
        except Exception as e:
            self.done.emit(None, f'{e}\n{traceback.format_exc()}')


class Studio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{APP} v{VERSION}')
        self.p = pr.Project()
        self.card_paths, self.lib = [], {}
        self.sel, self.worker, self.last = 0, None, None
        self.setStyleSheet(STYLE)
        self._ui()
        for path in DEFAULT_CARDS:
            if os.path.exists(path):
                self.add_cards(path)
        self.refresh()

    # ---------- layout ----------
    def _ui(self):
        root = QWidget()
        v = QVBoxLayout(root)
        head = QHBoxLayout()
        logo = QLabel(f'<span style="font-size:20pt; font-weight:700">Roland</span>&nbsp;&nbsp;'
                      f'<span style="font-size:26pt; font-weight:800; color:{BLUE}; font-style:italic">PRO-E</span>'
                      f'&nbsp;&nbsp;<span style="color:{BLUE}">ROSETTA ROM STUDIO</span>')
        head.addWidget(logo)
        head.addStretch()
        self.lcd = Lcd()
        head.addWidget(self.lcd)
        v.addLayout(head)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._styles_tab(), 'STYLES')
        self.tabs.addTab(self._os_tab(), 'OS TEXT')
        self.tabs.addTab(QLabel('v0.2: Style maker (MIDI from Cubase -> new style)'), 'STYLE MAKER')
        self.tabs.addTab(QLabel('v0.3: Rosetta Wave (D-110 wave tool hooked in: custom samples on IC37/IC38 + IC28 table)'), 'WAVES')
        self.tabs.setTabEnabled(2, False)
        self.tabs.setTabEnabled(3, False)
        v.addWidget(self.tabs, 1)

        bar = QHBoxLayout()
        self.space = QProgressBar()
        bar.addWidget(QLabel('Style ROM space'))
        bar.addWidget(self.space, 1)
        self.b_build = QPushButton('BUILD')
        self.b_build.setObjectName('build')
        self.b_build.clicked.connect(self.on_build)
        self.b_burn7 = QPushButton('BURN IC7 (styles + banner)')
        self.b_burn7.setObjectName('burn')
        self.b_burn7.clicked.connect(lambda: self.on_burn('IC7'))
        self.b_burn4 = QPushButton('BURN IC4 (version text)')
        self.b_burn4.setObjectName('burn')
        self.b_burn4.clicked.connect(lambda: self.on_burn('IC4'))
        for b in (self.b_build, self.b_burn7, self.b_burn4):
            bar.addWidget(b)
        v.addLayout(bar)
        self.logw = QPlainTextEdit()
        self.logw.setReadOnly(True)
        self.logw.setMaximumHeight(130)
        v.addWidget(self.logw)
        self.setCentralWidget(root)

        m = self.menuBar().addMenu('File')
        for text, fn in (('Load card / MSL-15 dump...', self.on_load_cards), ('Open project...', self.on_open),
                         ('Save project...', self.on_save)):
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
            l = QLabel(f'NUMBER {m + 1}')
            l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet(f'color:{DIM}')
            grid.addWidget(l, 0, m + 1)
        self.slot_btns = []
        for b in range(4):
            l = QLabel(f'BANK {b + 1}')
            l.setStyleSheet(f'color:{DIM}')
            grid.addWidget(l, b + 1, 0)
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
        self.info = QLabel()
        self.info.setStyleSheet(f'color:{DIM}')
        left.addLayout(ed)
        left.addWidget(self.info)
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
        g.setRowStretch(7, 1)
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
            s = self.p.slots[n]
            mark = '  LOCK' if n == pr.BAROQUE else ('  NEW' if self.p.changed(n) else '')
            btn.setText(f'{n % 8 + 1}{mark}\n{self.p.names[n]}')
            btn.setChecked(n == self.sel)
            col = '#3d3420' if n == pr.BAROQUE else ('#22402a' if self.p.changed(n) else '#34363b')
            if n == self.sel:
                col = '#2f5c7a'
            btn.setStyleSheet(f'background:{col}; text-align:center;')
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
        need, have = self.p.space()
        self.space.setMaximum(max(have, 1))
        self.space.setValue(min(need, have))
        self.space.setFormat(f'{need} / {have} bytes' + ('  (TOO BIG)' if need > have else ''))
        self.b_build.setEnabled(need <= have)

    def select(self, n):
        self.sel = n
        self.refresh()

    def log(self, msg):
        self.logw.appendPlainText(msg)

    # ---------- actions ----------
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

    def on_load_cards(self):
        path, _ = QFileDialog.getOpenFileName(self, 'TN-SC1 card or MSL-15 dump', pr.ROOT, 'ROM images (*.bin *.rom);;All (*)')
        if path:
            self.add_cards(path)

    def on_save(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save project', pr.ROOT, 'PRO-E project (*.proe.json)')
        if path:
            json.dump(self.p.to_dict(self.card_paths), open(path, 'w', encoding='utf-8'), indent=1)
            self.log(f'saved {path}')

    def on_open(self):
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
        self.refresh()
        self.log(f'opened {path}')

    def run(self, fn, after):
        if self.worker and self.worker.isRunning():
            return
        for b in (self.b_build, self.b_burn7, self.b_burn4):
            b.setEnabled(False)
        self.worker = Worker(fn)
        self.worker.log.connect(self.log)
        self.worker.done.connect(lambda res, err: self._done(res, err, after))
        self.worker.start()

    def _done(self, res, err, after):
        for b in (self.b_build, self.b_burn7, self.b_burn4):
            b.setEnabled(True)
        if err:
            self.log('ERROR: ' + err)
            QMessageBox.critical(self, APP, err.splitlines()[0])
        else:
            after(res)
        self.refresh()

    def on_build(self):
        tag = 'studio'

        def job(log):
            ic7, ic4, rep = self.p.build()
            files = pr.write_images(ic7, ic4, BUILD_DIR, tag)
            return rep, files

        def after(res):
            rep, files = res
            self.last = files
            self.log('BUILD OK (24 stock styles verified, Baroque locked, bank sums OK)' if not rep else 'BUILD OK')
            for r in rep:
                self.log('  ' + r)
            for name, (path, md5) in files.items():
                self.log(f'  {name}  md5 {md5}')
        self.log('building...')
        self.run(job, after)

    def on_burn(self, which):
        if not self.last:
            QMessageBox.information(self, APP, 'Press BUILD first.')
            return
        name = next(n for n in self.last if n.startswith(which))
        chip = pr.CHIPS[which][0]
        if QMessageBox.question(self, APP, f'Put the {chip} for {which} in the T48, then OK.\n\n'
                                           f'This erases the chip and writes {name}.') != QMessageBox.Yes:
            return
        path = self.last[name][0]
        self.run(lambda log: pr.burn(which, path, log),
                 lambda ok: self.log(f'{which} BURN {"DONE: chip == image" if ok else "FAILED"}'))


def main():
    app = QApplication(sys.argv)
    w = Studio()
    w.resize(1280, 760)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
