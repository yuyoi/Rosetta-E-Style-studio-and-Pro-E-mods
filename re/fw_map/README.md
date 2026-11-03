# fw_map: deep dives into both PRO-E firmwares

Seven analysis notes written by a multi-agent analysis run (Claude). **The run was stopped before its adversarial
checkers finished, so treat every claim as unverified** until you've checked it against a listing. Several have since
been confirmed on hardware: the MIDI link, the style format, the card format, the bank checksum.

| File | Subsystem |
|---|---|
| A1_hc11_kernel.md | 68HC11 boot, main loop, interrupts, RAM, banking, free space |
| A2_hc11_ui.md + a2_keymap_table.md | panel buttons, LEDs, LCD, menus, hidden power-on modes |
| A3_hc11_midi_and_ck34_link.md | MIDI in/out, SysEx, the serial link to the CK-34 (plain MIDI + MT-32 SysEx) |
| A4_hc11_arranger_styles.md | arranger engine, style format, chord recognition, composer, cards |
| B1_ck34_core_and_monitor.md | 8098 boot, memory/banks, interrupts, the debug monitor |
| B2_ck34_midi_sysex.md | 8098 MIDI parser, MT-32 / D-50 SysEx support |
| B3_ck34_sound_engine.md | wave/loop table, timbres, LA32 registers, reverb control |

The helper scripts read your own dumps from `../../dumps/` and write listings next to themselves. Listings are
derived from Roland code and stay out of git. `ck34_dis.py` uses `mcs96_dis.py` from the D110-rosetta-OS repo:
clone it next to this one or set `D110_ROSETTA_OS`.
