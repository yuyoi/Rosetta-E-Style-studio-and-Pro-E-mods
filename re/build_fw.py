"""Build Rosetta OS images for the Roland PRO-E from the original v2.00 dumps.

Every patch states the original bytes; the build stops if they don't match, so a wrong dump or
a typo can never produce a silently broken image.

Outputs (in ../build/):
  IC7_<ver>_W27C040.bin  256 KB image doubled to 512 KB (A18 = pin 31 can be anything)
  IC4_<ver>_W27C512.bin  16 KB image x4 = 64 KB (A14/A15 = pins 27/1 can be anything)
"""
import hashlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DUMPS = os.path.join(HERE, '..', 'dumps')
BUILD = os.path.join(HERE, '..', 'build')
VERSION = 'v0.1'

IC7_SRC = 'proe_ic7_R15179983_LH53234L_v2.00.bin'
IC4_SRC = 'proe_ic4_os_v2.00_051289_27c128.bin'

# (file offset, original bytes, new bytes, note). IC7 bank 0 sits at $4000-$BFFF, IC4 at $C000.
IC7_PATCHES = [
    (0x19E1, b'  ROLAND PRO-E  INTELL. ARRANGER',
             b' ROSETTA  PRO-E   OS v0.1 2026  ', 'boot banner ($59E1, shown from $C18A)'),
]
IC4_PATCHES = [
    (0x2DA8, b'  ROLAND PRO E  VER 02.00 051289',
             b'ROSETTA OS PRO-EVER 00.10 110226', 'version screen ($EDA8/$EDB8, REVERB ON/OFF at power-on)'),
]


def patch(name, patches):
    img = bytearray(open(os.path.join(DUMPS, name), 'rb').read())
    for off, old, new, note in patches:
        if len(old) != len(new):
            sys.exit(f'{name} @{off:#x}: length changes ({len(old)} -> {len(new)}): {note}')
        if img[off:off + len(old)] != old:
            sys.exit(f'{name} @{off:#x}: original bytes do not match: {note}')
        img[off:off + len(new)] = new
        print(f'  {name} @{off:#06x}: {note}')
    return bytes(img)


def bank_sum_ok(img, bank):
    """IC7 bank header: big-endian word at offset 0 + sum of bytes 2..0x7FFF == 0 mod 65536 (checked by $ECA6, test mode)."""
    b = img[bank * 0x8000:(bank + 1) * 0x8000]
    return ((b[0] << 8 | b[1]) + sum(b[2:])) & 0xFFFF == 0


def fix_bank_sum(img, bank):
    b0 = bank * 0x8000
    w = -sum(img[b0 + 2:b0 + 0x8000]) & 0xFFFF
    img[b0], img[b0 + 1] = w >> 8, w & 0xFF


def write(fname, data):
    os.makedirs(BUILD, exist_ok=True)
    path = os.path.join(BUILD, fname)
    tmp = path + '.tmp'
    open(tmp, 'wb').write(data)
    os.replace(tmp, path)
    print(f'  {fname}  {len(data)} B  md5 {hashlib.md5(data).hexdigest()}')


if __name__ == '__main__':
    print(f'Rosetta OS PRO-E {VERSION}')
    orig7 = bytearray(open(os.path.join(DUMPS, IC7_SRC), 'rb').read())
    assert all(bank_sum_ok(orig7, k) for k in range(8)), 'original IC7 bank sums should all be OK'
    ic7 = bytearray(patch(IC7_SRC, IC7_PATCHES))
    for k in range(8):
        if not bank_sum_ok(ic7, k):
            fix_bank_sum(ic7, k)
            print(f'  IC7 bank {k}: header checksum fixed')
    assert all(bank_sum_ok(ic7, k) for k in range(8))
    ic7 = bytes(ic7)
    ic4 = patch(IC4_SRC, IC4_PATCHES)
    assert len(ic7) == 0x40000 and len(ic4) == 0x4000
    write(f'IC7_{VERSION}_W27C040.bin', ic7 * 2)
    write(f'IC4_{VERSION}_W27C512.bin', ic4 * 4)
