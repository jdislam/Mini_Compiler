
# __init__.py
from .lexer import Lexer
from .parser import parse, ast_to_string
from .sema import analyze as sema_analyze
from .tac import generate as tac_generate
from .codegen import build_signatures, lower_to_asm
from .vm import run as vm_run
from .optimizer import optimize_tac

def compile_and_run(source: str, optimize: bool = False):
    lx = Lexer(source)
    toks, lex_errs = lx.tokenize()
    ast, parse_errs = parse(toks)
    if lex_errs or parse_errs or not ast:
        return 1, [*(str(e) for e in lex_errs), *(str(e) for e in parse_errs)]
    _, sema_errs, _ = sema_analyze(ast)
    if sema_errs:
        return 1, [str(e) for e in sema_errs]
    tac, tac_errs = tac_generate(ast)
    if tac_errs:
        return 1, [str(e) for e in tac_errs]
    if optimize:
        tac, _ = optimize_tac(tac)
    sigs = build_signatures(ast)
    asm, cg_errs = lower_to_asm(tac, signatures=sigs)
    if cg_errs:
        return 1, [str(e) for e in cg_errs]
    return vm_run(asm, signatures=sigs)
