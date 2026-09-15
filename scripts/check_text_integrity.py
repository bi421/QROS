#!/usr/bin/env python3
"""Reject UTF-8 BOMs and invalid UTF-8 in staged text files."""
from __future__ import annotations

import sys
from pathlib import Path

TEXT_SUFFIXES = {
    ".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".md", ".txt",
    ".ini", ".cfg", ".cmake", ".cpp", ".cc", ".cxx", ".h", ".hpp",
}

failures: list[str] = []
for name in sys.argv[1:]:
    path = Path(name)
    if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
        continue
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        failures.append(f"BOM: {name}")
        continue
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"UTF-8: {name}: {exc}")

if failures:
    print("\n".join(failures))
    raise SystemExit(1)

print("TEXT INTEGRITY: PASS")
