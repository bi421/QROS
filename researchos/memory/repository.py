"""
Market Memory Repository — stores and retrieves historical market states.

Provides query capabilities for:
    - Market snapshots by asset, timeframe, date range
    - Market regimes by asset and type
    - Macro states by geography and date range
    - Historical scenarios by tags and similarity
    - Dataset/source tracking for audit compatibility

Supports:
    - In-memory storage (default)
    - SQLite persistence (optional, via sqlite_path)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Protocol

from researchos.memory.models import (
    HistoricalScenario,
    MacroContextSnapshot,
    MarketRegime,
    MarketSnapshot,
)
from researchos.repository.memory import MemoryRepository

class _PersistableMarketObject(Protocol):
    id: str
    def to_dict(self) -> dict[str, object]: ...



class MarketMemoryRepository:
    """
    Repository for all market memory objects.

    Uses separate in-memory stores for each type to enable
    type-specific querying. Optionally persists to SQLite.

    Args:
        sqlite_path: Optional path to SQLite database file. If provided,
                     data is persisted to SQLite on every save.
    """

    def __init__(self, sqlite_path: str | None = None):
        self.snapshots: MemoryRepository[MarketSnapshot] = MemoryRepository()
        self.regimes: MemoryRepository[MarketRegime] = MemoryRepository()
        self.macro_states: MemoryRepository[MacroContextSnapshot] = MemoryRepository()
        self.scenarios: MemoryRepository[HistoricalScenario] = MemoryRepository()
        self.dataset_sources: set[str] = set()

        self._sqlite_path = sqlite_path
        self._sqlite_conn: sqlite3.Connection | None = None
        if sqlite_path:
            self._init_sqlite()
            self._load_all_from_sqlite()

    # -------------------------------------------------------------------------
    # SQLite persistence
    # -------------------------------------------------------------------------

    def _init_sqlite(self) -> None:
        """Initialize SQLite database and create tables if needed."""
        sqlite_path = self._sqlite_path
        if sqlite_path is None:
            raise RuntimeError("SQLite path is not configured")
        os.makedirs(os.path.dirname(sqlite_path) or ".", exist_ok=True)
        self._sqlite_conn = sqlite3.connect(sqlite_path)
        self._sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS market_memory_objects (
                id TEXT PRIMARY KEY,
                object_type TEXT NOT NULL,
                data TEXT NOT NULL,
                dataset_source TEXT DEFAULT '',
                saved_at TEXT NOT NULL
            )
        """)
        self._sqlite_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mm_object_type
            ON market_memory_objects(object_type)
        """)
        self._sqlite_conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mm_dataset_source
            ON market_memory_objects(dataset_source)
        """)
        self._sqlite_conn.commit()

    def _save_to_sqlite(self, obj: _PersistableMarketObject, object_type: str) -> None:
        """Save an object to SQLite."""
        if not self._sqlite_conn:
            return
        data = json.dumps(obj.to_dict(), sort_keys=True, default=str)
        dataset_source = str(getattr(obj, "dataset_source", ""))
        self._sqlite_conn.execute(
            "INSERT OR REPLACE INTO market_memory_objects (id, object_type, data, dataset_source, saved_at) VALUES (?, ?, ?, ?, ?)",
            (obj.id, object_type, data, dataset_source, datetime.now(timezone.utc).isoformat()),
        )
        self._sqlite_conn.commit()

    def _load_from_sqlite(self, object_type: str) -> list[dict]:
        """Load all objects of a given type from SQLite."""
        if not self._sqlite_conn:
            return []
        cursor = self._sqlite_conn.execute(
            "SELECT data FROM market_memory_objects WHERE object_type = ?",
            (object_type,),
        )
        results = []
        for row in cursor.fetchall():
            results.append(json.loads(row[0]))
        return results

    def _load_all_from_sqlite(self) -> None:
        """Load all objects from SQLite into in-memory stores."""
        if not self._sqlite_conn:
            return
        for data in self._load_from_sqlite("MarketSnapshot"):
            snapshot = MarketSnapshot.from_dict(data)
            self.snapshots.save(snapshot)
        for data in self._load_from_sqlite("MarketRegime"):
            regime = MarketRegime.from_dict(data)
            self.regimes.save(regime)
        for data in self._load_from_sqlite("MacroState"):
            macro_state = MacroContextSnapshot.from_dict(data)
            self.macro_states.save(macro_state)
        for data in self._load_from_sqlite("HistoricalScenario"):
            scenario = HistoricalScenario.from_dict(data)
            self.scenarios.save(scenario)
            if scenario.dataset_source:
                self.dataset_sources.add(scenario.dataset_source)

    def close(self) -> None:
        """Close SQLite connection if open."""
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None

    # -------------------------------------------------------------------------
    # Snapshot operations
    # -------------------------------------------------------------------------

    def save_snapshot(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """Save a market snapshot."""
        self.snapshots.save(snapshot)
        self._save_to_sqlite(snapshot, "MarketSnapshot")
        return snapshot

    def get_snapshot(self, id: str) -> MarketSnapshot | None:
        """Get a market snapshot by ID."""
        return self.snapshots.get(id)

    def get_snapshots_by_asset(self, asset: str, limit: int = 100) -> list[MarketSnapshot]:
        """Get snapshots for a specific asset, newest first."""
        results = [s for s in self.snapshots.get_all() if s.asset == asset]
        results.sort(key=lambda s: s.timestamp, reverse=True)
        return results[:limit]

    def get_snapshots_in_range(
        self,
        asset: str,
        start: datetime,
        end: datetime,
    ) -> list[MarketSnapshot]:
        """Get snapshots for an asset within a time range."""
        return [s for s in self.snapshots.get_all() if s.asset == asset and start <= s.timestamp <= end]

    # -------------------------------------------------------------------------
    # Regime operations
    # -------------------------------------------------------------------------

    def save_regime(self, regime: MarketRegime) -> MarketRegime:
        """Save a market regime classification."""
        self.regimes.save(regime)
        self._save_to_sqlite(regime, "MarketRegime")
        return regime

    def get_regime(self, id: str) -> MarketRegime | None:
        """Get a regime by ID."""
        return self.regimes.get(id)

    def get_regimes_by_asset(self, asset: str) -> list[MarketRegime]:
        """Get all regimes for a specific asset."""
        results = [r for r in self.regimes.get_all() if r.asset == asset]
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results

    # -------------------------------------------------------------------------
    # Macro state operations
    # -------------------------------------------------------------------------

    def save_macro_state(self, state: MacroContextSnapshot) -> MacroContextSnapshot:
        """Save a macro state snapshot."""
        self.macro_states.save(state)
        self._save_to_sqlite(state, "MacroState")
        return state

    def get_macro_state(self, id: str) -> MacroContextSnapshot | None:
        """Get a macro state by ID."""
        return self.macro_states.get(id)

    def get_macro_states_in_range(self, geography: str, start: datetime, end: datetime) -> list[MacroContextSnapshot]:
        """Get macro states for a geography within a time range."""
        return [m for m in self.macro_states.get_all() if m.geography == geography and start <= m.timestamp <= end]

    # -------------------------------------------------------------------------
    # Scenario operations
    # -------------------------------------------------------------------------

    def save_scenario(self, scenario: HistoricalScenario) -> HistoricalScenario:
        """Save a historical scenario."""
        self.scenarios.save(scenario)
        self._save_to_sqlite(scenario, "HistoricalScenario")
        if scenario.dataset_source:
            self.dataset_sources.add(scenario.dataset_source)
        return scenario

    def get_scenario(self, id: str) -> HistoricalScenario | None:
        """Get a scenario by ID."""
        return self.scenarios.get(id)

    def find_scenarios_by_tag(self, tag: str) -> list[HistoricalScenario]:
        """Find scenarios by tag (searches the scenario's `tags` attribute)."""
        return [s for s in self.scenarios.get_all() if tag in s.tags]

    def find_scenarios_by_outcome(self, outcome: str) -> list[HistoricalScenario]:
        """Find scenarios by outcome description."""
        return [s for s in self.scenarios.get_all() if outcome.lower() in s.outcome.lower()]

    def find_scenarios_by_dataset(self, dataset_source: str) -> list[HistoricalScenario]:
        """Find scenarios by dataset source."""
        return [s for s in self.scenarios.get_all() if s.dataset_source == dataset_source]

    def get_all_scenarios(self) -> list[HistoricalScenario]:
        """Get all scenarios."""
        return self.scenarios.get_all()

    # -------------------------------------------------------------------------
    # Dataset tracking
    # -------------------------------------------------------------------------

    def get_dataset_sources(self) -> list[str]:
        """Get all tracked dataset sources."""
        return sorted(self.dataset_sources)

    # -------------------------------------------------------------------------
    # Aggregation
    # -------------------------------------------------------------------------

    def count_all(self) -> dict[str, int]:
        """Get counts of all stored object types."""
        return {
            "snapshots": self.snapshots.count(),
            "regimes": self.regimes.count(),
            "macro_states": self.macro_states.count(),
            "scenarios": self.scenarios.count(),
        }

    def clear(self) -> None:
        """Clear all stored data."""
        self.snapshots.clear()
        self.regimes.clear()
        self.macro_states.clear()
        self.scenarios.clear()
        self.dataset_sources.clear()
        if self._sqlite_conn:
            self._sqlite_conn.execute("DELETE FROM market_memory_objects")
            self._sqlite_conn.commit()
