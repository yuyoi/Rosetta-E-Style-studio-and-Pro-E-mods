"""Small two-pass 68HC11 assembler for PRO-E patches.

The opcode table is generated from capstone's M680X decoder (every opcode on the 00/18/1A/CD pages), so mnemonics,
addressing modes and sizes match the disassembler exactly. test_hc11asm.py re-assembles the PRO-E OS from
capstone's own listing and requires identical bytes.

Syntax (one statement per line, ';' starts a comment):
  label:                     labels end with ':'
  NAME = expr                constant
  org $C000                  set the address (output is a {addr: bytes} map)
  db 1, $20, "TEXT"          bytes / strings      dw $1234, label    16-bit big-endian
  ds 8                       reserve (fills $FF)
  ldaa #$12   ldd #label     immediate (size from the opcode)
  ldaa $12    ldaa <$1234    direct if the address is < $100 and the mode exists ('<' forces direct)
  ldaa $1234  ldaa >$12      extended ('>' forces extended)
  ldaa 5,x    staa 0,y       indexed
  bra label                  relative branches (range-checked)
  bset $12,#$80   bclr 5,x,#$01   brset $12,#$80,label   brclr 5,x,#$01,label
Numbers: $hex, %binary, decimal (may be negative), 'c' chars, labels, + - * / & | << >> and ( ).
"""
import re
from capstone import Cs, CS_ARCH_M680X, CS_MODE_M680X_6811

_md = Cs(CS_ARCH_M680X, CS_MODE_M680X_6811)
BRANCH_BITOPS = {'brset', 'brclr'}
BITOPS = {'bset', 'bclr'}
BRANCHES = {'bra', 'brn', 'bhi', 'bls', 'bcc', 'bcs', 'bhs', 'blo', 'bne', 'beq', 'bvc', 'bvs', 'bpl', 'bmi',
            'bge', 'blt', 'bgt', 'ble', 'bsr'}


def _mode(mn, ops, opsize):
    if ops == '':
        return 'inh'
    if mn in BRANCH_BITOPS:
        return 'bit_idx_rel' if ', x' in ops or ', y' in ops else 'bit_dir_rel'
    if mn in BITOPS:
        return 'bit_idx' if ', x' in ops or ', y' in ops else 'bit_dir'
    if ops.startswith('#'):
        return f'imm{opsize * 8}'
    if ops.endswith(', x') or ops.endswith(', y'):
        return 'idx'
    if mn in BRANCHES:
        return 'rel'
    return 'dir' if opsize == 1 else 'ext'


def _build_table():
    table = {}
    for pre in (b'', b'\x18', b'\x1a', b'\xcd'):
        for op in range(256):
            code = pre + bytes([op])
            if not pre and op in (0x18, 0x1A, 0xCD):
                continue
            ins = next(_md.disasm(code + b'\x11\x22\x33\x44', 0x8000), None)
            if ins is None or bytes(ins.bytes[:len(code)]) != code or ins.mnemonic in ('fcb', 'fdb', 'illgl'):
                continue
            opsize = ins.size - len(code)
            mode = _mode(ins.mnemonic, ins.op_str, opsize)
            reg = 'y' if ', y' in ins.op_str else ('x' if ', x' in ins.op_str else '')
            key = (ins.mnemonic, mode + (':' + reg if reg else ''))
            table.setdefault(key, (code, ins.size))
    return table


TABLE = _build_table()
MNEMONICS = {m for m, _ in TABLE}


class AsmError(Exception):
    pass


def _tokens(expr):
    return re.findall(r"\$[0-9A-Fa-f]+|%[01]+|'.'|\d+|<<|>>|[A-Za-z_.][A-Za-z0-9_.]*|[-+*/&|()]", expr)


def evaluate(expr, syms, strict=True):
    toks = _tokens(expr.strip())
    pos = 0

    def atom():
        nonlocal pos
        t = toks[pos]
        pos += 1
        if t == '(':
            v = expr_()
            pos += 1
            return v
        if t == '-':
            return -atom()
        if t.startswith('$'):
            return int(t[1:], 16)
        if t.startswith('%'):
            return int(t[1:], 2)
        if t.startswith("'"):
            return ord(t[1])
        if t.isdigit():
            return int(t)
        if t in syms:
            return syms[t]
        if strict:
            raise AsmError(f'unknown symbol {t}')
        return 0

    def term():
        nonlocal pos
        v = atom()
        while pos < len(toks) and toks[pos] in ('*', '/'):
            o = toks[pos]
            pos += 1
            r = atom()
            v = v * r if o == '*' else v // r
        return v

    def expr_():
        nonlocal pos
        v = term()
        while pos < len(toks) and toks[pos] in ('+', '-', '&', '|', '<<', '>>'):
            o = toks[pos]
            pos += 1
            r = term()
            v = {'+': v + r, '-': v - r, '&': v & r, '|': v | r, '<<': v << r, '>>': v >> r}[o]
        return v

    if not toks:
        raise AsmError('empty expression')
    v = expr_()
    if pos != len(toks):
        raise AsmError(f'cannot parse {expr!r}')
    return v


def _split_args(s):
    out, cur, q = [], '', False
    for ch in s:
        if ch == '"':
            q = not q
        if ch == ',' and not q:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _encode(mn, args, pc, syms, strict, line):
    def ev(e):
        return evaluate(e, syms, strict)

    def need(mode):
        if (mn, mode) not in TABLE:
            raise AsmError(f'{line}: {mn} has no {mode} mode')
        return TABLE[(mn, mode)]

    def rel(target, end):
        d = target - end
        if strict and not -128 <= d <= 127:
            raise AsmError(f'{line}: branch out of range ({d})')
        return d & 0xFF

    if not args:
        code, size = need('inh')
        return code
    if mn in BITOPS or mn in BRANCH_BITOPS:
        indexed = len(args) >= 2 and args[1].lower() in ('x', 'y')
        if indexed:
            code, size = need(('bit_idx_rel' if mn in BRANCH_BITOPS else 'bit_idx') + ':' + args[1].lower())
            out = code + bytes([ev(args[0]) & 0xFF, ev(args[2].lstrip('#')) & 0xFF])
            rest = args[3:]
        else:
            code, size = need('bit_dir_rel' if mn in BRANCH_BITOPS else 'bit_dir')
            out = code + bytes([ev(args[0]) & 0xFF, ev(args[1].lstrip('#')) & 0xFF])
            rest = args[2:]
        if mn in BRANCH_BITOPS:
            out += bytes([rel(ev(rest[0]), pc + size)])
        return out
    a = args[0]
    if len(args) == 2 and args[1].lower() in ('x', 'y'):
        code, size = need('idx:' + args[1].lower())
        return code + bytes([ev(a) & 0xFF])
    if a.startswith('#'):
        for bits in (8, 16):
            if (mn, f'imm{bits}') in TABLE:
                code, size = TABLE[(mn, f'imm{bits}')]
                v = ev(a[1:]) & ((1 << bits) - 1)
                return code + v.to_bytes(bits // 8, 'big')
        raise AsmError(f'{line}: {mn} has no immediate mode')
    if (mn, 'rel') in TABLE:
        code, size = TABLE[(mn, 'rel')]
        return code + bytes([rel(ev(a), pc + size)])
    force = a[0] if a[0] in '<>' else ''
    v = ev(a.lstrip('<>'))
    if force == '<' or (not force and 0 <= v < 0x100 and (mn, 'dir') in TABLE):
        code, size = need('dir')
        return code + bytes([v & 0xFF])
    code, size = need('ext')
    return code + (v & 0xFFFF).to_bytes(2, 'big')


def assemble(src, syms=None):
    """-> (segments {start_addr: bytearray}, symbols). Passes repeat until every label is stable (a forward
    reference can pick the 2-byte direct form while it is still unknown), then one strict pass."""
    syms = dict(syms or {})
    lines = []
    for n, raw in enumerate(src.splitlines(), 1):
        s = raw.split(';', 1)[0] if '"' not in raw else re.sub(r';(?=(?:[^"]*"[^"]*")*[^"]*$).*', '', raw)
        s = s.strip()
        if s:
            lines.append((n, s))
    labels = None
    for _ in range(10):
        segs, new = _pass(lines, syms, False)
        if new == labels:
            break
        labels = new
    else:
        raise AsmError('labels still moving after 10 passes')
    segs, new = _pass(lines, syms, True)
    if new != labels:
        raise AsmError('labels moved in the strict pass')
    return segs, syms


def _pass(lines, syms, strict):
    pc, segs, cur, labels = 0, {}, None, {}
    for n, s in lines:
        where = f'line {n}: {s}'
        m = re.match(r'^([A-Za-z_.][A-Za-z0-9_.]*):\s*(.*)$', s)
        if m:
            syms[m.group(1)] = labels[m.group(1)] = pc
            s = m.group(2).strip()
            if not s:
                continue
        m = re.match(r'^([A-Za-z_.][A-Za-z0-9_.]*)\s*=\s*(.+)$', s)
        if m:
            syms[m.group(1)] = evaluate(m.group(2), syms, strict)
            continue
        parts = s.split(None, 1)
        op, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else '')
        if op == 'org':
            pc = evaluate(rest, syms, strict)
            cur = segs.setdefault(pc, bytearray())
            continue
        if cur is None:
            raise AsmError(f'{where}: code before org')
        op = {'fcb': 'db', 'fdb': 'dw', 'fcc': 'db'}.get(op, op)
        if op == 'db':
            data = bytearray()
            for a in _split_args(rest):
                if a.startswith('"'):
                    data += a.strip('"').encode('latin1')
                else:
                    data.append(evaluate(a, syms, strict) & 0xFF)
        elif op == 'dw':
            data = b''.join((evaluate(a, syms, strict) & 0xFFFF).to_bytes(2, 'big') for a in _split_args(rest))
        elif op == 'ds':
            data = b'\xff' * evaluate(rest, syms, strict)
        elif op in MNEMONICS:
            data = _encode(op, _split_args(rest), pc, syms, strict, where)
        else:
            raise AsmError(f'{where}: unknown instruction {op}')
        cur += data
        pc += len(data)
    return segs, labels


def disasm(data, addr):
    return [(i.address, i.mnemonic, i.op_str, bytes(i.bytes)) for i in _md.disasm(bytes(data), addr)]
