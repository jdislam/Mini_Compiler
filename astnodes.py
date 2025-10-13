# astnodes.py
# AST node definitions + pretty printer for debugging `--phase ast`.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Union

# ---------- Source span ----------

@dataclass(frozen=True)
class Span:
    line: int
    col: int

# ---------- Base node ----------

@dataclass
class Node:
    span: Span

# ---------- Program structure ----------

@dataclass
class Program(Node):
    decls: List["VarDecl"] = field(default_factory=list)
    funcs: List["FuncDef"] = field(default_factory=list)

@dataclass
class TypeNode(Node):
    name: str  # "int" | "bool" | "void"

@dataclass
class VarDecl(Node):
    type: TypeNode
    name: str
    init: Optional["Expr"] = None

@dataclass
class Param(Node):
    type: TypeNode
    name: str

@dataclass
class FuncDef(Node):
    ret_type: TypeNode
    name: str
    params: List[Param]
    body: "Block"

# ---------- Statements ----------

@dataclass
class Block(Node):
    stmts: List["Stmt"] = field(default_factory=list)

# Marker type for unions
class Stmt(Node):  # noqa: E701 (intentional single-line base)
    pass

@dataclass
class StmtDecl(Stmt):   # local variable declaration inside a block
    decl: VarDecl

@dataclass
class Assign(Stmt):
    name: str
    value: "Expr"

@dataclass
class If(Stmt):
    cond: "Expr"
    then_blk: Block
    else_blk: Optional[Block] = None

@dataclass
class While(Stmt):
    cond: "Expr"
    body: Block

@dataclass
class Return(Stmt):
    value: Optional["Expr"] = None

@dataclass
class Print(Stmt):
    value: "Expr"

# ---------- Expressions ----------

class Expr(Node):  # base class
    pass

@dataclass
class LiteralInt(Expr):
    value: int

@dataclass
class LiteralBool(Expr):
    value: bool

@dataclass
class Var(Expr):
    name: str

@dataclass
class Unary(Expr):
    op: str     # '!' or '-'
    rhs: Expr

@dataclass
class Binary(Expr):
    op: str     # '+','-','*','/','%','==','!=','<','<=','>','>=','&&','||'
    lhs: Expr
    rhs: Expr

@dataclass
class Call(Expr):
    name: str
    args: List[Expr]

# ---------- Pretty printer ----------

def _indent(s: int) -> str:
    return "  " * s

def print_ast(node: Node, depth: int = 0) -> str:
    """Return a human-readable tree."""
    I = _indent(depth)

    if isinstance(node, Program):
        out = [f"{I}Program"]
        if node.decls:
            out.append(f"{I}  Decls:")
            for d in node.decls:
                out.append(print_ast(d, depth + 2))
        if node.funcs:
            out.append(f"{I}  Funcs:")
            for f in node.funcs:
                out.append(print_ast(f, depth + 2))
        return "\n".join(out)

    if isinstance(node, VarDecl):
        base = f"{I}VarDecl {node.type.name} {node.name}"
        if node.init:
            return base + "\n" + print_ast(node.init, depth + 1)
        return base

    if isinstance(node, TypeNode):
        return f"{I}Type {node.name}"

    if isinstance(node, Param):
        return f"{I}Param {node.type.name} {node.name}"

    if isinstance(node, FuncDef):
        out = [f"{I}Func {node.ret_type.name} {node.name}"]
        if node.params:
            out.append(f"{I}  Params:")
            for p in node.params:
                out.append(print_ast(p, depth + 2))
        out.append(print_ast(node.body, depth + 1))
        return "\n".join(out)

    if isinstance(node, Block):
        out = [f"{I}Block"]
        for s in node.stmts:
            out.append(print_ast(s, depth + 1))
        return "\n".join(out)

    if isinstance(node, StmtDecl):
        return f"{I}StmtDecl\n" + print_ast(node.decl, depth + 1)

    if isinstance(node, Assign):
        return f"{I}Assign {node.name}\n" + print_ast(node.value, depth + 1)

    if isinstance(node, If):
        out = [f"{I}If"]
        out.append(print_ast(node.cond, depth + 1))
        out.append(f"{I}Then:")
        out.append(print_ast(node.then_blk, depth + 1))
        if node.else_blk:
            out.append(f"{I}Else:")
            out.append(print_ast(node.else_blk, depth + 1))
        return "\n".join(out)

    if isinstance(node, While):
        out = [f"{I}While"]
        out.append(print_ast(node.cond, depth + 1))
        out.append(print_ast(node.body, depth + 1))
        return "\n".join(out)

    if isinstance(node, Return):
        if node.value:
            return f"{I}Return\n" + print_ast(node.value, depth + 1)
        return f"{I}Return"

    if isinstance(node, Print):
        return f"{I}Print\n" + print_ast(node.value, depth + 1)

    if isinstance(node, LiteralInt):
        return f"{I}Int {node.value}"

    if isinstance(node, LiteralBool):
        return f"{I}Bool {str(node.value).lower()}"

    if isinstance(node, Var):
        return f"{I}Var {node.name}"

    if isinstance(node, Unary):
        return f"{I}Unary {node.op}\n" + print_ast(node.rhs, depth + 1)

    if isinstance(node, Binary):
        out = [f"{I}Binary {node.op}"]
        out.append(print_ast(node.lhs, depth + 1))
        out.append(print_ast(node.rhs, depth + 1))
        return "\n".join(out)

    if isinstance(node, Call):
        out = [f"{I}Call {node.name}"]
        for a in node.args:
            out.append(print_ast(a, depth + 1))
        return "\n".join(out)

    return f"{I}<unknown node {type(node).__name__}>"
