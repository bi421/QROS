import pandas as pd
import yfinance as yf


def fetch_multi_asset(
    symbols: list[str],
    start: str = "2021-01-01",
    end: str = "2026-08-20",
) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for sym in symbols:
        df = yf.download(sym, start=start, end=end, progress=False)
        data[sym] = df["Close"]
    return pd.DataFrame(data).dropna()


# Жишээ ашиглалт: df = fetch_multi_asset(['GC=F','BTC-USD','EURUSD=X','^GSPC'])
