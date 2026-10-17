# MT5 demo execution slippage capture

QROS does not submit orders. Use a demo account only if you choose to collect a small, controlled sample yourself, and export the terminal's deal/fill history plus the request-time bid/ask snapshot for each order. Do not export account passwords, investor passwords, access tokens, or unrelated account statements.

Save a UTF-8 CSV as `data/execution_logs/mt5_demo_fills.csv` with these columns:

```csv
timestamp,symbol,order_type,side,requested_price,fill_price,volume,order_id,deal_id,quote_bid,quote_ask
```

- `timestamp`: ISO timestamp with timezone/offset if available; preserve the broker-server timestamp and timezone.
- `symbol`: exact broker symbol, e.g. XAUUSD.
- `order_type`: one of `market_entry`, `tp_limit`, `sl_stop`, `market_exit`.
- `side`: `BUY` or `SELL` for the executed deal.
- `requested_price`: requested/trigger/limit price. Required for TP/SL fills; market order benchmark is request-time ask for BUY or bid for SELL.
- `fill_price`: actual deal price.
- `volume`: actual filled volume.
- `order_id` / `deal_id`: broker IDs used to reconcile partial fills and duplicates.
- `quote_bid` / `quote_ask`: bid and ask sampled at the request/trigger time, not at export time.

The importer fails closed if required quotes or benchmark prices are missing. Keep raw exports unchanged; hash them before and after processing. Partial fills should be separate deal rows and reconciled by order ID. Do not claim calibration verified until there are at least 100 usable fills per order class and broker quote/deal reconciliation is complete. That sample threshold is a minimum diagnostic, not proof of representativeness.
