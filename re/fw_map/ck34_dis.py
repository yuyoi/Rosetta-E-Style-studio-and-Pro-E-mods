import os
#!/usr/bin/env python3
"""CK-34 (Pro-E voice board) IC28 listing: wraps the D-110 MCS-96 disassembler with the CK-34 memory map.

  python -I ck34_dis.py <ic28.bin> <out.lst>

Differences from the D-110 tool's defaults:
  - bank window 0x8000-0xBFFF = IC28 file 0x8000-0xBFFF (bank latch value 2); the firmware never runs code there
    and never selects pages 0/1 (file 0x0000-0x0FFF is FF fill)
  - I/O names follow MAME mt32.cpp + what the CK-34 code does with them
  - labels found in B1_ck34_core_and_monitor.md are renamed (sub_1cf0 -> ser_putc, ...)
The listing is Roland's code: keep it out of any public repo.
"""
import io, re, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.environ.get('D110_ROSETTA_OS', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', 'D110-rosetta-OS')))
import mcs96_dis as M

M.D110_IO.clear()
M.D110_IO.update({0x0100: 'BANK', 0x0200: 'SYS_OUT', 0x021a: 'SC0_IN/OUT', 0x021c: 'SC1_IN', 0x0280: 'GA_0280',
                  0x0300: 'LCD_DATA', 0x0380: 'LCD_CTRL', 0x0400: 'REV_LATCH_A', 0x0800: 'REV_LATCH_B'})


class CK34(M.D110):
    @property
    def ranges(self):
        return ((0x1000, 0x8000),)

    def off(self, a):
        if 0x1000 <= a < 0xc000: return a        # 0x8000-0xBFFF shown as bank 2 = file 0x8000
        return None


NAMES = {
    'L20ef': 'cold_start', 'L222f': 'warm_start', 'L22c9': 'main_loop', 'L2ae2': 'partial_loop',
    'L529c': 'ui_task', 'L3fe9': 'sysex_entry', 'jtab_2466': 'midi_status_jtab', 'sub_2330': 'midi_dispatch_br',
    'L1820': 'mon_entry', 'L182d': 'mon_loop', 'sub_1920': 'mon_get_hex16', 'sub_192b': 'mon_get_hex8_sum',
    'sub_1931': 'mon_get_hex8', 'sub_193f': 'mon_get_nibble', 'sub_195f': 'put_hex16', 'sub_1967': 'put_hex8',
    'sub_1972': 'put_nibble', 'sub_198b': 'ser_puts', 'L191a': 'mon_sum_err', 'L1957': 'mon_hex_err',
    'sub_1cdb': 'mon_getc_nb', 'sub_1ce3': 'mon_getc', 'sub_1cf0': 'ser_putc', 'sub_1e92': 'ser_init',
    'sub_1994': 'key_init', 'sub_19a8': 'key_get', 'sub_19b7': 'key_wait', 'sub_1b68': 'key_push',
    'sub_1b99': 'lcd_print_at', 'sub_1be8': 'lcd_flush', 'sub_1c0e': 'lcd_cmd', 'sub_1c20': 'lcd_init',
    'sub_1c98': 'midi_get_event', 'sub_2dec': 'la32_init', 'sub_234d': 'parts_reset', 'sub_4f38': 'synth_reset',
    'sub_502a': 'all_reset_defaults', 'sub_535b': 'ui_init', 'sub_7000': 'test_mode', 'sub_22a1': 'version_wait',
    'sub_73e8': 'test_la32_reset', 'sub_7497': 'test_wait_key15', 'sub_5efd': 'demo_song_ptr',
    'sub_3e2b': 'demo_stream_getb', 'sub_5f0c': 'set_bank_r75', 'sub_4cfc': 'reverb_mode_out',
    'sub_4d2f': 'reverb_level_out', 'sub_4d6d': 'reverb_time_out', 'sub_472b': 'sysex_max_for_addr',
    'sub_44b8': 'sysex_area_lookup', 'api_2082': 'api_2082_monitor', 'api_2084': 'api_2084_mon_getc',
    'api_2086': 'api_2086_ser_putc', 'api_2088': 'api_2088_put_hex8', 'api_208a': 'api_208a_lcd_print',
    'api_208c': 'api_208c_lcd_cmd', 'api_208e': 'api_208e_key_get', 'api_2090': 'api_2090_key_wait',
    'api_2092': 'api_2092_key_init', 'api_2094': 'api_2094_get_adc', 'api_2096': 'api_2096_mon_getc_nb',
    'api_2098': 'api_2098_midi_get', 'api_209a': 'api_209a_ser_putc_rd0', 'api_209c': 'api_209c_put_hex8_rd0',
    'api_209e': 'api_209e_ser_init',
}

HEADER = """; IC28 = CK-34 control ROM R15179974, "CK-34 v2.06 89-02-28" (P8098 @ 12 MHz). Built by ck34_dis.py.
; CPU map: 0x0000-0x00FF SFR/regs | 0x0100 BANK | 0x0200 SYS_OUT (bit0 MIDI LED) | 0x021A/0x021C buttons
;          (0x021A also written = output latch) | 0x0280 gate array | 0x0300/0x0380 LCD | 0x0400/0x0800 reverb
;          | 0x0C00-0x0DFF LA32 | 0x1000-0x7FFF IC28 fixed | 0x8000-0xBFFF window (2 = file 0x8000,
;          3 = file 0xC000, 0x11 = SRAM 0x4000-0x7FFF) | 0xC000-0xFFFF SRAM 0x0000-0x3FFF fixed.
; See B1_ck34_core_and_monitor.md for what the named routines do.
"""


def main():
    rom = CK34(open(sys.argv[1], 'rb').read())
    t = M.build(rom)
    buf = io.StringIO()
    M.listing(t, buf)
    txt = buf.getvalue().replace('IC19', 'IC28')
    pat = re.compile(r'\b(' + '|'.join(sorted(map(re.escape, NAMES), key=len, reverse=True)) + r')\b')
    txt = pat.sub(lambda m: NAMES[m.group(1)], txt)
    with open(sys.argv[2], 'w', newline='\n') as f:
        f.write(HEADER + txt)


if __name__ == '__main__':
    main()
