from typing import List, Tuple, Dict, Union

Value = Union[int, float, str]

def run(asm_lines: List[str], signatures=None) -> Tuple[int, List[str]]:
    code = [ln.rstrip() for ln in asm_lines if ln.strip()]
    pc = 0
    mem: Dict[str, Value] = {}
    out: List[str] = []
    labels: Dict[str, int] = {}

    # collect labels
    for idx, ln in enumerate(code):
        if ln.endswith(":") and " " not in ln:
            labels[ln[:-1]] = idx

    def is_number(tok: str) -> bool:
        t = tok.replace(".", "", 1)
        if not t: return False
        if tok.count(".") > 1: return False
        return t.isdigit()

    def is_quoted(tok: str) -> bool:
        return len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"')

    def unescape(s: str) -> str:
        out = []
        i = 0
        while i < len(s):
            ch = s[i]
            if ch == "\\" and i + 1 < len(s):
                nxt = s[i+1]
                out.append({
                    "n":"\n","t":"\t","r":"\r","\\":"\\","\"":"\"", "'":"'"
                }.get(nxt, nxt))
                i += 2
                continue
            out.append(ch); i += 1
        return "".join(out)

    def val_of(tok: str) -> Value:
        if tok in mem: return mem[tok]
        if is_quoted(tok): return unescape(tok[1:-1])
        if is_number(tok): return float(tok) if "." in tok else int(tok)
        return 0

    def num_bin(op: str, a: Value, b: Value) -> Value:
        if op == "ADD": return a + b
        if op == "SUB": return a - b
        if op == "MUL": return a * b
        if op == "DIV":
            if isinstance(a, int) and isinstance(b, int):
                if b == 0: raise ZeroDivisionError("int divide by zero")
                return a // b
            else:
                if b == 0 or b == 0.0: raise ZeroDivisionError("float divide by zero")
                return a / b
        if op == "MOD":
            if not (isinstance(a, int) and isinstance(b, int)):
                raise RuntimeError("MOD only defined for ints")
            if b == 0: raise ZeroDivisionError("mod by zero")
            return a % b
        raise RuntimeError(f"Unknown op {op}")

    while pc < len(code):
        raw = code[pc].strip()
        pc += 1

        if raw.startswith("*") or raw.startswith(";;"):
            continue
        if raw.endswith(":") and " " not in raw:
            continue

        parts = [p for p in raw.replace(",", " ").split() if p]
        if not parts: continue
        op = parts[0]

        if op == "MOV" and len(parts) >= 3:
            dst, src = parts[1], parts[2]
            mem[dst] = val_of(src)
            continue

        # unary: "dst = - src"
        if "=" in raw and " - " in raw and raw.count("=") == 1 and raw.strip().split()[1] == "=":
            lhs, rhs = [x.strip() for x in raw.split("=", 1)]
            toks = [p for p in rhs.replace(",", " ").split() if p]
            if len(toks) == 2 and toks[0] in ("-", "uminus"):
                mem[lhs] = -val_of(toks[1])
                continue

        if op in ("ADD","SUB","MUL","DIV","MOD") and len(parts) >= 4:
            dst, a, b = parts[1], parts[2], parts[3]
            mem[dst] = num_bin(op, val_of(a), val_of(b))
            continue

        if op in ("EQ","NE","LT","LE","GT","GE") and len(parts) >= 4:
            dst, a, b = parts[1], parts[2], parts[3]
            av, bv = val_of(a), val_of(b)
            if op == "EQ": mem[dst] = 1 if av == bv else 0
            elif op == "NE": mem[dst] = 1 if av != bv else 0
            elif op == "LT": mem[dst] = 1 if av <  bv else 0
            elif op == "LE": mem[dst] = 1 if av <= bv else 0
            elif op == "GT": mem[dst] = 1 if av >  bv else 0
            elif op == "GE": mem[dst] = 1 if av >= bv else 0
            continue

        if op == "PRINT":
            x = parts[1] if len(parts) > 1 else None
            v = val_of(x) if x is not None else 0
            out.append(str(v))
            continue

        if op == "JMP" and len(parts) >= 2:
            pc = labels[parts[1]]
            continue

        if op == "JNZ":
            cond, label = (parts[1], parts[2]) if len(parts) == 3 else (parts[1], parts[-1])
            if val_of(cond) != 0:
                pc = labels[label]
            continue

        if op == "RET" or op == "HALT":
            return 0, out


    return 0, out
