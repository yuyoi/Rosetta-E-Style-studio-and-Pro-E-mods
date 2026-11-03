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
