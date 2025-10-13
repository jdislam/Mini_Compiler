import argparse
import sys
from pathlib import Path

from lexer import Lexer
from parser import parse, ast_to_string
from sema import analyze as sema_analyze
from tac import generate as tac_generate
from codegen import build_signatures, lower_to_asm
from vm import run as vm_run
from optimizer import optimize_tac

# ---------------- Banners ----------------

STAR_LINE_LEN = 56
LEFT_STARS = 10
RIGHT_STARS = 10

def print_banner(title: str) -> None:
    top_bot = "*" * STAR_LINE_LEN
    inside_width = STAR_LINE_LEN - LEFT_STARS - RIGHT_STARS
    text = title.upper()
    if len(text) > inside_width:
        text = text[:inside_width]
    left_spaces = (inside_width - len(text)) // 2
    right_spaces = inside_width - len(text) - left_spaces
    middle = ("*" * LEFT_STARS) + (" " * left_spaces) + text + (" " * right_spaces) + ("*" * RIGHT_STARS)
    print(top_bot)
    print(middle)
    print(top_bot)

def banner_for_phase(phase: str) -> str:
    mapping = {
        "tokens": "TOKENIZATION",
        "ast": "ABSTRACT SYNTAX TREE",
        "sema": "SEMANTIC ANALYSIS",
        "tac": "THREE-ADDRESS CODE",
        "opt": "OPTIMIZED TAC",
        "asm": "STACK-MACHINE ASSEMBLY",
        "run": "PROGRAM OUTPUT",
    }
    return mapping.get(phase, phase.upper())

# ------------- TAC Pretty Print ----------

def _pretty_tac_lines(tac_lines):
    """
    EXPANDED pretty TAC for display (kept for --phase tac):
    - Expands a binary 'lhs = a op b' into three lines:
         Tn = a
         Tn+1 = b
         Tn+2 = Tn op Tn+1
    - Prints '*' as 'x' and unary '-' as 'uminus'
    - Skips structural lines
    """
    import re
    next_T = 1

    def is_number(s: str) -> bool:
        return re.fullmatch(r"\d+(?:\.\d+)?", s or "") is not None

    def toks(s: str):
        return [p for p in s.replace(",", " , ").replace("(", " ( ").replace(")", " ) ").split() if p]

    out = []

    for line in tac_lines:
        s = line.strip()
        if not s or s.startswith(("#", "//")):
            continue
        if s.startswith(("func ", "endfunc", "var ", "label ", "goto ", "if ")):
            continue
        if " = " not in s:
            continue

        lhs, rhs = [p.strip() for p in s.split("=", 1)]
        tk = toks(rhs)

        # 1) Skip constant initializers in expanded view
        if len(tk) == 1 and is_number(tk[0]):
            continue

        # 2) Unary
        if (len(tk) == 2) and (tk[0].lower() in ("uminus", "-")):
            a = tk[1]
            T1 = f"T{next_T}"; next_T += 1
            out.append(f"{T1} = - {a}")
            continue

        # 3) Binary
        if len(tk) == 3 and tk[1] in {"+", "-", "*", "/", "%", "==", "!=", "<", "<=", ">", ">=", "&&", "||"}:
            a, op, b = tk
            op_out = "x" if op == "*" else op
            T1 = f"T{next_T}"; next_T += 1
            T2 = f"T{next_T}"; next_T += 1
            T3 = f"T{next_T}"; next_T += 1
            out.append(f"{T1} = {a}")
            out.append(f"{T2} = {b}")
            out.append(f"{T3} = {T1} {op_out} {T2}")
            continue

        # 4) Copy
        if len(tk) == 1 and not is_number(tk[0]):
            T1 = f"T{next_T}"; next_T += 1
            out.append(f"{T1} = {tk[0]}")
            continue

    return [f"({i}) {ln}" for i, ln in enumerate(out, 1)]


def _pretty_tac_lines_compact(tac_lines):
    """
    COMPACT pretty TAC (for --phase opt):
    - Does NOT expand expressions.
    - Normalizes '*' -> 'x' and 'uminus a'/'- a' -> '- a'.
    - Skips structural (func/label/goto/if/print/return) from numbering view,
      only shows assignments as a single line each.
    """
    def toks(s: str):
        return [p for p in s.replace(",", " , ").replace("(", " ( ").replace(")", " ) ").split() if p]

    lines = []
    for line in tac_lines:
        s = line.strip()
        if not s or s.startswith(("#","//")):
            continue
        if s.startswith(("func ","endfunc","label ","goto ","if ","print ","return")):
            # skip from numbered compact view (keep it strictly about assignments)
            continue
        if " = " not in s:
            continue

        lhs, rhs = [p.strip() for p in s.split("=", 1)]
        tk = toks(rhs)

        # copy / constant
        if len(tk) == 1:
            lines.append(f"{lhs} = {tk[0]}")
            continue

        # unary
        if len(tk) == 2 and tk[0].lower() in ("uminus","-"):
            lines.append(f"{lhs} = - {tk[1]}")
            continue

        # binary
        if len(tk) == 3:
            a, op, b = tk
            op_out = "x" if op == "*" else op
            lines.append(f"{lhs} = {a} {op_out} {b}")
            continue

        # fallback keep original
        lines.append(s)

    return [f"({i}) {ln}" for i, ln in enumerate(lines, 1)]

# ====== NEW: Readable ASM for --phase asm (keeps everything else unchanged) ======

_BINMAP = {"+": "ADD", "-": "SUB", "*": "MUL", "x": "MUL", "/": "DIV", "%": "MOD"}

def _toks(s: str):
    return [p for p in s.replace(",", " , ").replace("(", " ( ").replace(")", " ) ").split() if p]

def _format_readable_asm_from_tac(tac):
    """
    Convert TAC to the required readable ASM form:
    ;; function main
    main:
    MUL t3, a, b
    t4 = - t3
    ...
    MOV RET, r
    RET
    """
    out = []
    cur_fn = None

    def header(fn: str):
        out.append(";; function " + fn)
        out.append(f"{fn}:")

    for raw in tac:
        s = raw.strip()
        if not s:
            continue
        tk = _toks(s)

        # function header/footer
        if tk and tk[0] == "func":
            cur_fn = tk[1].rstrip(":")
            header(cur_fn)
            continue
        if s == "endfunc":
            cur_fn = None
            continue

        # labels / gotos (not needed in your example; include for completeness)
        if tk and tk[0] == "label" and len(tk) > 1:
            name = tk[1].rstrip(":")
            out.append(name + ":")
            continue
        if tk and tk[0] == "goto" and len(tk) > 1:
            out.append(f"JMP {tk[1]}")
            continue
        if tk and tk[0] == "if" and len(tk) >= 4:
            out.append(f"JNZ {tk[1]}, {tk[3]}")
            continue

        # return
        if tk and tk[0] == "return":
            if len(tk) == 1:
                out.append("RET")
            else:
                out.append(f"MOV RET, {tk[1]}")
                out.append("RET")
            continue

        # assignments
        if len(tk) >= 3 and tk[1] == "=":
            dst = tk[0]
            rhs = tk[2:]
            # copy / const
            if len(rhs) == 1:
                out.append(f"MOV {dst}, {rhs[0]}")
                continue
            # unary
            if len(rhs) == 2 and rhs[0] in {"uminus", "-"}:
                out.append(f"{dst} = - {rhs[1]}")
                continue
            # binary
            if len(rhs) == 3 and rhs[1] in {"+","-","*","/","%","x"}:
                a, op, b = rhs
                out.append(f"{_BINMAP[op]}, {dst}, {a}, {b}")
                # NOTE: if your earlier ASM wanted "ADD dst, a, b" (without comma after mnemonic),
                # change the previous line to: out.append(f"{_BINMAP[op]} {dst}, {a}, {b}")
                out[-1] = out[-1].replace(",,", ",")  # guard if formatting above changes
                continue

        # otherwise ignore/comment if needed

    return out

# ---------------- Utilities --------------

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception as ex:
        print(f"Failed to read file: {ex}", file=sys.stderr)
        sys.exit(1)

def load_sources(paths) -> str:
    # Concatenate many files into a single compilation unit.
    srcs = []
    for p in paths:
        text = read_text(p)
        if not text.endswith("\n"):
            text += "\n"
        srcs.append(text)
    return "".join(srcs)

# ---------------- Phases -----------------

def do_tokens(src: str) -> int:
    print_banner(banner_for_phase("tokens"))
    lx = Lexer(src)
    tokens, errors = lx.tokenize()
    for t in tokens:
        print(f"{t.kind:<10} '{t.lexeme}' ({t.line}:{t.col})")
    if errors:
        print("\nLEX ERRORS:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    return 0

def do_ast(src: str) -> int:
    print_banner(banner_for_phase("ast"))
    lx = Lexer(src)
    toks, lex_errs = lx.tokenize()
    ast, parse_errs = parse(toks)
    for e in lex_errs + parse_errs:
        print(e, file=sys.stderr)
    if not ast:
        return 1
    print(ast_to_string(ast))
    return 0 if not (lex_errs or parse_errs) else 1

def do_sema(src: str) -> int:
    print_banner(banner_for_phase("sema"))
    lx = Lexer(src)
    toks, lex_errs = lx.tokenize()
    ast, parse_errs = parse(toks)
    for e in lex_errs + parse_errs:
        print(e, file=sys.stderr)
    if not ast:
        return 1
    _, sema_errs, report = sema_analyze(ast)
    print(report)
    for e in sema_errs:
        print(e, file=sys.stderr)
    return 0 if not (lex_errs or parse_errs or sema_errs) else 1

def _tac_pipeline(src: str, do_opt: bool):
    lx = Lexer(src)
    toks, lex_errs = lx.tokenize()
    ast, parse_errs = parse(toks)
    errs = lex_errs + parse_errs
    if ast:
        _, sema_errs, _ = sema_analyze(ast)
        errs += sema_errs
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return None, errs
    tac, tac_errs = tac_generate(ast)
    if tac_errs:
        for e in tac_errs:
            print(e, file=sys.stderr)
        return None, tac_errs
    if do_opt:
        tac, _ = optimize_tac(tac)
    return (ast, tac), []

def do_tac(src: str, do_opt: bool=False) -> int:
    print_banner(banner_for_phase("tac") if not do_opt else banner_for_phase("opt"))
    res, errs = _tac_pipeline(src, do_opt)
    if errs or not res:
        return 1
    _, tac = res
    pretty = _pretty_tac_lines(tac)
    if pretty:
        for line in pretty:
            print(line)
    else:
        for i, raw in enumerate([l for l in tac if l.strip()], 1):
            print(f"({i}) {raw}")
    return 0

def do_opt(src: str) -> int:
    print_banner(banner_for_phase("opt"))
    res, errs = _tac_pipeline(src, do_opt=True)
    if errs or not res:
        return 1
    _, tac = res
    # Use COMPACT view for optimized TAC so you actually see the optimized form
    pretty = _pretty_tac_lines_compact(tac)
    if pretty:
        for line in pretty:
            print(line)
    else:
        for i, raw in enumerate([l for l in tac if l.strip()], 1):
            print(f"({i}) {raw}")
    return 0

def do_asm(src: str, do_opt: bool=False, dump_opt: bool=False) -> int:
    # EXACT banner required by your expected output (don’t change others)
    print("*******************************************************")
    print("**********    STACK-MACHINE ASSEMBLY    **********")
    print("*******************************************************")
    if do_opt and dump_opt:
        res, errs = _tac_pipeline(src, True)
        if not errs and res:
            _, tac = res
            print(";; --- OPTIMIZED TAC ---", file=sys.stderr)
            for line in tac:
                print(line, file=sys.stderr)

    res, errs = _tac_pipeline(src, do_opt)
    if errs or not res:
        return 1
    _, tac = res

    # Show the readable ASM (not the VM stack form) exactly as requested
    asm_pretty = _format_readable_asm_from_tac(tac)
    for line in asm_pretty:
        print(line)
    return 0

def do_run(src: str, do_opt: bool=False, dump_opt: bool=False) -> int:
    print_banner(banner_for_phase("run"))
    if do_opt and dump_opt:
        res, errs = _tac_pipeline(src, True)
        if not errs and res:
            _, tac = res
            print(";; --- OPTIMIZED TAC ---", file=sys.stderr)
            for line in tac:
                print(line, file=sys.stderr)

    res, errs = _tac_pipeline(src, do_opt)
    if errs or not res:
        return 1
    ast, tac = res
    sigs = build_signatures(ast)
    asm, cg_errs = lower_to_asm(tac, signatures=sigs)
    if cg_errs:
        for e in cg_errs:
            print(e, file=sys.stderr)
        return 1
    code, out = vm_run(asm, signatures=sigs)
    if code != 0:
        for line in out:
            print(line, file=sys.stderr)
        return code
    for line in out:
        print(line)
    return 0

# ---------------- Main -------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mini Compiler CLI")
    p.add_argument("files", nargs="+", help="input source files (one or more)")
    p.add_argument("--phase", choices=["tokens","ast","sema","tac","opt","asm","run"], required=True)
    p.add_argument("--opt", action="store_true", help="Enable optimizer for TAC/ASM/RUN phases")
    p.add_argument("--opt-dump", action="store_true", help="When used with --phase asm/run, print optimized TAC to stderr")
    p.add_argument("--status", action="store_true",
                   help="After --phase run, print a success/failure status line")
    args = p.parse_args(argv)

    paths = [Path(x) for x in args.files]
    for path in paths:
        if not path.exists() or not path.is_file():
            print(f"File not found: {path}", file=sys.stderr)
            return 1

    src = load_sources(paths)

    if args.phase == "tokens": return do_tokens(src)
    if args.phase == "ast":    return do_ast(src)
    if args.phase == "sema":   return do_sema(src)
    if args.phase == "tac":    return do_tac(src, do_opt=args.opt)
    if args.phase == "opt":    return do_opt(src)
    if args.phase == "asm":    return do_asm(src, do_opt=args.opt, dump_opt=args.opt_dump)
    if args.phase == "run":
        rc = do_run(src, do_opt=args.opt, dump_opt=args.opt_dump)
        if args.status:
            print("✅ Run successful" if rc == 0 else "❌ Run failed")
        return rc

    print("Unknown phase", file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
