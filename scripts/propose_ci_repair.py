#!/usr/bin/env python3
"""Create a bounded, proposal-only repair decision from classifier output."""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict, dataclass

REPAIRABLE_CATEGORIES = frozenset({
    "environment/tooling failure",
    "missing prerequisite",
    "formatting/static failure",
    "test/contract mismatch",
    "implementation defect",
})

@dataclass(frozen=True)
class RepairProposal:
    action: str
    category: str
    repairable: bool
    allowed: bool
    attempt_limit: int
    rationale: tuple[str, ...]

def propose(classification: dict[str, object], attempt_limit: int = 1) -> RepairProposal:
    if attempt_limit < 0:
        raise ValueError("attempt_limit must be non-negative")
    category = classification.get("category")
    repairable = classification.get("repairable") is True
    evidence = classification.get("evidence")
    if not isinstance(category, str):
        return RepairProposal("stop", "ambiguous/unsafe", False, False, attempt_limit, ("invalid or missing classification category",))
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        return RepairProposal("stop", category, False, False, attempt_limit, ("missing or invalid machine-readable evidence",))
    if not repairable or category not in REPAIRABLE_CATEGORIES:
        return RepairProposal("stop", category, False, False, attempt_limit, ("classification is not explicitly repairable",))
    if attempt_limit == 0:
        return RepairProposal("stop", category, True, False, 0, ("repair authority is disabled by attempt limit",))
    return RepairProposal("propose-only", category, True, True, attempt_limit, tuple(evidence))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classification", nargs="?", help="JSON file; stdin is used when omitted")
    parser.add_argument("--attempt-limit", type=int, default=1)
    args = parser.parse_args()
    raw = open(args.classification, encoding="utf-8").read() if args.classification else sys.stdin.read()
    proposal = propose(json.loads(raw), attempt_limit=args.attempt_limit)
    print(json.dumps(asdict(proposal), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
