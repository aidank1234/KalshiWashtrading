# Data Collection

Kalshi publishes daily trade data at:
```
https://kalshi-public-docs.s3.amazonaws.com/reporting/trade_data_{YYYY-MM-DD}.json
```

## Regenerate Dataset

```bash
# Install dependencies
npm install

# Download all historical data (saves daily JSON files to data/)
npm run download

# Combine into single CSV
npm run combine

# Convert to Parquet (requires DuckDB)
duckdb -c "COPY (SELECT * FROM 'data/all_trades.csv') TO 'data/all_trades.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)"
```

## Scripts

**`src/downloadHistory.ts`**

| Command | Description |
|---------|-------------|
| `npm run test` | Test fetch, show data shape |
| `npm run download` | Download full history from 2021-07-01 |
| `npm run combine` | Merge daily files into `all_trades.csv` |

Download resumes automatically if interrupted — each day saves to a separate file.

