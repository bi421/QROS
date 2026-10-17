"""CLI for reproducible combinatorial purged CV reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import timedelta, datetime, timezone
from pathlib import Path
from typing import Any

from researchos.orchestration.combinatorial_purged_cv import combinatorial_purged_cv_evaluate


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_sha(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, help="JSON array of labelled event rows or object with 'rows'"
    )
    parser.add_argument("--output", required=True, help="Path for the audit JSON")
    parser.add_argument("--groups", type=int, default=6)
    parser.add_argument("--test-groups", type=int, default=2)
    parser.add_argument("--embargo-minutes", type=int, default=0)
    parser.add_argument("--min-train-rows", type=int, default=100)
    parser.add_argument("--l2", type=float, default=1.0)
    args = parser.parse_args()
    if args.embargo_minutes < 0:
        parser.error("--embargo-minutes must be >= 0")

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not input_path.is_file():
        parser.error("--input must point to an existing JSON file")
    if input_path == output_path:
        parser.error("--output must not overwrite the input dataset")

    raw = input_path.read_bytes()
    try:
        decoded: Any = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(f"input must be valid UTF-8 JSON: {exc}")
    rows = decoded.get("rows") if isinstance(decoded, dict) else decoded
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        parser.error(
            "input JSON must be an array of row objects or an object containing a 'rows' array"
        )

    root = Path(__file__).resolve().parents[1]
    source_path = root / "researchos" / "orchestration" / "combinatorial_purged_cv.py"
    model_source_path = root / "researchos" / "orchestration" / "logistic_probability.py"
    config = {
        "groups": args.groups,
        "test_groups": args.test_groups,
        "embargo_minutes": args.embargo_minutes,
        "min_train_rows": args.min_train_rows,
        "l2": args.l2,
    }
    config_hash = _sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode())
    result = combinatorial_purged_cv_evaluate(
        rows,
        n_groups=args.groups,
        n_test_groups=args.test_groups,
        embargo=timedelta(minutes=args.embargo_minutes),
        min_train_rows=args.min_train_rows,
        l2=args.l2,
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_sha": _git_sha(root),
        "dataset_path": str(input_path),
        "dataset_sha256": _sha256(raw),
        "source_path": str(source_path),
        "source_sha256": _sha256(source_path.read_bytes()),
        "model_source_path": str(model_source_path),
        "model_source_sha256": _sha256(model_source_path.read_bytes()),
        "config": config,
        "config_sha256": config_hash,
        "deterministic_result_sha256": _sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ),
        "research_only": True,
        "execution_authorized": False,
    }
    report = {"manifest": manifest, "result": result}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output_path),
                "dataset_sha256": manifest["dataset_sha256"],
                "config_sha256": config_hash,
                "result_sha256": manifest["deterministic_result_sha256"],
                "status": result["status"],
                "splits": result.get("requested_split_count", 0),
                "valid_splits": result.get("valid_split_count", 0),
                "execution_authorized": False,
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
