"""Address-tagged test image: every 4 bytes hold their own address, so any stuck or aliased address line shows up on read-back."""
import sys

size = int(sys.argv[2], 0)
out = bytearray()
for a in range(0, size, 4):
    out += bytes([(a >> 16) & 0xFF, (a >> 8) & 0xFF, a & 0xFF, ((a >> 2) ^ 0xA5) & 0xFF])
open(sys.argv[1], 'wb').write(out)
