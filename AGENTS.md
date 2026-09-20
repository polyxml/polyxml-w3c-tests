# AGENTS.md

Instructions and guidelines for AI coding assistants working in the `polyxml-w3c-tests` repository.

---

## 1. Project Overview

`polyxml-w3c-tests` is the official conformance test suite and validation harness for the **[PolyXML](https://github.com/nth-bailey/PolyXML)** polyglot XML schema compiler and runtime engine.

Inspired by [tefra/xsdata-w3c-tests](https://github.com/tefra/xsdata-w3c-tests), this repository provides an automated, reproducible environment to execute the official **W3C XML Schema 1.0 / 1.1 Test Suite (XSTS)** against the `polyxml` compiler, verifying schema code generation correctness, type safety, and round-trip serialization fidelity.

- **Technology**: Python 3.12+, `uv`, `click`, `rich`, `pytest`.
- **Repository**: `nth-bailey/polyxml-w3c-tests`
- **Supported Python**: `Python >= 3.12` exclusively.
- **Maintainer**: Bailey Nguyen (`bailey.tan.nguyen@gmail.com`).

---

## 2. Core Architectural Decisions & Invariants

When contributing or refactoring in this repository, strictly maintain the following invariants:

1. **Strict Decoupling from PolyXML CI**:
   - This test repository is intentionally standalone and decoupled from the main `PolyXML` repository CI.
   - W3C XSTS contains thousands of schema groups; running them all in standard PolyXML PR CI would be prohibitively slow.
   - This repository serves as the deep conformance benchmark and stress testing platform.

2. **Git Submodule for W3C Test Data (`w3c/`)**:
   - The official W3C XML Schema Test Suite is tracked as a Git submodule in `w3c/` pointing to `https://github.com/w3c/xsdtests`.
   - **NEVER** commit test data files or schemas directly into the root repository.
   - Always ensure submodules are initialized via `git submodule update --init --recursive`.

3. **Dependency Management with `uv`**:
   - Always use `uv` for Python package and environment management.
   - **NEVER** run global `pip install` or activate virtual environments manually.
   - Run commands via `uv run <command>`.
   - Update `pyproject.toml` and synchronize with `uv lock` / `uv sync`.

4. **PolyXML Binary Resolution**:
   - The test runner looks for `polyxml` at `../PolyXML/target/release/polyxml` first, then falls back to `PATH`.
   - For maximum test throughput, ensure a release build exists (`cargo build --release -p polyxml-cli` in `../PolyXML`).

5. **Bidirectional Validation (Parse + Round-Trip)**:
   - Schema validation is not sufficient on its own. For valid instances, the harness must:
     1. Compile the XSD schema into Python models via `polyxml generate --lang python`.
     2. Dynamically load the generated Python module.
     3. Deserialize the XML instance document into typed models.
     4. Serialize the typed model back into XML and verify structural idempotence.

6. **Python 3.12 PEP 695 Type Aliases Handling**:
   - PolyXML generates modern PEP 695 `type Name = ...` statements, producing `typing.TypeAliasType` objects.
   - Inspection code must resolve `TypeAliasType.__value__` when finding root dataclasses and union variants.

---

## 3. Tooling & Development Workflow

### Environment Setup

```bash
# Clone with submodules
git clone --recursive https://github.com/nth-bailey/polyxml-w3c-tests.git
cd polyxml-w3c-tests

# Synchronize virtual environment with uv
uv sync
```

### Running Test Suites

- **Sun Microsystems Test Suite** (`suntest`):
  ```bash
  uv run runner.py --suite suntest
  ```

- **Complex Types** (`CType`):
  ```bash
  uv run runner.py --suite CType
  ```

- **Attribute Declarations** (`AttrDecl`):
  ```bash
  uv run runner.py --suite AttrDecl
  ```

- **Model Groups** (`MGroup`):
  ```bash
  uv run runner.py --suite MGroup
  ```

- **Running with Limits on Large Suites**:
  ```bash
  uv run runner.py --suite nist --limit 50
  uv run runner.py --suite ms-all --limit 100
  ```

- **Verbose Diagnostics for Failures**:
  ```bash
  uv run runner.py --suite CType --verbose
  ```

- **Targeting an Arbitrary Catalog File**:
  ```bash
  uv run runner.py --catalog w3c/msData/complexType/complexType.testSet
  ```

---

## 4. Common Pitfalls & Edge Cases

1. **Large Test Catalogs**:
   - Test suites like `nist` and `msData` contain thousands of test groups. Always use `--limit <N>` when testing changes interactively.
2. **Generated Files Location**:
   - Generated code is written to `output/` by default and is ignored by `.gitignore`.
   - Ensure tests clean up temporary files or use distinct subdirectories if running concurrently.
3. **Invalid XML and Schemas**:
   - The W3C test catalog explicitly marks negative test cases (`validity="invalid"`).
   - The harness correctly treats a compilation rejection of an invalid schema as a **PASS**.

---

## 5. Verification Checklist

Before pushing changes to this repository:

1. **Submodule Status**: Ensure `git status` shows clean submodule pointers.
2. **Runner Health**: Verify `uv run runner.py --suite suntest` executes cleanly without unexpected exceptions.
3. **Dependencies**: Ensure `uv.lock` is up to date with `pyproject.toml`.
4. **Code Quality**: Ensure any added Python code adheres to Python 3.12+ syntax and formatting standards.
