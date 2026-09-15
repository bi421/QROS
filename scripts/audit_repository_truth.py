#!/usr/bin/env python3
"""Repository-truth audit: verify claims against reachable Git/filesystem evidence.

Explicitly unverified historical references are distinguished from fabricated claims.
Static TODO reachability is a heuristic and is reported as such.
"""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs"
CODE_ROOTS = (ROOT / "researchos", ROOT / "scripts", ROOT / "cpp_quant_engine")
ARTIFACT_RE = re.compile(r"(?:`|\b)((?:artifacts|data)/[A-Za-z0-9_./-]+)(?:`|\b)")
SHA_RE = re.compile(r"\b[a-f0-9]{64}\b", re.I)
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
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


def enclosing_function(tree: ast.AST, lineno: int) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= lineno <= getattr(node, "end_lineno", node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    return best


def function_is_stub(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    meaningful = []
    for node in fn.body:
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) and isinstance(node.value.value, str):
            continue
        meaningful.append(node)
    if not meaningful:
        return True
    if all(isinstance(n, ast.Pass) or (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant) and n.value.value is Ellipsis) for n in meaningful):
        return True
    if len(meaningful) == 1 and isinstance(meaningful[0], ast.Raise):
        exc = meaningful[0].exc
        return isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError"
    return False


def module_symbol_stubs(source: Path, names: set[str]) -> set[str]:
    try:
        tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"), filename=str(source))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names and function_is_stub(node):
            found.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name in names:
            methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if any(function_is_stub(m) for m in methods):
                found.add(node.name)
    return found


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


def non_test_python() -> list[Path]:
    result: list[Path] = []
    for root in CODE_ROOTS:
        if root.exists():
            result.extend(p for p in root.rglob("*.py") if "tests" not in p.parts and not p.name.startswith("test_"))
    return sorted(set(result))


def call_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def doc_line_is_explicitly_unverified(lines: list[str], index: int) -> bool:
    window = "\n".join(lines[max(0, index - 4): min(len(lines), index + 4)]).lower()
    return any(x in window for x in ("unverified", "not recoverable", "not currently artifact-verified"))


def main() -> int:
    rows: list[Row] = []

    # 1. Verify artifact/data paths and SHA-256 claims in documentation.
    for path in files_under(DOC_ROOT):
        rel_parts = path.relative_to(ROOT).parts
        if "audits" in rel_parts or path.suffix.lower() not in {".md", ".rst", ".txt"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, text in enumerate(lines, 1):
            for match in ARTIFACT_RE.finditer(text):
                target = match.group(1)
                history, code = git_history(target)
                exists = (ROOT / target).exists()
                if code != 0 or not history:
                    unverified = doc_line_is_explicitly_unverified(lines, i - 1)
                    rows.append(Row(
                        "UNVERIFIED_ARTIFACT_REFERENCE" if unverified else "FABRICATED_CITATION",
                        rel, i, f"documentation references {target}",
                        f"git log --all --full-history -- {target}",
                        f"EXIT={code}; HISTORY={'EMPTY' if not history else history!r}; CURRENT_EXISTS={exists}",
                        "MEDIUM" if unverified else "CRITICAL",
                    ))
                else:
                    rows.append(Row("ARTIFACT_HISTORY", rel, i, f"documentation references {target}", f"git log --all --full-history -- {target}", f"EXIT=0; HISTORY_FOUND={history.splitlines()[0]}; CURRENT_EXISTS={exists}", "PASS"))
            for sha in SHA_RE.findall(text):
                nearby: list[str] = []
                for j in range(max(0, i - 3), min(len(lines), i + 2)):
                    nearby.extend(m.group(1) for m in ARTIFACT_RE.finditer(lines[j]))
                if not nearby:
                    rows.append(Row("SHA_WITHOUT_ARTIFACT_TARGET", rel, i, f"SHA-256 {sha} has no nearby artifact/data path", "context search for artifact path around SHA-256", "TARGET_UNRESOLVED", "MEDIUM"))
                    continue
                for target in sorted(set(nearby)):
                    target_path = ROOT / target
                    if target_path.exists():
                        digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
                        ok = digest.lower() == sha.lower()
                        rows.append(Row("SHA256_VERIFICATION" if ok else "SHA256_MISMATCH", rel, i, f"SHA-256 {sha} targets {target}", f"sha256sum {target}", f"ACTUAL_SHA256={digest}; MATCH={'YES' if ok else 'NO'}", "PASS" if ok else "CRITICAL"))
                    else:
                        rows.append(Row("SHA256_TARGET_MISSING", rel, i, f"SHA-256 {sha} targets {target}", f"sha256sum {target}", "TARGET_NOT_PRESENT_ON_CURRENT_WORKTREE", "MEDIUM" if doc_line_is_explicitly_unverified(lines, i - 1) else "CRITICAL"))

    # 2. Public exports: inspect the exported symbol/method, not unrelated module TODOs.
    for init in ROOT.joinpath("researchos").rglob("__init__.py"):
        for exposed, (module, symbol) in public_exports(init).items():
            source = resolve_module(module, init)
            if source is None:
                rows.append(Row("PUBLIC_EXPORT_TARGET_MISSING", init.relative_to(ROOT).as_posix(), 1, f"{exposed} target {module} cannot be resolved", f"resolve import {module}", "MODULE_NOT_FOUND", "CRITICAL"))
            elif module_symbol_stubs(source, {symbol}):
                rows.append(Row("STUB_EXPOSED_AS_PUBLIC_API", init.relative_to(ROOT).as_posix(), 1, f"public export {exposed} resolves to stub {symbol}", f"AST stub inspection of {source.relative_to(ROOT).as_posix()}", "STUB_METHOD_OR_SYMBOL", "CRITICAL"))
            else:
                rows.append(Row("PUBLIC_API_EXPORT", init.relative_to(ROOT).as_posix(), 1, f"public export {exposed} resolves to implemented symbol", f"AST inspection of {source.relative_to(ROOT).as_posix()}", "NO_EXPORTED_STUB_DETECTED", "PASS"))

    # 3. Existing root scripts are reported; check_scope.py blocks new/changed ones.
    for path in sorted(ROOT.glob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        matched = any(pattern.search(rel) for pattern in SCOPE_PATTERNS)
        rows.append(Row("SCOPE_COVERED" if matched else "SCOPE_GUARD_GAP", rel, 1, "root-level Python file scope coverage", "pattern comparison against scripts/check_scope.py", "MATCHED" if matched else "CURRENT_SCOPE_RULES_DO_NOT_MATCH_THIS_PATH", "PASS" if matched else "HIGH"))

    # 4. Static TODO reachability heuristic.
    sources = non_test_python()
    trees: dict[Path, ast.AST] = {}
    calls: set[str] = set()
    for path in sources:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue
        trees[path] = tree
        calls |= call_names(tree)
    for path, tree in trees.items():
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not TODO_RE.search(line):
                continue
            fn = enclosing_function(tree, i)
            symbol = fn.name if fn else "<module>"
            live = symbol != "<module>" and symbol in calls
            rows.append(Row("LIVE_TODO" if live else "DEAD_TODO", path.relative_to(ROOT).as_posix(), i, line.strip(), f"static AST call-name trace for {symbol}", "REFERENCED_BY_NON_TEST_CALL" if live else "NO_NON_TEST_CALL_REFERENCE_FOUND", "HIGH" if live else "MEDIUM"))

    # 5. Conservative duplicate-domain candidate detection.
    packages = [p for p in ROOT.rglob("__init__.py") if "researchos" in p.parts or "cpp_quant_engine" in p.parts]
    signatures: dict[str, set[str]] = {}
    for init in packages:
        try:
            tree = ast.parse(init.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        signatures[init.parent.relative_to(ROOT).as_posix()] = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    paths = sorted(signatures)
    for idx, a in enumerate(paths):
        for b in paths[idx + 1:]:
            overlap = signatures[a] & signatures[b]
            if overlap:
                na = re.sub(r"[^a-z0-9]", "", a.lower())
                nb = re.sub(r"[^a-z0-9]", "", b.lower())
                if na in nb or nb in na or len(overlap) >= 3:
                    rows.append(Row("DUPLICATE_DOMAIN_TREE_CANDIDATE", a, 1, f"package overlaps {b}; symbols={sorted(overlap)}", "AST package/signature comparison + docs/CANONICAL_ENGINE.md review", "MANUAL_REVIEW_REQUIRED", "MEDIUM"))

    out = ROOT / "docs" / "audits" / "repository_truth_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r.category, r.file, r.line, r.claim))
    report = ["# Repository Truth Audit", "", "Generated by `scripts/audit_repository_truth.py`.", "", "**Rule:** a claim is verified only when the verification command and result support it. Explicitly unverified historical references are not fabricated claims.", "", "| category | file | line | claim | verification command run | verification result | severity |", "|---|---|---:|---|---|---|---|"]
    for r in rows:
        def esc(v: str) -> str:
            return v.replace("|", "\\|").replace("\n", "<br>")
        report.append(f"| {esc(r.category)} | {esc(r.file)} | {r.line} | {esc(r.claim)} | `{esc(r.command)}` | {esc(r.result)} | {r.severity} |")
    if not rows:
        report.append("| CLEAN | — | — | No findings | — | AUDIT_CLEAN | PASS |")
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    critical = sum(r.severity == "CRITICAL" for r in rows)
    print(f"REPOSITORY TRUTH AUDIT: {'FAIL' if critical else 'PASS'}")
    print(f"ROWS={len(rows)} CRITICAL={critical}")
    print(f"REPORT={out.relative_to(ROOT).as_posix()}")
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
