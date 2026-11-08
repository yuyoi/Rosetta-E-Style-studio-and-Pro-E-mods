; ---------------- v0.7: ROSETTA FX pages + remote control ----------------
; Lives in its own segment (upper half bank 5 $6800, free in the lower half too), called from the v0.6 engine.

; ---- FX: the CK-34 reverb chip runs the IC13 program set by system params 10 00 01 = mode, time, level.
; Every FX page edits one mode; its two dials are fields packed into (time, level), kept per mode in FXT / FXL:
;   F_T = time 0-7, F_L = level 0-7, F_K = level*2 + time>>2 (0-15, the IC13 program), F_S = time & 3 (sawBits).
; Any edit sends 10 00 01 mode time level: the effect becomes the one she plays.
F_T      = 0
F_L      = 1
F_K      = 2

; A = value of the FX item IT (X = IT)
fxget:  ldaa IT_OFF,x
        staa FXF
        ldab IT_AUX,x
        ldx #FXT
        abx
        ldaa 8,x                ; FXL = FXT + 8
        staa FXLV
        ldaa 0,x
        ldab FXF
        cmpb #F_T
        beq fg_x
        cmpb #F_L
        beq fg_l
        cmpb #F_K
        beq fg_k
        anda #3                 ; F_S
fg_x:   rts
fg_l:   ldaa FXLV
        rts
fg_k:   lsra
        lsra
        anda #1
        adda FXLV
        adda FXLV
        rts

fxchg:  jsr getval
        psha
        ldx IT
        ldab IT_MAX,x
        stab MAXV
        ldab IT_AUX,x
        stab FXM
        pulb
        jsr addclamp
        stab NEWV
        ldx #FXT
        ldab FXM
        abx
        ldab FXF
        cmpb #F_T
        beq fc_t
        cmpb #F_L
        beq fc_l
        cmpb #F_K
        beq fc_k
        ldaa 0,x                ; F_S: time = (time & 4) | new
        anda #4
        oraa NEWV
        staa 0,x
        bra fxsend
fc_t:   ldaa NEWV
        staa 0,x
        bra fxsend
fc_l:   ldaa NEWV
        staa 8,x
        bra fxsend
fc_k:   ldaa NEWV               ; level = new >> 1, time bit 2 = new & 1
        lsra
        staa 8,x
        ldaa NEWV
        anda #1
        asla
        asla
        staa TMP
        ldaa 0,x
        anda #3
        oraa TMP
        staa 0,x
; X = this mode's FXT entry: DT1 10 00 01 mode time level
fxsend: ldaa 0,x
        staa TXB+4
        ldaa 8,x
        staa TXB+5
        ldaa FXM
        staa TXB+3
        ldd #$1000
        std TXB
        ldaa #$01
        staa TXB+2
        ldaa #6
        jmp dtn

; DT1 to device $10 (system / patch temp, like the PRO-E's own scheduler): TXB = address + data, A = byte count
dtn:    staa TXN
        ldaa #$F0
        jsr SENDCK
        ldaa #$41
        jsr SENDCK
        ldaa #$10
        jsr SENDCK
        ldaa #$16
        jsr SENDCK
        ldaa #$12
        jsr SENDCK
        clr SUM
        ldy #TXB
dn_lp:  ldaa 0,y
        adda SUM
        staa SUM
        ldaa 0,y
        jsr SENDCK              ; keeps A and Y
        iny
        dec TXN
        bne dn_lp
        ldaa SUM
        nega
        anda #$7F
        jsr SENDCK
        ldaa #$F7
        jmp SENDCK

; ---- PART FX: the part's reverb switch (patch temp +6) picks the CK-34 routing entry 0x39C2[switch]:
; 0 = dry, 1 = dry + FX, 2 = FX ONLY (IC28 LAB: bit 4 cleared), 3 = test (bit 4 cleared, no send). IT_AUX 1 = all 8 parts.
wetget: ldaa IT_AUX,x
        bne wg_all
        ldx #WETP
        ldab PARTIX
        abx
        ldaa 0,x
        rts
wg_all: ldaa WETA
        rts

wetchg: jsr getval
        psha
        ldx IT
        ldab IT_MAX,x
        stab MAXV
        ldaa IT_AUX,x
        staa FXM
        pulb
        jsr addclamp
        stab NEWV
        tst FXM
        bne wc_all
        ldx #WETP
        ldab PARTIX
        abx
        ldaa NEWV
        staa 0,x
        ldx #wetadr
        ldab PARTIX
        abx
        ldaa 0,x
        bra wc_one
wc_all: ldaa NEWV
        staa WETA
        staa WETP
        staa WETP+1
        staa WETP+2
        ldaa #$06               ; parts 1-8 = patch temp 03 00 06 + 16 n
wc_lp:  psha
        jsr wc_one
        pula
        adda #$10
        cmpa #$86
        bne wc_lp
        rts
wc_one: staa TXB+2              ; A = address low byte
        ldd #$0300
        std TXB
        ldaa NEWV
        staa TXB+3
        ldaa #4
        jmp dtn

fxinit: ldx #fxdef              ; per-mode defaults, part routing = dry + FX
        ldy #FXT
fi_lp:  ldaa 0,x
        staa 0,y
        inx
        iny
        cpy #FXT+16
        bne fi_lp
        ldaa #1
        staa WETP
        staa WETP+1
        staa WETP+2
        staa WETA
        clr RACT
        clr PKF
        clr BMODE               ; v0.10: bender = pitch
        clr BSKIP
        ldaa #$FF
        staa BLAST
        rts

; ---- v0.10 BENDER: CUTOFF / RESO move the DSP filter (IC13 mode 0) around the LIVE FILTER dial values (FXT/FXL[0])
bendchg: jsr getval
        psha
        ldx IT
        ldab IT_MAX,x
        stab MAXV
        pulb
        jsr addclamp
        stab BMODE
        ldaa #$FF
        staa BLAST              ; the next bend sends
        tstb
        beq bc_x
        clr FXM                 ; CUTOFF / RESO: put the filter on at the dial values
        ldx #FXT
        jmp fxsend
bc_x:   rts

; B = raw bender A/D (0-255, centre ~128). Offset -8..+8 cutoff steps, dead zone 122-135 like the stock bend table.
bend:   clr BSKIP
        ldaa BMODE
        bne bd_on
        clc
        rts
bd_on:  ldaa #1
        staa BSKIP
        cmpb #136
        bcc bd_hi
        cmpb #122
        bcc bd_0
        ldaa #136               ; down: -((136 - raw) >> 4)
        sba
        lsra
        lsra
        lsra
        lsra
        nega
        bra bd_g
bd_hi:  tba                     ; up: (raw - 120) >> 4
        suba #120
        lsra
        lsra
        lsra
        lsra
        bra bd_g
bd_0:   clra
bd_g:   staa OFFS
        ldab FXT                ; s = time & 3 (RESO), k = level * 2 + time >> 2 (CUTOFF)
        andb #3
        stab TMP
        ldaa FXT
        lsra
        lsra
        anda #1
        adda FXL
        adda FXL
        ldab BMODE
        cmpb #1
        bne bd_res
        adda OFFS               ; CUTOFF: k + offset, 0..15, never the OFF combination
        bpl bd_c1
        clra
bd_c1:  cmpa #15
        bls bd_c2
        ldaa #15
bd_c2:  tsta
        bne bd_s
        tst TMP
        bne bd_s
        ldaa #1
        bra bd_s
bd_res: ldab TMP                ; RESO: bend up = the RES version, down = without
        tst OFFS
        beq bd_s
        bmi bd_r0
        orab #1
        bra bd_r1
bd_r0:  andb #2
bd_r1:  stab TMP
bd_s:   tab                     ; B = k
        aslb
        aslb
        orab TMP                ; k * 4 + s
        cmpb BLAST
        beq bd_x
        stab BLAST
        tab                     ; level = k >> 1, time = (k & 1) * 4 + s
        lsra
        staa TXB+5
        andb #1
        aslb
        aslb
        orab TMP
        stab TXB+4
        clr TXB+3               ; mode 0 = RESONANT FILTER
        ldd #$1000
        std TXB
        ldaa #$01
        staa TXB+2
        ldaa #6
        jsr dtn
bd_x:   clc
        rts

; ---- REMOTE CONTROL over MIDI IN: F0 7D 52 xx cmd args F7 (7D = non-commercial ID, 52 = 'R'). The PRO-E's MIDI
; ISR overwrites the 3rd byte after F0 with $22 (fw_map A3), so xx is a don't-care, and her parser reads the
; next slot as a Roland command (11 = RQ1, 12 = DT1), so it must be 00. Replies go out of MIDI OUT as
; F0 7D 52 cmd payload F7, 8-bit data as two nibbles (high first).
;   01 kk  press panel key kk        02 kk  release        03 dd  dial dd - 64 steps
;   10     screen: 32 LCD chars       11     LED bytes $0B-$16
;   12 a a a a n   peek n (1-32) bytes at the address (4 nibbles)    13 a a a a v v   poke one byte (< $4000)
;   20 (nibble pairs)  send those bytes to the CK-34 as-is (raw SysEx tests)      7F  ping -> "RO07"
; A = 2 status byte / 3 data byte, B = the byte. Always continues to the stock parser (C = 0).
midi:   stab MBYTE
        cmpa #3
        beq md_d
        cmpb #$F0
        bne ms1
        ldaa #1
        staa RACT
        clr RCNT
        clc
        rts
ms1:    cmpb #$F7
        bne ms_off
        tst RACT
        beq ms_off
        clr RACT
        jsr rexec
ms_off: clr RACT
        clc
        rts
md_d:   tst RACT
        beq md_x
        ldab RCNT
        cmpb #RBUFN
        bcc md_x
        ldx #RBUF
        abx
        ldaa MBYTE
        staa 0,x
        inc RCNT
md_x:   clc
        rts

rexec:  ldaa RBUF
        cmpa #$7D
        bne rx_x
        ldaa RBUF+1
        cmpa #$52
        bne rx_x
        ldaa RBUF+3             ; 00 guard: her parser reads this slot as a Roland command (11 RQ1 / 12 DT1)
        bne rx_x
        ldaa RBUF+4
        ldx #rxtab
rx_t:   ldab 0,x
        beq rx_x
        cba
        beq rx_go
        inx
        inx
        inx
        bra rx_t
rx_go:  ldx 1,x
        jmp 0,x
rx_x:   rts
rx_prs: ldab #$80
        bra rx_k
rx_rel: clrb
rx_k:   stab PKB                ; done by the RAM hook back in bank 0 (the stock dispatcher lives there)
        ldaa RBUF+5
        staa PKEY
        ldaa #1
        staa PKF
        rts
rx_dial: ldab DVAL               ; DVAL + dd - 64, kept inside the dial range DLOW..DHIGH
        clra
        std T16
        ldab RBUF+5
        clra
        subd #64
        addd T16
        bmi rd_lo
        tsta
        bne rd_hi
        cmpb DLOW
        bcs rd_lo
        cmpb DHIGH
        bhi rd_hi
        stab DVAL
        rts
rd_lo:  ldab DLOW
        stab DVAL
        rts
rd_hi:  ldab DHIGH
        stab DVAL
        rts
rx_led: jsr rhead
        ldx #$000B
rl_lp:  ldaa 0,x
        jsr rnib
        inx
        cpx #$0017
        bne rl_lp
        jmp rtail
rx_peek: jsr raddr
        ldab RBUF+9
        beq rp_no
        cmpb #32
        bhi rp_no
        stab TXN
        jsr rhead
rp_lp:  ldx RADR
        ldaa 0,x
        jsr rnib
        inx
        stx RADR
        dec TXN
        bne rp_lp
        jmp rtail
rp_no:  rts
rx_poke: jsr raddr
        ldd RADR
        cmpa #$40
        bcc rp_no
        ldaa RBUF+9
        asla
        asla
        asla
        asla
        oraa RBUF+10
        ldx RADR
        staa 0,x
        rts
rx_ck:  ldaa RCNT               ; raw bytes for the CK-34 from nibble pairs RBUF+5..
        suba #5
        lsra
        beq rp_no
        staa TXN
        ldx #RBUF+5
rc_lp:  ldaa 0,x
        asla
        asla
        asla
        asla
        oraa 1,x
        pshx
        jsr SENDCK              ; clobbers B and X
        pulx
        inx
        inx
        dec TXN
        bne rc_lp
        rts
rx_ping: jsr rhead
        ldx #pingtx
rg_lp:  ldaa 0,x
        beq rg_x
        pshx
        jsr MIDIOUT
        pulx
        inx
        bra rg_lp
rg_x:   jmp rtail
; screen: read the HD44780 back with her own LCD routines (as the cursor blink at $4C0F does)
rx_scr: jsr rhead
        ldaa #$80
        jsr rs_line
        ldaa #$C0
        jsr rs_line
        jmp rtail
rs_line: psha
        ldab #$F8
        jsr LCDWAIT             ; busy wait, then control = B
        pula
        jsr LCDCMD              ; DDRAM address
        ldab #16
        stab TXN
rs_lp:  ldab #$06               ; RS = 1, R/W = 1
        jsr LCDWAIT
        andb #$FE
        stab 0,x                ; E low
        ldaa LCDDATA
        jsr rnib
        dec TXN
        bne rs_lp
        rts

raddr:  ldaa RBUF+5             ; 4 nibbles -> RADR
        asla
        asla
        asla
        asla
        oraa RBUF+6
        staa RADR
        ldaa RBUF+7
        asla
        asla
        asla
        asla
        oraa RBUF+8
        staa RADR+1
        rts
rhead:  ldx #rhdr
rh_lp:  ldaa 0,x
        pshx
        jsr MIDIOUT
        pulx
        inx
        cpx #rhdr+3
        bne rh_lp
        ldaa RBUF+4             ; the command echoed
        jmp MIDIOUT
rtail:  ldaa #$F7
        jmp MIDIOUT
rnib:   psha                    ; A -> two nibbles out (keeps X)
        pshx
        lsra
        lsra
        lsra
        lsra
        jsr MIDIOUT
        pulx
        pula
        pshx
        anda #$0F
        jsr MIDIOUT
        pulx
        rts

rxtab:  db $01
        dw rx_prs
        db $02
        dw rx_rel
        db $03
        dw rx_dial
        db $10
        dw rx_scr
        db $11
        dw rx_led
        db $12
        dw rx_peek
        db $13
        dw rx_poke
        db $14
        dw rx_ppk
        db $15
        dw rx_ppe
        db $20
        dw rx_ck
        db $7F
        dw rx_ping
        db 0
rhdr:   db $F0,$7D,$52
pingtx: db "RO07",0
wetadr: db $26,$16,$06          ; patch temp reverb switch of SOLO / LOWER / M.BASS

; ---------------- v0.13: USER PROGRAM tones ----------------
; Each of the 48 USER PROGRAMs (bank 1-6 x 1-8) gets a 256-byte record in SRAM pages 2-3 (the composer's old songs
; 2 + 3; the composer is gone, page 1 is left alone because boot still reads its header): "RT", the SOLO timbre temp (246 bytes), FX mode, its time, its level, BENDER mode.
; WRITE + USER n: the stock store, then the SOLO tone is read back from the CK-34 (RQ1) and saved with the FX.
; USER n: the stock recall arms PEND; when the stock link queue is empty (HTK) the tone goes out as one DT1 and the
; FX + bender come back, so nothing stock overwrites them.
UPMAG0  = $52                   ; 'R'
UPMAG1  = $54                   ; 'T'
uprog:  cmpa #6
        beq up_arm
        bcs up_st
        jmp up_snd
up_st:  jsr upidx               ; ---- store ----
        bcs up_x
        clr PARTIX              ; SOLO
        jsr readtone
        tst VALID
        beq up_x                ; no reply: keep the old record
        ldx PB2
        ldaa #UPMAG0
        jsr pgwr
        inx
        ldaa #UPMAG1
        jsr pgwr
        inx
        ldy #WORK
us_lp:  ldaa 0,y
        jsr pgwr
        inx
        iny
        cpy #WORK+246
        bne us_lp
        ldaa FXM
        jsr pgwr
        inx
        ldy #FXT
        ldab FXM
        aby
        ldaa 0,y
        jsr pgwr
        inx
        ldaa 8,y
        jsr pgwr
        inx
        ldaa BMODE
        jsr pgwr
up_x:   clc
        rts
up_arm: clr PEND                ; ---- recall: arm only a slot that holds a tone ----
        jsr upidx
        bcs up_x
        ldx PB2
        jsr pgrd
        cmpa #UPMAG0
        bne up_x
        inx
        jsr pgrd
        cmpa #UPMAG1
        bne up_x
        ldaa UIDX
        staa PEND
        ldaa #3                 ; 3 idle scheduler ticks (60 ms) after the stock queue empties
        staa PCNT
        clc
        rts
up_snd: ldaa PEND               ; ---- send (link idle) ----
        clr PEND
        jsr upix2
        bcc ur_go
ur_x:   clc
        rts
ur_go:
        ldx PB2
        inx
        inx
        ldy #WORK
ur_lp:  jsr pgrd
        staa 0,y
        inx
        iny
        cpy #WORK+246
        bne ur_lp
        jsr pgrd
        anda #$07
        staa FXM
        inx
        ldy #FXT
        ldab FXM
        aby
        jsr pgrd
        staa 0,y
        inx
        jsr pgrd
        staa 8,y
        inx
        jsr pgrd
        cmpa #3
        bcs ur_bm
        clra
ur_bm:  staa BMODE
        ldaa #$FF
        staa BLAST              ; the next bend sends
        clr PARTIX
        ldx #devtab
        ldaa 0,x
        staa DEV
        jsr dtall               ; the tone, one DT1
        ldaa $0C                ; REVERB ON: the saved effect (stock sent its own type before; this one wins)
        bita #$20
        beq ur_x
        ldx #FXT
        ldab FXM
        abx
        jsr fxsend
        clc
        rts

; program index from the stock state (= $F3E7): $2683 = number 1-8 (0 = none), $2678 = bank 0-5
upidx:  ldaa $2683
        beq ui_bad
        ldab $2678
        aslb
        aslb
        aslb
        aba
upix2:  staa UIDX               ; A = index 1-48 -> UPG = page 2/3, PB2 = $2000 + 256 * ((index - 1) & 31)
        tsta
        beq ui_bad
        cmpa #49
        bcc ui_bad
        deca
        tab
        andb #$1F
        addb #$20
        stab PB2
        clr PB2+1
        lsra
        lsra
        lsra
        lsra
        lsra
        adda #2
        staa UPG
        clc
        rts
ui_bad: sec
        rts

; A = byte at X in SRAM page UPG (interrupts held off while the page is switched; keeps X, Y)
pgrd:   tpa
        psha
        sei
        ldab SHADOW
        andb #$FC
        orab UPG
        stab LATCH
        ldaa 0,x
        ldab SHADOW
        stab LATCH
        staa TMP
        pula
        tap
        ldaa TMP
        rts
; store A at X in SRAM page UPG (keeps A, X, Y)
pgwr:   staa TMP
        tpa
        psha
        sei
        ldaa TMP
        ldab SHADOW
        andb #$FC
        orab UPG
        stab LATCH
        staa 0,x
        ldab SHADOW
        stab LATCH
        pula
        tap
        ldaa TMP
        rts

; v0.13: tone pages 2-3 over the remote (load / back up USER PROGRAM tones from the PC)
rx_ppk: jsr raddr               ; $14: addr (4 nibbles), value (2), page (1) -> SRAM page 2/3 $2000-$3FFF
        ldaa RBUF+11
        cmpa #2
        bcs rq_no
        cmpa #4
        bcc rq_no
        staa UPG
        ldd RADR
        cmpa #$20
        bcs rq_no
        cmpa #$40
        bcc rq_no
        ldaa RBUF+9
        asla
        asla
        asla
        asla
        oraa RBUF+10
        ldx RADR
        jmp pgwr
rx_ppe: jsr raddr               ; $15: addr (4 nibbles), count (1-32), page (1) -> reply like peek
        ldaa RBUF+10
        cmpa #2
        bcs rq_no
        cmpa #4
        bcc rq_no
        staa UPG
        ldab RBUF+9
        beq rq_no
        cmpb #32
        bhi rq_no
        stab TXN
        jsr rhead
rq_lp:  ldx RADR
        jsr pgrd
        jsr rnib
        inx
        stx RADR
        dec TXN
        bne rq_lp
        jmp rtail
rq_no:  rts
