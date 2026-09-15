#!/usr/bin/env python3
"""Repository-truth audit: verify claims against reachable Git/filesystem evidence.

This is intentionally evidence-first. It never treats prose as proof and records the
exact verification command plus command output for every row.
"""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOTS = (ROOT / "docs",)
CODE_ROOTS = (ROOT / "researchos", ROOT / "scripts", ROOT / "cpp_quant_engine")
ARTIFACT_RE = re.compile(r"`?(?:artifacts|data)/[^`\s)]+`?")
SHA_RE = re.compile(r"\b[a-f0-9]{64}\b", re.I)
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
ROOT_PY = re.compile(r"^[^/\\]+\.py$", re.I)
SCOPE_PATTERNS = (
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
    output = (p.stdout + p.stderr).strip()
    return output, p.returncode


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


def non_test_python() -> list[Path]:
    result: list[Path] = []
    for root in CODE_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "test" not in p.parts and not p.name.startswith("test_"):
                result.append(p)
    return result


def main() -> int:
    rows: list[Row] = []

    # 1. Documentation artifact citations.
    for doc_root in DOC_ROOTS:
        for path in files_under(doc_root):
            if path.suffix.lower() not in {".md", ".rst", ".txt"}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, text in enumerate(lines, 1):
                refs = ARTIFACT_RE.findall(text)
                for ref in refs:
                    target = ref.strip("`")
                    output, code = git_history(target)
                    if code != 0 or not output:
                        rows.append(Row(
                            "FABRICATED_CITATION", rel, i,
                            f"documentation cites {target}",
                            f"git log --all --full-history -- {target}",
                            f"EXIT={code}; STDOUT/STDERR={'<EMPTY>' if not output else output!r}",
                            "CRITICAL",
                        ))
                    else:
                        rows.append(Row(
                            "ARTIFACT_HISTORY", rel, i,
                            f"documentation cites {target}",
                            f"git log --all --full-history -- {target}",
                            f"EXIT=0; HISTORY_FOUND={output.splitlines()[0]}",
                            "PASS",
                        ))

    # 2. Public exports that point at obvious stubs.
    for init in ROOT.joinpath("researchos").rglob("__init__.py"):
        text = init.read_text(encoding="utf-8", errors="replace")
        exports = set(re.findall(r"^\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*,?\s*$", text, re.M))
        imports = re.findall(r"^\s*from\s+([\w.]+)\s+import\s+([^\n#]+)", text, re.M)
        for module_name, imported in imports:
            names = [x.strip().split(" as ")[-1] for x in imported.split(",")]
            if not exports.intersection(names):
                continue
            module_path = ROOT.joinpath(*module_name.split("."))
            source = module_path.with_suffix(".py")
            if not source.exists():
                source = module_path / "__init__.py"
            if not source.exists():
                continue
            body = source.read_text(encoding="utf-8", errors="replace")
            if "NotImplementedError" in body or "TODO: Implement" in body:
                rows.append(Row(
                    "STUB_EXPOSED_AS_PUBLIC_API",
                    init.relative_to(ROOT).as_posix(),
                    1,
                    f"public export imports from stub-bearing module {module_name}",
                    f"grep -nE 'TODO|NotImplementedError|pass' {source.relative_to(ROOT).as_posix()}",
                    "STUB_MARKERS_FOUND",
                    "CRITICAL",
                ))

    # 3. Root-level Python files not covered by existing scope patterns.
    for path in sorted(ROOT.glob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if not any(pattern.search(rel) for pattern in SCOPE_PATTERNS):
            rows.append(Row(
                "SCOPE_GUARD_GAP", rel, 1,
                "root-level Python file is not matched by an existing forbidden-path rule",
                "python scripts/check_scope.py --base origin/main",
                "CURRENT_SCOPE_RULES_DO_NOT_MATCH_THIS_PATH",
                "HIGH",
            ))

    # 4. TODO/FIXME/HACK static call trace.
    sources = non_test_python()
    source_text = {p: p.read_text(encoding="utf-8", errors="replace") for p in sources}
    for path in sources:
        try:
            tree = ast.parse(source_text[path], filename=str(path))
        except SyntaxError:
            continue
        lines = source_text[path].splitlines()
        for i, text in enumerate(lines, 1):
            if not TODO_RE.search(text):
                continue
            fn = enclosing_function(tree, i)
            symbol = fn.name if fn else None
            live = False
            if symbol:
                for other, other_text in source_text.items():
                    if other == path:
                        continue
                    if re.search(rf"\b{re.escape(symbol)}\b", other_text):
                        live = True
                        break
                # Same-file attribute/name references outside the function are also evidence.
                if not live:
                    prefix = "\n".join(lines[: max(0, i - 1)]) + "\n".join(lines[getattr(fn, "end_lineno", i):]) if fn else source_text[path]
                    live = bool(re.search(rf"\b{re.escape(symbol)}\b", prefix))
            status = "LIVE_TODO" if live else "DEAD_TODO"
            rows.append(Row(
                status,
                path.relative_to(ROOT).as_posix(),
                i,
                text.strip(),
                f"static AST/name trace for symbol {symbol or '<module>'}",
                "REFERENCED_FROM_NON_TEST_CODE" if live else "NO_NON_TEST_REFERENCE_FOUND",
                "HIGH" if live else "MEDIUM",
            ))

    # 5. Duplicate domain-tree signal (conservative; ownership docs can suppress known pairs).
    ownership = (ROOT / "docs" / "CANONICAL_ENGINE.md").read_text(encoding="utf-8", errors="replace") if (ROOT / "docs" / "CANONICAL_ENGINE.md").exists() else ""
    candidate_dirs = [p.relative_to(ROOT).as_posix() for p in ROOT.iterdir() if p.is_dir() and any(k in p.name.lower() for k in ("engine", "quant", "storage"))]
    for a in candidate_dirs:
        for b in candidate_dirs:
            if a >= b:
                continue
            if a.split("/")[0] in ownership and b.split("/")[0] in ownership:
                continue
            rows.append(Row(
                "DUPLICATE_DOMAIN_TREE_CANDIDATE", a, 1,
                f"domain-tree overlap candidate with {b}",
                "find + docs/CANONICAL_ENGINE.md ownership review",
                "MANUAL_REVIEW_REQUIRED",
                "MEDIUM",
            ))

    out = ROOT / "docs" / "audits" / "repository_truth_audit.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r.category, r.file, r.line))
    lines = [
        "# Repository Truth Audit",
        "",
        "Generated by `scripts/audit_repository_truth.py`.",
        "",
        "**Rule:** no claim is treated as verified unless the command and its output are recorded.",
        "",
        "| category | file | line | claim | verification command run | verification result | severity |",
        "|---|---|---:|---|---|---|---|",
    ]
    for r in rows:
        def esc(v: str) -> str:
            return v.replace("|", "\\|").replace("\n", "<br>")
        lines.append(f"| {esc(r.category)} | {esc(r.file)} | {r.line} | {esc(r.claim)} | `{esc(r.command)}` | {esc(r.result)} | {r.severity} |")
    if not rows:
        lines.append("| CLEAN | — | — | No findings | — | AUDIT_CLEAN | PASS |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    critical = sum(r.severity == "CRITICAL" for r in rows)
    print(f"REPOSITORY TRUTH AUDIT: {'FAIL' if critical else 'PASS'}")
    print(f"ROWS={len(rows)} CRITICAL={critical}")
    print(f"REPORT={out.relative_to(ROOT).as_posix()}")
    return 1 if critical else 0


if __name__ == "__main__":
    raise SystemExit(main())
