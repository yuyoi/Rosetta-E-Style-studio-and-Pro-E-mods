"""CK-34 (IC28) LAB build: LONG2 wave table + live filter (build_ck34_live) + FX unlocks + moving JUNO CHORUS.

  python -I build_ck34_lab.py [IC28_base.bin]   -> ../build/fx/IC28_lab_W27C512.bin
  (base default: build/waves_long2/IC28_R15179974_patched.bin = the LONG2 table, the waves she has now)

1. WET ONLY. The partial control byte (LA32 0x0D00) gets its routing bits from 0x39C2[reverb switch]: 0 = 0x98, 1 = 0x90
   (bit 7 = add the part's pan, bit 4 = ?, bit 3 = 1 no effect send). Only 0 and 1 are ever used. Theory: bit 4 = dry
   bus. New entries: 2 = 0x80 (pan, bit 4 clear, send on = WET ONLY?), 3 = 0x88 (bit 4 clear, no send = silent?).
   Patch reverb-switch max 1 -> 7 (0x4849), so SysEx 03 00 x6 can pick them per part.
2. 8 MODES. System reverb-mode max 3 -> 7 (0x485D). Mode bits 1-3 go to latch 0x021A bits 1-3 (sub_4CFC), so mode 4-7
   may switch IC13 A14 (its upper 16 KB). The IC13 FX image puts test effects there.
3. MOVING CHORUS. The idle loop's turn-around (0x2AEB ljmp 0x529C) goes through STEPPER first: in reverb mode 1
   (CHORUS) or 4 (FLANGER) with time/level not both 0, every >= 1 ms (Timer1, 2 us) a 16-bit triangle LFO moves the chorus position:
   rate = TIME (0.25-6 Hz), depth = LEVEL. Position p -> 0x0400 bits 0-3 + 0x0800 bits 0-1 (= time + level as
   sub_4D6D / sub_4D2F write them), shadows 0xF4A3 / 0xF4A2. Leaving chorus mode restores the stock latches.
   v4: the panel's JUNO CHORUS (mode 1) plays chorus B: the stepper sets mode bits 1-3 to 3 (IC13 modes 6/7) and
   steps mode bit 0 as the third row bit; leaving gives the stock mode back (sub_4CFC). IC13 mode 1 (v4 chorus) is then
   only a fallback.
   v2: snake order (odd 16-rows get bits 0-3 inverted) so each step changes ONE latch: the two writes left the chip
   on position 0 / 31 for an instant at every row crossing = the clicks heard on her (gen_chorus.snake, IC13 v2).
   RAM 0xDF00-0xDF05 (0xC000-0xDFFF is unused, fw_map B1).
"""
import hashlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'ref_tools'))
import build_ck34_live as LIVE

BUILD = os.path.join(HERE, '..', 'build')
TURN, IDLE, STEPPER = 0x2AEB, 0x529C, 0x6300
ROUTE, PATCH_REV_MAX, SYS_MODE_MAX = 0x39C2, 0x4849, 0x485D
CH_LAST, CH_PHASE, CH_POS, CH_MODE, CH_BIG = 0xDF00, 0xDF02, 0xDF04, 0xDF06, 0xDF07
CHORUS_B = 6                                                # v3: modes 6 + 7 = JUNO CHORUS B, 128 positions
CHORUS_MODE, FLANGER_MODE = 1, 4
RATES_HZ = [0.25, 0.4, 0.51, 0.7, 0.86, 1.5, 3.0, 6.0]      # TIME 0-7 (2 = Juno Chorus I, 4 = Chorus II)
SPAN = [0, 8, 16, 24, 32, 44, 54, 62]                       # LEVEL 0-7, in chorus positions (1-63)
SPAN2 = [0, 24, 48, 80, 124, 124, 124, 124]                # chorus B: LEVEL 4-7 = the full Juno sweep (1.7-5.3 ms, 0.513 / 0.863 Hz). v4 had half


def rate_word(f):
    """phase += high word of (elapsed_2us * rate): rate = 65536 * f * 2e-6 * 65536"""
    return round(65536 * f * 2e-6 * 65536)


def build(base=None):
    if base is None:                                    # the LONG2 wave build if you have one, else your stock IC28 dump
        long2 = os.path.join(BUILD, 'waves_long2', 'IC28_R15179974_patched.bin')
        base = long2 if os.path.exists(long2) else None
    rom, _, _ = LIVE.build(base)
    rom = bytearray(rom)
    assert rom[ROUTE:ROUTE + 8] == bytes.fromhex('9890181f070f0008'), 'routing table not stock'
    rom[ROUTE + 2], rom[ROUTE + 3] = 0x80, 0x88
    assert rom[PATCH_REV_MAX] == 1 and rom[SYS_MODE_MAX] == 3
    rom[PATCH_REV_MAX], rom[SYS_MODE_MAX] = 7, 7
    assert rom[TURN] == 0xE7 and (TURN + 3 + int.from_bytes(rom[TURN + 1:TURN + 3], 'little')) & 0xFFFF == IDLE

    from mcs96_asm import Asm
    syms = dict(CH_LAST=CH_LAST, CH_PHASE=CH_PHASE, CH_POS=CH_POS, CH_MODE=CH_MODE, CH_BIG=CH_BIG, IDLE=IDLE,
                CHORUS_MODE=CHORUS_MODE,
                FLANGER_MODE=FLANGER_MODE, CHORUS_B=CHORUS_B)
    a = Asm(STEPPER, syms)
    a.src('''
    STEP:   ldb   r70, 0xed95           ; reverb mode
            stb   r70, CH_MODE
            cmpb  r70, #CHORUS_MODE       ; v4: the panel's JUNO CHORUS (mode 1) plays chorus B (IC13 modes 6 + 7)
            je    st_big
            cmpb  r70, #FLANGER_MODE      ; mode 4 sweeps 64 positions (IC13 mode 4)
            je    st_64
            andb  r71, r70, #0xfe
            cmpb  r71, #CHORUS_B          ; modes 6 + 7: chorus B, 128 positions
            je    st_big
            ldb   r70, CH_POS           ; not chorus: if we moved the latches, give them back once
            cmpb  r70, #0xff
            je!   st_x
            ldb   r70, #0xff
            stb   r70, CH_POS
            lcall 0x4cfc                ; stock: mode -> 0x021A + 0x0800 bit 2 (chorus B moved it)
            lcall 0x4d6d                ; stock: time -> 0x0400
            lcall 0x4d2f                ; stock: level -> 0x0800 / 0x0400
            sjmp  st_x
    st_64:  clrb  r71
            sjmp  st_fl
    st_big: ldb   r71, #1
    st_fl:  stb   r71, CH_BIG
    st_on:  ldbze r72, 0xed96           ; TIME = rate
            ldbze r74, 0xed97           ; LEVEL = depth
            ld    r76, r72
            or    r76, r74
            je!   st_x                  ; REVERB OFF: the stock latches (position 0, silent) stay
            ld    r76, timer1
            sub   r78, r76, CH_LAST
            cmp   r78, #500             ; >= 1 ms since the last step
            jnc!  st_x
            st    r76, CH_LAST
            add   r72, r72
            ld    r70, ratetab[r72]
            mulu  r70, r78              ; r70:r72 = rate * elapsed, phase += high word
            ld    r78, CH_PHASE
            add   r78, r72
            st    r78, CH_PHASE
            jbc   r79, 7, st_t          ; triangle: 0..0x7FFF up, then down
            not   r78
    st_t:   shl   r78, #1               ; 0..0xFFFE
            ldb   r70, CH_BIG
            cmpb  r70, #0
            jne   st_b                  ; chorus B: the 128-position tables
            ldbze r70, spantab[r74]
            mulu  r70, r78              ; r72 = span * tri >> 16
            ldbze r76, basetab[r74]
            sjmp  st_p
    st_b:   ldbze r70, spantab2[r74]
            mulu  r70, r78
            ldbze r76, basetab2[r74]
    st_p:   add   r76, r72              ; p = base + span * tri
            cmpb  r76, CH_POS
            je!   st_x
            stb   r76, CH_POS
            di
            ldb   r70, 0xed95           ; the mode changed under us (SysEx in an interrupt): leave it to the stock code
            cmpb  r70, CH_MODE
            jne   st_ei
            ldb   r70, 0xf4a3           ; 0x0400 bits 0-3 = p bits 0-3 (time + level bit 0)
            andb  r70, #0xf0
            andb  r71, r76, #0x0f
            jbc   r76, 4, st_e          ; odd rows run backwards (snake): one latch changes per step
            xorb  r71, #0x0f
    st_e:   orb   r70, r71
            stb   r70, 0xf4a3
            stb   r70, 0x0400
            ldb   r70, 0xf4a2           ; 0x0800 bits 0-1 = p bits 4-5 (level bits 1-2), chorus B also bit 2 = p bit 6
            ldb   r71, r76
            shrb  r71, #4
            ldb   r72, CH_BIG
            cmpb  r72, #0
            jne   st_8b
            andb  r70, #0xfc
            andb  r71, #0x03
            sjmp  st_8w
    st_8b:  andb  r70, #0xf8            ; mode bit 0 = row bit 2: mode 6 <-> 7 in the same single write
            andb  r71, #0x07
    st_8w:  orb   r70, r71
            stb   r70, 0xf4a2
            stb   r70, 0x0800
            ldb   r72, CH_BIG
            cmpb  r72, #0
            je    st_ei
            andb  r73, rc8, #0x0e       ; chorus B lives in IC13 modes 6/7: mode bits 1-3 = 3 (asked for mode 1 too)
            cmpb  r73, #0x06
            je    st_ei
            andb  rc8, #0xf1
            orb   rc8, #0x06
            stb   rc8, 0x021a
    st_ei:  ei
    st_x:   ljmp  IDLE
            even
    ratetab:
    ''' + ''.join('        dw %d\n' % rate_word(f) for f in RATES_HZ) + '''
    spantab:
    ''' + ''.join('        db %d\n' % s for s in SPAN) + '''
    basetab:
    ''' + ''.join('        db %d\n' % (32 - s // 2) for s in SPAN) + '''
    spantab2:
    ''' + ''.join('        db %d\n' % s for s in SPAN2) + '''
    basetab2:
    ''' + ''.join('        db %d\n' % (64 - s // 2) for s in SPAN2))
    code = bytes(a.assemble())
    assert all(x == 0xFF for x in rom[STEPPER:STEPPER + len(code)]), 'STEPPER area not free'
    rom[STEPPER:STEPPER + len(code)] = code
    d = (STEPPER - (TURN + 3)) & 0xFFFF
    rom[TURN + 1:TURN + 3] = d.to_bytes(2, 'little')
    return bytes(rom), code, a


if __name__ == '__main__':
    rom, code, a = build(sys.argv[1] if len(sys.argv) > 1 else None)
    out = os.path.join(BUILD, 'fx')
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, 'IC28_lab_W27C512.bin')
    open(p + '.tmp', 'wb').write(rom); os.replace(p + '.tmp', p)
    print('STEPPER %d bytes at $%04X. IC28_lab_W27C512.bin md5 %s' % (len(code), STEPPER, hashlib.md5(rom).hexdigest()))
