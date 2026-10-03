"""
Instrument metadata registry: symbol -> asset class, currency, annualization days, etc.
"""

from typing import NamedTuple


class InstrumentMetadata(NamedTuple):
    symbol: str
    asset_class: str  # "equity", "forex", "metal", "commodity", "crypto", "bond"
    currency: str
    tick_size: float
    session_calendar: str  # e.g., "US", "24/7", "FX"
    annualization_days: int  # number of trading days per year


class InstrumentMetadataRegistry:
    """Singleton registry for instrument metadata."""

    _instance = None
    _metadata: dict[str, InstrumentMetadata] = {}

    def __new__(cls) -> "InstrumentMetadataRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        # Pre-populate with common symbols
        self._metadata = {
            "XAUUSD": InstrumentMetadata(
                symbol="XAUUSD",
                asset_class="metal",
                currency="USD",
                tick_size=0.01,
                session_calendar="24/7",
                annualization_days=260,
            ),
            "DXY": InstrumentMetadata(
                symbol="DXY",
                asset_class="forex",
                currency="USD",
                tick_size=0.001,
                session_calendar="FX",
                annualization_days=260,
            ),
            "US10Y": InstrumentMetadata(
                symbol="US10Y",
                asset_class="bond",
                currency="USD",
                tick_size=0.01,
                session_calendar="US",
                annualization_days=252,
            ),
            "VIX": InstrumentMetadata(
                symbol="VIX",
                asset_class="equity",
                currency="USD",
                tick_size=0.01,
                session_calendar="US",
                annualization_days=252,
            ),
            "BTCUSD": InstrumentMetadata(
                symbol="BTCUSD",
                asset_class="crypto",
                currency="USD",
                tick_size=0.01,
                session_calendar="24/7",
                annualization_days=365,
            ),
            # Add more as needed
        }

    def get(self, symbol: str) -> InstrumentMetadata | None:
        return self._metadata.get(symbol)

    def register(self, metadata: InstrumentMetadata) -> None:
        self._metadata[metadata.symbol] = metadata

    def get_asset_class(self, symbol: str) -> str:
        meta = self.get(symbol)
        if meta is None:
            # Default to equity (252 days) to preserve backward compatibility
            return "equity"
        return meta.asset_class

    def get_annualization_days(self, symbol: str) -> int:
        meta = self.get(symbol)
        if meta is None:
            return 252
        return meta.annualization_days
