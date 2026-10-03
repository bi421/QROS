"""
Test Market Intelligence Layer.
"""

import pytest  # noqa: E402

# noqa: E402

pytest.skip("Requires live market data provider — not a unit test", allow_module_level=True)

from researchos.data_engine.contracts import Timeframe  # noqa: E402

# noqa: E402
from researchos.data_engine.macro_analyzer import MacroAnalyzer  # noqa: E402

# noqa: E402
from researchos.data_engine.macro_provider import MacroFactorProvider  # noqa: E402

# noqa: E402
from researchos.data_engine.repository import SqliteDatasetRepository  # noqa: E402

# noqa: E402

# 1. Init
repo = SqliteDatasetRepository("researchos.db")
provider = MacroFactorProvider(repo)
analyzer = MacroAnalyzer()

# 2. Get data
df = provider.get_factors(
    symbols=["XAUUSD"],
    start_date="2025-01-01",
    end_date="2025-12-31",
    timeframe=Timeframe.D1,
)
print("DataFrame shape:", df.shape)
print(df.head())

# 3. Analyze
corr = analyzer.compute_correlation(df, "XAUUSD")
print("Correlations with XAUUSD:", corr if corr else "(no other factors yet)")
