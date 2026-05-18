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


## ⚙️ How to Run & Use the CLI

The project features a comprehensive Command Line Interface (`cli.py`). You can stop and dump compilation data at **any** specific phase of execution using the `--phase` flag.

### 1. Compile and run a source file directly:
```bash
python cli.py your_program.txt --phase run

# Dump the Lexical Tokens
python cli.py your_program.txt --phase tokens

# Dump the Abstract Syntax Tree (AST)
python cli.py your_program.txt --phase ast

# Dump the Intermediate Three-Address Code (TAC)
python cli.py your_program.txt --phase tac

# Dump the optimized Stack-Machine Assembly
python cli.py your_program.txt --phase asm --opt
