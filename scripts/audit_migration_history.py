"""Audit canonical Supabase migration names against a read-only history export.

This tool deliberately separates migration-history identity from schema equivalence.
It never connects to or mutates a database.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MIGRATION_NAME = re.compile(r"^(?P<stamp>\d{14})_(?P<name>.+)\.sql$")


def canonical_names(migrations_dir: Path) -> list[str]:
    return sorted(
        path.stem
        for path in migrations_dir.glob("*.sql")
        if MIGRATION_NAME.fullmatch(path.name)
    )


def remote_names(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        rows = payload.get("migrations", payload.get("rows", payload))
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError(
            "history export must be a JSON list or an object containing migrations/rows"
        )

    result: list[str] = []
    for row in rows:
        if isinstance(row, str):
            value = row
        elif isinstance(row, dict):
            value = row.get("name") or row.get("version")
        else:
            raise ValueError("each history row must be a string or object")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("each history row must contain a non-empty name/version")
        result.append(value.strip())
    return result


def load_aliases(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(
            "alias file must be a JSON object mapping canonical names to historical names"
        )
    aliases: dict[str, str] = {}
    for canonical, remote in value.items():
        if not isinstance(canonical, str) or not isinstance(remote, str):
            raise ValueError("migration aliases must map strings to strings")
        aliases[canonical] = remote
    return aliases


def audit(canonical: list[str], remote: list[str], aliases: dict[str, str]) -> dict[str, Any]:
    remote_set = set(remote)
    canonical_set = set(canonical)

    exact = sorted(canonical_set & remote_set)
    aliased = sorted(
        name
        for name, historical in aliases.items()
        if name in canonical_set and historical in remote_set
    )
    missing = sorted(canonical_set - set(exact) - set(aliased))

    alias_targets = [aliases[name] for name in aliased]
    duplicate_alias_targets = sorted(
        target for target in set(alias_targets) if alias_targets.count(target) > 1
    )
    duplicate_remote_names = sorted(
        name for name in remote_set if remote.count(name) > 1
    )

    return {
        "canonical_count": len(canonical),
        "remote_count": len(remote),
        "exact_matches": exact,
        "historical_alias_matches": [
            {"canonical": name, "remote": aliases[name]} for name in aliased
        ],
        "missing_canonical_names": missing,
        "unknown_remote_names": sorted(
            remote_set - canonical_set - set(alias_targets)
        ),
        "duplicate_remote_names": duplicate_remote_names,
        "duplicate_alias_targets": duplicate_alias_targets,
        "history_parity": (
            not missing
            and not duplicate_remote_names
            and not duplicate_alias_targets
        ),
        "schema_equivalence": "NOT_EVALUATED",
        "mutation_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--migrations-dir", type=Path, required=True)
    parser.add_argument("--remote-history-json", type=Path, required=True)
    parser.add_argument("--aliases-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = audit(
        canonical_names(args.migrations_dir),
        remote_names(
            json.loads(args.remote_history_json.read_text(encoding="utf-8"))
        ),
        load_aliases(args.aliases_json),
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
