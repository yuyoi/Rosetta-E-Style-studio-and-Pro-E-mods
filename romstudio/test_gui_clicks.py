"""Scripted-click test of the GUI (offscreen): rebuild v0.2 by clicking, compare with the burned image."""
import hashlib, os, sys, time
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import importlib.util
spec = importlib.util.spec_from_file_location('studio', os.path.join(os.path.dirname(__file__), 'romstudio.pyw'))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

app = QApplication(sys.argv)
w = st.Studio()
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name)


tree = w.tree
tops = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
msl = [t for t in tops if 'msl15' in t.text(0)]
check('library: stock + 16 MSL-15 cards', len(msl) == 16 and tops[0].text(0).startswith('Her stock'))
turkey, asia = msl[15], msl[14]
check('last card is Turkey', turkey.child(0).text(0) == 'DUEK')

for i, card in enumerate([turkey] * 4 + [asia] * 4):
    w.slot_btns[16 + i].click()
    tree.setCurrentItem(card.child(i % 4))
    w.b_put.click()
check('slot 16 shows DUEK', 'DUEK' in w.slot_btns[16].text())
w.slot_btns[16].click()
check('LCD shows DUEK', 'DUEK' in w.lcd.text())

w.slot_btns[24].click()
check('Baroque editors disabled', not w.e_name.isEnabled() and not w.b_put.isEnabled())
tree.setCurrentItem(turkey.child(0))
w.on_lib_pick(turkey.child(0))
check('Baroque refused a style', 'BAROQUE' in w.slot_btns[24].text())

for a, i, e in w.os_edits:
    if a == 'banner':
        e.setText([' ROSETTA  PRO-E ', '  OS v0.2 2026  '][i])
w.b_build.click()
t0 = time.time()
while w.worker.isRunning() and time.time() - t0 < 240:
    app.processEvents()
    time.sleep(0.05)
app.processEvents()
ic7 = w.last['IC7_studio_W27C040.bin'][0]
v02 = os.path.join(st.pr.ROOT, 'build', 'IC7_v0.2_W27C040.bin')
check('clicked build == burned v0.2 IC7', open(ic7, 'rb').read() == open(v02, 'rb').read())
w.grab().save(os.path.join(os.path.dirname(__file__), 'screenshot.png'))
print('ALL PASS' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
