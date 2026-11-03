| code | $245F byte.bit | strobe (PORTA b5-3) | row | test idx | test name | meaning (INFERRED from name/manual) | handler | LED bit |
|---|---|---|---|---|---|---|---|---|
| $00 | 0.0 | 0 | $1200 D0 | $00 | Style | STYLE select mode | $754B | $0B.0 |
| $01 | 0.1 | 0 | $1200 D1 | $01 | MnlBs | MANUAL BASS tone sel. | $755F | $0B.1 |
| $02 | 0.2 | 0 | $1200 D2 | $02 | LwrTn | LOWER tone sel. | $7628 | $0B.2 |
| $03 | 0.3 | 0 | $1200 D3 | $03 | SolTn | SOLO tone sel. | $7658 | $0B.3 |
| $04 | 0.4 | 0 | $1200 D4 | $04 | Midi | MIDI menu | $7178 | $0B.4 |
| $05 | 0.5 | 0 | $1200 D5 | $05 | Prmtr | PARAMETER menu | $7688 | $0B.5 |
| $06 | 0.6 | 0 | $1200 D6 | $06 | AlR/P | ARR.LOOP rec/play | $A34B | $0B.6 |
| $07 | 0.7 | 0 | $1200 D7 | $07 | AlExe | ARR.LOOP execute | $A261 | $0B.7 |
| $08 | 1.0 | 1 | $1200 D0 | $0B | Trans | TRANSPOSE (tap on/off, hold 640 ms = page) | $8EC4 | $0C.0 |
| $09 | 1.1 | 1 | $1200 D1 | $0C | MldyI | MELODY INTELLIGENCE | $FD2B | $0C.1 |
| $0A | 1.2 | 1 | $1200 D2 | $0D | Vartn | VARIATION | $76B5 | $0C.2 |
| $0B | 1.3 | 1 | $1200 D3 | $0E | AdvAr | ADVANCED ARRANGER | $6FF9 | $0C.3 |
| $0C | 1.4 | 1 | $1200 D4 | $0F | ArrHd | ARRANGER HOLD | $7031 | $0C.4 |
| $0D | 1.5 | 1 | $1200 D5 | $10 | RevOF | REVERB ON/OFF | $7142 | $0C.5 |
| $0E | 1.6 | 1 | $1200 D6 | $11 | SynSp | SYNC STOP | $6FA1 | $0C.6 |
| $0F | 1.7 | 1 | $1200 D7 | $12 | SynSt | SYNC START | $6FC8 | $0C.7 |
| $10 | 2.0 | 2 | $1200 D0 | $16 | User1 | USER PROGRAM 1 | $F41A | $0D.0 |
| $11 | 2.1 | 2 | $1200 D1 | $17 | User2 | USER PROGRAM 2 | $F41A | $0D.1 |
| $12 | 2.2 | 2 | $1200 D2 | $18 | User3 | USER PROGRAM 3 | $F41A | $0D.2 |
| $13 | 2.3 | 2 | $1200 D3 | $19 | User4 | USER PROGRAM 4 | $F41A | $0D.3 |
| $14 | 2.4 | 2 | $1200 D4 | $1A | User5 | USER PROGRAM 5 | $F41A | $0D.4 |
| $15 | 2.5 | 2 | $1200 D5 | $1B | User6 | USER PROGRAM 6 | $F41A | $0D.5 |
| $16 | 2.6 | 2 | $1200 D6 | $1C | User7 | USER PROGRAM 7 | $F41A | $0D.6 |
| $17 | 2.7 | 2 | $1200 D7 | $1D | User8 | USER PROGRAM 8 | $F41A | $0D.7 |
| $18 | 3.0 | 3 | $1200 D0 | $21 | KMMnD | key mode MANUAL DRUMS | $76D5 | $0E.0 |
| $19 | 3.1 | 3 | $1200 D1 | $22 | FllOr | FILL-IN to ORIGINAL | $6DA3 | $0E.1 |
| $1A | 3.2 | 3 | $1200 D2 | $23 | KMSnE | key mode SOUND EFFECTS | $76F0 | $0E.2 |
| $1B | 3.3 | 3 | $1200 D3 | $24 | FllVr | FILL-IN to VARIATION | $6E18 | $0E.3 |
| $1C | 3.4 | 3 | $1200 D4 | $25 | In/En | INTRO/ENDING | $6E7A | $0E.4 |
| $1D | 3.5 | 3 | $1200 D5 | $26 | Br/Tp | BREAK MUTE / TAP | $6EE4 | $0E.5 |
| $1E | 3.6 | 3 | $1200 D6 | $27 | Pl/Dm | PLAY / DEMO (hold 640 ms = PLAY SONG) | $FC89 | $0E.6 |
| $1F | 3.7 | 3 | $1200 D7 | $28 | Rc/Pi | REC / PUNCH IN | $FC90 | $0E.7 |
| $20 | 4.0 | 4 | $1200 D0 | $2C | KMSol | key mode SOLO | $7704 | $0F.0 |
| $21 | 4.1 | 4 | $1200 D1 | $2D | GrpAB | GROUP A/B | $FC49 | $0F.1 |
| $22 | 4.2 | 4 | $1200 D2 | $2E | KMLow | key mode LOWER | $FD0B | $0F.2 |
| $23 | 4.3 | 4 | $1200 D3 | $2F | Write | WRITE | $924E | $0F.3 |
| $24 | 4.4 | 4 | $1200 D4 | $30 | KMArr | key mode ARRANGER | $7829 | $0F.4 |
| $25 | 4.5 | 4 | $1200 D5 | $31 | FrCrd | FROM CARD menu | $5712 | $0F.5 |
| $26 | 4.6 | 4 | $1200 D6 | $32 | KMMnB | key mode MANUAL BASS | $782E | $0F.6 |
| $27 | 4.7 | 4 | $1200 D7 | $33 | ToCrd | TO CARD menu | $57E8 | $0F.7 |
| $28 | 5.0 | 5 | $1200 D0 | $37 | Solo+ | SOLO vol + | $7867 | ($10.0 = beat LED) |
| $29 | 5.1 | 5 | $1200 D1 | $38 | Solo- | SOLO vol - | $7867 | ($10.1 = beat LED) |
| $2A | 5.2 | 5 | $1200 D2 | $39 | SnE + | SOUND EFFECTS vol + | $786C | ($10.2 = beat LED) |
| $2B | 5.3 | 5 | $1200 D3 | $3A | SnE - | SOUND EFFECTS vol - | $786C | ($10.3 = beat LED) |
| $2C | 5.4 | 5 | $1200 D4 | $3B | FadeO | FADE OUT | $7871 | $10.4 |
| $2D | 5.5 | 5 | $1200 D5 | $3C | FadeI | FADE IN | $789C | $10.5 |
| $2E | 5.6 | 5 | $1200 D6 | $3D | St/Sp | START/STOP | $78BE | $10.6 |
| $2F | 5.7 | 5 | $1200 D7 | $3E | SnEHd | SOUND EFFECTS HOLD | $70FA | $10.7 |
| $30 | 6.0 | 6 | $1200 D0 | $42 | Lwr + | LOWER vol + | $796F | - |
| $31 | 6.1 | 6 | $1200 D1 | $43 | Lwr - | LOWER vol - | $796F | - |
| $32 | 6.2 | 6 | $1200 D2 | $44 | Acc + | ACC vol + | $7974 | - |
| $33 | 6.3 | 6 | $1200 D3 | $45 | Acc - | ACC vol - | $7974 | - |
| $34 | 6.4 | 6 | $1200 D4 | $46 | Bss + | BASS vol + | $797A | - |
| $35 | 6.5 | 6 | $1200 D5 | $47 | Bss - | BASS vol - | $797A | - |
| $36 | 6.6 | 6 | $1200 D6 | $48 | Drms+ | ACC DRUMS vol + | $7980 | - |
| $37 | 6.7 | 6 | $1200 D7 | $49 | Drms- | ACC DRUMS vol - | $7980 | - |
| $38 | 7.0 | 7 | $1200 D0 | $4D | Bank1 | BANK 1 | $7988 | - |
| $39 | 7.1 | 7 | $1200 D1 | $4E | Bank2 | BANK 2 | $7988 | - |
| $3A | 7.2 | 7 | $1200 D2 | $4F | Bank3 | BANK 3 | $7988 | - |
| $3B | 7.3 | 7 | $1200 D3 | $50 | Bank4 | BANK 4 | $7988 | - |
| $3C | 7.4 | 7 | $1200 D4 | $51 | Bank5 | BANK 5 | $7988 | - |
| $3D | 7.5 | 7 | $1200 D5 | $52 | Bank6 | BANK 6 | $7988 | - |
| $3E | 7.6 | 7 | $1200 D6 | $53 | Bank7 | BANK 7 | $7988 | - |
| $3F | 7.7 | 7 | $1200 D7 | $54 | Bank8 | BANK 8 | $7988 | - |
| $40 | 8.0 | 1 | PA0 | $13 | Nmbr1 | NUMBER 1 | $7988 | - |
| $41 | 8.1 | 1 | PA1 | $14 | Nmbr2 | NUMBER 2 | $7988 | - |
| $42 | 8.2 | 1 | PA2 | $15 | Nmbr3 | NUMBER 3 | $7988 | - |
| $43 | 8.3 | 0 | PA0 | $08 | Nmbr4 | NUMBER 4 | $7988 | - |
| $44 | 8.4 | 0 | PA1 | $09 | Nmbr5 | NUMBER 5 | $7988 | - |
| $45 | 8.5 | 0 | PA2 | $0A | Nmbr6 | NUMBER 6 | $7988 | - |
| $48 | 9.0 | 3 | PA0 | $29 | SnE g | SFX pad g | $7095 | - |
| $49 | 9.1 | 3 | PA1 | $2A | SnE h | SFX pad h | $7095 | - |
| $4A | 9.2 | 3 | PA2 | $2B | SnE i | SFX pad i | $7095 | - |
| $4B | 9.3 | 2 | PA0 | $1E | SnE j | SFX pad j | $7095 | - |
| $4C | 9.4 | 2 | PA1 | $1F | SnE k | SFX pad k | $7095 | - |
| $4D | 9.5 | 2 | PA2 | $20 | SnE l | SFX pad l | $7095 | - |
| $50 | 10.0 | 5 | PA0 | $3F | SnE a | SFX pad a | $7095 | - |
| $51 | 10.1 | 5 | PA1 | $40 | SnE b | SFX pad b | $7095 | - |
| $52 | 10.2 | 5 | PA2 | $41 | SnE c | SFX pad c | $7095 | - |
| $53 | 10.3 | 4 | PA0 | $34 | SnE d | SFX pad d | $7095 | - |
| $54 | 10.4 | 4 | PA1 | $35 | SnE e | SFX pad e | $7095 | - |
| $55 | 10.5 | 4 | PA2 | $36 | SnE f | SFX pad f | $7095 | - |
| $58 | 11.0 | 7 | PA0 | $55 | Nmbr7 | NUMBER 7 | $7988 | - |
| $59 | 11.1 | 7 | PA1 | $56 | Nmbr8 | NUMBER 8 | $7988 | - |
| $5A | 11.2 | 7 | PA2 | $57 | RevTp | REVERB TYPE menu | $7496 | - |
| $5B | 11.3 | 6 | PA0 | $4A | PlyTs | ? (PlyTs) | $7C75 | - |
| $5C | 11.4 | 6 | PA1 | $4B | UsrBk | USER (program) BANK | $F581 | - |
| $5D | 11.5 | 6 | PA2 | $4C | Cursr | CURSOR | $FC2B | - |
