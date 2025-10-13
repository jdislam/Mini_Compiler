from typing import List, Tuple
# --- dual import for parser types ---
try:
    from parser import (
        Program, FuncDef, VarDecl, Block, Assign, ExprStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt,
        Expr, IntLiteral, FloatLiteral, BoolLiteral, CharLiteral, StringLiteral,
        VarRef, BinOp, UnaryOp, Call
    )
except ImportError:
    from .parser import (
        Program, FuncDef, VarDecl, Block, Assign, ExprStmt, IfStmt, WhileStmt, ForStmt, ReturnStmt,
        Expr, IntLiteral, FloatLiteral, BoolLiteral, CharLiteral, StringLiteral,
        VarRef, BinOp, UnaryOp, Call
    )

class TACGen:
    def __init__(self):
        self.tac: List[str] = []
        self.temp_i = 0
        self.errors: List[str] = []

    def t(self) -> str:
        self.temp_i += 1
        return f"t{self.temp_i}"

    def generate(self, prog: Program) -> Tuple[List[str], List[str]]:
        for d in prog.decls:
            if d.init is not None:
                v = self.emit_expr(d.init)
                self.tac.append(f"{d.name} = {v}")
        for f in prog.funcs:
            self.emit_func(f)
        return self.tac, self.errors

    def emit_func(self, fn: FuncDef):
        self.tac.append(f"func {fn.name}:")
        self.emit_block(fn.body)
        self.tac.append("endfunc")

    def emit_block(self, blk: Block):
        for st in blk.stmts:
            if isinstance(st, VarDecl):
                if st.init is not None:
                    v = self.emit_expr(st.init)
                    self.tac.append(f"{st.name} = {v}")
            elif isinstance(st, Assign):
                v = self.emit_expr(st.expr)
                self.tac.append(f"{st.name} = {v}")
            elif isinstance(st, ExprStmt):
                self.emit_expr(st.expr, discard=True)
            elif isinstance(st, IfStmt):
                cond = self.emit_expr(st.cond)
                L_then = f"L{self.t()}"; L_else = f"L{self.t()}"; L_end  = f"L{self.t()}"
                self.tac.append(f"if {cond} goto {L_then}")
                self.tac.append(f"goto {L_else}")
                self.tac.append(f"label {L_then}:")
                self.emit_block(st.then_blk)
                self.tac.append(f"goto {L_end}")
                self.tac.append(f"label {L_else}:")
                if st.else_blk:
                    self.emit_block(st.else_blk)
                self.tac.append(f"label {L_end}:")
            elif isinstance(st, WhileStmt):
                L_head = f"L{self.t()}"; L_body = f"L{self.t()}"; L_end = f"L{self.t()}"
                self.tac.append(f"label {L_head}:")
                cond = self.emit_expr(st.cond)
                self.tac.append(f"if {cond} goto {L_body}")
                self.tac.append(f"goto {L_end}")
                self.tac.append(f"label {L_body}:")
                self.emit_block(st.body)
                self.tac.append(f"goto {L_head}")
                self.tac.append(f"label {L_end}:")
            elif isinstance(st, ForStmt):
                # init
                if isinstance(st.init, VarDecl):
                    vinit = self.emit_expr(st.init.init) if st.init.init is not None else None
                    if vinit is not None:
                        self.tac.append(f"{st.init.name} = {vinit}")
                elif isinstance(st.init, Assign):
                    v = self.emit_expr(st.init.expr)
                    self.tac.append(f"{st.init.name} = {v}")
                elif isinstance(st.init, ExprStmt):
                    self.emit_expr(st.init.expr, discard=True)

                # loop
                L_head = f"L{self.t()}"; L_body = f"L{self.t()}"; L_end = f"L{self.t()}"
                self.tac.append(f"label {L_head}:")
                if st.cond is not None:
                    c = self.emit_expr(st.cond)
                    self.tac.append(f"if {c} goto {L_body}")
                    self.tac.append(f"goto {L_end}")
                else:
                    self.tac.append(f"goto {L_body}")
                self.tac.append(f"label {L_body}:")
                self.emit_block(st.body)

                # post
                if isinstance(st.post, Assign):
                    v = self.emit_expr(st.post.expr)
                    self.tac.append(f"{st.post.name} = {v}")
                elif isinstance(st.post, ExprStmt):
                    self.emit_expr(st.post.expr, discard=True)

                self.tac.append(f"goto {L_head}")
                self.tac.append(f"label {L_end}:")
            elif isinstance(st, ReturnStmt):
                if st.expr is None:
                    self.tac.append("return")
                else:
                    v = self.emit_expr(st.expr)
                    self.tac.append(f"return {v}")

    def emit_expr(self, e: Expr, discard: bool = False) -> str:
        if isinstance(e, IntLiteral):   return str(e.value)
        if isinstance(e, FloatLiteral): return repr(float(e.value))
        if isinstance(e, BoolLiteral):  return "1" if e.value else "0"
        if isinstance(e, CharLiteral):
            ch = e.value.replace("\\", "\\\\").replace("'", "\\'").replace("\n","\\n").replace("\t","\\t").replace("\r","\\r")
            return "'" + ch + "'"
        if isinstance(e, StringLiteral):
            s = e.value.replace("\\", "\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\t","\\t").replace("\r","\\r")
            return "\"" + s + "\""
        if isinstance(e, VarRef):       return e.name

        if isinstance(e, UnaryOp):
            a = self.emit_expr(e.expr)
            if discard: return a
            t = self.t()
            if e.op == "uminus":
                self.tac.append(f"{t} = uminus {a}")
            elif e.op == "!":
                z = self.t()
                self.tac.append(f"{z} = {a} == 0")
                return z
            else:
                self.errors.append(f"Unknown unary op {e.op}")
            return t

        if isinstance(e, BinOp):
            # Short-circuit logical ops expanded into labels:
            if e.op == "&&":
                a = self.emit_expr(e.lhs)
                b = self.emit_expr(e.rhs)
                t = self.t()
                L_set1 = f"L{self.t()}"; L_end = f"L{self.t()}"
                # t = 0; set to 1 only if both a and b are true
                self.tac.append(f"{t} = 0")
                self.tac.append(f"if {a} goto {L_set1}")
                self.tac.append(f"goto {L_end}")
                self.tac.append(f"label {L_set1}:")
                # need to check b as well
                L_set1b = f"L{self.t()}"; L_after = f"L{self.t()}"
                self.tac.append(f"if {b} goto {L_set1b}")
                self.tac.append(f"goto {L_end}")
                self.tac.append(f"label {L_set1b}:")
                self.tac.append(f"{t} = 1")
                self.tac.append(f"label {L_end}:")
                return t

            if e.op == "||":
                a = self.emit_expr(e.lhs)
                b = self.emit_expr(e.rhs)
                t = self.t()
                L_set1 = f"L{self.t()}"; L_end = f"L{self.t()}"
                # t = 0; set to 1 if a or b is true
                self.tac.append(f"{t} = 0")
                self.tac.append(f"if {a} goto {L_set1}")
                self.tac.append(f"if {b} goto {L_set1}")
                self.tac.append(f"goto {L_end}")
                self.tac.append(f"label {L_set1}:")
                self.tac.append(f"{t} = 1")
                self.tac.append(f"label {L_end}:")
                return t

            a = self.emit_expr(e.lhs)
            b = self.emit_expr(e.rhs)
            if discard: return a
            t = self.t()
            self.tac.append(f"{t} = {a} {e.op} {b}")
            return t

        if isinstance(e, Call):
            if e.name == "print" and len(e.args) == 1:
                v = self.emit_expr(e.args[0])
                self.tac.append(f"print {v}")
                return v
            # user-defined functions not lowered here (can be added later)
            self.errors.append(f"Unsupported call '{e.name}'")
            return "0"

        self.errors.append("Unknown expression")
        return "0"

def generate(ast: Program) -> Tuple[List[str], List[str]]:

    return TACGen().generate(ast)
