# PolyXML W3C XML Schema Test Suite Conformance Harness

[![W3C XSTS Conformance](https://img.shields.io/badge/W3C%20XSTS-Conformance-brightgreen.svg)](https://github.com/w3c/xsdtests)
[![PolyXML](https://img.shields.io/badge/Engine-PolyXML-blue.svg)](https://github.com/nth-bailey/PolyXML)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Tested with uv](https://img.shields.io/badge/tested%20with-uv-purple.svg)](https://github.com/astral-sh/uv)

Automated conformance testing harness for the **[PolyXML](https://github.com/nth-bailey/PolyXML)** polyglot schema compiler against the official **[W3C XML Schema 1.0 / 1.1 Test Suite (XSTS)](https://github.com/w3c/xsdtests)**.

Inspired by [tefra/xsdata-w3c-tests](https://github.com/tefra/xsdata-w3c-tests), this repository provides a standalone, reproducible test environment to validate code generation correctness, type safety, and bidirectional serialization fidelity across hundreds of standard W3C test groups.

---

## 📊 Conformance Results

Tested against the official W3C XML Schema Test Collection:

| Test Suite / Category | Description | Schemas Compiled | Instances Validated | Status |
|---|---|:---:|:---:|:---:|
| **`suntest`** | Sun Microsystems General Schema Tests | 54 / 54 (100.0%) | 51 / 55 (92.7%) | ✅ Verified |
| **`AttrDecl`** | Attribute Declarations | 83 / 83 (100.0%) | 82 / 82 (100.0%) | ✅ Verified |
| **`CType`** | Complex Type Definitions & Derivations | 31 / 31 (100.0%) | 28 / 28 (100.0%) | ✅ Verified |
| **`MGroup`** | Model Groups (`sequence`, `choice`, `all`) | 59 / 59 (100.0%) | 32 / 32 (100.0%) | ✅ Verified |
| **`AGroupDef`** | Attribute Group Definitions | 13 / 13 (100.0%) | 6 / 6 (100.0%) | ✅ Verified |
| **`AttrUse`** | Attribute Uses & Constraints | 4 / 4 (100.0%) | 3 / 3 (100.0%) | ✅ Verified |
| **`IdConstrDefs`** | Identity Constraints (`key`, `unique`, `keyref`) | 27 / 27 (100.0%) | 14 / 14 (100.0%) | ✅ Verified |
| **`SType`** | Simple Types & Facets (`restriction`, `list`, `union`) | 138 / 138 (100.0%) | 135 / 136 (99.3%) | ✅ Verified |
| **`ElemDecl`** | Element Declarations & Substitution Groups | 226 / 227 (99.6%) | 138 / 151 (91.4%) | ✅ Verified |
| **Overall** | **Cumulative Evaluated Groups** | **635 / 636 (99.8%)** | **489 / 507 (96.4%)** | **Production Ready** |

---

## 🚀 Key Features

- **Automated Catalog Parsing**: Traverses W3C `.testSet` and `suite.xml` manifests, resolving schema references (`xlink:href`) and expected validities (`valid` vs `invalid`).
- **Live Schema Compilation**: Invokes `polyxml generate --lang python` on each test group schema.
- **Dynamic Type Loading & Inspection**: Dynamically imports compiled Python modules, correctly handling Python 3.12 PEP 695 `TypeAliasType` definitions and type unions.
- **Bidirectional Serialization Verification**: Deserializes valid XML instances into typed models and performs round-trip serialization tests to ensure data fidelity.
- **Rich Terminal UI**: Live progress indicators and colored summary tables powered by `rich` and `click`.

---

## 🛠️ Quickstart

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (recommended) or Python 3.12+
- `polyxml` CLI binary built and available on PATH or in `../PolyXML/target/release/polyxml`

### Setup

Clone this repository with submodules:

```bash
git clone --recursive https://github.com/nth-bailey/polyxml-w3c-tests.git
cd polyxml-w3c-tests

# Install dependencies using uv
uv sync
```

If you already cloned without `--recursive`:
```bash
git submodule update --init --recursive
```

---

## 🏃 Running Tests

### Run a specific suite
```bash
uv run runner.py --suite suntest
```

### Run NIST or Microsoft test sets with a limit
```bash
uv run runner.py --suite nist --limit 50
uv run runner.py --suite ms-all --limit 100
```

### Run with verbose output and failure diagnostics
```bash
uv run runner.py --suite CType --verbose
```

### Run against an arbitrary `.testSet` catalog
```bash
uv run runner.py --catalog w3c/msData/complexType/complexType.testSet
```

---

## 📁 Repository Structure

```
polyxml-w3c-tests/
├── w3c/                   # Official W3C XSD Test Suite git submodule
│   ├── sunData/           # Sun Microsystems test suite
│   ├── msData/            # Microsoft test suite
│   ├── nistData/          # NIST test suite
│   └── ...
├── runner.py              # XSTS catalog parser & test runner
├── pyproject.toml         # Python package configuration & dependencies
└── README.md
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

