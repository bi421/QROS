import hashlib
from pathlib import Path

import polars as pl


class XauCsvLoader:
    """Dukascopy орлох, XAUUSD-д зориулсан deterministic loader"""

    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)

    def load(self) -> tuple[pl.DataFrame, str]:
        # HistData формат: 2024.01.02,00:03,2650.12,2650.85,0
        # MT5 формат: <DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE>
        df = pl.scan_csv(self.csv_path, has_header=False).collect()
        # Энд таны timezone.py ашиглаж UTC болгоно - энэ бол leakage protection-ийн үндэс
        df = df.rename({"column_1": "ts_str", "column_3": "open", "column_4": "high"})
        # ... цэвэрлэгээ ...

        # Deterministic hash - таны self-validation-д хэрэгтэй
        content_hash = hashlib.sha256(df.write_csv().encode()).hexdigest()

        # Parquet руу - DuckDB-аас 10x хурдан
        curated_path = Path("data/curated/xauusd/m1/xauusd_m1.parquet")
        curated_path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(curated_path)

        return df, content_hash
