"""Rosetta firmware patcher: your own PRO-E dumps -> every chip image, in one go.

  IC7 + IC4   styles (ROM Studio project) + Rosetta OS (SYNTH EDIT, JUNO, ROSETTA FX pages, USER PROGRAM tones,
              bender modes, MIDI remote: re/build_v07.py). Needs the pin-31 mod for the OS.
  IC28        CK-34 v8.1: live filter, PWM LFO, moving Juno chorus, 8 FX modes, wet-only routing (re/build_ck34_lab.py),
              on top of the sample wave table when the SAMPLES tab has sounds.
  IC13        ROSETTA FX for the Boss reverb chip (re/gen_fx.py).
  IC37 / IC38 your long samples (proe_samples.py).
Nothing here holds Roland data: every image is made from the dumps in ../dumps at build time.
"""
import hashlib, io, os, sys, tempfile, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
RE = os.path.join(ROOT, 're')
for p in (RE, os.path.join(ROOT, 'ref_tools')):
    if p not in sys.path:
        sys.path.insert(0, p)
DUMPS = os.path.join(ROOT, 'dumps')
STOCK = {
    'IC4': ('proe_ic4_os_v2.00_051289_27c128.bin', '600D50B26B8AF8C05280AF3550D71491064E6551'),
    'IC7': ('proe_ic7_R15179983_LH53234L_v2.00.bin', 'DBF467CF0ADBC3B5DBF2471B092D6CF2D07043FD'),
    'IC13': ('ck34_ic13_reverb_R15179917_HN623257.bin', 'E1C03905C46E962D1DEB15EEED92EB61B42BBA4A'),
    'IC28': ('ck34_ic28_control_R15179974_CK-34_v2.06.bin', 'D80449D4E241B5A5665C31A39D839D17592B411F'),
    'IC37': ('ck34_ic37_wave_R15449121_TC534000P.bin', 'F6B1EEBC4B2D200EC6D3D21D51325D5B48C60252'),
    'IC38': ('ck34_ic38_wave_R15179945_HN62304.bin', '3AD889FDE5DB5B6437CBC2EB6E305312FEC3DF93'),
}
SIZES = {'IC4': 0x4000, 'IC7': 0x40000, 'IC13': 0x8000, 'IC28': 0x10000, 'IC37': 0x80000, 'IC38': 0x80000}
# burn target per chip: minipro device, chip ID, what it does
CHIPS = {
    'IC7': ('W27C040', 0xDA86, 'styles + Rosetta OS'),
    'IC4': ('W27C512@DIP28', 0xDA08, 'OS kernel + version text'),
    'IC28': ('W27C512@DIP28', 0xDA08, 'CK-34 voice board firmware + wave table'),
    'IC13': ('W27C512@DIP28', 0xDA08, 'ROSETTA FX (Boss reverb chip)'),
    'IC37': ('W27C040', 0xDA86, 'wave ROM, lower 512 KB'),
    'IC38': ('W27C040', 0xDA86, 'wave ROM, upper 512 KB'),
}
VERSIONS = {'os': 'Rosetta OS v0.14', 'ck34': 'CK-34 v8.1', 'fx': 'ROSETTA FX v8.2c'}


def sha1(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest().upper()


def check_dumps():
    """{chip: (path or None, 'ok' | 'missing' | 'different')}: is each stock dump in ../dumps and is it v2.00?"""
    out = {}
    for chip, (name, want) in STOCK.items():
        p = os.path.join(DUMPS, name)
        out[chip] = (p, 'ok' if sha1(p) == want else 'different') if os.path.exists(p) else (None, 'missing')
    return out


def import_dump(path):
    """copy any file whose SHA-1 is a known PRO-E v2.00 chip into ../dumps under its standard name. -> chip or None"""
    h = sha1(path)
    for chip, (name, want) in STOCK.items():
        if h == want:
            os.makedirs(DUMPS, exist_ok=True)
            dst = os.path.join(DUMPS, name)
            if os.path.abspath(dst) != os.path.abspath(path):
                open(dst, 'wb').write(open(path, 'rb').read())
            return chip
    return None


@contextlib.contextmanager
def _quiet(log):
    """the build scripts print as they go: pass their lines to the log"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            yield
        except SystemExit as e:              # their stock-byte checks sys.exit() with the reason
            raise RuntimeError(str(e)) from None
    for line in buf.getvalue().splitlines():
        if line.strip():
            log('    ' + line)


def build(project, out, os_on=True, ck34_on=True, fx_on=True, samples=None, banner=None, version=None, log=print):
    """-> {chip: (path, md5)} for every chip this build changes. samples = proe_samples files {IC37, IC38, IC28} or None."""
    os.makedirs(out, exist_ok=True)
    imgs = {}
    project.reserve = os_on
    ic7, ic4, rep = project.build()
    for r in rep:
        log('  ' + r)
    if os_on:
        import build_v07 as B7
        with tempfile.TemporaryDirectory() as t:
            p7, p4 = os.path.join(t, 'ic7.bin'), os.path.join(t, 'ic4.bin')
            open(p7, 'wb').write(ic7)
            open(p4, 'wb').write(ic4)
            with _quiet(lambda s: None):
                img7, img4, *_ = B7.build(p7, p4, banner, version)
        imgs['IC7'], imgs['IC4'] = img7, img4
        log('  IC7 + IC4: %s on top of the styles' % VERSIONS['os'])
    else:
        imgs['IC7'], imgs['IC4'] = ic7 * 2, ic4 * 4
    base28 = samples['IC28'] if samples else os.path.join(DUMPS, STOCK['IC28'][0])
    if ck34_on:
        import build_ck34_lab as LAB
        with _quiet(lambda s: None):
            rom, *_ = LAB.build(base28)
        imgs['IC28'] = rom
        log('  IC28: %s%s' % (VERSIONS['ck34'], ' + your sample table' if samples else ''))
    elif samples:
        imgs['IC28'] = open(base28, 'rb').read()
        log('  IC28: stock firmware + your sample table')
    if fx_on:
        import gen_fx as FX
        stock = open(os.path.join(DUMPS, STOCK['IC13'][0]), 'rb').read()
        with _quiet(lambda s: None):
            rom = FX.build(stock)
        imgs['IC13'] = rom + rom              # W27C512: A15 (27C256 pin 1) is a don't-care
        log('  IC13: %s' % VERSIONS['fx'])
    if samples:
        imgs['IC37'] = open(samples['IC37'], 'rb').read()
        imgs['IC38'] = open(samples['IC38'], 'rb').read()
    res = {}
    for chip, data in imgs.items():
        dev = CHIPS[chip][0].split('@')[0]
        p = os.path.join(out, '%s_rosetta_%s.bin' % (chip, dev))
        open(p + '.tmp', 'wb').write(data)
        os.replace(p + '.tmp', p)
        res[chip] = (p, hashlib.md5(data).hexdigest())
    return res
