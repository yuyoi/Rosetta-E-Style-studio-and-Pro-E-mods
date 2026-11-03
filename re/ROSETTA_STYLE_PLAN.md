# Rosetta Style: plan

Source of truth for the format: re/fw_map/A4_hc11_arranger_styles.md sec. 3 (unverified, but styles.py walks all 2496 pattern pointers, 37 SFX and 5 demo songs cleanly to their end markers).

## Format in one screen
- Directory: 32 records x 197 B at IC7 bank 0 $A701 (+$00 drum bank nibbles, +$03 6 drum ptrs, +$0F ticks/bar, +$10 tempo, then 4 parts (A.BASS, ACC1, ACC2, ACC3) x (9 nibble bytes + 18 ptrs = 6 sections x Major/minor/7th)).
- Sections: BASIC, VARIATION, FILL>ORIG, FILL>VAR, INTRO, ENDING. Names 8 B at bank 0 $63D9.
- Events: byte0 b7 = program change, b6 = 3-byte (long delta), b5-0 = note field ($3D no-op, $3F END); byte1 hi nibble = velocity index ($ED5A table), lo = delta. Written in C. Note offsets: drums +36, bass +24, acc +36.
- Pattern data lives in banks 1-7 (banks 2-7 = pure data). Pointers >= $C000 = IC4 silent bars. Every bank has a header checksum (build_fw.py already fixes it).

## Status 2026-11-03
- **Milestone 1 DONE:** `python -I rosetta_style.py roundtrip` wipes every pattern + record, rebuilds them from JSON, and the result is a byte-identical IC7. That covers 32 styles, 1968 distinct patterns, 101,570 events, 207,373 bytes.
- **Baroque lock tested:** changing one Baroque drum event or its tempo is refused. A ROCK1 tempo edit is accepted.
- A pattern shared between Baroque and another style is protected too. That's intended: such styles get their own copy.
- Records are still stored raw (`record_hex`) except tempo and ticks/bar. Pointer/bank fields get re-derived from `slots` in milestone 2.

## Style source #1: the user's MSL-15 dump (dumps_ext/msl15/CARDS.txt)
16 TN-SC1 cards x 32 KB (header `Roland E-20 ` + card id at +0x10, 8 x 16-byte names at +0x30) = ~68 styles. 5 cards == MAME, 11 unpublished.
**Card layout found:** 8 style records x 197 B at card offset **0xB0**, the same record format as the internal directory (ticks/bar +0x0F, tempo +0x10). Records 4-7 repeat 0-3 (4 styles per card; card 10 has 8). Turkey card: 9/8 = 108 ticks/bar, 5/8 = 60 (24 ppqn), DUEK/ANADOLU 96. Asia: JOGET 48 (2/4). So the import = copy records + patterns, remapping card bank nibbles 8/9 to IC7 banks.
Next: decode the card layout (the OS copies 8 card records to RAM $2729, names to $26A9, bank nibble 8/9 = card) -> import into the JSON -> internal slots, or a RAM card.

## Tool: re/rosetta_style.py
1. **decode**: IC7 -> every style as JSON (records + event lists), and **export** each section/part/chord-class as a Standard MIDI File (C major / C minor / C7) for Cubase.
2. **encode**: JSON -> pattern bytes -> packed into banks 1-7 -> directory records -> bank checksums -> IC7 image (W27C040, doubled).
3. **Milestone 1 = lossless round-trip:** decode the stock ROM -> encode -> **byte-identical IC7**. That proves the format 100% with no burn.
4. **Milestone 2 = import:** a MIDI file per section/part (Cubase, in C) -> replaces one style. Burn, play, compare.
5. Later: names/tempo editing, repacking for more room, RAM-card styles (8 records at RAM $2729, card bank nibble 8).

**HARD RULE (user, 2026-11-03): BAROQUE (style 24, record $B979, data in banks 4+5) is never changed or replaced.** Its record and every byte of its pattern data stay byte-identical at the same addresses, even when repacking. The encoder asserts this on every build and refuses to write an image otherwise. Adding instruments elsewhere is fine; the original Baroque must always be there.

Space: the banks are full, so new styles replace stock ones (32 slots) or come from repacking. Dead data found: bank 6 3 unreferenced patterns, bank 1 $BEEF-$BFFF duplicate.
