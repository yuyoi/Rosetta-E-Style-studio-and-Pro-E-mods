"""Compare a read-back with the expected image and report which address/data bits are wrong."""
import sys

exp = open(sys.argv[1], 'rb').read()
got = open(sys.argv[2], 'rb').read()
bad = [i for i in range(min(len(exp), len(got))) if exp[i] != got[i]]
print('size', len(got), 'mismatches', len(bad))
if bad:
    data_bits = 0
    for i in bad:
        data_bits |= exp[i] ^ got[i]
    print('first bad', [hex(i) for i in bad[:10]], 'data bits wrong', bin(data_bits))
    # aliasing: does a bad byte equal the expected byte at an address with one bit flipped?
    for bit in range(19):
        hits = sum(1 for i in bad[:2000] if got[i] == exp[i ^ (1 << bit)])
        if hits > len(bad[:2000]) // 2:
            print(f'looks like address line A{bit} is stuck/aliased ({hits} hits)')
