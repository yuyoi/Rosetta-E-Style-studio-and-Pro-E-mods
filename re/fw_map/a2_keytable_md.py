import os
"""Emit the markdown button table for A2_hc11_ui.md (code, matrix, test name, meaning, handler, LED)."""
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..') + '/'
ic7 = open(D + 'dumps/proe_ic7_R15179983_LH53234L_v2.00.bin', 'rb').read()
img = open(D + 're/map_bank0.bin', 'rb').read()
b1 = ic7[0x8000:0x10000]
names = [b1[0xB809 - 0x4000 + 5 * i:0xB809 - 0x4000 + 5 * i + 5].decode() for i in range(88)]
M = {'Style': 'STYLE select mode', 'MnlBs': 'MANUAL BASS tone sel.', 'LwrTn': 'LOWER tone sel.', 'SolTn': 'SOLO tone sel.',
 'Midi ': 'MIDI menu', 'Prmtr': 'PARAMETER menu', 'AlR/P': 'ARR.LOOP rec/play', 'AlExe': 'ARR.LOOP execute',
 'Trans': 'TRANSPOSE (tap on/off, hold 640 ms = page)', 'MldyI': 'MELODY INTELLIGENCE', 'Vartn': 'VARIATION', 'AdvAr': 'ADVANCED ARRANGER',
 'ArrHd': 'ARRANGER HOLD', 'RevOF': 'REVERB ON/OFF', 'SynSp': 'SYNC STOP', 'SynSt': 'SYNC START',
 'KMMnD': 'key mode MANUAL DRUMS', 'FllOr': 'FILL-IN to ORIGINAL', 'KMSnE': 'key mode SOUND EFFECTS', 'FllVr': 'FILL-IN to VARIATION',
 'In/En': 'INTRO/ENDING', 'Br/Tp': 'BREAK MUTE / TAP', 'Pl/Dm': 'PLAY / DEMO (hold 640 ms = PLAY SONG)', 'Rc/Pi': 'REC / PUNCH IN',
 'KMSol': 'key mode SOLO', 'GrpAB': 'GROUP A/B', 'KMLow': 'key mode LOWER', 'Write': 'WRITE', 'KMArr': 'key mode ARRANGER',
 'FrCrd': 'FROM CARD menu', 'KMMnB': 'key mode MANUAL BASS', 'ToCrd': 'TO CARD menu', 'Solo+': 'SOLO vol +', 'Solo-': 'SOLO vol -',
 'SnE +': 'SOUND EFFECTS vol +', 'SnE -': 'SOUND EFFECTS vol -', 'FadeO': 'FADE OUT', 'FadeI': 'FADE IN', 'St/Sp': 'START/STOP',
 'SnEHd': 'SOUND EFFECTS HOLD', 'Lwr +': 'LOWER vol +', 'Lwr -': 'LOWER vol -', 'Acc +': 'ACC vol +', 'Acc -': 'ACC vol -',
 'Bss +': 'BASS vol +', 'Bss -': 'BASS vol -', 'Drms+': 'ACC DRUMS vol +', 'Drms-': 'ACC DRUMS vol -', 'PlyTs': '? (PlyTs)',
 'UsrBk': 'USER (program) BANK', 'Cursr': 'CURSOR', 'RevTp': 'REVERB TYPE menu'}
for i in range(1, 9):
    M['User%d' % i] = 'USER PROGRAM %d' % i; M['Bank%d' % i] = 'BANK %d' % i; M['Nmbr%d' % i] = 'NUMBER %d' % i
for c in 'abcdefghijkl': M['SnE ' + c] = 'SFX pad ' + c
print('| code | $245F byte.bit | strobe (PORTA b5-3) | row | test idx | test name | meaning (INFERRED from name/manual) | handler | LED bit |')
print('|---|---|---|---|---|---|---|---|---|')
for code in range(96):
    byte, bit = divmod(code, 8)
    if byte < 8:
        col, src, row = byte, '$1200 D%d' % bit, bit
    else:
        if bit > 5: continue
        col = 2 * (byte - 8) + (0 if bit >= 3 else 1)
        pa = bit - 3 if bit >= 3 else bit
        src, row = 'PA%d' % pa, 8 + pa
    n = col * 11 + row
    e = img[0xF74B + 3 * code - 0x4000:0xF74B + 3 * code - 0x4000 + 3]
    h = '$%02X%02X' % (e[1], e[2])
    led = '$%02X.%d' % (0x0B + byte, bit) if code < 0x30 else '-'
    if 0x28 <= code <= 0x2B: led = '($10.%d = beat LED)' % bit
    print('| $%02X | %d.%d | %d | %s | $%02X | %s | %s | %s | %s |' % (code, byte, bit, col, src, n, names[n].strip(), M.get(names[n], ''), h, led))
