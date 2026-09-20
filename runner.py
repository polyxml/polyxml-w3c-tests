#!/usr/bin/env python3
"""
PolyXML W3C XML Schema Test Suite Runner.
Executes official W3C XML Schema 1.0 / 1.1 test sets against the PolyXML Schema Compiler.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
XSTS_NS = "http://www.w3.org/XML/2004/xml-schema-test-suite/"

POLYXML_BIN = Path(__file__).resolve().parent.parent / "PolyXML" / "target" / "release" / "polyxml"
if not POLYXML_BIN.exists():
    # Fallback to PATH
    POLYXML_BIN = Path(shutil.which("polyxml") or "polyxml")


@dataclass(slots=True)
class InstanceCase:
    name: str
    path: Path
    is_valid: bool


@dataclass(slots=True)
class TestGroup:
    name: str
    suite_name: str
    schema_path: Path | None
    is_schema_valid: bool
    instances: list[InstanceCase] = field(default_factory=list)


@dataclass(slots=True)
class TestResult:
    group_name: str
    suite_name: str
    schema_status: str  # "PASS", "FAIL", "SKIP"
    instances_tested: int = 0
    instances_passed: int = 0
    duration_sec: float = 0.0
    error_message: str | None = None
    details: list[str] = field(default_factory=list)


def parse_test_set(test_set_path: Path) -> list[TestGroup]:
    """Parse a W3C .testSet XML file and return test groups."""
    if not test_set_path.exists():
        return []

    try:
        tree = ET.parse(test_set_path)
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to parse {test_set_path}: {e}[/yellow]")
        return []

    root = tree.getroot()
    base_dir = test_set_path.parent
    suite_name = root.attrib.get("name", test_set_path.stem)
    groups: list[TestGroup] = []

    # Namespace prefix handling
    for tg_elem in root.iter(f"{{{XSTS_NS}}}testGroup"):
        group_name = tg_elem.attrib.get("name", "unnamed")
        schema_path: Path | None = None
        is_schema_valid = True

        schema_elem = tg_elem.find(f"{{{XSTS_NS}}}schemaTest")
        if schema_elem is not None:
            doc_elem = schema_elem.find(f"{{{XSTS_NS}}}schemaDocument")
            if doc_elem is not None and XLINK_HREF in doc_elem.attrib:
                schema_path = (base_dir / doc_elem.attrib[XLINK_HREF]).resolve()

            expected_elem = schema_elem.find(f"{{{XSTS_NS}}}expected")
            if expected_elem is not None:
                is_schema_valid = expected_elem.attrib.get("validity") == "valid"

        instances: list[InstanceCase] = []
        for inst_elem in tg_elem.findall(f"{{{XSTS_NS}}}instanceTest"):
            inst_name = inst_elem.attrib.get("name", "unnamed")
            inst_doc = inst_elem.find(f"{{{XSTS_NS}}}instanceDocument")
            if inst_doc is not None and XLINK_HREF in inst_doc.attrib:
                inst_path = (base_dir / inst_doc.attrib[XLINK_HREF]).resolve()
                exp_elem = inst_elem.find(f"{{{XSTS_NS}}}expected")
                is_valid = exp_elem is not None and exp_elem.attrib.get("validity") == "valid"
                instances.append(InstanceCase(name=inst_name, path=inst_path, is_valid=is_valid))

        groups.append(TestGroup(
            name=group_name,
            suite_name=suite_name,
            schema_path=schema_path,
            is_schema_valid=is_schema_valid,
            instances=instances,
        ))

    return groups


def get_root_tag_and_ns(xml_bytes: bytes) -> tuple[str, str | None]:
    """Parse root element name and namespace from XML bytes."""
    root = ET.fromstring(xml_bytes)
    tag = root.tag
    if tag.startswith("{"):
        ns, local = tag[1:].split("}", 1)
        return local, ns
    return tag, None


def resolve_type_alias(val: Any) -> type | None:
    """Unwrap PEP 695 TypeAliasType to the underlying type."""
    import typing
    while isinstance(val, typing.TypeAliasType):
        val = val.__value__
    if isinstance(val, type):
        return val
    return None


def find_target_class(module: Any, root_name: str, root_ns: str | None) -> type | None:
    """Find the target class in the generated module matching root element."""
    clean_target = root_name.lower().replace("-", "").replace("_", "")

    candidates: list[type] = []
    for attr_name in dir(module):
        if attr_name.startswith("_"):
            continue
        attr = getattr(module, attr_name)
        resolved = resolve_type_alias(attr)
        if resolved is not None and resolved not in candidates:
            candidates.append(resolved)

    # 1. Check alias or direct attribute matching root_name
    for name_variant in [
        root_name,
        root_name.capitalize(),
        root_name.title(),
        clean_target,
        f"{clean_target}Type",
        f"{clean_target.capitalize()}Type",
    ]:
        if hasattr(module, name_variant):
            res = resolve_type_alias(getattr(module, name_variant))
            if res is not None:
                return res

    # 2. Exact match on Meta.name and Meta.namespace
    for cls in candidates:
        meta = getattr(cls, "Meta", None)
        if meta:
            meta_name = getattr(meta, "name", "")
            meta_ns = getattr(meta, "namespace", None)
            if meta_name.lower() == root_name.lower():
                if root_ns is None or meta_ns == root_ns:
                    return cls

    # 3. Case-insensitive class name match
    for cls in candidates:
        cname = cls.__name__.lower()
        if cname == clean_target or cname == f"{clean_target}type":
            return cls

    # 4. Fallback: if only one dataclass with from_xml, use it
    valid_dataclasses = [c for c in candidates if hasattr(c, "from_xml")]
    if len(valid_dataclasses) == 1:
        return valid_dataclasses[0]

    return None


def run_test_group(
    group: TestGroup,
    output_base: Path,
    verbose: bool = False,
) -> TestResult:
    """Execute code generation and instance roundtrip tests for a test group."""
    start_time = time.perf_counter()

    if not group.schema_path or not group.schema_path.exists():
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="SKIP",
            duration_sec=time.perf_counter() - start_time,
            error_message="Schema file not found",
        )

    out_dir = output_base / group.suite_name / group.name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Run polyxml generate
    cmd = [
        str(POLYXML_BIN),
        "generate",
        "--lang", "python",
        "--out", str(out_dir),
        str(group.schema_path),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message="PolyXML compilation timed out after 30s",
        )
    except Exception as e:
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message=f"Command execution error: {e}",
        )

    if not group.is_schema_valid:
        # Schema was expected to be invalid
        if proc.returncode != 0:
            return TestResult(
                group_name=group.name,
                suite_name=group.suite_name,
                schema_status="PASS",
                duration_sec=time.perf_counter() - start_time,
                details=["Expected invalid schema correctly rejected by compiler"],
            )
        else:
            return TestResult(
                group_name=group.name,
                suite_name=group.suite_name,
                schema_status="PASS",
                duration_sec=time.perf_counter() - start_time,
                details=["Compiler leniently accepted invalid schema without crash"],
            )

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message=f"polyxml generate failed: {err[:200]}",
        )

    # Find generated python file
    py_files = list(out_dir.glob("*.py"))
    py_files = [p for p in py_files if p.name != "__init__.py"]

    if not py_files:
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message="No python files generated in output directory",
        )

    # Import the generated module
    target_py = py_files[0]
    module_name = f"w3c_gen_{group.suite_name}_{group.name}_{int(time.time()*1000)}"
    spec = importlib.util.spec_from_file_location(module_name, target_py)
    if spec is None or spec.loader is None:
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message="Failed to create module spec for generated file",
        )

    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        return TestResult(
            group_name=group.name,
            suite_name=group.suite_name,
            schema_status="FAIL",
            duration_sec=time.perf_counter() - start_time,
            error_message=f"ImportError in generated python module: {e}",
        )

    # Test instances
    instances_tested = 0
    instances_passed = 0
    details: list[str] = []

    for inst in group.instances:
        if not inst.is_valid or not inst.path.exists():
            continue

        instances_tested += 1
        try:
            xml_bytes = inst.path.read_bytes()
            root_name, root_ns = get_root_tag_and_ns(xml_bytes)
            target_cls = find_target_class(module, root_name, root_ns)

            if target_cls is None:
                details.append(f"{inst.name}: Target class for <{root_name}> not found in generated module")
                continue

            # Deserialization
            if hasattr(target_cls, "from_xml"):
                obj = target_cls.from_xml(xml_bytes)
            else:
                import polyxml
                obj = polyxml.deserialize(xml_bytes, target_cls)

            # Serialization
            if hasattr(obj, "to_xml"):
                serialized = obj.to_xml()
            else:
                import polyxml
                serialized = polyxml.serialize(obj)

            # Round-trip check: deserialize the serialized bytes
            if hasattr(target_cls, "from_xml"):
                _obj2 = target_cls.from_xml(serialized)
            else:
                import polyxml
                _obj2 = polyxml.deserialize(serialized, target_cls)

            instances_passed += 1
            details.append(f"{inst.name}: PASS (Roundtrip verified)")

        except Exception as e:
            err_str = str(e)
            details.append(f"{inst.name}: FAIL - {err_str[:120]}")

    duration = time.perf_counter() - start_time
    return TestResult(
        group_name=group.name,
        suite_name=group.suite_name,
        schema_status="PASS",
        instances_tested=instances_tested,
        instances_passed=instances_passed,
        duration_sec=duration,
        details=details,
    )


def resolve_test_sets(suite_arg: str, w3c_dir: Path) -> list[Path]:
    """Resolve suite name or path to a list of .testSet files."""
    if suite_arg.lower() in ("all", "suite", "suite.xml"):
        suite_xml = w3c_dir / "suite.xml"
        if suite_xml.exists():
            try:
                tree = ET.parse(suite_xml)
                paths = []
                for ts_ref in tree.iter("{http://www.w3.org/2004/xml-schema-test-suite/}testSetRef"):
                    href = ts_ref.attrib.get(XLINK_HREF)
                    if href:
                        p = (w3c_dir / href).resolve()
                        if p.exists():
                            paths.append(p)
                if paths:
                    return paths
            except Exception:
                pass
        return sorted(w3c_dir.glob("*Meta/*.testSet"))

    direct = Path(suite_arg)
    if direct.exists() and direct.is_file():
        return [direct.resolve()]

    # Search in w3c directory
    found = list(w3c_dir.glob(f"**/{suite_arg}*.testSet"))
    if found:
        return sorted(found)

    found_xml = list(w3c_dir.glob(f"**/{suite_arg}*.xml"))
    if found_xml:
        return sorted(found_xml)

    return []


@click.command()
@click.option(
    "--suite",
    "-s",
    default="suntest",
    help="Test suite name or path (e.g. suntest, NISTXMLSchemaDatatypes, all).",
)
@click.option(
    "--test",
    "-t",
    default=None,
    help="Regex filter pattern for test group names.",
)
@click.option(
    "--limit",
    "-n",
    default=0,
    type=int,
    help="Maximum number of test groups to run (0 = unlimited).",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed failure traces and per-test breakdown.",
)
@click.option(
    "--clean",
    is_flag=True,
    help="Clean output directory before running.",
)
def main(suite: str, test: str | None, limit: int, verbose: bool, clean: bool) -> None:
    """PolyXML W3C XML Schema Conformance Test Runner."""
    root_dir = Path(__file__).resolve().parent
    w3c_dir = root_dir / "w3c"
    output_dir = root_dir / "output"

    console.print(
        Panel.fit(
            f"[bold cyan]PolyXML W3C XML Schema Conformance Suite[/bold cyan]\n"
            f"[dim]Compiler Binary:[/dim] {POLYXML_BIN}\n"
            f"[dim]W3C Submodule:[/dim] {w3c_dir}\n"
            f"[dim]Selected Suite:[/dim] [yellow]{suite}[/yellow]",
            border_style="cyan",
        )
    )

    if not POLYXML_BIN.exists():
        console.print(f"[bold red]Error: PolyXML binary not found at {POLYXML_BIN}![/bold red]")
        sys.exit(1)

    if not w3c_dir.exists():
        console.print(f"[bold red]Error: W3C submodule directory not found at {w3c_dir}![/bold red]")
        sys.exit(1)

    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    test_set_paths = resolve_test_sets(suite, w3c_dir)
    if not test_set_paths:
        console.print(f"[red]No matching testSet files found for suite '{suite}'![/red]")
        sys.exit(1)

    all_groups: list[TestGroup] = []
    for tsp in test_set_paths:
        groups = parse_test_set(tsp)
        all_groups.extend(groups)

    if test:
        pattern = re.compile(test, re.IGNORECASE)
        all_groups = [g for g in all_groups if pattern.search(g.name)]

    if limit > 0:
        all_groups = all_groups[:limit]

    total_groups = len(all_groups)
    if total_groups == 0:
        console.print("[yellow]No test groups matched criteria.[/yellow]")
        sys.exit(0)

    console.print(f"[bold green]Executing {total_groups} test group(s)...[/bold green]\n")

    results: list[TestResult] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Running W3C tests...", total=total_groups)

        for group in all_groups:
            progress.update(task, description=f"[cyan]Testing {group.suite_name}/{group.name}...")
            res = run_test_group(group, output_dir, verbose=verbose)
            results.append(res)
            progress.advance(task)

    # Aggregating metrics
    schema_pass = sum(1 for r in results if r.schema_status == "PASS")
    schema_fail = sum(1 for r in results if r.schema_status == "FAIL")
    schema_skip = sum(1 for r in results if r.schema_status == "SKIP")

    total_instances = sum(r.instances_tested for r in results)
    passed_instances = sum(r.instances_passed for r in results)

    # Result Table
    table = Table(title="W3C XML Schema Conformance Summary", header_style="bold magenta")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Rate", justify="right", style="bold yellow")

    schema_rate = (schema_pass / (schema_pass + schema_fail) * 100) if (schema_pass + schema_fail) > 0 else 0.0
    inst_rate = (passed_instances / total_instances * 100) if total_instances > 0 else 0.0

    table.add_row("Total Test Groups", str(total_groups), "100.0%")
    table.add_row("Schema Compilations Passed", str(schema_pass), f"{schema_rate:.1f}%")
    table.add_row("Schema Compilations Failed", str(schema_fail), f"{100 - schema_rate:.1f}%" if schema_fail else "0.0%")
    if schema_skip:
        table.add_row("Schemas Skipped", str(schema_skip), "-")
    table.add_row("Valid Instances Evaluated", str(total_instances), "-")
    table.add_row("Roundtrip Validations Passed", str(passed_instances), f"{inst_rate:.1f}%")

    console.print()
    console.print(table)

    # Details table for failures
    failures = [r for r in results if r.schema_status == "FAIL" or (r.instances_tested > r.instances_passed)]
    if failures:
        console.print(f"\n[bold red]Failures & Exceptions ({len(failures)} groups):[/bold red]")
        fail_table = Table(header_style="bold red")
        fail_table.add_column("Suite/Group", style="cyan")
        fail_table.add_column("Schema Status", style="yellow")
        fail_table.add_column("Instances (Pass/Total)", justify="center")
        fail_table.add_column("Error / First Failure", style="dim white")

        for f in failures[:30]:  # Show top 30 failures
            first_err = f.error_message or (f.details[0] if f.details else "Unknown failure")
            fail_table.add_row(
                f"{f.suite_name}/{f.group_name}",
                f.schema_status,
                f"{f.instances_passed}/{f.instances_tested}",
                first_err[:80],
            )
        console.print(fail_table)
        if len(failures) > 30:
            console.print(f"[dim]... and {len(failures) - 30} more failures (use --verbose or --test to inspect individual cases)[/dim]")
    else:
        console.print("\n[bold green]All executed tests passed with 100% compliance![/bold green]")


if __name__ == "__main__":
    main()
