# lexer.py
# Converts source text to a stream of tokens with (kind, lexeme, line, col).
# Supports C-like whitespace, // line comments, and /* block */ comments.
# NEW: string and char literal scanning, && and ||, 'for' keyword.

from dataclasses import dataclass
from typing import List, Tuple

# ----- Token model -----

@dataclass
class Token:
    kind: str    # e.g., ID, INT, PLUS, IF_KW
    lexeme: str  # original text (for STRING/CHAR literals the quotes are kept)
    line: int    # 1-based
    col: int     # 1-based

# ----- Lexer -----

class Lexer:
    def __init__(self, src: str):
        self.src = src

    # Public API
    def tokenize(self) -> Tuple[List[Token], List[str]]:
        s = self.src
        i, n = 0, len(s)
        line, col = 1, 1
        out: List[Token] = []
        errors: List[str] = []

        KEYWORDS = {
            "int":    "INT_KW",
            "char":   "CHAR_KW",
            "string": "STR_KW",
            "bool":   "BOOL_KW",
            "void":   "VOID_KW",
            "float":  "FLOAT_KW",
            "if":     "IF_KW",
            "else":   "ELSE_KW",
            "while":  "WHILE_KW",
            "for":    "FOR_KW",
            "return": "RETURN_KW",
            "print":  "PRINT_KW",
            "true":   "TRUE_KW",
            "false":  "FALSE_KW",
        }

        def add(kind: str, lexeme: str, li: int, co: int):
            out.append(Token(kind, lexeme, li, co))

        def is_alpha(ch: str) -> bool:
            return ch.isalpha() or ch == "_"

        def is_digit(ch: str) -> bool:
            return ch.isdigit()

        def is_alnum(ch: str) -> bool:
            return ch.isalnum() or ch == "_"

        def bump(k=1):
            nonlocal i, col
            i += k
            col += k

        def newline():
            nonlocal line, col, i
            line += 1
            col = 1
            i += 1

        # --- number scanner with float support ---
        def scan_number():
            """Scan INT or FLOAT (with digits before and after the dot)."""
            nonlocal i, col
            start_i, li, co = i, line, col
            saw_dot = False
            while i < n and is_digit(s[i]):
                i += 1; col += 1
            if i < n and s[i] == '.' and (i + 1 < n and s[i+1].isdigit()):
                saw_dot = True
                i += 1; col += 1
                while i < n and is_digit(s[i]):
                    i += 1; col += 1
            lexeme = s[start_i:i]
            add("FLOAT" if saw_dot else "INT", lexeme, li, co)

        # --- string / char literal scanners ---
        def scan_string():
            nonlocal i, col, line
            li, co = line, col
            i += 1; col += 1  # consume opening "
            buf = ['"']
            closed = False
            while i < n:
                ch = s[i]
                if ch == "\n":
                    errors.append(f"LexError: unterminated string at {li}:{co}")
                    break
                if ch == "\\":
                    if i + 1 < n:
                        nxt = s[i+1]
                        buf.append("\\" + nxt)
                        i += 2; col += 2
                        continue
                if ch == '"':
                    buf.append('"')
                    i += 1; col += 1
                    closed = True
                    break
                buf.append(ch)
                i += 1; col += 1
            if not closed:
                errors.append(f"LexError: unterminated string at {li}:{co}")
            add("STRING", "".join(buf), li, co)

        def scan_char():
            nonlocal i, col, line
            li, co = line, col
            i += 1; col += 1  # consume opening '
            buf = ["'"]
            if i >= n:
                errors.append(f"LexError: unterminated char at {li}:{co}")
                add("CHAR", "''", li, co)
                return
            if s[i] == "\\":
                if i + 1 < n:
                    buf.append("\\" + s[i+1])
                    i += 2; col += 2
                else:
                    errors.append(f"LexError: unterminated char at {li}:{co}")
            else:
                buf.append(s[i])
                i += 1; col += 1
            if i < n and s[i] == "'":
                buf.append("'")
                i += 1; col += 1
            else:
                errors.append(f"LexError: unterminated char at {li}:{co}")
            add("CHAR", "".join(buf), li, co)

        # main loop
        while i < n:
            ch = s[i]

            # whitespace
            if ch in " \t\r":
                bump()
                continue
            if ch == "\n":
                newline()
                continue

            # comments
            if ch == "/" and i + 1 < n and s[i + 1] == "/":
                while i < n and s[i] != "\n":
                    i += 1
                continue
            if ch == "/" and i + 1 < n and s[i + 1] == "*":
                i += 2; col += 2
                closed = False
                while i < n:
                    if s[i] == "\n":
                        newline()
                        continue
                    if s[i] == "*" and i + 1 < n and s[i + 1] == "/":
                        i += 2; col += 2
                        closed = True
                        break
                    i += 1; col += 1
                if not closed:
                    errors.append(f"LexError: unterminated block comment at {line}:{col}")
                continue

            # identifiers / keywords
            if is_alpha(ch):
                li, co = line, col
                j = i + 1
                while j < n and is_alnum(s[j]):
                    j += 1
                lex = s[i:j]
                kind = KEYWORDS.get(lex, "ID")
                out.append(Token(kind, lex, li, co))
                col += (j - i); i = j
                continue

            # numbers (INT or FLOAT)
            if is_digit(ch):
                scan_number()
                continue

            li, co = line, col
            two = s[i:i+2]
            # two-char operators (now includes &&, ||)
            if two in ("==", "!=", "<=", ">=", "&&", "||"):
                add({
                    "==": "EQEQ", "!=": "NEQ", "<=": "LE", ">=": "GE", "&&": "ANDAND", "||": "OROR"
                }[two], two, li, co)
                bump(2)
                continue

            # strings / chars
            if ch == '"':
                scan_string(); continue
            if ch == "'":
                scan_char(); continue

            single_map = {
                "+": "PLUS",
                "-": "MINUS",
                "*": "STAR",
                "/": "SLASH",
                "%": "PERCENT",
                "<": "LT",
                ">": "GT",
                "!": "NOT",
                "=": "ASSIGN",
                "(": "LPAREN",
                ")": "RPAREN",
                "{": "LBRACE",
                "}": "RBRACE",
                ",": "COMMA",
                ";": "SEMI",
            }
            if ch in single_map:
                add(single_map[ch], ch, li, co)
                bump()
                continue

            # anything else is an error
            errors.append(f"LexError: unexpected character '{ch}' at {line}:{col}")
            bump()

        return out, errors