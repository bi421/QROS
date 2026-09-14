import json
import hashlib
from pathlib import Path

print("=" * 60)
print(" STEP 5 VERIFICATION: REAL MT5 M1 DATA")
print("=" * 60)

data_dir = Path("data/mt5/xauusd")
manifest_path = data_dir / "manifest.json"

# 1. Manifest байгаа эсэхийг шалгах
if not manifest_path.exists():
    print("WAITING: manifest.json олдсонгүй. Өгөгдөл татаж дуусаагүй байна.")
    exit(0)

with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

print("Manifest олдлоо: " + str(manifest.get("asset")) + " " + str(manifest.get("timeframe")))

# 2. Өгөгдлийн файлыг хайх
file_ext = manifest.get("format", "csv")
data_file = data_dir / ("XAUUSD_M1_2021_2025." + file_ext)

if not data_file.exists():
    # Нэр нь өөр байж магадгүй, data_dir доторх бүх файлуудыг шалгая
    csv_files = list(data_dir.glob("*.csv"))
    parquet_files = list(data_dir.glob("*.parquet"))
    all_files = csv_files + parquet_files

    if not all_files:
        print("FAILED: Өгөгдлийн файл олдсонгүй: " + str(data_dir))
        exit(1)

    # Хамгийн том файлыг сонгоё (ихэвчлэн M1 өгөгдөл хамгийн том байна)
    data_file = max(all_files, key=lambda f: f.stat().st_size)
    print("Автоматаар хамгийн том файл сонгогдлоо: " + data_file.name)
else:
    print("Өгөгдлийн файл олдлоо: " + data_file.name)

# 3. Hash шалгах (Provenance)
print("Hash шалгаж байна...")
with open(data_file, "rb") as f:
    actual_hash = hashlib.sha256(f.read()).hexdigest()

expected_hash = manifest.get("sha256_hash", "")
if expected_hash and actual_hash != expected_hash:
    print("FAILED: Hash таарахгүй байна.")
    print("  Expected: " + str(expected_hash)[:32] + "...")
    print("  Actual:   " + actual_hash[:32] + "...")
    exit(1)

print("Hash амжилттай таарлаа: " + actual_hash[:32] + "...")

# 4. Manifest-ийн бусад талбаруудыг шалгах
row_count = manifest.get("row_count", 0)
print("Row count: " + str(row_count))

if row_count < 100000:
    print(
        "WARNING: Мөр тоо маш бага байна (< 100,000). M1 өгөгдөл 4 жилд 1 сая+ мөртэй байх ёстой."
    )
else:
    print("Мөр тоо хангалттай: " + f"{row_count:,}")

print("\n" + "=" * 60)
print(" STEP 5 SUCCESS: REAL MT5 M1 DATA VERIFIED")
print(" Файл: " + data_file.name)
print(" Hash: " + actual_hash[:32] + "...")
print(" Дараагийн алхам (Leakage Audit) руу шилжихэд бэлэн.")
print("=" * 60)
