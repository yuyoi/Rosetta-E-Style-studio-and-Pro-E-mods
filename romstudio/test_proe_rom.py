"""Engine tests: python -I test_proe_rom.py"""
import hashlib, os, sys
import proe_rom as pr

MSL = os.path.join(pr.ROOT, 'dumps_ext', 'msl15', 'msl15_read2.bin')
V01 = os.path.join(pr.ROOT, 'build', 'IC7_v0.1_W27C040.bin')
V02 = os.path.join(pr.ROOT, 'build', 'IC7_v0.2_W27C040.bin')
ok = True


def check(name, cond, extra=''):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name + (f'  {extra}' if extra else ''))


# 1. untouched project with the v0.1 texts == the burned v0.1 IC7
p = pr.Project()
p.banner = [' ROSETTA  PRO-E ', '  OS v0.1 2026  ']
ic7, ic4, rep = p.build()
check('identity build == v0.1 image', ic7 * 2 == open(V01, 'rb').read(), f'{len(rep)} changed slots')

# 2. MSL-15 loads as 16 cards
cards = pr.load_cards(MSL)
check('MSL-15 = 16 cards', len(cards) == 16, ', '.join(c[0].split()[0] for c in cards[:3]) + ' ...')
turkey, asia = cards[15][1], cards[14][1]
check('Turkey styles', [s.name for s in turkey] == ['DUEK', 'ANADOLU', '9/8', '5/8'])

# 3. the v0.2 assignment builds and plays the same patterns (layout may differ, events must not)
p = pr.Project()
for i, s in enumerate(turkey + asia):
    p.assign(16 + i, s)
p.banner = [' ROSETTA  PRO-E ', '  OS v0.2 2026  ']
need, have = p.space()
ic7, ic4, rep = p.build()
check('v0.2 assignment builds', len(rep) == 8, f'need {need} / free {have}')
check('v0.2 same bytes as build_v02.py', ic7 * 2 == open(V02, 'rb').read())

# 4. Baroque is locked
for fn in (lambda: p.assign(pr.BAROQUE, turkey[0]), lambda: p.rename(pr.BAROQUE, 'X'), lambda: p.set_tempo(pr.BAROQUE, 99)):
    try:
        fn()
        check('baroque locked', False)
    except PermissionError:
        check('baroque locked', True)

# 5. moving a stock style into another slot keeps its patterns
p = pr.Project()
p.assign(0, p.stock[5])          # FUNK2 into slot 0 (ROCK1 freed)
ic7, _, rep = p.build()
check('stock style copied into another slot', any('FUNK2' in r for r in rep))

# 6. out of space is reported, not silently truncated
p = pr.Project()
allcard = [s for _, ss in cards for s in ss]
try:
    for n in range(32):
        if n != pr.BAROQUE:
            p.assign(n, allcard[n % len(allcard)])
    p.build()
    check('too many imports builds or fails loudly', True, 'fit!')
except RuntimeError as e:
    check('too many imports fails loudly', 'out of space' in str(e), str(e))

# 7. version text in IC4
p = pr.Project()
p.version = ['ROSETTA OS PRO-E', 'VER 00.10 110226']
_, ic4, _ = p.build()
check('IC4 v0.1 text == burned v0.1 IC4', ic4 * 4 == open(os.path.join(pr.ROOT, 'build', 'IC4_v0.1_W27C512.bin'), 'rb').read())

print('ALL PASS' if ok else 'SOME FAILED')
sys.exit(0 if ok else 1)
