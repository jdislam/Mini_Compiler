# optimizer.py — simple TAC optimizer:
# - copy propagation
# - dead copy elimination
# - local common subexpression elimination (CSE)
#
# API: optimize_tac(tac_lines: list[str]) -> (optimized_lines: list[str], errors: list[str])

from typing import List, Tuple, Dict, Optional
import re

BINOPS = {"+","-","*","/","%","==","!=", "<","<=",">",">=","&&","||"}
COMMUTATIVE = {"+","*","==","!=","&&","||"}  # canonicalize operands for these

_num_re = re.compile(r"^\d+(?:\.\d+)?$")

def _is_number(s: str) -> bool:
    return bool(_num_re.match(s))

def _tokenize_rhs(rhs: str) -> List[str]:
    # split by whitespace; commas already not expected in TAC
    return [p for p in rhs.split() if p]

def _is_temp(name: str) -> bool:
    # Treat names like t1, t12, T1, T12 as temps
    return bool(re.match(r"^[tT]\d+$", name))

def _parse_assign(line: str):
    # Returns (lhs, rhs_tokens) or None if not assignment
    if " = " not in line:
        return None
    lhs, rhs = [p.strip() for p in line.split("=", 1)]
    if not lhs:
        return None
    toks = _tokenize_rhs(rhs)
    return lhs, toks

def _is_structural(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith(("func ","endfunc","label ","goto ","if ","print ","return")):
        return True
    return False

def _canon_key(toks: List[str]) -> Optional[Tuple]:
    """Create a hashable key for expressions: copy / unary / binary."""
    if not toks:
        return None
    if len(toks) == 1:
        # copy or constant
        return ("copy", toks[0])
    if len(toks) == 2 and toks[0] in ("uminus", "-"):
        return ("uminus", toks[1])
    if len(toks) == 3 and toks[1] in BINOPS:
        a, op, b = toks
        if op in COMMUTATIVE:
            # canonicalize commutative by ordering operands (numbers before names, then lexicographic)
            def _ord(x):
                return (0, float(x) if _is_number(x) else 0.0, x) if _is_number(x) else (1, 0.0, x)
            a2, b2 = sorted([a,b], key=_ord)
            return ("bin", op, a2, b2)
        else:
            return ("bin", op, a, b)
    return None

def _subst(name: str, alias: Dict[str, str]) -> str:
    # resolve aliases transitively, but stop at numbers / non-temps or if cycles
    seen = set()
    cur = name
    while cur in alias and cur not in seen:
        seen.add(cur)
        cur = alias[cur]
    return cur

def _rewrite_rhs_toks(toks: List[str], alias: Dict[str, str]) -> List[str]:
    return [ _subst(t, alias) for t in toks ]

def _reads_of(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("if "):
        parts = s.split()
        return [parts[1]]  # "if t1 goto Lx"
    if s.startswith("goto ") or s.startswith("label "):
        return []
    if s.startswith("print "):
        return [s.split(" ",1)[1]]
    if s.startswith("return"):
        parts = s.split()
        return [parts[1]] if len(parts) > 1 else []
    pa = _parse_assign(s)
    if not pa:
        return []
    _, toks = pa
    # exclude operator tokens
    return [t for t in toks if t not in BINOPS and t not in ("uminus","-")]

def _writes_of(line: str) -> List[str]:
    s = line.strip()
    pa = _parse_assign(s)
    if not pa:
        return []
    lhs, _ = pa
    return [lhs]

def optimize_tac(tac: List[str]) -> Tuple[List[str], List[str]]:
    errs: List[str] = []

    # Work in simple "basic blocks": split by labels and gotos/ifs/returns/prints/func boundaries
    # For simplicity and safety, we'll optimize linearly across the whole list but reset CSE on labels/branches.
    out: List[str] = []
    alias: Dict[str, str] = {}            # copy aliases t -> x
    expr_table: Dict[Tuple, str] = {}     # CSE table: expr_key -> temp/name
    killed: set = set()                   # names that got a new value -> invalidate expression table entries using them

    def reset_block():
        alias.clear()
        expr_table.clear()
        killed.clear()

    def invalidate_on_write(name: str):
        # any expression mentioning 'name' becomes unsafe; drop table
        to_del = []
        for k, v in expr_table.items():
            if isinstance(k, tuple) and any(name == part for part in k[2:] if isinstance(k[0], str)):
                to_del.append(k)
        for k in to_del:
            expr_table.pop(k, None)

    reset_block()

    # First pass: copy propagation + CSE, producing a normalized TAC
    norm: List[str] = []

    for line in tac:
        s = line.strip()
        if not s:
            continue

        if s.startswith("func "):
            reset_block()
            norm.append(s)
            continue
        if s == "endfunc":
            reset_block()
            norm.append(s)
            continue
        if s.startswith("label "):
            reset_block()
            # normalize label name once
            parts = s.split()
            norm.append(f"label {parts[1]}")
            continue
        if s.startswith(("goto ","if ","print ","return")):
            # rewrite reads through alias
            if s.startswith("if "):
                parts = s.split()
                cond = _subst(parts[1], alias)
                norm.append(f"if {cond} goto {parts[3]}")
            elif s.startswith("goto "):
                norm.append(s)
            elif s.startswith("print "):
                what = _subst(s.split(" ",1)[1], alias)
                norm.append(f"print {what}")
            else:  # return
                parts = s.split()
                if len(parts) == 1:
                    norm.append("return")
                else:
                    v = _subst(parts[1], alias)
                    norm.append(f"return {v}")
            continue

        pa = _parse_assign(s)
        if not pa:
            norm.append(s)
            continue

        lhs, rhs_toks = pa

        # Rewrite RHS via alias map
        rhs_toks = _rewrite_rhs_toks(rhs_toks, alias)

        # Constant folding for unary/binary
        if len(rhs_toks) == 2 and rhs_toks[0] in ("uminus","-") and _is_number(rhs_toks[1]):
            val = float(rhs_toks[1]) if "." in rhs_toks[1] else int(rhs_toks[1])
            folded = -val
            rhs_toks = [str(folded)]
        elif len(rhs_toks) == 3 and rhs_toks[1] in BINOPS and _is_number(rhs_toks[0]) and _is_number(rhs_toks[2]):
            a = float(rhs_toks[0]) if "." in rhs_toks[0] else int(rhs_toks[0])
            b = float(rhs_toks[2]) if "." in rhs_toks[2] else int(rhs_toks[2])
            op = rhs_toks[1]
            try:
                if op == "+": folded = a + b
                elif op == "-": folded = a - b
                elif op == "*": folded = a * b
                elif op == "/": folded = a / b
                elif op == "%": folded = a % b
                elif op == "==": folded = 1 if a == b else 0
                elif op == "!=": folded = 1 if a != b else 0
                elif op == "<": folded = 1 if a < b else 0
                elif op == "<=": folded = 1 if a <= b else 0
                elif op == ">": folded = 1 if a > b else 0
                elif op == ">=": folded = 1 if a >= b else 0
                elif op == "&&": folded = 1 if (a != 0 and b != 0) else 0
                elif op == "||": folded = 1 if (a != 0 or b != 0) else 0
                else: folded = None
                if folded is not None:
                    rhs_toks = [str(folded)]
            except Exception:
                pass

        # Algebraic simplifications (safe subset)
        if len(rhs_toks) == 3 and rhs_toks[1] in BINOPS:
            a, op, b = rhs_toks
            if op == "+" and b == "0": rhs_toks = [a]
            elif op == "+" and a == "0": rhs_toks = [b]
            elif op == "-" and b == "0": rhs_toks = [a]
            elif op == "*" and b == "1": rhs_toks = [a]
            elif op == "*" and a == "1": rhs_toks = [b]
            elif op == "*" and (a == "0" or b == "0"): rhs_toks = ["0"]

        # CSE key after folding/simplify
        key = _canon_key(rhs_toks)

        # Copy propagation: maintain alias for simple copy
        if key and key[0] == "copy":
            src = rhs_toks[0]
            alias[lhs] = _subst(src, alias)
            # writing to name invalidates exprs that depend on lhs
            invalidate_on_write(lhs)
            norm.append(f"{lhs} = {alias[lhs]}")
            continue

        # Unary op
        if key and key[0] == "uminus":
            src = rhs_toks[1]
            # CSE for unary
            if key in expr_table:
                prev = expr_table[key]
                alias[lhs] = prev
                invalidate_on_write(lhs)
                norm.append(f"{lhs} = {prev}")
            else:
                expr_table[key] = lhs
                invalidate_on_write(lhs)
                norm.append(f"{lhs} = uminus {src}")
            continue

        # Binary op
        if key and key[0] == "bin":
            # CSE for binary
            if key in expr_table:
                prev = expr_table[key]
                alias[lhs] = prev
                invalidate_on_write(lhs)
                norm.append(f"{lhs} = {prev}")
            else:
                expr_table[key] = lhs
                a, op, b = rhs_toks[0], rhs_toks[1], rhs_toks[2]
                invalidate_on_write(lhs)
                norm.append(f"{lhs} = {a} {op} {b}")
            continue

        # Fallback: emit rewritten assignment
        invalidate_on_write(lhs)
        norm.append(f"{lhs} = {' '.join(rhs_toks)}")

    # Second pass: substitute aliases everywhere and compute use counts
    alias2 = dict(alias)  # final alias map (already propagated once)
    final_lines: List[str] = []
    uses: Dict[str, int] = {}

    def _acc_uses(tokens: List[str]):
        for t in tokens:
            if t in BINOPS or t in ("uminus","-"): 
                continue
            uses[t] = uses.get(t, 0) + 1

    for s in norm:
        st = s.strip()
        if st.startswith(("func ","endfunc","label ","goto ","if ")):
            final_lines.append(st)
            continue
        if st.startswith("print "):
            v = _subst(st.split(" ",1)[1], alias2)
            final_lines.append(f"print {v}")
            _acc_uses([v])
            continue
        if st.startswith("return"):
            parts = st.split()
            if len(parts) == 1:
                final_lines.append("return")
            else:
                v = _subst(parts[1], alias2)
                final_lines.append(f"return {v}")
                _acc_uses([v])
            continue
        pa = _parse_assign(st)
        if not pa:
            final_lines.append(st)
            continue
        lhs, rhs_toks = pa
        rhs_toks = _rewrite_rhs_toks(rhs_toks, alias2)
        final_lines.append(f"{lhs} = {' '.join(rhs_toks)}")
        _acc_uses([t for t in rhs_toks if t not in BINOPS and t not in ("uminus","-")])

    # Third pass: drop dead simple copies (t = x) where t is never used
    optimized: List[str] = []
    for s in final_lines:
        st = s.strip()
        pa = _parse_assign(st)
        if not pa:
            optimized.append(st); continue
        lhs, rhs_toks = pa
        if len(rhs_toks) == 1 and _is_temp(lhs) and uses.get(lhs, 0) == 0:
            # dead copy temp; drop it
            continue
        optimized.append(st)

    return optimized, errs