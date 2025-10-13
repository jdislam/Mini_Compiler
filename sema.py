# sema.py — Semantic analysis (symbol table + type checking)
# - Types: int, float, bool, char, string, void
# - Built-in functions (hidden from printed symbol table): print/println/printc/printlnc/prints
# - For-loop: init may be VarDecl/Assign/ExprStmt; post may be Assign/ExprStmt
# - Allows bare 'return;' in int functions
# - Report prints a SYMBOL TABLE (globals, then per-function params/locals)

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# --- dual import for parser types ---
try:
    from parser import (
        Program, FuncDef, VarDecl, Block, Assign, ExprStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt,
        Expr, IntLiteral, FloatLiteral, BoolLiteral, CharLiteral, StringLiteral,
        VarRef, BinOp, UnaryOp, Call, TypeName, Span
    )
except ImportError:
    from .parser import (
        Program, FuncDef, VarDecl, Block, Assign, ExprStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt,
        Expr, IntLiteral, FloatLiteral, BoolLiteral, CharLiteral, StringLiteral,
        VarRef, BinOp, UnaryOp, Call, TypeName, Span
    )

@dataclass
class Symbol:
    name: str
    kind: str              # "var" | "func"
    ty: str                # "int" | "bool" | "void" | "float" | "char" | "string"
    params: Optional[List[str]] = None
    span: Optional[Span] = None

class SymbolTable:
    def __init__(self):
        self.scopes: List[Dict[str, Symbol]] = [{}]

    def push(self): self.scopes.append({})
    def pop(self):  self.scopes.pop()

    def declare(self, sym: Symbol, errors: List[str]):
        cur = self.scopes[-1]
        if sym.name in cur:
            at = f"{sym.span.line}:{sym.span.col}" if sym.span else "?:?"
            errors.append(f"SemanticError: redeclaration of '{sym.name}' at {at}")
        else:
            cur[sym.name] = sym

    def lookup(self, name: str) -> Optional[Symbol]:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return None

class Sema:
    def __init__(self):
        self.tab = SymbolTable()
        self.errors: List[str] = []
        self.fn_locals: Dict[str, Dict[str, Symbol]] = {}
        self._builtin_names = {"print", "println", "printc", "printlnc", "prints"}

    def analyze(self, prog: Program) -> Tuple[SymbolTable, List[str], str]:
        # built-ins (hidden from printed symbol table, but used for checking)
        for b in [
            Symbol("print",   "func", "void", ["float"]),
            Symbol("println", "func", "void", ["float"]),
            Symbol("printc",  "func", "void", ["int"]),
            Symbol("printlnc","func", "void", ["int"]),
            Symbol("prints",  "func", "void", ["string"]),
        ]:
            self.tab.declare(b, self.errors)

        # predeclare user functions
        for fn in prog.funcs:
            argtys = [p.type.name for p in fn.params]
            self.tab.declare(Symbol(fn.name, "func", fn.ret_type.name, argtys, fn.span), self.errors)

        # globals
        for d in prog.decls:
            self.tab.declare(Symbol(d.name, "var", d.type.name, span=d.span), self.errors)

        # functions
        for fn in prog.funcs:
            self._analyze_func(fn)

        # build symbol-table printout
        report = self._report_symbol_table(prog)
        return self.tab, self.errors, report

    def _analyze_func(self, fn: FuncDef):
        self.tab.push()
        # params
        for p in fn.params:
            self.tab.declare(Symbol(p.name, "var", p.type.name, span=fn.span), self.errors)
        # body
        self._analyze_block(fn.body, ret_ty=fn.ret_type.name)
        # snapshot locals for reporting
        self.fn_locals[fn.name] = dict(self.tab.scopes[-1])
        self.tab.pop()

    def _analyze_block(self, blk: Block, ret_ty: str):
        for st in blk.stmts:
            if isinstance(st, VarDecl):
                self.tab.declare(Symbol(st.name, "var", st.type.name, span=st.span), self.errors)
                if st.init:
                    vt = self._expr(st.init)
                    if st.type.name == "float" and vt == "int":
                        pass
                    elif vt and vt != st.type.name:
                        self.errors.append(
                            f"SemanticError: cannot init '{st.name}' ({st.type.name}) with {vt} at {st.span.line}:{st.span.col}"
                        )
            elif isinstance(st, Assign):
                vt = self._expr(st.expr)
                sym = self.tab.lookup(st.name)
                if not sym:
                    self.errors.append(f"SemanticError: '{st.name}' not declared at {st.span.line}:{st.span.col}")
                else:
                    if sym.ty == "float" and vt == "int":
                        pass
                    elif vt and sym.ty and vt != sym.ty:
                        self.errors.append(
                            f"SemanticError: type mismatch assigning {vt} to {sym.ty} at {st.span.line}:{st.span.col}"
                        )
            elif isinstance(st, ExprStmt):
                self._expr(st.expr)
            elif isinstance(st, IfStmt):
                ct = self._expr(st.cond)
                if ct and ct != "bool":
                    self.errors.append(f"SemanticError: if condition must be bool at {st.span.line}:{st.span.col}")
                self._analyze_block(st.then_blk, ret_ty)
                if st.else_blk:
                    self._analyze_block(st.else_blk, ret_ty)
            elif isinstance(st, WhileStmt):
                ct = self._expr(st.cond)
                if ct and ct != "bool":
                    self.errors.append(f"SemanticError: while condition must be bool at {st.span.line}:{st.span.col}")
                self._analyze_block(st.body, ret_ty)
            elif isinstance(st, ForStmt):
                # init
                if isinstance(st.init, VarDecl):
                    self.tab.declare(Symbol(st.init.name, "var", st.init.type.name, span=st.init.span), self.errors)
                    if st.init.init:
                        self._expr(st.init.init)
                elif isinstance(st.init, Assign):
                    self._expr(st.init.expr)
                elif isinstance(st.init, ExprStmt):
                    self._expr(st.init.expr)

                # cond
                if st.cond is not None:
                    ct = self._expr(st.cond)
                    if ct and ct != "bool":
                        self.errors.append(f"SemanticError: for condition must be bool at {st.span.line}:{st.span.col}")

                # body
                self._analyze_block(st.body, ret_ty)

                # post
                if isinstance(st.post, Assign):
                    self._expr(st.post.expr)
                elif isinstance(st.post, ExprStmt):
                    self._expr(st.post.expr)
            elif isinstance(st, ReturnStmt):
                if st.expr is None:
                    # allow bare return; in int functions (per earlier request)
                    if ret_ty != "void" and ret_ty != "int":
                        self.errors.append(
                            f"SemanticError: non-void function must return a value at {st.span.line}:{st.span.col}"
                        )
                else:
                    vt = self._expr(st.expr)
                    if ret_ty == "float" and vt == "int":
                        pass
                    elif ret_ty != "void" and vt and ret_ty != vt:
                        self.errors.append(
                            f"SemanticError: return {vt} in function returning {ret_ty} at {st.span.line}:{st.span.col}"
                        )

    # ---- expressions
    def _expr(self, e: Expr) -> Optional[str]:
        if isinstance(e, IntLiteral):    return "int"
        if isinstance(e, FloatLiteral):  return "float"
        if isinstance(e, BoolLiteral):   return "bool"
        if isinstance(e, CharLiteral):   return "char"
        if isinstance(e, StringLiteral): return "string"

        if isinstance(e, VarRef):
            sym = self.tab.lookup(e.name)
            if not sym:
                self.errors.append(f"SemanticError: '{e.name}' not declared at {e.span.line}:{e.span.col}")
                return None
            return sym.ty

        if isinstance(e, UnaryOp):
            t = self._expr(e.expr)
            if e.op == "uminus":
                if t in ("int","float"):
                    return t
                self.errors.append(f"SemanticError: unary '-' requires numeric at {e.span.line}:{e.span.col}")
                return None
            if e.op == "!":
                if t == "bool":
                    return "bool"
                self.errors.append(f"SemanticError: '!' requires bool at {e.span.line}:{e.span.col}")
                return None

        if isinstance(e, BinOp):
            lt = self._expr(e.lhs)
            rt = self._expr(e.rhs)
            if e.op in ("+","-","*","/"):
                if lt not in ("int","float") or rt not in ("int","float"):
                    self.errors.append(f"SemanticError: arithmetic '{e.op}' requires numeric at {e.span.line}:{e.span.col}")
                    return None
                return "float" if "float" in (lt, rt) else "int"
            if e.op == "%":
                if lt != "int" or rt != "int":
                    self.errors.append(f"SemanticError: '%' requires int at {e.span.line}:{e.span.col}")
                    return None
                return "int"
            if e.op in ("&&","||"):
                if lt != "bool" or rt != "bool":
                    self.errors.append(f"SemanticError: logical op requires bool at {e.span.line}:{e.span.col}")
                    return None
                return "bool"
            if e.op in ("<","<=",">",">=","==","!="):
                if (lt in ("int","float") and rt in ("int","float")) or (lt=="bool" and rt=="bool"):
                    return "bool"
                if e.op in ("==","!=") and lt == rt and lt in ("char","string"):
                    return "bool"
                self.errors.append(f"SemanticError: comparison between incompatible types at {e.span.line}:{e.span.col}")
                return None

        if isinstance(e, Call):
            # built-ins allowed
            if e.name in ("print","println"):
                if len(e.args) != 1:
                    self.errors.append(f"SemanticError: {e.name} takes 1 arg at {e.span.line}:{e.span.col}")
                else:
                    at = self._expr(e.args[0])
                    if at not in ("int","bool","float","char","string"):
                        self.errors.append(f"SemanticError: {e.name} supports int/bool/float/char/string at {e.span.line}:{e.span.col}")
                return "void"
            if e.name in ("printc","printlnc"):
                if len(e.args) != 1:
                    self.errors.append(f"SemanticError: {e.name} takes 1 arg at {e.span.line}:{e.span.col}")
                else:
                    at = self._expr(e.args[0])
                    if at not in ("int","char"):
                        self.errors.append(f"SemanticError: {e.name} expects int/char at {e.span.line}:{e.span.col}")
                return "void"
            if e.name == "prints":
                if len(e.args) != 1:
                    self.errors.append(f"SemanticError: prints takes 1 arg at {e.span.line}:{e.span.col}")
                else:
                    at = self._expr(e.args[0])
                    if at != "string":
                        self.errors.append(f"SemanticError: prints expects string at {e.span.line}:{e.span.col}")
                return "void"

            sym = self.tab.lookup(e.name)
            if sym and sym.kind == "func":
                if sym.params is not None and len(e.args) != len(sym.params):
                    self.errors.append(f"SemanticError: function '{e.name}' expects {len(sym.params)} args at {e.span.line}:{e.span.col}")
                else:
                    for i, (arg, pty) in enumerate(zip(e.args, sym.params or []), 1):
                        at = self._expr(arg)
                        if at != pty:
                            self.errors.append(f"SemanticError: arg {i} to '{e.name}' is {at}, expected {pty} at {e.span.line}:{e.span.col}")
                return sym.ty

            self.errors.append(f"SemanticError: call to unknown function '{e.name}' at {e.span.line}:{e.span.col}")
            return None

        return None

    # ---- reporting
    def _report_symbol_table(self, prog: Program) -> str:
        lines: List[str] = []
        lines.append("SYMBOL TABLE\n")
        lines.append("------------\n")
        globals_scope = self.tab.scopes[0]
        user_funcs = []
        lines.append("Globals:\n")
        for name, sym in sorted(globals_scope.items()):
            if sym.kind == "var":
                lines.append(f"  var   {name} : {sym.ty}\n")
            elif sym.kind == "func" and name not in self._builtin_names:
                params = ", ".join(sym.params or [])
                lines.append(f"  func  {name}({params}) : {sym.ty}\n")
                user_funcs.append(name)
        lines.append("\n")
        for fn in sorted(user_funcs):
            sym = globals_scope[fn]
            params = sym.params or []
            lines.append(f"Function: {fn}\n")
            if params:
                lines.append("  params:\n")
                func_obj = next(f for f in prog.funcs if f.name == fn)
                for p_ast, p_ty in zip(func_obj.params, params):
                    lines.append(f"    {p_ast.name} : {p_ty}\n")
            else:
                lines.append("  params: (none)\n")
            scope = self.fn_locals.get(fn, {})
            param_names = set(next(f for f in prog.funcs if f.name == fn).params[i].name for i in range(len(params))) if params else set()
            locals_list = [(nm, s.ty) for nm, s in scope.items() if s.kind == "var" and nm not in param_names]
            if locals_list:
                lines.append("  locals:\n")
                for nm, ty in sorted(locals_list):
                    lines.append(f"    {nm} : {ty}\n")
            else:
                lines.append("  locals: (none)\n")
            lines.append("\n")
        lines.append("OK: no semantic errors.\n")
        return "".join(lines)

# Public API
def analyze(program: Program):
    return Sema().analyze(program)