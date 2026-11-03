#!/bin/sh
# rng.sh FROM TO : print listing lines with address in [FROM,TO] (hex), plus labels inside
awk -v f="$1" -v t="$2" 'BEGIN{F=strtonum("0x" f);T=strtonum("0x" t)}
/^L[0-9A-F]{4}:/{a=strtonum("0x" substr($1,2,4)); if(a>=F&&a<=T) print; next}
/^  [0-9A-F]{4}  /{a=strtonum("0x" $1); if(a>=F&&a<=T) print; next}
/^  ; ---- gap/{ if (p) print }' "$(dirname "$0")/bank0_ic4_x.lst"
