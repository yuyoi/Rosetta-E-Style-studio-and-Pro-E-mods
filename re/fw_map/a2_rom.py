import os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..') + '/'
img = open(D + 're/map_bank0.bin', 'rb').read()
def b(a): return img[a - 0x4000]
def w(a): return (img[a - 0x4000] << 8) | img[a - 0x4000 + 1]
def s(a, n=16): return ''.join(chr(c) if 32 <= c < 127 else '{%02x}' % c for c in img[a - 0x4000:a - 0x4000 + n])
