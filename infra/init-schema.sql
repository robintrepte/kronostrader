CREATE TABLE IF NOT EXISTS candles (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(32) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  open DOUBLE PRECISION NOT NULL,
  high DOUBLE PRECISION NOT NULL,
  low DOUBLE PRECISION NOT NULL,
  close DOUBLE PRECISION NOT NULL,
  volume DOUBLE PRECISION NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_candles_symbol ON candles (symbol);
CREATE INDEX IF NOT EXISTS ix_candles_timestamp ON candles (timestamp);

CREATE TABLE IF NOT EXISTS forecasts (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(32) NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL,
  model VARCHAR(128) NOT NULL,
  sample_count INTEGER NOT NULL DEFAULT 1,
  points JSON NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_forecasts_symbol ON forecasts (symbol);

CREATE TABLE IF NOT EXISTS signals (
  id VARCHAR(64) PRIMARY KEY,
  symbol VARCHAR(32) NOT NULL,
  side VARCHAR(8) NOT NULL,
  strength DOUBLE PRECISION NOT NULL,
  reason TEXT NOT NULL,
  strategy VARCHAR(64) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  meta JSON
);
CREATE INDEX IF NOT EXISTS ix_signals_symbol ON signals (symbol);

CREATE TABLE IF NOT EXISTS orders (
  id VARCHAR(64) PRIMARY KEY,
  client_order_id VARCHAR(64),
  symbol VARCHAR(32) NOT NULL,
  side VARCHAR(8) NOT NULL,
  qty DOUBLE PRECISION NOT NULL,
  type VARCHAR(16) NOT NULL DEFAULT 'market',
  status VARCHAR(32) NOT NULL,
  filled_avg_price DOUBLE PRECISION,
  submitted_at TIMESTAMPTZ NOT NULL,
  filled_at TIMESTAMPTZ,
  dry_run BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_orders_symbol ON orders (symbol);

CREATE TABLE IF NOT EXISTS positions (
  symbol VARCHAR(32) PRIMARY KEY,
  qty DOUBLE PRECISION NOT NULL,
  side VARCHAR(8) NOT NULL,
  avg_entry_price DOUBLE PRECISION NOT NULL,
  current_price DOUBLE PRECISION NOT NULL,
  market_value DOUBLE PRECISION NOT NULL,
  unrealized_pnl DOUBLE PRECISION NOT NULL,
  unrealized_pnl_pct DOUBLE PRECISION NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
  id SERIAL PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL,
  equity DOUBLE PRECISION NOT NULL,
  cash DOUBLE PRECISION NOT NULL,
  buying_power DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS ix_equity_snapshots_timestamp ON equity_snapshots (timestamp);

CREATE TABLE IF NOT EXISTS activity_log (
  id VARCHAR(64) PRIMARY KEY,
  kind VARCHAR(32) NOT NULL,
  message TEXT NOT NULL,
  symbol VARCHAR(32),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  meta JSON
);
CREATE INDEX IF NOT EXISTS ix_activity_log_kind ON activity_log (kind);
