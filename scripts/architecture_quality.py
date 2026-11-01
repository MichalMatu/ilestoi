from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEFAULT_FILE_LINE_LIMITS = {
    ".py": 650,
    ".js": 650,
    ".html": 1250,
    ".css": 650,
}
FILE_LINE_LIMIT_OVERRIDES: dict[str, int] = {
    # Contract cases cover many independent UI modules, not a runtime monolith.
    "tests/test_frontend_contracts.py": 700,
}
FUNCTION_LINE_LIMITS = {
    "python": 140,
    "javascript": 90,
}
# The trackpad controller owns one gesture lifecycle and needs its closures together.
FUNCTION_LINE_LIMIT_OVERRIDES = {("web/app/trackpad_zoom.js", "installSmoothTrackpadZoom"): 120}
FORBIDDEN_LAYER_IMPORTS = {
    "core": {"app", "scripts", "tests", "web"},
    "app": {"scripts", "tests", "web"},
    "scripts": {"tests", "web"},
}
RUNTIME_ARTIFACT_SCAN_TARGETS = ("app", "core", "scripts", "web", "README.md", "pyproject.toml")
RUNTIME_ARTIFACT_EXCLUDED_FILES = {"scripts/diagnose_architecture.py", "scripts/architecture_quality.py"}
RETIRED_ARTIFACT_RE = re.compile(
    r"/api/wrecks|zidentyfikowane_wraki|wreck_photos|attached_wreck|saved_wreck|saved-wreck|"
    r"manual_wreck|WRECKS_DIR|WRECKS_URL|WRECKS_ROUTE|saved_wrecks|wreck_review|scan_analysis|yolo_wrecks",
    re.IGNORECASE,
)


def rel(root_dir: Path, path: Path) -> str:
    return path.relative_to(root_dir).as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def iter_artifact_scan_files(root_dir: Path, excluded_dirs: set[str]) -> list[Path]:
    files: list[Path] = []
    for target in RUNTIME_ARTIFACT_SCAN_TARGETS:
        base = root_dir / target
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else list(base.rglob("*"))
        for path in candidates:
            if not path.is_file():
                continue
            if any(part in excluded_dirs for part in path.relative_to(root_dir).parts):
                continue
            if rel(root_dir, path) in RUNTIME_ARTIFACT_EXCLUDED_FILES:
                continue
            if path.suffix in {".py", ".js", ".html", ".css", ".md", ".toml"}:
                files.append(path)
    return sorted(files)


def collect_retired_artifacts(root_dir: Path, excluded_dirs: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in iter_artifact_scan_files(root_dir, excluded_dirs):
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            for match in RETIRED_ARTIFACT_RE.finditer(line):
                findings.append(
                    {
                        "path": rel(root_dir, path),
                        "line": lineno,
                        "match": match.group(0),
                        "snippet": line.strip()[:180],
                    }
                )
    return findings


def forbidden_layer_imports(imports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for item in imports:
        source_group = item["from"].split(".", 1)[0]
        target_group = item["to"].split(".", 1)[0]
        if target_group not in FORBIDDEN_LAYER_IMPORTS.get(source_group, set()):
            continue
        violations.append(
            {
                "from": item["from"],
                "to": item["to"],
                "path": item["path"],
                "line": item["line"],
            }
        )
    return violations


def file_line_limit(path: str) -> int | None:
    if path in FILE_LINE_LIMIT_OVERRIDES:
        return FILE_LINE_LIMIT_OVERRIDES[path]
    return DEFAULT_FILE_LINE_LIMITS.get(Path(path).suffix)


def file_size_violations(biggest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for item in biggest:
        limit = file_line_limit(item["path"])
        if limit is None or item["lines"] <= limit:
            continue
        violations.append({**item, "limit": limit})
    return violations


def function_size_violations(longest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for item in longest:
        limit = FUNCTION_LINE_LIMIT_OVERRIDES.get((item["path"], item["name"]), FUNCTION_LINE_LIMITS.get(item["kind"]))
        if limit is None or item["lines"] <= limit:
            continue
        violations.append({**item, "limit": limit})
    return violations


def evaluate_quality_gates(report: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "file_size": file_size_violations(report.get("biggest_files", [])),
        "function_size": function_size_violations(report.get("longest_functions", [])),
        "layer_imports": report.get("forbidden_layer_imports", []),
        "retired_artifacts": report.get("retired_artifacts", []),
        "parse_errors": report.get("parse_errors", []),
    }
    return {
        "status": "fail" if any(checks.values()) else "pass",
        "checks": checks,
    }
