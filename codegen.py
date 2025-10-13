from typing import Dict, List, Tuple
from parser import Program

# Public API expected by cli.py
#   build_signatures(ast) -> dict
#   lower_to_asm(tac_lines, signatures=None) -> (asm_lines, errors)

def build_signatures(ast: Program) -> Dict[str, Tuple[str, List[str]]]:
    sigs = {}
    for fn in ast.funcs:
        ret = fn.ret_type.name
        params = [p.type.name for p in fn.params]
        sigs[fn.name] = (ret, params)
    return sigs

BINMAP = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD"}
CMPMAP = {"==": "EQ", "!=": "NE", "<": "LT", "<=": "LE", ">": "GT", ">=": "GE"}

def _is_number(tok: str) -> bool:
    tok2 = tok.replace(".", "", 1)
    return tok2.isdigit()

def lower_to_asm(tac: List[str], signatures=None) -> Tuple[List[str], List[str]]:
    out: List[str] = []
    errs: List[str] = []

    # banner
    out.append("*******************************************************")
    out.append("************    STACK-MACHINE ASSEMBLY    *************")
    out.append("*******************************************************")

    # Track temps defined as a negation so we can undo bad "g - (-f)" peepholes.
    neg_of: Dict[str, str] = {}

    cur_fn = None

    def header(fn: str):
        out.append(";; function " + fn)
        out.append(f"{fn}:")

    for raw in tac:
        s = raw.strip()
        if not s:
            continue

        # function markers
        if s.startswith("func "):
            cur_fn = s.split()[1].rstrip(":")
            header(cur_fn)
            continue
        if s == "endfunc":
            cur_fn = None
            continue

        # labels (normalize to a single trailing colon)
        if s.startswith("label "):
            name = s.split()[1].rstrip(":")
            out.append(name + ":")
            continue

        # branches
        if s.startswith("if "):
            # TAC: "if t1 goto Lx"
            parts = s.split()
            out.append(f"JNZ {parts[1]}, {parts[3]}")
            continue
        if s.startswith("goto "):
            out.append(f"JMP {s.split()[1]}")
            continue

        # print
        if s.startswith("print "):
            x = s.split(" ", 1)[1]
            out.append(f"PRINT {x}")
            continue

        # return
        if s.startswith("return"):
            parts = s.split()
            if len(parts) == 1:
                out.append("RET")
            else:
                out.append(f"MOV RET, {parts[1]}")
                out.append("RET")
            continue

        # assignments
        if " = " in s:
            lhs, rhs = [p.strip() for p in s.split("=", 1)]
            toks = rhs.split()

            # copy / constant
            if len(toks) == 1:
                out.append(f"MOV {lhs}, {toks[0]}")
                continue

            # unary uminus
            if len(toks) == 2 and toks[0] in ("uminus", "-"):
                # remember this is a negated value
                neg_of[lhs] = toks[1]
                out.append(f"{lhs} = - {toks[1]}")
                continue

            # binary arithmetic a op b
            if len(toks) == 3 and toks[1] in BINMAP:
                a, op, b = toks

                # Fix bad pattern from earlier peephole: a - (tneg) where tneg = - x  ==> a - x
                if op == "-" and b in neg_of:
                    out.append(f"SUB {lhs}, {a}, {neg_of[b]}")
                    continue

                out.append(f"{BINMAP[op]} {lhs}, {a}, {b}")
                continue

            # binary comparisons a cmp b -> CMP dst, a, b
            if len(toks) == 3 and toks[1] in CMPMAP:
                a, op, b = toks
                out.append(f"{CMPMAP[op]} {lhs}, {a}, {b}")
                continue

        # fallback
        errs.append(f"unhandled TAC: {s}")

    return out, errs
