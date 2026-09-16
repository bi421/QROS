import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any

from researchos.claims.claim import ResearchClaim
from researchos.core.base_object import BaseObject
from researchos.core.identity import deterministic_hash
from researchos.core.timestamp import parse_timestamp
from researchos.objects.attribution import Attribution, AttributionGraph
from researchos.objects.cognitive import Bias, CognitiveAssessment, LearningRecord
from researchos.objects.confidence import Confidence, ConfidenceReport
from researchos.objects.contradiction import Contradiction, ContradictionReport
from researchos.objects.evidence import Evidence, EvidenceRegistry
from researchos.objects.hypothesis import Hypothesis, HypothesisSet
from researchos.objects.interpretation import Interpretation, Narrative
from researchos.objects.knowledge import Knowledge, Lesson, Pattern
from researchos.objects.macro import (
    CentralBankDemand,
    DollarStrengthSnapshot,
    EconomicGrowthAssessment,
    FedPolicyAssessment,
    InflationAssessment,
    LaborMarketAssessment,
    MacroProbability,
    MacroRegime,
    MacroReport,
    MacroScore,
    PhysicalDemandSnapshot,
    PositioningAssessment,
    RealYieldSnapshot,
    SafeHavenAssessment,
)
from researchos.objects.market_memory import (
    LiquidityEvent,
    MarketEvent,
    MarketOutcome,
    MarketSession,
    MarketStructure,
    NewsReference,
    VolatilityState,
)
from researchos.objects.observation import MacroState, MarketState, Observation
from researchos.objects.process import AuditEntry, ReasoningChain, ResearchCycle
from researchos.objects.research import Research, ResearchQuestion, ResearchReport
from researchos.objects.scenario import Scenario, ScenarioSet
from researchos.objects.validation import FailureAnalysis, Validation
from researchos.repository.interface import RepositoryInterface

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3
SCHEMA_VERSION_KEY = "researchos_schema_version"
BUSY_TIMEOUT_MS = 5000
MAX_WRITE_RETRIES = 5


OBJECT_REGISTRY: dict[str, type] = {
    "Observation": Observation,
    "MarketState": MarketState,
    "MacroState": MacroState,
    "Evidence": Evidence,
    "EvidenceRegistry": EvidenceRegistry,
    "Interpretation": Interpretation,
    "Narrative": Narrative,
    "Hypothesis": Hypothesis,
    "HypothesisSet": HypothesisSet,
    "Scenario": Scenario,
    "ScenarioSet": ScenarioSet,
    "Confidence": Confidence,
    "ConfidenceReport": ConfidenceReport,
    "Contradiction": Contradiction,
    "ContradictionReport": ContradictionReport,
    "Research": Research,
    "ResearchQuestion": ResearchQuestion,
    "ResearchReport": ResearchReport,
    "ResearchClaim": ResearchClaim,
    "Validation": Validation,
    "FailureAnalysis": FailureAnalysis,
    "Knowledge": Knowledge,
    "Pattern": Pattern,
    "Lesson": Lesson,
    "Bias": Bias,
    "LearningRecord": LearningRecord,
    "CognitiveAssessment": CognitiveAssessment,
    "ResearchCycle": ResearchCycle,
    "ReasoningChain": ReasoningChain,
    "AuditEntry": AuditEntry,
    "MarketEvent": MarketEvent,
    "MarketStructure": MarketStructure,
    "LiquidityEvent": LiquidityEvent,
    "MarketSession": MarketSession,
    "VolatilityState": VolatilityState,
    "NewsReference": NewsReference,
    "MarketOutcome": MarketOutcome,
    "Attribution": Attribution,
    "AttributionGraph": AttributionGraph,
    "RealYieldSnapshot": RealYieldSnapshot,
    "DollarStrengthSnapshot": DollarStrengthSnapshot,
    "FedPolicyAssessment": FedPolicyAssessment,
    "InflationAssessment": InflationAssessment,
    "LaborMarketAssessment": LaborMarketAssessment,
    "EconomicGrowthAssessment": EconomicGrowthAssessment,
    "SafeHavenAssessment": SafeHavenAssessment,
    "CentralBankDemand": CentralBankDemand,
    "PhysicalDemandSnapshot": PhysicalDemandSnapshot,
    "PositioningAssessment": PositioningAssessment,
    "MacroScore": MacroScore,
    "MacroProbability": MacroProbability,
    "MacroRegime": MacroRegime,
    "MacroReport": MacroReport,
}


class _TransactionContext:
    """Retry-capable context manager for SQLite transactions."""

    def __init__(self, repo: "ResearchRepository"):
        self.repo = repo
        self.cursor: sqlite3.Cursor | None = None
        self.conn: sqlite3.Connection | None = None
        self._locked = False

    def _acquire_lock(self):
        self.repo._lock.acquire()
        self._locked = True

    def _release_lock(self):
        if self._locked:
            self.repo._lock.release()
            self._locked = False

    def __enter__(self) -> sqlite3.Cursor:
        last_exc: Exception | None = None
        for attempt in range(MAX_WRITE_RETRIES):
            self._acquire_lock()
            try:
                self.conn = self.repo._get_conn()
            except sqlite3.Error:
                self.conn = self.repo._reconnect()
            self.cursor = self.conn.cursor()
            try:
                return self.cursor
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) or "cannot commit" in str(e):
                    last_exc = e
                    self.conn.rollback()
                    self._release_lock()
                    time.sleep(0.1 * (2**attempt))
                    continue
                self._release_lock()
                raise
        self._release_lock()
        raise sqlite3.OperationalError(f"Could not acquire read lock after {MAX_WRITE_RETRIES} retries") from last_exc

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object | None) -> bool:
        last_exc: Exception | None = None
        try:
            for attempt in range(MAX_WRITE_RETRIES):
                try:
                    if exc_type is None and self.conn is not None:
                        self.conn.commit()
                    elif self.conn is not None:
                        self.conn.rollback()
                    return False
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e) or "cannot commit" in str(e):
                        last_exc = e
                        if self.conn is not None:
                            self.conn.rollback()
                        self._release_lock()
                        time.sleep(0.1 * (2**attempt))
                        self._acquire_lock()
                        continue
                    raise
            if last_exc is not None:
                raise sqlite3.OperationalError(f"Could not commit after {MAX_WRITE_RETRIES} retries") from last_exc
        finally:
            self._release_lock()
        return False


class ResearchRepository(RepositoryInterface[BaseObject]):
    def __init__(self, db_path: str = "researchos.db"):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._init_db()

    def close(self) -> None:
        """Close the repository SQLite connection safely."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:
                    logger.debug(
                        "SQLite connection close failed",
                        exc_info=True,
                    )
                finally:
                    self._conn = None
            self._closed = True

    def __enter__(self) -> "ResearchRepository":
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> bool:
        self.close()
        return False

    def __del__(self):
        """Best-effort cleanup for callers that do not explicitly close."""
        try:
            self.close()
        except Exception:
            # Never allow destructor cleanup to raise.
            pass

    def _configure_conn(self, conn: sqlite3.Connection):
        """Apply standard PRAGMAs to a connection."""
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

    def _get_conn(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("ResearchRepository is closed")

        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._configure_conn(self._conn)
        return self._conn

    def _reconnect(self) -> sqlite3.Connection:
        """Close stale connection and open a new one."""
        try:
            if self._conn is not None:
                self._conn.close()
        except sqlite3.Error:
            pass
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._configure_conn(self._conn)
        return self._conn

    def _transaction(self) -> "_TransactionContext":
        return _TransactionContext(self)

    def _check_integrity(self) -> str:
        """Run PRAGMA integrity_check and return the result."""
        cursor = self._get_conn().cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        if result != "ok":
            logger.warning("Database integrity check failed: %s", result)
        return result

    # ------------------------------------------------------------------
    # Schema migrations (ordered by target version)
    # ------------------------------------------------------------------

    @staticmethod
    def _migrate_v1_to_v2(cursor: sqlite3.Cursor):
        """Add reasoning_chain_id and ontology_tags to audit_logs (v1 → v2)."""
        columns = [row[1] for row in cursor.execute("PRAGMA table_info(audit_logs)")]
        if "reasoning_chain_id" not in columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN reasoning_chain_id TEXT DEFAULT ''")
        if "ontology_tags" not in columns:
            cursor.execute("ALTER TABLE audit_logs ADD COLUMN ontology_tags TEXT DEFAULT '[]'")

    @staticmethod
    def _migrate_v2_to_v3(cursor: sqlite3.Cursor):
        """Create the evidence & lineage tables (Phase 5.3a, v2 → v3).

        Additive only: any pre-existing tables are preserved.  The new tables
        are append-only, content-addressed evidence records and parent→child
        lineage edges consumed by ``EvidenceRepository``.
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                artifact_type TEXT NOT NULL,
                artifact_hash TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                parent_hashes TEXT NOT NULL,
                lineage_hash TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_evidence_type
            ON evidence(artifact_type)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lineage (
                parent_hash TEXT NOT NULL,
                child_hash TEXT NOT NULL,
                relation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (parent_hash, child_hash, relation)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lineage_child
            ON lineage(child_hash)
        """)

    MIGRATIONS: dict[int, Any] = {
        2: _migrate_v1_to_v2,
        3: _migrate_v2_to_v3,
    }

    def _get_schema_version(self, cursor: sqlite3.Cursor) -> int:
        cursor.execute("CREATE TABLE IF NOT EXISTS _schema_version (key TEXT PRIMARY KEY, version INTEGER)")
        cursor.execute("SELECT version FROM _schema_version WHERE key = ?", (SCHEMA_VERSION_KEY,))
        row = cursor.fetchone()
        return row[0] if row else 0

    def _set_schema_version(self, cursor: sqlite3.Cursor, version: int):
        cursor.execute(
            "INSERT OR REPLACE INTO _schema_version (key, version) VALUES (?, ?)",
            (SCHEMA_VERSION_KEY, version),
        )

    def _run_migrations(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        current = self._get_schema_version(cursor)

        for target_version in sorted(self.MIGRATIONS.keys()):
            if current < target_version:
                migrate_fn = self.MIGRATIONS[target_version]
                migrate_fn(cursor)
                self._set_schema_version(cursor, target_version)
                conn.commit()
                current = target_version

        if current < SCHEMA_VERSION:
            self._set_schema_version(cursor, SCHEMA_VERSION)
            conn.commit()

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cycles (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                research_id TEXT,
                status TEXT,
                data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                actor TEXT,
                action TEXT,
                object_id TEXT,
                object_type TEXT,
                before_state TEXT,
                after_state TEXT,
                previous_entry TEXT,
                entry_hash TEXT,
                reasoning_chain_id TEXT DEFAULT '',
                ontology_tags TEXT DEFAULT '[]'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS objects (
                id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_type
            ON objects(object_type)
        """)
        conn.commit()
        self._run_migrations()

    # ------------------------------------------------------------------
    # Generic object storage (Phase 4 expansion)
    # ------------------------------------------------------------------

    def save_object(self, obj: Any) -> None:
        """
        Save any ResearchOS object to the generic objects store.

        Uses the object's to_dict() for serialization. No business logic.

        Args:
            obj: Any object with id and to_dict().
        """
        data = obj.to_dict()
        created_at = data.get("created_at", datetime.now(timezone.utc).isoformat())
        object_type = data.get("object_type", type(obj).__name__)
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO objects (id, object_type, created_at, data)
                VALUES (?, ?, ?, ?)
                """,
                (obj.id, object_type, created_at, json.dumps(data, ensure_ascii=False)),
            )

    def load_by_id(self, object_id: str) -> dict[str, Any] | None:
        """
        Load any object by its deterministic ID.

        Args:
            object_id: The deterministic ID to look up.

        Returns:
            Dictionary representation of the object, or None if not found.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM objects WHERE id = ?", (object_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def load_by_type(self, object_type: str) -> list[dict[str, Any]]:
        """
        Load all objects of a given type.

        Args:
            object_type: The type name (e.g., "Observation", "Evidence").

        Returns:
            List of dictionary representations.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data FROM objects WHERE object_type = ? ORDER BY created_at",
            (object_type,),
        )
        return [json.loads(row[0]) for row in cursor.fetchall()]

    def delete_object(self, object_id: str) -> None:
        """Delete an object from the generic store."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM objects WHERE id = ?", (object_id,))
        conn.commit()

    def object_count(self, object_type: str | None = None) -> int:
        """Count objects, optionally filtered by type."""
        conn = self._get_conn()
        cursor = conn.cursor()
        if object_type:
            cursor.execute(
                "SELECT COUNT(*) FROM objects WHERE object_type = ?",
                (object_type,),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM objects")
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Object rehydration (Phase 2 — from_dict support)
    # ------------------------------------------------------------------

    def load_object(self, object_id: str) -> BaseObject | None:
        """
        Load and reconstruct an object by ID using from_dict().

        Args:
            object_id: The deterministic ID to look up.

        Returns:
            Reconstructed object, or None if not found.

        Raises:
            ValueError: If the stored object_type has no registered class.
        """
        data = self.load_by_id(object_id)
        if data is None:
            return None
        object_type = data.get("object_type")
        cls = OBJECT_REGISTRY.get(object_type)
        if cls is None:
            raise ValueError(f"No registered class for object_type '{object_type}'. Register the class in OBJECT_REGISTRY.")
        return cls.from_dict(data)

    def load_objects_by_type(self, object_type: str) -> list[BaseObject]:
        """
        Load and reconstruct all objects of a given type.

        Args:
            object_type: The type name.

        Returns:
            List of reconstructed objects.

        Raises:
            ValueError: If the object_type has no registered class.
        """
        cls = OBJECT_REGISTRY.get(object_type)
        if cls is None:
            raise ValueError(f"No registered class for object_type '{object_type}'. Register the class in OBJECT_REGISTRY.")
        dicts = self.load_by_type(object_type)
        return [cls.from_dict(d) for d in dicts]

    def delete(self, id: str) -> bool:
        """
        RepositoryInterface-compatible delete.

        Args:
            id: The object ID to delete.

        Returns:
            True if the object was deleted, False if not found.
        """
        with self._transaction() as cursor:
            cursor.execute("DELETE FROM objects WHERE id = ?", (id,))
            return cursor.rowcount > 0

    def find_by_tag(self, tag: str) -> list[BaseObject]:
        """
        RepositoryInterface-compatible find_by_tag.

        Searches the JSON data field for objects containing the given tag.

        Args:
            tag: The ontology tag to search for.

        Returns:
            List of matching objects.
        """
        result: list[BaseObject] = []
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM objects ORDER BY created_at")
        for row in cursor.fetchall():
            data = json.loads(row[0])
            tags = data.get("ontology_tags", [])
            if tag in tags:
                object_type = data.get("object_type")
                cls = OBJECT_REGISTRY.get(object_type)
                if cls is not None:
                    result.append(cls.from_dict(data))
        return result

    def count(self) -> int:
        """RepositoryInterface-compatible count."""
        return self.object_count()

    # ------------------------------------------------------------------
    # RepositoryInterface compatibility (Phase 3)
    # ------------------------------------------------------------------

    def save(self, obj: BaseObject) -> BaseObject:
        """
        RepositoryInterface-compatible save.

        Routes AuditEntry to save_audit_entry() for audit chain storage;
        delegates all other objects to save_object(). Returns the saved object.
        """
        if isinstance(obj, AuditEntry):
            self.save_audit_entry(obj)
        elif isinstance(obj, ResearchCycle):
            self.save_cycle(obj)
        else:
            self.save_object(obj)
        return obj

    def get(self, id: str) -> BaseObject | None:
        """
        RepositoryInterface-compatible get.

        Delegates to load_object() for rehydration via from_dict().
        """
        return self.load_object(id)

    def get_all(self) -> list[BaseObject]:
        """
        RepositoryInterface-compatible get_all.

        Loads all objects from the generic store and reconstructs them.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM objects ORDER BY created_at")
        result: list[BaseObject] = []
        for row in cursor.fetchall():
            data = json.loads(row[0])
            object_type = data.get("object_type")
            cls = OBJECT_REGISTRY.get(object_type)
            if cls is not None:
                result.append(cls.from_dict(data))
        return result

    # ------------------------------------------------------------------
    # Legacy ResearchCycle storage
    # ------------------------------------------------------------------

    def save_cycle(self, cycle: ResearchCycle):
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO cycles (id, created_at, research_id, status, data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cycle.id,
                    cycle.created_at.isoformat() if hasattr(cycle, "created_at") else "",
                    cycle.research_id,
                    cycle.status,
                    json.dumps(cycle.to_dict(), ensure_ascii=False),
                ),
            )

    def load_cycle(self, cycle_id: str) -> ResearchCycle | None:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM cycles WHERE id = ?", (cycle_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return ResearchCycle.from_dict(json.loads(row[0]))

    def save_audit_entry(self, entry: AuditEntry):
        data = entry.to_dict()
        with self._transaction() as cursor:
            cursor.execute(
                """
                INSERT OR REPLACE INTO audit_logs
                (id, timestamp, actor, action, object_id, object_type,
                 before_state, after_state, previous_entry, entry_hash,
                 reasoning_chain_id, ontology_tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.actor,
                    entry.action,
                    entry.object_id,
                    entry.object_type,
                    json.dumps(entry.before_state, ensure_ascii=False),
                    json.dumps(entry.after_state, ensure_ascii=False),
                    entry.previous_entry,
                    entry.entry_hash,
                    entry.reasoning_chain_id,
                    json.dumps(entry.ontology_tags, ensure_ascii=False),
                ),
            )

    def load_audit_entries(self) -> list[AuditEntry]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp")
        rows = cursor.fetchall()
        return [AuditEntry.from_dict(json.loads(row[7])) for row in rows]
