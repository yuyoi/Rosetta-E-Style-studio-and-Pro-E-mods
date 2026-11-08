; RAM trampoline at $2DA6 (SRAM page 0 gap, copied from the upper half at boot by BOOTCOPY in IC4).
; Far call into the SYNTH code (upper half, bank 5) and back: latch bank 5 + PA6 high = IC7 A18 high.
; The $180D shadow ($0A) is kept in step, so ISRs that switch banks put bank 5 back.
        org $2DA6
RAMKEY:  clra                    ; key event (B = $80 / 0), continue at the stock dispatcher
         ldx #$4D32
         bra FAR
RAMTICK: ldaa #1                 ; page $0D tick, continue at the stock REVERB tick
         ldx #$83FF
FAR:     pshx
         pshb
         psha
         ldab SHADOW
         pshb
         andb #$03               ; keep the RAM page bits, card off
         orab #BANKSEL
         stab SHADOW
         stab LATCH
         ldx #PORTA
         bset 0,x,#$40           ; PA6 = 1: upper half
         tsx
         ldd 1,x                 ; A = selector, B = event
         jsr ENTRY
         ldx #PORTA
         bclr 0,x,#$40           ; PA6 = 0: lower half (C survives ldx/bclr/pul/stab)
         pulb
         stab SHADOW
         stab LATCH
         pula
         pulb
         pulx
         bcs FARRTS
         jmp 0,x
FARRTS:  rts
; end of the boot copy: back to the lower half and the boot's own bank, return to BOOTCOPY in IC4
BOOTRET: ldx #PORTA
         bclr 0,x,#$40
         ldaa OLDSH
         staa SHADOW
         staa LATCH
         rts
TRAMP_END:

; ---- v0.5: tempo-LED hooks. Her beat code in IC4 writes the 4 tempo LEDs at 5 places; each one is patched to jsr here.
; While SYNTH EDIT is open the LEDs show the partials, so the write is skipped. Registers come out exactly as stock.
        org HOOKBASE
HB1:     tst EDIT                ; $C490: new bar = red LED only
         bne HBR
         bclr BEAT,#$0F
         bclr BEAT2,#$0F
         bset BEAT,#$08
         bset BEAT2,#$08
HBR:     rts
HB2:     ldaa BEAT               ; $C4A7: next beat = shift the lit LED
         jsr $D2D8
         tst EDIT
         bne hb2a
         staa BEAT
hb2a:    ldaa BEAT2
         jsr $D2D8
         tst EDIT
         bne HBR
         staa BEAT2
         rts
HB3:     tst EDIT                ; $C4C7: beat over = all off
         bne HBR
         bclr BEAT,#$0F
         bclr BEAT2,#$0F
         rts
HB4:     tst EDIT                ; $C4D5: downbeat = red LED only
         bne HBR
         bclr BEAT,#$07
         bclr BEAT2,#$07
         bset BEAT,#$08
         bset BEAT2,#$08
         rts
HB5:     ldaa BEAT               ; $C859: beat position from the song position
         anda #$F0
         aba
         tst EDIT
         bne hb5a
         staa BEAT
hb5a:    ldaa BEAT2
         anda #$F0
         aba
         tst EDIT
         bne HBR
         staa BEAT2
         rts
; ---- v0.7: MIDI IN hooks for remote control. IC7 bank 0 $9703 (status) / $9745 (data) jsr here instead of their
; first instruction; the byte goes to the SYNTH code, then the stock parser runs exactly as before.
HMS:     pshx                    ; $9703: A = status byte
         psha
         tab
         ldaa #2
         ldx #HMS2
         jmp FAR
HMS2:    jsr RPEND
         pula
         pulx
         ldab $268A              ; the replaced instruction
         rts
HMD:     pshx                    ; $9745: A = data byte
         psha
         tab
         ldaa #3
         ldx #HMD2
         jmp FAR
HMD2:    jsr RPEND
         pula
         pulx
         bset $5B,#$40           ; the replaced instruction
         rts
; a remote key press is run here, back in the lower half + bank 0, through the normal key path
RPEND:   tst PKF
         beq RPX
         clr PKF
         ldaa PKEY
         staa $2648
         ldab PKB
         jsr RAMKEY
RPX:     rts
; ---- v0.10: bender hook. IC7 bank 0 $551D (stab $266C, B = raw bender A/D) jsr here. The SYNTH code decides:
; BENDER = PITCH: back to $5520, the stock pitch bend. CUTOFF / RESO: it moved the DSP filter, BSKIP = 1, return
; straight to the A/D loop (no pitch bend sent). FAR keeps B.
HBD:     stab $266C              ; the replaced instruction
         ldaa #4
         ldx #HBD2
         jmp FAR
HBD2:    tst BSKIP
         beq HBDX
         ins                     ; drop the return to $5520
         ins
HBDX:    rts
; ---- v0.13: USER PROGRAM tones. IC4 $F4DD (end of WRITE + USER n) and $F57E (end of a USER n recall) jmp here;
; the SYNTH code saves / arms the slot, then FAR continues at the stock target. IC7 bank 0 $51C4 (link scheduler,
; ldaa $2673) jsr HTK: when no stock link task is pending, an armed recall sends its tone + FX (selector 7).
HST:     ldaa #5
         ldx #$9419
         jmp FAR
HRC:     ldaa #6
         ldx #$FC67
         jmp FAR
HTK:     ldaa $2673              ; the replaced instruction: every exit reloads it, so the stock beq sees A / Z
         bne HTKX
         tst PEND
         beq HTKX
         dec PCNT
         bne HTKX
         ldaa #7
         ldx #HTKX
         jmp FAR
HTKX:    ldaa $2673
         rts
; ---- v0.14: ARPEGGIATOR. IC7 bank 0 $42CB (the SOLO note send, jsr $EBF1 with D = key, velocity) jsr HAR: the SYNTH
; code plays the note (ARP off) or adds it to / takes it off the held list, returns C = 1 = FAR rts = back to $42CE.
; IC7 bank 0 $A118 (arranger, once per 24 PPQN tick, stopped or playing) jsr ATK: the SYNTH code steps the ARP
; (C = 0 -> ATK2), then the replaced brclr $10,#$40,$A164 runs here. A and X are kept for the stock code.
HAR:     std ARPK
         ldaa #8
         jmp FAR
ATK:     pshx
         psha
         ldaa #9
         ldx #ATK2
         jmp FAR
ATK2:    pula
         pulx
         brclr $10,#$40,ATK3
         rts
ATK3:    ins
         ins
         jmp $A164
HOOK_END:
