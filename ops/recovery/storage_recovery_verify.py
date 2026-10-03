#!/usr/bin/env python3
"""Dependency-free storage recovery drill helper.

The caller supplies a source object downloaded from QROS/Supabase Storage and
an independent recovery copy path. The helper verifies byte-for-byte identity
and SHA-256 before any restore operation is considered successful.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--recovery-copy", required=True)
    p.add_argument("--restored", required=True)
    args = p.parse_args()

    source = Path(args.source)
    recovery = Path(args.recovery_copy)
    restored = Path(args.restored)
    for path in (source, recovery, restored):
        if not path.is_file():
            raise SystemExit(f"missing file: {path}")

    expected = sha256(source)
    recovery_hash = sha256(recovery)
    restored_hash = sha256(restored)

    if recovery_hash != expected:
        raise SystemExit(
            f"recovery copy hash mismatch: expected {expected}, got {recovery_hash}"
        )
    if restored_hash != expected:
        raise SystemExit(
            f"restored object hash mismatch: expected {expected}, got {restored_hash}"
        )

    print(f"source_sha256={expected}")
    print(f"recovery_copy_sha256={recovery_hash}")
    print(f"restored_sha256={restored_hash}")
    print("storage_recovery_verification=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
