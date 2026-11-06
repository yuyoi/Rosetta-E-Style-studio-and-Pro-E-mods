"""CK-34 (IC28) patch: LIVE CUTOFF + LIVE RESONANCE. Changes reach the notes you are already holding.

  python -I build_ck34_live.py [IC28_base.bin]   -> ../build/IC28_live_W27C512.bin   (base: the stock IC28 dump)

Stock: the TVF base cutoff of a synth partial (LA32 0x0C41 + 2p) is computed once, at partial start (sub_3416,
0x36AC-0x3735), from the timbre-temp params the partial points at (0xEE80[2p]), its key and its pitch. SysEx edits change
the timbre temp but nothing recomputes the cutoff, so only the next note hears them.

Patch: the idle partial service (L2AE2, one partial per main-loop pass, r40 = 2p, r56 and the bank already set) gets an
lcall at 0x2B0F into LIVECUT (free ROM 0x6100). For a sounding synth partial it runs Roland's own cutoff code again,
copied byte for byte from 0x36AC-0x372F with the index register changed from r54 to r40, and writes 0x0C41 only when
the value changed (shadow 0xF1C0[2p]). Then it does the replaced instruction (ldb r76, 0xF040[r40]) and returns.
PCM partials have no TVF in the LA32, so they are skipped. Every partial is refreshed within 32 main-loop passes.
Glide: each visit moves the LA32 value half way to the target, so a dial step sweeps instead of clicking.
Mod wheel: the part's mod wheel (0xF287[part], 0-127, the value the LFO already uses) is added to the target, clamped
at 255: the lever opens the filter on held notes, Juno style. Wheel at 0 = the tone's own cutoff.
Resonance: recomputed like sub_3416 0x357D-0x3594 (0x18[r56]), shadow 0xEF81[2p], written as 0x0D00 then 0x0D01
(stock order) only when it changed; bit 7 of the shadow is kept.
"""
import hashlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
DUMPS = os.path.join(HERE, '..', 'dumps')
BUILD = os.path.join(HERE, '..', 'build')
HOOK, LIVECUT = 0x2B0F, 0x6100
SPAN = (0x36AC, 0x3730)                      # cutoff computation, ends where stock stores r70 to 0xF1C0 / 0x0C41


def rel16(frm_next, to):
    d = (to - frm_next) & 0xFFFF
    return bytes([d & 0xFF, d >> 8])


def build(base=None):
    rom = bytearray(open(base or os.path.join(DUMPS, 'ck34_ic28_control_R15179974_CK-34_v2.06.bin'), 'rb').read())
    assert len(rom) == 0x10000
    old_hook = bytes.fromhex('b34140f076')           # ldb r76, 0xf040[r40]
    assert bytes(rom[HOOK:HOOK + 5]) == old_hook, 'hook site is not stock: %s' % rom[HOOK:HOOK + 5].hex()
    span = bytearray(rom[SPAN[0]:SPAN[1]])
    assert span.hex().startswith('af561976b377f81670'), 'cutoff code is not stock'
    # the one indexed access to a per-partial table inside the span: ld r74, 0xef40[r54] -> [r40]
    i = span.find(bytes.fromhex('a35540ef74'))
    assert i >= 0 and span.count(bytes.fromhex('a35540ef74')) == 1
    span[i + 1] = 0x41

    sys.path.insert(0, os.path.join(HERE, '..', 'ref_tools'))
    from mcs96_asm import Asm
    a = Asm(LIVECUT, {})
    a.src('''
            ldb   r70, 0xef80[r40]      ; PCM partial: no TVF in the LA32
            jbs!  r70, 7, lc_x
            ldb   r74, 0x18[r56]        ; LIVE RESONANCE: Roland's 0x357D-0x358C, r = res + 1
            incb  r74
            ldb   r75, r74
            shlb  r75, #3
            andb  r75, #0xe0
            orb   r74, r75
            ldb   r75, 0xef81[r40]      ; keep bit 7 of what the partial has
            andb  r75, #0x80
            orb   r74, r75
            cmpb  r74, 0xef81[r40]
            je    lc_c
            stb   r74, 0xef81[r40]
            ldb   r75, 0xef80[r40]      ; stock order: control byte, then resonance
            stb   r75, 0x0d00[r40]
            stb   r74, 0x0d01[r40]
    lc_c:   ldbze r76, 0xee01[r40]      ; LIVE CUTOFF: the partial's poly
            ldb   r47, 0xf400[r76]      ; its key
    ''' + ''.join('        db %d\n' % b for b in span) + '''
            ldbze r78, r70              ; r70 = Roland's cutoff for the tone as it is NOW
            ldbze r76, 0xf287[r50]      ; + this part's mod wheel (0-127): the lever opens the filter
            add   r78, r76
            cmp   r78, #0x00ff
            jle   lc_t
            ld    r78, #0x00ff
    lc_t:   ldbze r72, 0xf1c0[r40]      ; what the LA32 has
            ld    r74, r78
            sub   r74, r72
            je    lc_x                  ; already there
            shra  r74, #1               ; glide: half way per visit (a dial step = a short sweep, not a click)
            jne   lc_st
            ld    r72, r78              ; one step left: land on it
            sjmp  lc_wr
    lc_st:  add   r72, r74
    lc_wr:  stb   r72, 0xf1c0[r40]
            stb   r72, 0x0c41[r40]      ; LA32 base cutoff, live
    lc_x:   ldb   r76, 0xf040[r40]      ; the instruction the hook replaced
            ret
    ''')
    code = bytes(a.assemble())
    lc_x = a.labels['lc_x'] - LIVECUT
    assert all(x == 0xFF for x in rom[LIVECUT:LIVECUT + len(code)]), 'LIVECUT area is not free'
    rom[LIVECUT:LIVECUT + len(code)] = code
    rom[HOOK:HOOK + 5] = b'\xef' + rel16(HOOK + 3, LIVECUT) + b'\xfd\xfd'   # lcall LIVECUT ; nop ; nop
    return bytes(rom), bytes(code), lc_x


if __name__ == '__main__':
    out, code, lc_x = build(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.path.insert(0, os.path.join(HERE, '..', 'ref_tools'))
    try:
        from mcs96_dis import decode, fmt_ins
        a = LIVECUT
        while a < LIVECUT + len(code):
            ins = decode(lambda x: out[x], a)
            print('  ' + fmt_ins(ins))
            a += ins.n
        print('  hook: ' + fmt_ins(decode(lambda x: out[x], HOOK)))
    except Exception as e:
        print('  (disassembly skipped: %s)' % e)
    p = os.path.join(BUILD, 'IC28_live_W27C512.bin')
    open(p + '.tmp', 'wb').write(out)
    os.replace(p + '.tmp', p)
    print('LIVECUT %d bytes at $%04X, hook at $%04X. IC28_live_W27C512.bin md5 %s' %
          (len(code), LIVECUT, HOOK, hashlib.md5(out).hexdigest()))
