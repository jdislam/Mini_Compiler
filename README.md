# Mini-Compiler Pipeline with Custom VM (CSE430)

An end-to-end hobby compiler pipeline implemented in Python for a modular C-like language. This project spans all core compiler design phases—from raw lexical parsing to target lowering and virtual machine execution. Developed as an academic laboratory project for **CSE430: Compiler Laboratory** at the University of Asia Pacific (UAP).

---

## 🏗️ Architecture & Pipeline Phases

The compiler is organized strictly into separate decoupled components, processing code through the following sequential pipeline:

```text
[ Source File ] 
       │
       ▼
 1. Lexical Analysis (`lexer.py`) ──► Generates typed Tokens
       │
       ▼
 2. Syntax Analysis (`parser.py`, `astnodes.py`) ──► Constructs Abstract Syntax Tree (AST)
       │
       ▼
 3. Semantic Analysis (`sema.py`) ──► Checks Scopes, Variable Declarations & Data Types
       │
       ▼
 4. Intermediate Code (`tac.py`) ──► Emits Linear Three-Address Code (TAC)
       │
       ▼
 5. Optimization (`optimizer.py`) ──► Constant Folding, Copy Propagation & Dead Code Elimination
       │
       ▼
 6. Code Generation (`codegen.py`) ──► Lowers TAC into Custom Stack-Machine Assembly
       │
       ▼
 7. Runtime Execution (`vm.py`) ──► Executes Assembly on an Isolated Virtual Machine Engine
