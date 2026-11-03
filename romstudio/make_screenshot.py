"""Render docs/screenshot.png offscreen: python make_screenshot.py [project.proe.json] [slot]"""
import importlib.util, json, os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_QPA_FONTDIR', r'C:\Windows\Fonts')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from PySide6.QtWidgets import QApplication

spec = importlib.util.spec_from_file_location('studio', os.path.join(HERE, 'romstudio.pyw'))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)
app = QApplication(sys.argv)
w = st.Studio()
w.resize(1320, 780)
if len(sys.argv) > 1:
    d = json.load(open(sys.argv[1], encoding='utf-8'))
    for c in d['cards']:
        if c not in w.card_paths and os.path.exists(c):
            w.add_cards(c)
    w.p.from_dict(d, w.lib)
    for a, i, e in w.os_edits:
        e.setText(getattr(w.p, a)[i])
w.select(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
w.show()
app.processEvents()
out = os.path.join(HERE, '..', 'docs', 'screenshot.png')
os.makedirs(os.path.dirname(out), exist_ok=True)
w.grab().save(out)
print(out)
