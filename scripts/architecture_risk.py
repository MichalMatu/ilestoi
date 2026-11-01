from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

PathLabel = Callable[[Path], str]
TextReader = Callable[[Path], str]


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _collect_except_finding(
    path: Path,
    node: ast.ExceptHandler,
    findings: dict[str, list[dict[str, Any]]],
    path_label: PathLabel,
) -> None:
    broad = node.type is None
    name = "bare"
    if isinstance(node.type, ast.Name):
        name = node.type.id
        broad = name in {"Exception", "BaseException"}
    if broad:
        findings["broad_excepts"].append({"path": path_label(path), "line": node.lineno, "type": name})


def _collect_call_findings(
    path: Path,
    node: ast.Call,
    findings: dict[str, list[dict[str, Any]]],
    path_label: PathLabel,
) -> None:
    name = _call_name(node.func)
    if name in {"eval", "exec"}:
        findings["dynamic_code"].append({"path": path_label(path), "line": node.lineno, "call": name})
    if name == "print":
        findings["print_calls"].append({"path": path_label(path), "line": node.lineno})
    if any(
        keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
        for keyword in node.keywords
    ):
        findings["shell_true"].append({"path": path_label(path), "line": node.lineno, "call": name})


def _collect_import_finding(
    path: Path,
    node: ast.Import | ast.ImportFrom,
    findings: dict[str, list[dict[str, Any]]],
    path_label: PathLabel,
) -> None:
    imported_names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
    if any(name == "pickle" or name.startswith("pickle.") for name in imported_names):
        findings["pickle_usage"].append({"path": path_label(path), "line": node.lineno, "import": imported_names})


def _collect_python_patterns(
    py_trees: dict[Path, ast.AST],
    findings: dict[str, list[dict[str, Any]]],
    path_label: PathLabel,
) -> None:
    for path, tree in py_trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                _collect_except_finding(path, node, findings, path_label)
            elif isinstance(node, ast.Call):
                _collect_call_findings(path, node, findings, path_label)
            elif isinstance(node, ast.Import | ast.ImportFrom):
                _collect_import_finding(path, node, findings, path_label)


def _collect_console_calls(
    js_files: list[Path],
    findings: dict[str, list[dict[str, Any]]],
    path_label: PathLabel,
    read_source: TextReader,
) -> None:
    for path in js_files:
        for lineno, line in enumerate(read_source(path).splitlines(), start=1):
            if "console." in line:
                findings["console_calls"].append(
                    {"path": path_label(path), "line": lineno, "snippet": line.strip()[:160]}
                )


def collect_risky_patterns(
    py_trees: dict[Path, ast.AST],
    js_files: list[Path],
    *,
    path_label: PathLabel,
    read_source: TextReader,
) -> dict[str, list[dict[str, Any]]]:
    findings: dict[str, list[dict[str, Any]]] = {
        "broad_excepts": [],
        "shell_true": [],
        "dynamic_code": [],
        "pickle_usage": [],
        "print_calls": [],
        "console_calls": [],
    }
    _collect_python_patterns(py_trees, findings, path_label)
    _collect_console_calls(js_files, findings, path_label, read_source)
    return findings
