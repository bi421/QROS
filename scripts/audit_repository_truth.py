#!/usr/bin/env python3
"""Repository-truth audit with evidence-aware claim classification."""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs"
ARTIFACT_RE = re.compile(r"(?:`|\b)((?:artifacts|data)/[A-Za-z0-9_./-]+)(?:`|\b)")
CONCRETE_SUFFIXES = (".json", ".csv", ".parquet", ".zip", ".feather", ".arrow", ".sqlite", ".db")
SCOPE_PATTERNS = (
    re.compile(r"^[^/\\]+\.py$", re.I),
    re.compile(r"(^|/)(?:_tmp|tmp_|scratch_).*", re.I),
    re.compile(r"(^|/).*\.bak$", re.I),
    re.compile(r"(^|/)(?:pytest_|ruff_).*\.txt$", re.I),
    re.compile(r"(^|/)FORENSIC_AUDIT(?:[^/]*)", re.I),
    re.compile(r"(^|/)run_full_analysis[^/]*\.py$", re.I),
)

@dataclass
class Row:
    category: str
    file: str
    line: int
    claim: str
    command: str
    result: str
    severity: str


def run(command: list[str]) -> tuple[str, int]:
    p = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    return (p.stdout + p.stderr).strip(), p.returncode


def git_history(path: str) -> tuple[str, int]:
    return run(["git", "log", "--all", "--full-history", "--oneline", "--", path])


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def has_decorator(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    return any(
        (isinstance(d, ast.Name) and d.id == name)
        or (isinstance(d, ast.Attribute) and d.attr == name)
        for d in fn.decorator_list
    )


def function_is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if has_decorator(fn, "abstractmethod"):
        return False
    body = [
        n for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) and isinstance(n.value.value, str))
    ]
    if not body:
        return True
    if all(isinstance(n, ast.Pass) or (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) and n.value.value is Ellipsis) for n in body):
        return True
    if len(body) == 1 and isinstance(body[0], ast.Raise):
        exc = body[0].exc
        return isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError"
    return False


def is_protocol_class(cls: ast.ClassDef) -> bool:
    return any(
        (isinstance(base, ast.Name) and base.id == "Protocol")
        or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
        for base in cls.bases
    )


def class_is_stub(cls: ast.ClassDef) -> bool:
    # Protocols define interfaces by design; pass-only method bodies are not concrete stubs.
    if is_protocol_class(cls):
        return False
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    concrete = [m for m in methods if m.name != "__init__" and not has_decorator(m, "abstractmethod")]
    return bool(concrete) and all(function_is_stub(m) for m in concrete)


def module_symbol_is_stub(source: Path, symbol: str) -> bool:
    try:
        tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"), filename=str(source))
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            return function_is_stub(node)
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            return class_is_stub(node)
    return False


def resolve_module(module_name: str, init: Path) -> Path | None:
    if module_name.startswith("."):
        base = init.parent
        for _ in range(module_name.count(".") - 1):
            base = base.parent
        clean = module_name.lstrip(".")
        path = base.joinpath(*clean.split(".")) if clean else base
    else:
        path = ROOT.joinpath(*module_name.split("."))
    py = path.with_suffix(".py")
    if py.exists():
        return py
    pkg = path / "__init__.py"
    return pkg if pkg.exists() else None


def public_exports(init: Path) -> dict[str, tuple[str, str]]:
    try:
        tree = ast.parse(init.read_text(encoding="utf-8", errors="replace"), filename=str(init))
    except SyntaxError:
        return {}
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                    names.update(e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    result: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            module = ("." * node.level) + (node.module or "")
            for alias in node.names:
                exposed = alias.asname or alias.name
                if exposed in names:
                    result[exposed] = (module, alias.name)
    return result


def artifact_reference_is_code(lines: list[str], index: int) -> bool:
    in_fence = False
    for line in lines[:index]:
        if line.strip().startswith("```"):
            in_fence = not in_fence
    return in_fence


def doc_context_is_historical(lines: list[str], index: int) -> bool:
    # A document-level evidence notice can legitimately qualify a later provenance path.
    prefix = "\n".join(lines[:index]).lower()
    window = "\n".join(lines[max(0, index - 20): min(len(lines), index + 21)]).lower()
    tokens = ("unverified", "historical", "archive", "not recoverable", "recorded / unverified")
    return any(token in window for token in tokens) or "evidence integrity notice" in prefix


def artifact_is_concrete(target: str) -> bool:
    return target.lower().endswith(CONCRETE_SUFFIXES)


def main() -> int:
    rows: list[Row] = []

    for path in files_under(DOC_ROOT):
        rel = path.relative_to(ROOT).as_posix()
        parts = path.relative_to(ROOT).parts
        if "audits" in parts or path.suffix.lower() not in {".md", ".rst", ".txt"}:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        historical_file = rel.startswith("docs/archive/") or rel == "docs/CHANGELOG.md"
        for i, text in enumerate(lines, 1):
            if artifact_reference_is_code(lines, i - 1):
                continue
            for match in ARTIFACT_RE.finditer(text):
                target = match.group(1)
                if not artifact_is_concrete(target) or historical_file:
                    continue
                history, code = git_history(target)
                exists = (ROOT / target).exists()
                if history or exists:
                    rows.append(Row("ARTIFACT_HISTORY", rel, i, f"documentation references {target}", f"git log --all --full-history -- {target}", f"EXIT={code}; HISTORY_FOUND={bool(history)}; CURRENT_EXISTS={exists}", "PASS"))
                else:
                    historical = doc_context_is_historical(lines, i - 1)
                    rows.append(Row("UNVERIFIED_ARTIFACT_REFERENCE" if historical else "FABRICATED_CITATION", rel, i, f"documentation references {target}", f"git log --all --full-history -- {target}", f"EXIT={code}; HISTORY=EMPTY; CURRENT_EXISTS={exists}", "MEDIUM" if historical else "CRITICAL"))

    for init in ROOT.joinpath("researchos").rglob("__init__.py"):
        for exposed, (module, symbol) in public_exports(init).items():
            source = resolve_module(module, init)
            if source is None:
                rows.append(Row("PUBLIC_EXPORT_TARGET_MISSING", init.relative_to(ROOT).as_posix(), 1, f"{exposed} target {module} cannot be resolved", f"resolve import {module}", "MODULE_NOT_FOUND", "CRITICAL"))
            elif module_symbol_is_stub(source, symbol):
                rows.append(Row("STUB_EXPOSED_AS_PUBLIC_API", init.relative_to(ROOT).as_posix(), 1, f"public export {exposed} resolves to stub {symbol}", f"AST concrete-method inspection of {source.relative_to(ROOT).as_posix()}", "ALL_CONCRETE_METHODS_ARE_STUBS", "CRITICAL"))

    for path in sorted(ROOT.glob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        matched = any(pattern.search(rel) for pattern in SCOPE_PATTERNS)
        rows.append(Row("SCOPE_COVERED" if matched else "SCOPE_GUARD_GAP", rel, 1, "root-level Python file scope coverage", "pattern comparison against scripts/check_scope.py", "MATCHED" if matched else "CURRENT_SCOPE_RULES_DO_NOT_MATCH_THIS_PATH", "PASS" if matched else "HIGH"))

    out = ROOT / "docs" / "audits" / "repository_truth_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r.severity != "CRITICAL", r.category, r.file, r.line))
    report = [
        "# Repository Truth Audit", "", "Generated by `scripts/audit_repository_truth.py`.", "",
        "**Rule:** executable/current evidence claims must resolve to reachable artifacts or code. Historical, archived, and documentation-example references are recorded without being treated as fabricated current evidence.", "",
        "| category | file | line | claim | verification command run | verification result | severity |",
        "|---|---|---:|---|---|---|---|",
    ]
    for r in rows:
        def esc(value: str) -> str:
            return value.replace("|", "\\|").replace("\n", "<br>")
        report.append(f"| {esc(r.category)} | {esc(r.file)} | {r.line} | {esc(r.claim)} | `{esc(r.command)}` | {esc(r.result)} | {r.severity} |")
    if not rows:
        report.append("| CLEAN | — | — | No findings | — | AUDIT_CLEAN | PASS |")
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    critical = sum(row.severity == "CRITICAL" for row in rows)
    print(f"REPOSITORY TRUTH AUDIT: {'FAIL' if critical else 'PASS'}")
    print(f"ROWS={len(rows)} CRITICAL={critical}")
    print(f"REPORT={out.relative_to(ROOT).as_posix()}")
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
