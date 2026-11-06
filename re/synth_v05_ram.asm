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
HOOK_END:
