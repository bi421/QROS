from dataclasses import dataclass
from pathlib import Path

import polars as pl


@dataclass
class XAUUSD_M1_Dataset:
    path: Path = Path("data/curated/xauusd/xauusd_m1_2023_2025.parquet")

    def load(self, year: int | None = None, resample: str | None = "1h") -> pl.DataFrame:
        df = pl.read_parquet(self.path).sort("ts_utc")
        if year:
            df = df.filter(pl.col("ts_utc").dt.year() == year)
        if resample:
            df = (
                df.group_by_dynamic("ts_utc", every=resample)
                .agg(
                    [
                        pl.col("open").first().alias("open"),
                        pl.col("high").max().alias("high"),
                        pl.col("low").min().alias("low"),
                        pl.col("close").last().alias("close"),
                    ]
                )
                .sort("ts_utc")
            )
        return df


if __name__ == "__main__":
    ds = XAUUSD_M1_Dataset()
    print("H1 2025:", ds.load(year=2025, resample="1h").height, "rows")
    print("M1 2025:", ds.load(year=2025, resample=None).height, "rows")
    print("Бэлэн - одоо таны бүх experiment үүнийг дуудаж болно: XAUUSD_M1_Dataset().load()")
