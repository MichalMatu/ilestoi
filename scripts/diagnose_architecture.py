#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess  # nosec B404
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from scripts.architecture_quality import (  # noqa: E402
    collect_retired_artifacts,
    evaluate_quality_gates,
    forbidden_layer_imports,
)
from scripts.architecture_risk import collect_risky_patterns  # noqa: E402

TARGET_DIRS = ("app", "core", "scripts", "tests", "web")
PY_GROUPS = {"app", "core", "scripts", "tests"}
ARCH_GROUPS = {"app", "core", "scripts", "web"}
EXCLUDED_DIRS = {
    ".cache",
    ".git",
    ".ruff_cache",
    ".venv",
    ".venv-audit",
    "__pycache__",
    "analiza",
    "node_modules",
}
ENDPOINT_RE = re.compile(r"['\"](?P<path>/(?:api|wms_proxy|wraki|wrecks|report|privacy)[^'\"\s]*)['\"]")
JS_FUNCTION_RE = re.compile(
    r"\bfunction\s+(?P<fn>[A-Za-z_$][\w$]*)\s*\(|"
    r"\b(?P<const>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def iter_source_files() -> list[Path]:
    files: list[Path] = []
    for dirname in TARGET_DIRS:
        base = ROOT_DIR / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT_DIR).parts):
                continue
            if path.suffix in {".py", ".js", ".html", ".css"}:
                files.append(path)
    return sorted(files)


def module_name(path: Path) -> str | None:
    if path.suffix != ".py":
        return None
    parts = path.relative_to(ROOT_DIR).with_suffix("").parts
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_python(path: Path) -> ast.AST | None:
    try:
        return ast.parse(read_text(path), filename=rel(path))
    except SyntaxError:
        return None


def biggest_files(files: list[Path], limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for path in files:
        text = read_text(path)
        rows.append({"path": rel(path), "bytes": path.stat().st_size, "lines": len(text.splitlines())})
    return sorted(rows, key=lambda item: (item["lines"], item["bytes"]), reverse=True)[:limit]


def python_long_functions(path: Path, tree: ast.AST) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            end_lineno = getattr(node, "end_lineno", node.lineno)
            rows.append(
                {
                    "path": rel(path),
                    "name": node.name,
                    "line": node.lineno,
                    "lines": max(1, end_lineno - node.lineno + 1),
                    "kind": "python",
                }
            )
    return rows


def js_long_functions(path: Path) -> list[dict[str, Any]]:
    lines = read_text(path).splitlines()
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = JS_FUNCTION_RE.search(line)
        if not match:
            continue
        name = match.group("fn") or match.group("const") or "<anonymous>"
        brace_depth = line.count("{") - line.count("}")
        end_index = index
        while brace_depth > 0 and end_index + 1 < len(lines):
            end_index += 1
            brace_depth += lines[end_index].count("{") - lines[end_index].count("}")
        rows.append(
            {
                "path": rel(path),
                "name": name,
                "line": index + 1,
                "lines": max(1, end_index - index + 1),
                "kind": "javascript",
            }
        )
    return rows


def longest_functions(py_trees: dict[Path, ast.AST], js_files: list[Path], limit: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path, tree in py_trees.items():
        rows.extend(python_long_functions(path, tree))
    for path in js_files:
        rows.extend(js_long_functions(path))
    return sorted(rows, key=lambda item: item["lines"], reverse=True)[:limit]


def resolve_relative_import(current: str, node: ast.ImportFrom) -> str | None:
    current_parts = current.split(".")
    base_parts = current_parts[: -node.level] if node.level else current_parts[:-1]
    if node.module:
        base_parts.extend(part for part in node.module.split(".") if part)
    if not base_parts:
        return None
    return ".".join(base_parts)


def known_module(imported: str, modules: set[str]) -> str | None:
    parts = imported.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
        parts.pop()
    root = imported.split(".", 1)[0]
    return root if root in PY_GROUPS else None


def collect_imports(py_trees: dict[Path, ast.AST]) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    modules_by_path = {path: module_name(path) for path in py_trees}
    modules = {name for name in modules_by_path.values() if name}
    imports: list[dict[str, Any]] = []
    graph: dict[str, set[str]] = defaultdict(set)

    for path, tree in py_trees.items():
        current = modules_by_path[path]
        if not current:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = known_module(alias.name, modules)
                    if not target or target == current:
                        continue
                    imports.append(
                        {"from": current, "to": target, "path": rel(path), "line": node.lineno, "kind": "import"}
                    )
                    graph[current].add(target)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_relative_import(current, node) if node.level else node.module
                if not base:
                    continue
                for alias in node.names:
                    imported = base if alias.name == "*" else f"{base}.{alias.name}"
                    target = known_module(imported, modules) or known_module(base, modules)
                    if not target or target == current:
                        continue
                    imports.append(
                        {"from": current, "to": target, "path": rel(path), "line": node.lineno, "kind": "from"}
                    )
                    graph[current].add(target)

    return sorted(imports, key=lambda item: (item["from"], item["to"], item["line"])), graph


def find_cycles(graph: dict[str, set[str]], limit: int = 20) -> list[list[str]]:
    cycles: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()

    def canonical(cycle: list[str]) -> tuple[str, ...]:
        body = cycle[:-1]
        rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
        return min(rotations)

    def walk(start: str, node: str, stack: list[str]) -> None:
        if len(cycles) >= limit:
            return
        for target in sorted(graph.get(node, set())):
            if target == start:
                cycle = stack + [start]
                key = canonical(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle)
                continue
            if target in stack or len(stack) >= 12:
                continue
            walk(start, target, stack + [target])

    for start in sorted(graph):
        walk(start, start, [start])
        if len(cycles) >= limit:
            break
    return cycles


def current_function_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    cursor = node
    while cursor in parents:
        cursor = parents[cursor]
        if isinstance(cursor, ast.FunctionDef | ast.AsyncFunctionDef):
            return cursor.name
    return None


def parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def collect_endpoints(py_trees: dict[Path, ast.AST], js_files: list[Path]) -> list[dict[str, Any]]:
    endpoints: dict[tuple[str, str, str], dict[str, Any]] = {}

    for path, tree in py_trees.items():
        parents = parent_map(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if not value.startswith("/") or len(value) > 180 or any(char.isspace() for char in value):
                continue
            if value == "/" or value.startswith(("/api/", "/wms_proxy/", "/report", "/privacy")):
                fn_name = current_function_name(node, parents) or ""
                method = "HTTP"
                if fn_name.startswith("do_"):
                    method = fn_name.removeprefix("do_")
                key = (value, rel(path), method)
                endpoints.setdefault(
                    key,
                    {"path": value, "source": rel(path), "line": node.lineno, "method_hint": method, "contexts": []},
                )
                if fn_name and fn_name not in endpoints[key]["contexts"]:
                    endpoints[key]["contexts"].append(fn_name)

    for path in js_files:
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            for match in ENDPOINT_RE.finditer(line):
                endpoint = match.group("path")
                key = (endpoint, rel(path), "JS")
                endpoints.setdefault(
                    key,
                    {"path": endpoint, "source": rel(path), "line": lineno, "method_hint": "JS", "contexts": []},
                )

    return sorted(endpoints.values(), key=lambda item: (item["path"], item["source"], item["line"]))


def group_dependencies(imports: list[dict[str, Any]], js_files: list[Path]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for item in imports:
        from_group = item["from"].split(".", 1)[0]
        to_group = item["to"].split(".", 1)[0]
        if from_group in ARCH_GROUPS and to_group in ARCH_GROUPS:
            counter[(from_group, to_group)] += 1

    for path in js_files:
        for line in read_text(path).splitlines():
            if re.search(r"\bimport\b.+['\"]\./", line):
                counter[("web", "web")] += 1

    return [
        {"from": source, "to": target, "count": count}
        for (source, target), count in sorted(counter.items(), key=lambda item: (item[0][0], item[0][1]))
    ]


def _tool_executable(command: str) -> str | None:
    executable = shutil.which(command)
    if executable:
        return executable
    sibling = Path(sys.executable).parent / command
    if sibling.exists() and sibling.is_file():
        return str(sibling)
    return None


def tool_info(command: str, *version_args: str, module: str | None = None) -> dict[str, Any]:
    executable = _tool_executable(command)
    if executable:
        args = [executable, *(version_args or ("--version",))]
        path_label = executable
    elif module:
        args = [sys.executable, "-m", module, *(version_args or ("--version",))]
        path_label = f"{sys.executable} -m {module}"
    else:
        return {"command": command, "available": False}
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)  # nosec B603
    except (OSError, subprocess.SubprocessError) as exc:
        return {"command": command, "available": False, "path": path_label, "error": str(exc)}
    output = (completed.stdout or completed.stderr).strip().splitlines()
    result = {
        "command": command,
        "available": completed.returncode == 0,
        "path": path_label,
        "returncode": completed.returncode,
    }
    if completed.returncode == 0:
        result["version"] = output[0] if output else ""
    else:
        result["error"] = output[0] if output else f"{command} exited with {completed.returncode}"
    return result


def collect_tool_availability() -> list[dict[str, Any]]:
    return [
        {"command": "python", "available": True, "path": sys.executable, "version": sys.version.split()[0]},
        tool_info("git", "--version"),
        tool_info("pytest", "--version", module="pytest"),
        tool_info("ruff", "--version"),
        tool_info("bandit", "--version", module="bandit"),
        tool_info("pip-audit", "--version", module="pip_audit"),
        tool_info("radon", "--version", module="radon"),
        tool_info("vulture", "--version", module="vulture"),
        tool_info("node", "--version"),
        tool_info("npm", "--version"),
    ]


def collect_parse_errors(py_files: list[Path]) -> list[dict[str, Any]]:
    errors = []
    for path in py_files:
        try:
            ast.parse(read_text(path), filename=rel(path))
        except SyntaxError as exc:
            errors.append({"path": rel(path), "line": exc.lineno, "error": exc.msg})
    return errors


def build_report() -> dict[str, Any]:
    files = iter_source_files()
    py_files = [path for path in files if path.suffix == ".py"]
    js_files = [path for path in files if path.suffix == ".js"]
    py_trees = {path: tree for path in py_files if (tree := parse_python(path)) is not None}
    imports, graph = collect_imports(py_trees)
    risky_patterns = collect_risky_patterns(py_trees, js_files, path_label=rel, read_source=read_text)

    report = {
        "generated_at": now_iso(),
        "root": str(ROOT_DIR),
        "summary": {
            "source_files": len(files),
            "python_files": len(py_files),
            "javascript_files": len(js_files),
            "html_css_files": len(files) - len(py_files) - len(js_files),
        },
        "biggest_files": biggest_files(files),
        "longest_functions": longest_functions(py_trees, js_files),
        "internal_imports": imports,
        "dependency_cycles": find_cycles(graph),
        "http_endpoints": collect_endpoints(py_trees, js_files),
        "risky_patterns": risky_patterns,
        "forbidden_layer_imports": forbidden_layer_imports(imports),
        "retired_artifacts": collect_retired_artifacts(ROOT_DIR, EXCLUDED_DIRS),
        "group_dependencies": group_dependencies(imports, js_files),
        "tool_availability": collect_tool_availability(),
        "parse_errors": collect_parse_errors(py_files),
    }
    report["quality_gates"] = evaluate_quality_gates(report)
    return report


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_None found._\n"
    output = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(output) + "\n"


def quality_gate_table(report: dict[str, Any]) -> str:
    quality_gates = report.get("quality_gates", {})
    gate_checks = quality_gates.get("checks", {})
    return table(
        ["Gate", "Status", "Findings"],
        [[key, "FAIL" if findings else "PASS", len(findings)] for key, findings in gate_checks.items()],
    )


def format_forbidden_layer_imports(report: dict[str, Any]) -> list[str]:
    if not report["forbidden_layer_imports"]:
        return []
    return [
        "## Forbidden layer imports",
        "",
        table(
            ["From", "To", "Path", "Line"],
            [[item["from"], item["to"], item["path"], item["line"]] for item in report["forbidden_layer_imports"]],
        ),
    ]


def format_retired_artifacts(report: dict[str, Any]) -> list[str]:
    if not report["retired_artifacts"]:
        return []
    return [
        "## Retired runtime artifacts",
        "",
        table(
            ["Path", "Line", "Match", "Snippet"],
            [[item["path"], item["line"], item["match"], item["snippet"]] for item in report["retired_artifacts"][:60]],
        ),
    ]


def format_parse_errors(report: dict[str, Any]) -> list[str]:
    if not report["parse_errors"]:
        return []
    return [
        "## Parse errors",
        "",
        table(
            ["Path", "Line", "Error"],
            [[item["path"], item["line"], item["error"]] for item in report["parse_errors"]],
        ),
    ]


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# WreckScanner architecture diagnostics",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Summary",
        "",
        table(["Metric", "Value"], [[key, value] for key, value in report["summary"].items()]),
        "## Quality gates",
        "",
        quality_gate_table(report),
        "## Biggest files",
        "",
        table(
            ["Path", "Lines", "Bytes"],
            [[item["path"], item["lines"], item["bytes"]] for item in report["biggest_files"][:15]],
        ),
        "## Longest functions",
        "",
        table(
            ["Path", "Function", "Line", "Lines", "Kind"],
            [
                [item["path"], item["name"], item["line"], item["lines"], item["kind"]]
                for item in report["longest_functions"][:20]
            ],
        ),
        "## Dependency cycles",
        "",
    ]
    cycles = report["dependency_cycles"]
    if cycles:
        lines.extend(f"- {' -> '.join(cycle)}" for cycle in cycles[:20])
        lines.append("")
    else:
        lines.append("_None found._\n")

    lines.extend(
        [
            "## Group dependencies",
            "",
            table(
                ["From", "To", "Count"],
                [[item["from"], item["to"], item["count"]] for item in report["group_dependencies"]],
            ),
            "## HTTP endpoints and route strings",
            "",
            table(
                ["Endpoint", "Source", "Line", "Method hint"],
                [
                    [item["path"], item["source"], item["line"], item["method_hint"]]
                    for item in report["http_endpoints"][:60]
                ],
            ),
            "## Risky patterns",
            "",
        ]
    )

    risky = report["risky_patterns"]
    for key in ["broad_excepts", "shell_true", "dynamic_code", "pickle_usage", "print_calls", "console_calls"]:
        lines.extend([f"### {key}", ""])
        sample = risky.get(key, [])[:30]
        if not sample:
            lines.append("_None found._\n")
            continue
        rows = [
            [item.get("path"), item.get("line"), item.get("type") or item.get("call") or item.get("snippet") or ""]
            for item in sample
        ]
        lines.append(table(["Path", "Line", "Detail"], rows))

    lines.extend(
        [
            "## Tool availability",
            "",
            table(
                ["Command", "Available", "Version"],
                [
                    [item["command"], item["available"], item.get("version") or item.get("error") or ""]
                    for item in report["tool_availability"]
                ],
            ),
        ]
    )
    lines.extend(format_forbidden_layer_imports(report))
    lines.extend(format_retired_artifacts(report))
    lines.extend(format_parse_errors(report))

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only architecture diagnostics for WreckScanner.")
    parser.add_argument("--markdown", action="store_true", help="Print a Markdown report.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--output-json", type=Path, help="Write the full JSON report to this path.")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when architecture quality gates fail.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()

    if args.output_json:
        output_path = args.output_json
        if not output_path.is_absolute():
            output_path = ROOT_DIR / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.markdown or not args.output_json:
        print(format_markdown(report), end="")

    return 1 if args.strict and report["quality_gates"]["status"] != "pass" else 0


if __name__ == "__main__":
    raise SystemExit(main())
