"""Scripted-click test of the GUI (offscreen).

1. styles only (firmware off): rebuild v0.2 by clicking, compare with the burned v0.2 IC7.
2. stock styles + Rosetta OS: the build must refuse until "Make room for the OS" is clicked, then build.
3. the v0.3 project + 4 test WAVs dropped on SAMPLES + all firmware on: IC7 / IC4 / IC13 must equal the chips in her
   (v0.14, ROSETTA FX v8.2c); IC28 must equal her v8.1 chip when the sample table equals her LONG2 table.
   Needs ../dumps, ../v0.3_songs.proe.json and the cards it names (the author's machine).
"""
import hashlib, os, sys, time, tempfile, wave
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox
import importlib.util
spec = importlib.util.spec_from_file_location('studio', os.path.join(HERE, 'romstudio.pyw'))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)
QMessageBox.critical = staticmethod(lambda *a, **k: print('   (dialog) ' + str(a[2]).splitlines()[0]))

app = QApplication(sys.argv)
w = st.Studio()
tmp = tempfile.mkdtemp()
w.out_dir = tmp
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name)


def build():
    w.last = {}
    w.b_build.click()
    t0 = time.time()
    while w.worker and w.worker.isRunning() and time.time() - t0 < 600:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    return w.last


# ---- 1. styles only ----
tree = w.tree
tops = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
msl = [t for t in tops if 'msl15' in t.text(0)]
check('library: stock + 16 MSL-15 cards', len(msl) == 16 and tops[0].text(0).startswith('Her stock'))
turkey, asia = msl[15], msl[14]
check('last card is Turkey', turkey.child(0).text(0) == 'DUEK')
for k in ('os', 'ck34', 'fx'):
    w.fw_checks[k].click()
check('firmware all off', not any(w.fw_on.values()))
for i, card in enumerate([turkey] * 4 + [asia] * 4):
    w.slot_btns[16 + i].click()
    tree.setCurrentItem(card.child(i % 4))
    w.b_put.click()
check('slot 16 shows DUEK', 'DUEK' in w.slot_btns[16].text())
w.slot_btns[16].click()
check('LCD shows DUEK', 'DUEK' in w.lcd.text())
w.slot_btns[24].click()
check('Baroque editors disabled', not w.e_name.isEnabled() and not w.b_put.isEnabled())
w.on_lib_pick(turkey.child(0))
check('Baroque refused a style', 'BAROQUE' in w.slot_btns[24].text())
for a, i, e in w.os_edits:
    if a == 'banner':
        e.setText([' ROSETTA  PRO-E ', '  OS v0.2 2026  '][i])
last = build()
v02 = os.path.join(st.pr.ROOT, 'build', 'IC7_v0.2_W27C040.bin')
check('clicked build == burned v0.2 IC7', set(last) == {'IC7', 'IC4'} and open(last['IC7'][0], 'rb').read() == open(v02, 'rb').read())
check('burn buttons: only IC7 + IC4 enabled', [c for c, b in w.b_burn.items() if b.isEnabled()] == ['IC7', 'IC4'])

# ---- 2. stock styles + Rosetta OS ----
for n in range(32):
    if n != st.pr.BAROQUE:
        w.p.restore(n)
for a, i, e in w.os_edits:
    e.setText(getattr(st.pr.Project(), a)[i])
w.fw_checks['os'].click()
w.refresh()
check('OS on + stock styles: warning names BIG BAND + COUNTRY + WALTZ1',
      all(n in w.fw_room.text() for n in ('BIG BAND', 'COUNTRY', 'WALTZ1')))
check('Make room button shown', not w.b_room.isHidden())
check('stock + OS build refused', not build())
w.b_room.click()
check('room made: warning gone', w.fw_room.text() == '' and all('BEAT' in w.slot_btns[n].text() for n in (17, 19, 20)))
last = build()
check('stock styles + OS built (IC7 512 KB, IC4 64 KB)', set(last) == {'IC7', 'IC4'}
      and os.path.getsize(last['IC7'][0]) == 0x80000 and os.path.getsize(last['IC4'][0]) == 0x10000)

# ---- 3. her setup: v0.3 project + samples + all firmware ----
proj = os.path.join(st.pr.ROOT, 'v0.3_songs.proe.json')
w.on_open(proj)
for k in ('ck34', 'fx'):
    w.fw_checks[k].click()
check('firmware all on', all(w.fw_on.values()))
wavs = []
rng = np.random.default_rng(1)
for name, secs, sr in (('m6.wav', 8.0, 44100), ('Recording (214).wav', 6.95, 48000), ('Recording (226).wav', 3.99, 44100),
                       ('Recording (228).wav', 3.84, 32000)):
    t = np.arange(int(secs * sr)) / sr
    x = 0.5 * np.sin(2 * np.pi * 220 * t * (1 + 0.1 * t)) + 0.1 * rng.standard_normal(len(t))
    p = os.path.join(tmp, name)
    f = wave.open(p, 'wb'); f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
    f.writeframes((x * 20000).astype('<i2').tobytes()); f.close()
    wavs.append(p)
w.tabs.setCurrentIndex(2)
w.s_tree.dropped.emit(wavs)                       # = dropping 4 WAVs on the list
check('4 samples, hosts #128-#131', [s['host'] for s in w.samples] == [128, 129, 130, 131])
for k in (2, 3):                                  # LONG2 stored these two at quarter rate: pick it in the combo
    combo = w.s_tree.itemWidget(w.s_tree.topLevelItem(k), 3)
    combo.setCurrentIndex(combo.findData(4))
check('rate combos -> quarter', [s['rate'] for s in w.samples] == [0, 0, 4, 4])
last = build()
her = {'IC7': '6a107e72', 'IC4': '641ba5b8', 'IC28': '4be7339e', 'IC13': 'ddef6264'}
for chip, want in her.items():
    check(f'{chip} == the chip in her ({want})', chip in last and last[chip][1].startswith(want))
check('IC37 + IC38 built', 'IC37' in last and 'IC38' in last)
check('Stored column filled', w.s_tree.topLevelItem(0).text(6).startswith('4.10 s slot, half'))
check('preview decoded', os.path.exists(os.path.join(tmp, 'samples', 'preview.wav')))
check('all 6 burn buttons enabled', all(b.isEnabled() for b in w.b_burn.values()))
w.resize(1320, 820)
for idx, name in ((3, 'screenshot_firmware.png'), (2, 'screenshot_samples.png'), (0, 'screenshot.png')):
    w.tabs.setCurrentIndex(idx)
    app.processEvents()
    w.grab().save(os.path.join(HERE, name))
print('ALL PASS' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
