import yfinance as yf

print("Downloading DXY...")
dxy = yf.download("DX-Y.NYB", start="2021-01-01", end="2025-12-31", progress=False)
print("DXY rows:", len(dxy))

print("Downloading VIX...")
vix = yf.download("^VIX", start="2021-01-01", end="2025-12-31", progress=False)
print("VIX rows:", len(vix))

dxy.to_csv("dxy_real_2021_2025.csv")
vix.to_csv("vix_real_2021_2025.csv")

print("Saved both files.")
print(dxy.head())
print(vix.head())
