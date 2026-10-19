#!/usr/bin/env python
"""Validate a fresh HFT snapshot and append it to local QROS evidence storage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from researchos.data_engine.hft_feed import HFTQuoteSnapshotError, load_hft_quote_snapshot
from researchos.evidence.hft_quote_emission import emit_hft_quote_snapshot
from researchos.evidence.repository import EvidenceRepository
from researchos.storage.repository import ResearchRepository


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(root / ".health" / "hft-xauusd-quote.json"))
    parser.add_argument("--db", default=str(root / ".healthcheck" / "hft-evidence.sqlite3"))
    parser.add_argument("--max-age-seconds", type=float, default=15.0)
    args = parser.parse_args()
    if not 0 < args.max_age_seconds <= 15:
        parser.error("max-age-seconds must be > 0 and <= 15")

    db_path = Path(args.db).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot = load_hft_quote_snapshot(args.input, max_age_seconds=args.max_age_seconds)
        storage = ResearchRepository(db_path=str(db_path))
        try:
            evidence = EvidenceRepository(repository=storage)
            envelope = emit_hft_quote_snapshot(snapshot, repository=evidence)
            verified = evidence.verify_evidence()
            stored = evidence.get_artifact(envelope.artifact_hash)
            if not verified or stored is None or not stored.verify():
                raise RuntimeError("persisted evidence failed read-back integrity verification")
        finally:
            storage.close()
    except (OSError, HFTQuoteSnapshotError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, indent=2, ensure_ascii=False))
        return 2

    print(json.dumps({
        "status": "EVIDENCE_PERSISTED_AND_VERIFIED",
        "artifact_type": envelope.artifact_type,
        "artifact_hash": envelope.artifact_hash,
        "lineage_hash": envelope.lineage_hash,
        "source_payload_sha256": snapshot.payload_sha256,
        "symbol": snapshot.symbol,
        "provider": snapshot.provider,
        "event_time_utc": snapshot.event_time_utc.isoformat(),
        "ingest_time_utc": snapshot.ingest_time_utc.isoformat(),
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "mid_price": snapshot.mid_price,
        "database_path": str(db_path),
        "database_scope": "local SQLite only; not tenant-scoped production storage",
        "research_run_attached": False,
        "order_routing": "not called",
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
