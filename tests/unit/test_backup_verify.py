from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.backup_verify import sha256_file


def test_sha256_file_matches_hashlib_for_binary_payload(tmp_path: Path) -> None:
    payload = (b"qros-backup\x00" * 100_000) + b"tail"
    path = tmp_path / "backup.dump"
    path.write_bytes(payload)

    assert sha256_file(path, chunk_size=17) == hashlib.sha256(payload).hexdigest()


def test_sha256_file_rejects_non_positive_chunk_size(tmp_path: Path) -> None:
    path = tmp_path / "backup.dump"
    path.write_bytes(b"payload")

    with pytest.raises(ValueError, match="chunk_size must be positive"):
        sha256_file(path, chunk_size=0)
