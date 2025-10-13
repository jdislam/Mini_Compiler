# errors.py
# Central error types and tiny helpers for consistent, readable messages.

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# -------- Base + phase-specific exceptions --------

class CompilerError(Exception):
    """Generic compiler error."""

class LexerError(CompilerError):
    """Lexical analysis error."""

class ParserError(CompilerError):
    """Syntactic parsing error."""

class SemanticError(CompilerError):
    """Type/scope checking error."""

class TACError(CompilerError):
    """Three-address code generation error."""

class CodegenError(CompilerError):
    """Lowering to ASM error."""

class VMError(CompilerError):
    """Virtual machine runtime error."""

# -------- Structured error record (for non-exception flows) --------

@dataclass
class ErrorRecord:
    phase: str                 # "lex", "parse", "sema", "tac", "codegen", "vm"
    message: str               # short description
    line: int                  # 1-based
    col: int                   # 1-based
    file: Optional[str] = None # optional source filename

    def __str__(self) -> str:
        loc = f"{self.line}:{self.col}"
        f = f"{self.file}:" if self.file else ""
        return f"{self.phase.upper()} Error: {self.message} at {f}{loc}"

# -------- Pretty formatting with caret underline --------

def format_with_caret(src: str, line: int, col: int, width: int = 1) -> str:
    """
    Return a two-line snippet:
      <line text>
      <spaces>^~~
    Safe on out-of-range positions.
    """
    if line < 1:
        line = 1
    lines = src.splitlines() or [""]
    idx = min(max(line - 1, 0), len(lines) - 1)
    text = lines[idx]
    # Build caret underline
    caret_pos = max(col - 1, 0)
    caret_pos = min(caret_pos, len(text))
    carets = "^" + "~" * max(width - 1, 0)
    underline = " " * caret_pos + carets
    return f"{text}\n{underline}"

def make_error_line(phase: str, msg: str, line: int, col: int, file: Optional[str] = None) -> str:
    """Single-line canonical message."""
    loc = f"{file+':' if file else ''}{line}:{col}"
    return f"{phase.upper()} Error: {msg} at {loc}"
