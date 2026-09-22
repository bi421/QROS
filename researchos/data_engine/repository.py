"""
DatasetRepository — storage and retrieval interfaces for market data.

Based on Article XVII: Object Model — Data Layer.

Provides both in-memory and SQLite-backed repositories for storing
and querying historical datasets and their metadata.

Guarantees:
    - Deterministic: Same data → same storage results
    - Auditable: Full CRUD tracking
    - Serializable: All stored objects support to_dict/from_dict
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, TypeVar, cast

from researchos.core.base_object import BaseObject
from researchos.data_engine.candle import Candle
from researchos.data_engine.contracts import DatasetStatus
from researchos.data_engine.dataset import HistoricalDataset
from researchos.data_engine.metadata import DatasetMetadata
from researchos.repository.interface import RepositoryInterface

T = TypeVar("T", bound=BaseObject)

DataRecord = Any


class DatasetRepository(RepositoryInterface[T]):
    """
    Repository for HistoricalDataset objects.

    Stores datasets and their metadata in memory.
    """

    def __init__(self):
        self._store: dict[str, T] = {}
        self._metadata_store: dict[str, DatasetMetadata] = {}

    def save(self, obj: T) -> T:
        self._store[obj.id] = obj
        if isinstance(obj, HistoricalDataset):
            self._update_metadata(obj)
        return obj

    def get(self, id: str) -> T | None:
        return self._store.get(id)

    def get_all(self) -> list[T]:
        return list(self._store.values())

    def delete(self, id: str) -> bool:
        if id in self._store:
            del self._store[id]
            self._metadata_store.pop(id, None)
            return True
        return False

    def find_by_tag(self, tag: str) -> list[T]:
        return [obj for obj in self._store.values() if tag in obj.ontology_tags]

    def count(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self._metadata_store.clear()

    def find_by_symbol(self, symbol: str) -> list[T]:
        return [obj for obj in self._store.values() if isinstance(obj, HistoricalDataset) and obj.symbol == symbol]

    def find_by_timeframe(self, timeframe: str) -> list[T]:
        return [obj for obj in self._store.values() if isinstance(obj, HistoricalDataset) and obj.timeframe == timeframe]

    def find_by_symbol_and_timeframe(self, symbol: str, timeframe: str) -> T | None:
        for obj in self._store.values():
            if isinstance(obj, HistoricalDataset) and obj.symbol == symbol and obj.timeframe == timeframe:
                return obj
        return None

    def find_by_date_range(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[T]:
        """Find datasets whose records overlap the given date range."""
        results: list[T] = []
        for obj in self._store.values():
            if not isinstance(obj, HistoricalDataset):
                continue
            if symbol is not None and obj.symbol != symbol:
                continue
            if timeframe is not None and obj.timeframe != timeframe:
                continue
            if obj.start_time and obj.end_time:
                if obj.start_time <= end_time and obj.end_time >= start_time:
                    results.append(obj)
        return results

    def get_metadata(self, dataset_id: str) -> DatasetMetadata | None:
        return self._metadata_store.get(dataset_id)

    def get_all_metadata(self) -> list[DatasetMetadata]:
        return list(self._metadata_store.values())

    def _update_metadata(self, dataset: HistoricalDataset) -> None:
        meta = DatasetMetadata(
            dataset_id=dataset.id,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            data_type=dataset.data_type,
            source=dataset.source,
            record_count=dataset.record_count,
            start_time=dataset.start_time,
            end_time=dataset.end_time,
            quality=dataset.quality.value,
            status=dataset.status.value,
            dataset_hash=dataset.dataset_hash,
            version=dataset.version,
            tags=dataset.tags,
        )
        self._metadata_store[dataset.id] = meta


class SqliteDatasetRepository(RepositoryInterface[T]):
    """
    SQLite-backed repository for HistoricalDataset objects.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    data_type TEXT DEFAULT 'candle',
                    source TEXT DEFAULT '',
                    quality TEXT DEFAULT 'Raw',
                    status TEXT DEFAULT 'Pending',
                    record_count INTEGER DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    dataset_hash TEXT DEFAULT '',
                    dataset_content_hash TEXT DEFAULT '',
                    version TEXT DEFAULT '1.0.0',
                    tags TEXT DEFAULT '[]',
                    ontology_tags TEXT DEFAULT '[]',
                    created_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dataset_metadata (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    data_type TEXT DEFAULT 'candle',
                    source TEXT DEFAULT '',
                    source_file TEXT DEFAULT '',
                    record_count INTEGER DEFAULT 0,
                    start_time TEXT,
                    end_time TEXT,
                    quality TEXT DEFAULT 'Raw',
                    status TEXT DEFAULT 'Pending',
                    dataset_hash TEXT DEFAULT '',
                    version TEXT DEFAULT '1.0.0',
                    statistics TEXT DEFAULT '{}',
                    tags TEXT DEFAULT '[]',
                    description TEXT DEFAULT '',
                    ontology_tags TEXT DEFAULT '[]',
                    created_at TEXT,
                    FOREIGN KEY (dataset_id) REFERENCES datasets(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_symbol ON datasets(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_timeframe ON datasets(timeframe)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_datasets_symbol_timeframe ON datasets(symbol, timeframe)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_symbol_timeframe ON dataset_metadata(symbol, timeframe)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_start_time ON dataset_metadata(start_time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_end_time ON dataset_metadata(end_time)")
            conn.commit()
        finally:
            conn.close()

    def _ensure_record_table(self, dataset_id: str, data_type: str) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            table_name = f"records_{dataset_id.replace('-', '_')}"
            if data_type == "candle":
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        open REAL, high REAL, low REAL, close REAL,
                        volume REAL DEFAULT 0.0, quote_volume REAL DEFAULT 0.0,
                        trades_count INTEGER DEFAULT 0, is_complete INTEGER DEFAULT 1,
                        spread REAL, tick_volume REAL, real_volume REAL
                    )
                """)
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name}(timestamp)")
            else:
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, data TEXT NOT NULL
                    )
                """)
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name}(timestamp)")
            conn.commit()
        finally:
            conn.close()

    def save(self, obj: T) -> T:
        if isinstance(obj, HistoricalDataset):
            self._save_dataset(obj)
            self._save_records(obj)
        elif isinstance(obj, DatasetMetadata):
            self._save_metadata(obj)
        else:
            self._save_generic(obj)
        return obj

    def _save_dataset(self, dataset: HistoricalDataset) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO datasets
                (id, symbol, timeframe, data_type, source, quality, status,
                 record_count, start_time, end_time, dataset_hash,
                 dataset_content_hash, version, tags, ontology_tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dataset.id,
                    dataset.symbol,
                    dataset.timeframe,
                    dataset.data_type,
                    dataset.source,
                    dataset.quality.value,
                    dataset.status.value,
                    dataset.record_count,
                    dataset.start_time.isoformat() if dataset.start_time else None,
                    dataset.end_time.isoformat() if dataset.end_time else None,
                    dataset.dataset_hash,
                    dataset.dataset_content_hash,
                    dataset.version,
                    json.dumps(dataset.tags),
                    json.dumps(dataset.ontology_tags),
                    dataset.created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _save_records(self, dataset: HistoricalDataset) -> None:
        if not dataset._records:
            return
        self._ensure_record_table(dataset.id, dataset.data_type)
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            table_name = f"records_{dataset.id.replace('-', '_')}"
            rows: list[Any] = []
            for record in dataset._records:
                if isinstance(record, Candle):
                    rows.append(
                        (
                            record.id,
                            record.symbol,
                            record.timeframe,
                            record.timestamp.isoformat(),
                            record.open,
                            record.high,
                            record.low,
                            record.close,
                            record.volume,
                            record.quote_volume,
                            record.trades_count,
                            1 if record.is_complete else 0,
                            record.spread,
                            record.tick_volume,
                            record.real_volume,
                        )
                    )
            if rows:
                cursor.executemany(
                    f"""
                    INSERT OR REPLACE INTO {table_name}
                    (id, symbol, timeframe, timestamp, open, high, low, close,
                     volume, quote_volume, trades_count, is_complete,
                     spread, tick_volume, real_volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
            conn.commit()
        finally:
            conn.close()

    def _save_metadata(self, metadata: DatasetMetadata) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO dataset_metadata
                (id, dataset_id, symbol, timeframe, data_type, source, source_file,
                 record_count, start_time, end_time, quality, status, dataset_hash,
                 version, statistics, tags, description, ontology_tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metadata.id,
                    metadata.dataset_id,
                    metadata.symbol,
                    metadata.timeframe,
                    metadata.data_type,
                    metadata.source,
                    metadata.source_file,
                    metadata.record_count,
                    metadata.start_time.isoformat() if metadata.start_time else None,
                    metadata.end_time.isoformat() if metadata.end_time else None,
                    metadata.quality.value,
                    metadata.status.value,
                    metadata.dataset_hash,
                    metadata.version,
                    json.dumps(metadata.statistics),
                    json.dumps(metadata.tags),
                    metadata.description,
                    json.dumps(metadata.ontology_tags),
                    metadata.created_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _save_generic(self, obj: T) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS generic_objects (
                    id TEXT PRIMARY KEY, object_type TEXT NOT NULL, data TEXT NOT NULL
                )
            """)
            cursor.execute(
                """
                INSERT OR REPLACE INTO generic_objects (id, object_type, data)
                VALUES (?, ?, ?)
            """,
                (obj.id, obj.__class__.__name__, json.dumps(obj.to_dict())),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, id: str) -> T | None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                return cast(T, self._row_to_dataset(row))
            cursor.execute("SELECT * FROM dataset_metadata WHERE id = ?", (id,))
            row = cursor.fetchone()
            if row:
                return cast(T, self._row_to_metadata(row))
            return None
        finally:
            conn.close()

    def get_all(self) -> list[T]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets")
            results: list[T] = []
            for row in cursor.fetchall():
                dataset = self._row_to_dataset(row)
                if dataset is not None:
                    results.append(cast(T, dataset))
            return results
        finally:
            conn.close()

    def delete(self, id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM datasets WHERE id = ?", (id,))
            deleted = cursor.rowcount
            cursor.execute("DELETE FROM dataset_metadata WHERE id = ? OR dataset_id = ?", (id, id))
            try:
                cursor.execute("DELETE FROM generic_objects WHERE id = ?", (id,))
            except sqlite3.OperationalError:
                pass
            table_name = f"records_{id.replace('-', '_')}"
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.commit()
            return deleted > 0
        finally:
            conn.close()

    def find_by_tag(self, tag: str) -> list[T]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE ontology_tags LIKE ?", (f"%{tag}%",))
            results: list[T] = []
            for row in cursor.fetchall():
                dataset = self._row_to_dataset(row)
                if dataset is not None:
                    results.append(dataset)
            return results
        finally:
            conn.close()

    def count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM datasets")
            return int(cursor.fetchone()[0])
        finally:
            conn.close()

    def find_by_symbol(self, symbol: str) -> list[T]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE symbol = ?", (symbol,))
            results: list[T] = []
            for row in cursor.fetchall():
                dataset = self._row_to_dataset(row)
                if dataset is not None:
                    results.append(dataset)
            return results
        finally:
            conn.close()

    def find_by_timeframe(self, timeframe: str) -> list[T]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM datasets WHERE timeframe = ?", (timeframe,))
            results: list[T] = []
            for row in cursor.fetchall():
                dataset = self._row_to_dataset(row)
                if dataset is not None:
                    results.append(dataset)
            return results
        finally:
            conn.close()

    def find_by_symbol_and_timeframe(self, symbol: str, timeframe: str) -> T | None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM datasets WHERE symbol = ? AND timeframe = ?",
                (symbol, timeframe),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_dataset(row)
            return None
        finally:
            conn.close()

    def find_by_date_range(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: str | None = None,
        timeframe: str | None = None,
    ) -> list[T]:
        """
        Find datasets whose records overlap the given date range.

        Uses the (symbol, timeframe) and (start_time, end_time) indexes for
        fast lookup.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM datasets WHERE start_time IS NOT NULL AND end_time IS NOT NULL AND start_time <= ? AND end_time >= ?"
            params: list[Any] = [end_time.isoformat(), start_time.isoformat()]
            if symbol is not None:
                query += " AND symbol = ?"
                params.append(symbol)
            if timeframe is not None:
                query += " AND timeframe = ?"
                params.append(timeframe)
            cursor.execute(query, params)
            results: list[T] = []
            for row in cursor.fetchall():
                dataset = self._row_to_dataset(row)
                if dataset is not None:
                    results.append(dataset)
            return results
        finally:
            conn.close()

    def query_records(
        self,
        dataset_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 0,
    ) -> list[Any]:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            table_name = f"records_{dataset_id.replace('-', '_')}"
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if not cursor.fetchone():
                return []
            query = f"SELECT * FROM {table_name} WHERE 1=1"
            params: list[Any] = []
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time.isoformat())
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time.isoformat())
            query += " ORDER BY timestamp ASC"
            if limit > 0:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            records = []
            for row in rows:
                record = {
                    "id": row[0],
                    "symbol": row[1],
                    "timeframe": row[2],
                    "timestamp": row[3],
                }
                if len(row) > 4:
                    record.update(
                        {
                            "open": row[4],
                            "high": row[5],
                            "low": row[6],
                            "close": row[7],
                            "volume": row[8],
                        }
                    )
                records.append(record)
            return records
        finally:
            conn.close()

    def close(self) -> None:
        pass

    def _row_to_dataset(self, row: tuple[Any, ...]) -> HistoricalDataset | None:
        try:
            dataset = HistoricalDataset(
                symbol=row[1],
                timeframe=row[2],
                data_type=row[3],
                source=row[4],
                quality=row[5],
                version=row[11],
                id=row[0],
            )
            dataset.status = DatasetStatus(row[6])
            dataset.dataset_hash = row[10] if row[10] else ""
            dataset.dataset_content_hash = row[11] if len(row) > 11 and row[11] else ""
            if len(row) > 12 and row[12]:
                dataset.version = row[12]
            if len(row) > 13 and row[13]:
                dataset.tags = json.loads(row[13])
            if len(row) > 14 and row[14]:
                dataset.ontology_tags = json.loads(row[14])
            # Hydrate records so a retrieved dataset is a full dataset, not a shell.
            dataset._records = self._hydrate_records(dataset)
            # Restore frozen state for committed datasets.
            dataset._frozen = dataset.status in (
                DatasetStatus.READY,
                DatasetStatus.VALIDATED,
                DatasetStatus.ARCHIVED,
            )
            return dataset
        except Exception:
            return None

    def _hydrate_records(self, dataset: HistoricalDataset) -> list[Any]:
        """
        Reconstruct typed data records from the per-dataset SQLite table.

        Records are stored in `records_<dataset_id>` (dashes → underscores).
        Candle rows are converted back into Candle objects so the dataset
        contract is preserved exactly as it was saved.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            table_name = f"records_{dataset.id.replace('-', '_')}"
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if not cursor.fetchone():
                return []
            cursor.execute(f"SELECT * FROM {table_name} ORDER BY timestamp ASC")
            rows = cursor.fetchall()
            records: list[Any] = []
            for r in rows:
                if dataset.data_type == "candle":
                    from researchos.core.timestamp import parse_timestamp

                    records.append(
                        Candle(
                            symbol=r[1],
                            timeframe=r[2],
                            timestamp=parse_timestamp(r[3]),
                            open=r[4],
                            high=r[5],
                            low=r[6],
                            close=r[7],
                            volume=r[8] if len(r) > 8 else 0.0,
                            quote_volume=r[9] if len(r) > 9 else 0.0,
                            trades_count=r[10] if len(r) > 10 else 0,
                            is_complete=bool(r[11]) if len(r) > 11 else True,
                            spread=r[12] if len(r) > 12 and r[12] is not None else None,
                            tick_volume=r[13] if len(r) > 13 and r[13] is not None else None,
                            real_volume=r[14] if len(r) > 14 and r[14] is not None else None,
                        )
                    )
            return records
        finally:
            conn.close()

    def _row_to_metadata(self, row: tuple[Any, ...]) -> DatasetMetadata | None:
        try:
            meta = DatasetMetadata(
                dataset_id=row[1],
                symbol=row[2],
                timeframe=row[3],
                data_type=row[4],
                source=row[5],
                source_file=row[6],
                record_count=row[7],
                quality=row[10],
                status=row[11],
                dataset_hash=row[12] if row[12] else "",
                version=row[13],
                tags=json.loads(row[15]) if row[15] else [],
                description=row[16] if row[16] else "",
                id=row[0],
            )
            return meta
        except Exception:
            return None
