"""Point-in-time multi-source market-state reconstruction.

Additive research component: observable features and source freshness only.
It does not infer hidden institutional intent or emit calibrated probabilities.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class EventClock:
    source: str
    event_time_ns: int
    ingest_time_ns: int
    sequence: int | None = None

    def validate(self) -> None:
        if not self.source.strip():
            raise ValueError("source is required")
        if self.event_time_ns <= 0 or self.ingest_time_ns <= 0:
            raise ValueError("timestamps must be positive UTC epoch nanoseconds")


@dataclass(frozen=True)
class Quote:
    clock: EventClock
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class BookSnapshot:
    clock: EventClock
    symbol: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]


@dataclass(frozen=True)
class TradePrint:
    clock: EventClock
    symbol: str
    price: float
    size: float
    aggressor_side: int  # +1 buy, -1 sell, 0 unknown


@dataclass(frozen=True)
class MacroPoint:
    clock: EventClock
    instrument: str
    value: float


@dataclass(frozen=True)
class SourcePolicy:
    max_age_ms: float = 2_000.0
    allow_clock_skew_ms: float = 250.0

    def validate(self) -> None:
        if not math.isfinite(self.max_age_ms) or self.max_age_ms < 0:
            raise ValueError("max_age_ms must be finite and non-negative")
        if not math.isfinite(self.allow_clock_skew_ms) or self.allow_clock_skew_ms < 0:
            raise ValueError("allow_clock_skew_ms must be finite and non-negative")


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _clock_features(clock: EventClock, decision_time_ns: int, policy: SourcePolicy) -> dict:
    clock.validate()
    age_ms = (decision_time_ns - clock.event_time_ns) / 1_000_000.0
    transport_ms = (clock.ingest_time_ns - clock.event_time_ns) / 1_000_000.0
    ingest_age_ms = (decision_time_ns - clock.ingest_time_ns) / 1_000_000.0
    valid = (age_ms >= 0 and ingest_age_ms >= 0
             and transport_ms >= -policy.allow_clock_skew_ms
             and age_ms <= policy.max_age_ms)
    return {
        "source": clock.source, "event_age_ms": age_ms,
        "ingest_age_ms": ingest_age_ms, "transport_ms": transport_ms,
        "clock_skew_suspected": transport_ms < 0, "fresh": valid,
        "reason": None if valid else "STALE_FUTURE_OR_CLOCK_SKEW",
    }


def _quote_features(quotes: Sequence[Quote], symbol: str, now: int, policy: SourcePolicy) -> dict:
    if not quotes:
        return {"status": "NOT_CONFIGURED", "reason": "NO_QUOTES"}
    q = max(quotes, key=lambda x: x.clock.ingest_time_ns)
    if q.symbol != symbol:
        raise ValueError("quote symbol mismatch")
    bid, ask = _finite(q.bid, "bid"), _finite(q.ask, "ask")
    bs, ass = _finite(q.bid_size, "bid_size"), _finite(q.ask_size, "ask_size")
    if bid <= 0 or ask < bid or bs < 0 or ass < 0:
        raise ValueError("invalid quote: require 0 < bid <= ask and non-negative sizes")
    clock = _clock_features(q.clock, now, policy)
    total = bs + ass
    mid = (bid + ask) / 2.0
    return {
        "status": "OK" if clock["fresh"] else "STALE", "best_bid": bid,
        "best_ask": ask, "mid_price": mid, "spread": ask - bid,
        "spread_bps": (ask - bid) / mid * 10_000,
        "top_size_imbalance": (bs - ass) / total if total else None,
        "clock": clock,
    }


def _book_features(books: Sequence[BookSnapshot], symbol: str, now: int, policy: SourcePolicy) -> dict:
    if not books:
        return {"status": "NOT_CONFIGURED", "reason": "NO_ORDER_BOOK"}
    book = max(books, key=lambda x: x.clock.ingest_time_ns)
    if book.symbol != symbol:
        raise ValueError("book symbol mismatch")
    if not book.bids or not book.asks:
        raise ValueError("order book must contain bid and ask levels")
    bids = [(_finite(x.price, "bid.price"), _finite(x.size, "bid.size")) for x in book.bids]
    asks = [(_finite(x.price, "ask.price"), _finite(x.size, "ask.size")) for x in book.asks]
    if any(p <= 0 or s < 0 for p, s in bids + asks):
        raise ValueError("book prices must be positive and sizes non-negative")
    if any(bids[i][0] < bids[i + 1][0] for i in range(len(bids) - 1)):
        raise ValueError("bid levels must be sorted descending")
    if any(asks[i][0] > asks[i + 1][0] for i in range(len(asks) - 1)):
        raise ValueError("ask levels must be sorted ascending")
    if bids[0][0] >= asks[0][0]:
        raise ValueError("crossed order book")
    bid_depth, ask_depth = sum(s for _, s in bids), sum(s for _, s in asks)
    total = bid_depth + ask_depth
    clock = _clock_features(book.clock, now, policy)
    return {
        "status": "OK" if clock["fresh"] else "STALE", "venue": book.clock.source,
        "best_bid": bids[0][0], "best_ask": asks[0][0],
        "bid_depth": bid_depth, "ask_depth": ask_depth,
        "depth_imbalance": (bid_depth - ask_depth) / total if total else None,
        "clock": clock,
    }


def _trade_features(trades: Sequence[TradePrint], symbol: str, now: int, policy: SourcePolicy) -> dict:
    if not trades:
        return {"status": "NOT_CONFIGURED", "reason": "NO_TRADE_PRINTS"}
    ordered = sorted(trades, key=lambda x: (x.clock.event_time_ns, x.clock.ingest_time_ns))
    for trade in ordered:
        trade.clock.validate()
        if trade.symbol != symbol:
            raise ValueError("trade symbol mismatch")
        if _finite(trade.price, "trade.price") <= 0 or _finite(trade.size, "trade.size") < 0:
            raise ValueError("trade price must be positive and size non-negative")
        if trade.aggressor_side not in (-1, 0, 1):
            raise ValueError("aggressor_side must be -1, 0 or 1")
    latest = max(ordered, key=lambda x: x.clock.ingest_time_ns)
    clock = _clock_features(latest.clock, now, policy)
    signed = sum(t.size * t.aggressor_side for t in ordered)
    total = sum(t.size for t in ordered)
    return {
        "status": "OK" if clock["fresh"] else "STALE", "print_count": len(ordered),
        "signed_volume": signed, "total_volume": total,
        "signed_volume_imbalance": signed / total if total else None, "clock": clock,
    }


def _macro_features(points: Sequence[MacroPoint], now: int, policy: SourcePolicy) -> dict:
    grouped: dict[str, list[MacroPoint]] = {}
    for point in points:
        point.clock.validate()
        value = _finite(point.value, "macro.value")
        if value <= 0:
            raise ValueError("macro values must be positive")
        grouped.setdefault(point.instrument.upper(), []).append(point)
    output = {}
    for instrument, values in grouped.items():
        values.sort(key=lambda p: (p.clock.event_time_ns, p.clock.ingest_time_ns))
        latest = values[-1]
        clock = _clock_features(latest.clock, now, policy)
        change = (latest.value / values[-2].value - 1.0) if len(values) >= 2 else None
        output[instrument] = {
            "status": "OK" if clock["fresh"] else "STALE", "value": latest.value,
            "return_since_previous": change, "clock": clock,
        }
    for required in ("DXY", "VXY"):
        output.setdefault(required, {"status": "NOT_CONFIGURED", "reason": "NO_PROVIDER_DATA"})
    return output


class ParallelMarketStateEngine:
    """Deterministic bounded fan-out/fan-in over source-specific kernels."""
    engine_version = "PARALLEL_MARKET_STATE_V1"

    def __init__(self, *, quote_policy: SourcePolicy | None = None,
                 book_policy: SourcePolicy | None = None,
                 trade_policy: SourcePolicy | None = None,
                 macro_policy: SourcePolicy | None = None, workers: int = 4) -> None:
        if workers < 1 or workers > 32:
            raise ValueError("workers must be in [1, 32]")
        self.policies = {
            "quote": quote_policy or SourcePolicy(max_age_ms=500),
            "book": book_policy or SourcePolicy(max_age_ms=500),
            "trade": trade_policy or SourcePolicy(max_age_ms=1_000),
            "macro": macro_policy or SourcePolicy(max_age_ms=120_000),
        }
        for policy in self.policies.values():
            policy.validate()
        self.workers = workers

    def reconstruct(self, *, symbol: str, decision_time_ns: int,
                    quotes: Sequence[Quote] = (), books: Sequence[BookSnapshot] = (),
                    trades: Sequence[TradePrint] = (), macro: Sequence[MacroPoint] = ()) -> dict:
        if symbol != "XAUUSD":
            raise ValueError("V1 supports XAUUSD only")
        if decision_time_ns <= 0:
            raise ValueError("decision_time_ns must be positive UTC epoch nanoseconds")
        jobs = {
            "broker_quote": lambda: _quote_features(quotes, symbol, decision_time_ns, self.policies["quote"]),
            "futures_order_book": lambda: _book_features(books, symbol, decision_time_ns, self.policies["book"]),
            "futures_trade_flow": lambda: _trade_features(trades, symbol, decision_time_ns, self.policies["trade"]),
            "macro": lambda: _macro_features(macro, decision_time_ns, self.policies["macro"]),
        }
        with ThreadPoolExecutor(max_workers=min(self.workers, len(jobs))) as pool:
            futures = {name: pool.submit(fn) for name, fn in jobs.items()}
            features = {name: futures[name].result() for name in jobs}
        statuses = [value["status"] for key, value in features.items() if key != "macro"]
        statuses.extend(value["status"] for value in features["macro"].values())
        ready = len(statuses) > 0 and all(s == "OK" for s in statuses)
        return {
            "engine": self.engine_version, "instrument": symbol,
            "decision_time_ns": decision_time_ns,
            "status": "READY_FOR_FUSION" if ready else "PARTIAL_OR_STALE",
            "features": features, "probabilities": None,
            "probability_status": "NOT_CALIBRATED", "execution_enabled": False,
            "capability_boundary": {
                "observed_features_only": True, "institutional_intent_proven": False,
                "live_providers_connected": False,
                "future_adapter_contract": "Quote/Book/Trade/Macro dataclasses",
            },
        }


__all__ = ["BookLevel", "BookSnapshot", "EventClock", "MacroPoint",
           "ParallelMarketStateEngine", "Quote", "SourcePolicy", "TradePrint"]
