"""EvidenceRepository — append-only evidence and lineage storage facade."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from researchos.evidence.envelope import (
    LINEAGE_RELATIONS,
    EvidenceEnvelope,
    compute_artifact_hash,
    compute_lineage_hash,
)
from researchos.storage.repository import ResearchRepository

logger = logging.getLogger(__name__)


class EvidenceRepository:
    """Append-only evidence and lineage store over ``ResearchRepository``."""

    def __init__(self, repository: ResearchRepository | None = None) -> None:
        self._repo = repository or ResearchRepository(db_path=":memory:")

    def append_artifact(self, envelope: EvidenceEnvelope) -> EvidenceEnvelope:
        """Insert an immutable evidence envelope and its parent edges.

        Every declared parent must already exist. This prevents append-time
        creation of orphan lineage edges and makes the evidence graph closed
        under its parent references.
        """
        if not envelope.verify():
            raise ValueError(
                f"EvidenceEnvelope lineage_hash mismatch for artifact {envelope.artifact_hash}"
            )
        with self._repo._transaction() as cursor:
            cursor.execute(
                """
                SELECT artifact_type, version, created_at, payload, parent_hashes, lineage_hash
                FROM evidence
                WHERE artifact_hash = ?
                """,
                (envelope.artifact_hash,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                existing_payload = json.loads(existing[3])
                existing_parents = tuple(json.loads(existing[4]))
                if (
                    existing[0] != envelope.artifact_type
                    or existing[1] != envelope.version
                    or existing_payload != envelope.payload
                    or existing_parents != envelope.parent_hashes
                    or existing[5] != envelope.lineage_hash
                ):
                    raise ValueError(
                        f"Evidence artifact {envelope.artifact_hash} is immutable and cannot be overwritten"
                    )
                return EvidenceEnvelope(
                    artifact_type=existing[0],
                    artifact_hash=envelope.artifact_hash,
                    version=existing[1],
                    created_at=existing[2],
                    payload=existing_payload,
                    parent_hashes=existing_parents,
                    lineage_hash=existing[5],
                )

            for parent in envelope.parent_hashes:
                cursor.execute(
                    "SELECT 1 FROM evidence WHERE artifact_hash = ?",
                    (parent,),
                )
                if cursor.fetchone() is None:
                    raise ValueError(
                        f"Cannot append artifact {envelope.artifact_hash}: "
                        f"parent evidence {parent} does not exist"
                    )

            cursor.execute(
                """
                INSERT INTO evidence
                (artifact_type, artifact_hash, version, created_at, payload,
                 parent_hashes, lineage_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    envelope.artifact_type,
                    envelope.artifact_hash,
                    envelope.version,
                    envelope.created_at,
                    json.dumps(envelope.payload, ensure_ascii=False, default=str),
                    json.dumps(list(envelope.parent_hashes), ensure_ascii=False),
                    envelope.lineage_hash,
                ),
            )
            _insert_evidence_mirror(cursor, envelope)
            for parent in envelope.parent_hashes:
                self._insert_edge(
                    cursor,
                    parent,
                    envelope.artifact_hash,
                    _default_relation(envelope.artifact_type),
                )
        return envelope

    def add_lineage_edge(
        self,
        parent_hash: str,
        child_hash: str,
        relation: str = "feeds",
    ) -> None:
        if relation not in LINEAGE_RELATIONS:
            raise ValueError(
                f"Unknown lineage relation '{relation}'. Expected one of {LINEAGE_RELATIONS}."
            )
        with self._repo._transaction() as cursor:
            for artifact_hash, role in (
                (parent_hash, "parent"),
                (child_hash, "child"),
            ):
                cursor.execute(
                    "SELECT 1 FROM evidence WHERE artifact_hash = ?",
                    (artifact_hash,),
                )
                if cursor.fetchone() is None:
                    raise ValueError(
                        f"Cannot add lineage edge: {role} evidence {artifact_hash} does not exist"
                    )
            self._insert_edge(cursor, parent_hash, child_hash, relation)

    def get_artifact(self, artifact_hash: str) -> EvidenceEnvelope | None:
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT artifact_type, artifact_hash, version, created_at, payload, parent_hashes, lineage_hash FROM evidence WHERE artifact_hash = ?",
            (artifact_hash,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return EvidenceEnvelope(
            artifact_type=row[0],
            artifact_hash=row[1],
            version=row[2],
            created_at=row[3],
            payload=json.loads(row[4]),
            parent_hashes=tuple(json.loads(row[5])),
            lineage_hash=row[6],
        )

    def get_children(self, artifact_hash: str) -> list[str]:
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT child_hash FROM lineage WHERE parent_hash = ? ORDER BY child_hash",
            (artifact_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_parents(self, artifact_hash: str) -> list[str]:
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT parent_hash FROM lineage WHERE child_hash = ? ORDER BY parent_hash",
            (artifact_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def verify_evidence(self) -> bool:
        """Verify artifact hashes, lineage hashes, parent closure, and edge closure."""
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT artifact_type, artifact_hash, version, payload, parent_hashes, lineage_hash FROM evidence"
        )
        rows = cursor.fetchall()
        evidence_hashes = {row[1] for row in rows}

        for row in rows:
            payload = json.loads(row[3])
            parent_hashes = tuple(json.loads(row[4]))
            expected_artifact = compute_artifact_hash(row[0], row[2], payload)
            if expected_artifact != row[1]:
                return False
            expected_lineage = compute_lineage_hash(row[0], row[2], payload, parent_hashes)
            if expected_lineage != row[5]:
                return False
            if any(parent not in evidence_hashes for parent in parent_hashes):
                return False

        cursor.execute("SELECT parent_hash, child_hash, relation FROM lineage")
        for parent_hash, child_hash, relation in cursor.fetchall():
            if parent_hash not in evidence_hashes or child_hash not in evidence_hashes:
                return False
            if relation not in LINEAGE_RELATIONS:
                return False
            child = next((row for row in rows if row[1] == child_hash), None)
            if child is None or parent_hash not in tuple(json.loads(child[4])):
                return False
            if relation not in {_default_relation(child[0]), "contradicts", "replicates"}:
                return False

        cursor.execute("SELECT parent_hash, child_hash, relation FROM lineage")
        actual_edges = set(cursor.fetchall())
        row_by_hash = {row[1]: row for row in rows}
        for parent_hash, child_hash, relation in actual_edges:
            child = row_by_hash.get(child_hash)
            if child is None or parent_hash not in tuple(json.loads(child[4])):
                return False
            if relation not in {_default_relation(child[0]), "contradicts", "replicates"}:
                return False
        for row in rows:
            allowed = {_default_relation(row[0]), "contradicts", "replicates"}
            for parent in tuple(json.loads(row[4])):
                if not any((parent, row[1], relation) in actual_edges for relation in allowed):
                    return False
        return True

    def count_artifacts(self) -> int:
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evidence")
        return int(cursor.fetchone()[0])

    def count_edges(self) -> int:
        conn = self._repo._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM lineage")
        return int(cursor.fetchone()[0])

    def _insert_edge(self, cursor: Any, parent_hash: str, child_hash: str, relation: str) -> None:
        """Insert one typed relation for a parent/child pair.

        Repeating the exact typed edge is idempotent. Distinct relations for
        the same parent/child pair are valid and are stored independently.
        """
        cursor.execute(
            """
            SELECT 1
            FROM lineage
            WHERE parent_hash = ? AND child_hash = ? AND relation = ?
            """,
            (parent_hash, child_hash, relation),
        )
        if cursor.fetchone() is not None:
            return

        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO lineage
            (parent_hash, child_hash, relation, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (parent_hash, child_hash, relation, now),
        )


def _insert_evidence_mirror(cursor: Any, envelope: EvidenceEnvelope) -> None:
    """Persist the generic mirror without allowing overwrite or cross-type collision."""
    data = envelope.to_dict()
    data["object_type"] = "EvidenceEnvelope"
    cursor.execute("SELECT object_type, data FROM objects WHERE id = ?", (envelope.artifact_hash,))
    existing = cursor.fetchone()
    if existing is not None:
        existing_data = json.loads(existing[1])
        if existing[0] != "EvidenceEnvelope" or existing_data != data:
            raise ValueError(
                f"Object id {envelope.artifact_hash} already exists with conflicting content"
            )
        return
    cursor.execute(
        """
        INSERT INTO objects (id, object_type, created_at, data)
        VALUES (?, ?, ?, ?)
        """,
        (
            envelope.artifact_hash,
            "EvidenceEnvelope",
            envelope.created_at,
            json.dumps(data, ensure_ascii=False, default=str),
        ),
    )


def _default_relation(artifact_type: str) -> str:
    mapping = {
        "Feature": "feeds",
        "Experiment": "feeds",
        "Run": "executes",
        "Result": "produces",
        "Validation": "validates",
        "Finding": "derives",
        "Model": "trains",
        "Dataset": "feeds",
    }
    return mapping.get(artifact_type, "feeds")


class _EnvelopeObject:
    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def id(self) -> str:
        return str(self._data["artifact_hash"])

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


def _envelope_as_object(envelope: EvidenceEnvelope) -> _EnvelopeObject:
    data = envelope.to_dict()
    data["object_type"] = "EvidenceEnvelope"
    data["created_at"] = envelope.created_at
    return _EnvelopeObject(data)


__all__ = ["EvidenceRepository"]
