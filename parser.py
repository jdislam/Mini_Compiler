from dataclasses import dataclass
from typing import List, Optional, Tuple

# ---------- AST Nodes ----------

@dataclass
class Span:
    line: int
    col: int

@dataclass
class TypeName:
    name: str
    span: Span

# Program
@dataclass
class VarDecl:
    span: Span
    type: TypeName
    name: str
    init: Optional['Expr']

@dataclass
class Param:
    type: TypeName
    name: str

@dataclass
class Block:
    span: Span
    stmts: List['Stmt']

@dataclass
class FuncDef:
    span: Span
    ret_type: TypeName
    name: str
    params: List[Param]
    body: Block

@dataclass
class Program:
    decls: List[VarDecl]
    funcs: List[FuncDef]

# Expr
class Expr: ...
@dataclass
class IntLiteral(Expr):
    value: int
    span: Span

@dataclass
class FloatLiteral(Expr):
    value: float
    span: Span

@dataclass
class BoolLiteral(Expr):
    value: bool
    span: Span

@dataclass
class CharLiteral(Expr):
    value: str  # single character (no quotes)
    span: Span

@dataclass
class StringLiteral(Expr):
    value: str  # raw content (no quotes)
    span: Span

@dataclass
class VarRef(Expr):
    name: str
    span: Span

@dataclass
class BinOp(Expr):
    lhs: Expr
    op: str
    rhs: Expr
    span: Span

@dataclass
class UnaryOp(Expr):
    op: str
    expr: Expr
    span: Span

@dataclass
class Call(Expr):
    name: str
    args: List[Expr]
    span: Span

# Stmt
class Stmt: ...
@dataclass
class Assign(Stmt):
    name: str
    expr: Expr
    span: Span

@dataclass
class ExprStmt(Stmt):
    expr: Expr
    span: Span

@dataclass
class IfStmt(Stmt):
    cond: Expr
    then_blk: Block
    else_blk: Optional[Block]
    span: Span

@dataclass
class WhileStmt(Stmt):
    cond: Expr
    body: Block
    span: Span

@dataclass
class ForStmt(Stmt):
    # NOTE: post is a statement now -> can be Assign or ExprStmt
    init: Optional[Stmt]      # VarDecl | Assign | ExprStmt | None
    cond: Optional[Expr]      # None => true
    post: Optional[Stmt]      # Assign | ExprStmt | None
    body: Block
    span: Span

@dataclass
class ReturnStmt(Stmt):
    expr: Optional[Expr]
    span: Span

# ---------- Tokens / TS ----------

@dataclass
class Token:
    kind: str
    lexeme: str
    line: int
    col: int

class TS:
    def __init__(self, toks: List[Token]):
        self.toks = toks
        self.i = 0

    def at(self) -> Token:
        return self.toks[self.i] if self.i < len(self.toks) else Token("EOF", "", -1, -1)

    def match(self, kind: str) -> bool:
        if self.at().kind == kind:
            self.i += 1
            return True
        return False

    def need(self, kind: str, errs: List[str], msg: str):
        if not self.match(kind):
            t = self.at()
            errs.append(f"ParseError: expected {msg} at {t.line}:{t.col} (saw {t.kind} '{t.lexeme}')")

# ---------- Parser ----------

class Parser:
    def __init__(self, toks: List[Token]):
        self.ts = TS(toks)
        self.errors: List[str] = []

    # entry
    def parse(self) -> Tuple[Optional[Program], List[str]]:
        decls: List[VarDecl] = []
        funcs: List[FuncDef] = []

        # globals (var decls or function defs)
        while self.ts.at().kind in ("INT_KW","BOOL_KW","VOID_KW","FLOAT_KW","CHAR_KW","STR_KW"):
            ty = self.type_name()
            idtok = self.ts.at()
            self.ts.need("ID", self.errors, "identifier")
            if self.ts.match("LPAREN"):
                params = self.params_opt()
                self.ts.need("RPAREN", self.errors, "')'")
                body = self.block()
                funcs.append(FuncDef(span=Span(idtok.line, idtok.col), ret_type=ty, name=idtok.lexeme, params=params, body=body))
            else:
                init = None
                if self.ts.match("ASSIGN"):
                    init = self.expr()
                self.ts.need("SEMI", self.errors, "';'")
                decls.append(VarDecl(span=Span(idtok.line, idtok.col), type=ty, name=idtok.lexeme, init=init))

        return (Program(decls=decls, funcs=funcs), self.errors)

    # helpers
    def type_name(self) -> TypeName:
        t = self.ts.at()
        if t.kind not in ("INT_KW","BOOL_KW","VOID_KW","FLOAT_KW","CHAR_KW","STR_KW"):
            self.errors.append(f"ParseError: expected type at {t.line}:{t.col}")
            self.ts.i += 1
            return TypeName("int", Span(t.line, t.col))
        self.ts.i += 1
        name = {"INT_KW":"int","BOOL_KW":"bool","VOID_KW":"void","FLOAT_KW":"float","CHAR_KW":"char","STR_KW":"string"}[t.kind]
        return TypeName(name, Span(t.line, t.col))

    def params_opt(self) -> List[Param]:
        res: List[Param] = []
        if self.ts.at().kind in ("INT_KW","BOOL_KW","VOID_KW","FLOAT_KW","CHAR_KW","STR_KW"):
            while True:
                ty = self.type_name()
                idt = self.ts.at(); self.ts.need("ID", self.errors, "identifier")
                res.append(Param(ty, idt.lexeme))
                if not self.ts.match("COMMA"):
                    break
        return res

    def block(self) -> Block:
        t = self.ts.at()
        self.ts.need("LBRACE", self.errors, "'{'")
        body: List[Stmt] = []
        while self.ts.at().kind not in ("RBRACE","EOF"):
            body.append(self.stmt())
        self.ts.need("RBRACE", self.errors, "'}'")
        return Block(span=Span(t.line, t.col), stmts=body)

    # small helper for assignment statement
    def parse_assignment_stmt(self) -> Assign:
        name_tok = self.ts.at()  # ID
        self.ts.i += 1
        self.ts.need("ASSIGN", self.errors, "'='")
        rhs = self.expr()
        return Assign(name=name_tok.lexeme, expr=rhs, span=Span(name_tok.line, name_tok.col))

    def stmt(self) -> Stmt:
        t = self.ts.at()
        k = t.kind

        # var decl (all supported types)
        if k in ("INT_KW","BOOL_KW","VOID_KW","FLOAT_KW","CHAR_KW","STR_KW"):
            ty = self.type_name()
            idt = self.ts.at(); self.ts.need("ID", self.errors, "identifier")
            init = None
            if self.ts.match("ASSIGN"):
                init = self.expr()
            self.ts.need("SEMI", self.errors, "';'")
            return VarDecl(span=Span(idt.line, idt.col), type=ty, name=idt.lexeme, init=init)

        # print(expr);   (parsed as a call wrapped in ExprStmt)
        if k == "PRINT_KW":
            self.ts.i += 1
            self.ts.need("LPAREN", self.errors, "'('")
            arg = self.expr()
            self.ts.need("RPAREN", self.errors, "')'")
            self.ts.need("SEMI", self.errors, "';'")
            return ExprStmt(expr=Call("print", [arg], Span(t.line, t.col)), span=Span(t.line, t.col))

        if k == "IF_KW":
            self.ts.i += 1
            self.ts.need("LPAREN", self.errors, "'('")
            cond = self.expr()
            self.ts.need("RPAREN", self.errors, "')'")
            then_blk = self.block()
            else_blk = None
            if self.ts.match("ELSE_KW"):
                else_blk = self.block()
            return IfStmt(cond, then_blk, else_blk, Span(t.line, t.col))

        if k == "WHILE_KW":
            self.ts.i += 1
            self.ts.need("LPAREN", self.errors, "'('")
            cond = self.expr()
            self.ts.need("RPAREN", self.errors, "')'")
            body = self.block()
            return WhileStmt(cond, body, Span(t.line, t.col))

        if k == "FOR_KW":
            self.ts.i += 1
            self.ts.need("LPAREN", self.errors, "'('")

            # init: VarDecl | Assign | Expr | empty
            init_stmt: Optional[Stmt] = None
            if self.ts.at().kind != "SEMI":
                if self.ts.at().kind in ("INT_KW","BOOL_KW","VOID_KW","FLOAT_KW","CHAR_KW","STR_KW"):
                    ty = self.type_name()
                    idt = self.ts.at(); self.ts.need("ID", self.errors, "identifier")
                    init_expr = None
                    if self.ts.match("ASSIGN"):
                        init_expr = self.expr()
                    self.ts.need("SEMI", self.errors, "';'")
                    init_stmt = VarDecl(span=Span(idt.line, idt.col), type=ty, name=idt.lexeme, init=init_expr)
                else:
                    if self.ts.at().kind == "ID" and (self.ts.i + 1) < len(self.ts.toks) and self.ts.toks[self.ts.i+1].kind == "ASSIGN":
                        asg = self.parse_assignment_stmt()
                        self.ts.need("SEMI", self.errors, "';'")
                        init_stmt = asg
                    else:
                        e0 = self.expr()
                        self.ts.need("SEMI", self.errors, "';'")
                        init_stmt = ExprStmt(e0, Span(t.line, t.col))
            else:
                self.ts.need("SEMI", self.errors, "';'")

            # cond: Expr | empty
            cond: Optional[Expr] = None
            if self.ts.at().kind != "SEMI":
                cond = self.expr()
            self.ts.need("SEMI", self.errors, "';'")

            # post: Assign | Expr | empty
            post_stmt: Optional[Stmt] = None
            if self.ts.at().kind != "RPAREN":
                if self.ts.at().kind == "ID" and (self.ts.i + 1) < len(self.ts.toks) and self.ts.toks[self.ts.i+1].kind == "ASSIGN":
                    post_stmt = self.parse_assignment_stmt()
                else:
                    e1 = self.expr()
                    post_stmt = ExprStmt(e1, Span(self.ts.at().line, self.ts.at().col))
            self.ts.need("RPAREN", self.errors, "')'")

            body = self.block()
            return ForStmt(init_stmt, cond, post_stmt, body, Span(t.line, t.col))

        if k == "RETURN_KW":
            self.ts.i += 1
            expr = None
            if self.ts.at().kind not in ("SEMI","RBRACE"):
                expr = self.expr()
            self.ts.need("SEMI", self.errors, "';'")
            return ReturnStmt(expr, Span(t.line, t.col))

        # assignment stmt
        if k == "ID" and (self.ts.i + 1) < len(self.ts.toks) and self.ts.toks[self.ts.i+1].kind == "ASSIGN":
            asg = self.parse_assignment_stmt()
            self.ts.need("SEMI", self.errors, "';'")
            return asg

        # expr stmt
        e = self.expr()
        self.ts.need("SEMI", self.errors, "';'")
        return ExprStmt(e, Span(t.line, t.col))

    # -------- Expressions with precedence --------

    def expr(self) -> Expr:
        return self.e_or()

    def e_or(self) -> Expr:
        e = self.e_and()
        while self.ts.match("OROR"):
            rhs = self.e_and()
            e = BinOp(e, "||", rhs, Span(self.ts.at().line, self.ts.at().col))
        return e

    def e_and(self) -> Expr:
        e = self.e_eq()
        while self.ts.match("ANDAND"):
            rhs = self.e_eq()
            e = BinOp(e, "&&", rhs, Span(self.ts.at().line, self.ts.at().col))
        return e

    def e_eq(self) -> Expr:
        e = self.e_rel()
        while self.ts.at().kind in ("EQEQ","NEQ"):
            if self.ts.match("EQEQ"):
                rhs = self.e_rel()
                e = BinOp(e, "==", rhs, Span(self.ts.at().line, self.ts.at().col))
            elif self.ts.match("NEQ"):
                rhs = self.e_rel()
                e = BinOp(e, "!=", rhs, Span(self.ts.at().line, self.ts.at().col))
        return e

    def e_rel(self) -> Expr:
        e = self.e_add()
        while self.ts.at().kind in ("LT","LE","GT","GE"):
            t = self.ts.at(); self.ts.i += 1
            m = {"LT":"<","LE":"<=","GT":">","GE":">="}[t.kind]
            rhs = self.e_add()
            e = BinOp(e, m, rhs, Span(t.line, t.col))
        return e

    def e_add(self) -> Expr:
        e = self.e_mul()
        while self.ts.at().kind in ("PLUS","MINUS"):
            op = "+" if self.ts.match("PLUS") else "-"
            rhs = self.e_mul()
            e = BinOp(e, op, rhs, Span(self.ts.at().line, self.ts.at().col))
        return e

    def e_mul(self) -> Expr:
        e = self.e_un()
        while self.ts.at().kind in ("STAR","SLASH","PERCENT"):
            k = self.ts.at().kind; self.ts.i += 1
            op = {"STAR":"*","SLASH":"/","PERCENT":"%"}[k]
            rhs = self.e_un()
            e = BinOp(e, op, rhs, Span(self.ts.at().line, self.ts.at().col))
        return e

    def e_un(self) -> Expr:
        if self.ts.match("MINUS"):
            e = self.e_un()
            return UnaryOp("uminus", e, Span(self.ts.at().line, self.ts.at().col))
        if self.ts.match("NOT"):
            e = self.e_un()
            return UnaryOp("!", e, Span(self.ts.at().line, self.ts.at().col))
        return self.e_primary()

    def e_primary(self) -> Expr:
        t = self.ts.at()
        if t.kind == "INT":
            self.ts.i += 1
            return IntLiteral(int(t.lexeme), Span(t.line, t.col))
        if t.kind == "FLOAT":
            self.ts.i += 1
            return FloatLiteral(float(t.lexeme), Span(t.line, t.col))
        if t.kind == "TRUE_KW":
            self.ts.i += 1
            return BoolLiteral(True, Span(t.line, t.col))
        if t.kind == "FALSE_KW":
            self.ts.i += 1
            return BoolLiteral(False, Span(t.line, t.col))
        if t.kind == "STRING":
            self.ts.i += 1
            return StringLiteral(t.lexeme[1:-1], Span(t.line, t.col))
        if t.kind == "CHAR":
            self.ts.i += 1
            return CharLiteral(t.lexeme[1:-1], Span(t.line, t.col))
        if t.kind == "ID":
            name = t.lexeme; self.ts.i += 1
            if self.ts.match("LPAREN"):
                args: List[Expr] = []
                if self.ts.at().kind != "RPAREN":
                    args.append(self.expr())
                    while self.ts.match("COMMA"):
                        args.append(self.expr())
                self.ts.need("RPAREN", self.errors, "')'")
                return Call(name, args, Span(t.line, t.col))
            return VarRef(name, Span(t.line, t.col))
        if t.kind == "LPAREN":
            self.ts.i += 1
            e = self.expr()
            self.ts.need("RPAREN", self.errors, "')'")
            return e
        self.errors.append(f"ParseError: unexpected token {t.kind} '{t.lexeme}' at {t.line}:{t.col}")
        self.ts.i += 1
        return IntLiteral(0, Span(t.line, t.col))

# Public API
def parse(tokens: List[Token]) -> Tuple[Optional[Program], List[str]]:
    return Parser(tokens).parse()

def ast_to_string(ast: Program) -> str:
    lines = []
    for d in ast.decls:
        init = " = <expr>" if d.init else ""
        lines.append(f"{d.type.name} {d.name}{init};")
    for f in ast.funcs:
        ps = ", ".join(f"{p.type.name} {p.name}" for p in f.params)
        lines.append(f"{f.ret_type.name} {f.name}({ps}) {{ ... }}")

    return "\n".join(lines)
