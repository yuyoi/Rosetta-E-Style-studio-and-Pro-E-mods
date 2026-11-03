# MSL-15 "Music Style Super Card"

The MSL-15 holds **16 TN-SC1 cards** (16 × 32 KB in one 512 KB ROM) but only has buttons **01-14 + EXT CARD**.
The last two cards were never selectable:

- **card 15 (Asia):** KRONCONG, LGM'ASLI, DANGDUT, JOGET
- **card 16 (Turkey):** DUEK (düyek), ANADOLU, 9/8, 5/8, with real 9/8 (108-tick) and 5/8 (60-tick) bars

Both carry the card id `TN-SC1-01`. 5 of the 16 cards match MAME byte for byte (02, 03, 05, 06, 07). The other 11
are not in MAME as of 2026-11. `CARDS.txt` has the SHA-1 of every card. Put your own dump here as `msl15_read2.bin`
(or load any card file from the app), and `split_cards.py` writes one file per card.
