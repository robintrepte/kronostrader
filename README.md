# Kronos Trader

Automated paper-trading stack: **Kronos** price forecasts → strategy/risk layer → **Alpaca** orders → live **Next.js** desk.

> Default is paper / dry-run. Live trading requires an explicit, conscious env change.

## Architecture

| Service | Role |
|---------|------|
| `apps/inference` | FastAPI + Kronos (`NeoQuasar/Kronos-small\|base`) |
| `apps/trader` | Loop: market data → forecast → strict strategy → exits → top-K → Alpaca; WS fanout |
| `apps/dashboard` | Next.js live UI (candles, Edge metrics panel, gold forecast overlay) |
| Postgres / Redis | Persistence + pub/sub |

Default strategy is `strict_forecast` (path + confidence bands + forecast-quality gate + regime + ranked top-K entries; mostly HOLD). Legacy `forecast_momentum` remains available.

Cost-aware backtest:

```powershell
cd apps/trader
.\.venv\Scripts\python.exe scripts\run_backtest.py --symbols "BTC/USD,SPY" --max-steps 24
```

Results land in `apps/trader/data/backtest_last.json` and on `GET /api/backtest/last` (Edge panel on the desk).

## Prerequisites

- Node.js 22+, [pnpm](https://pnpm.io) 9+ (or `npx pnpm`)
- Python 3.10+ (3.12 recommended)
- Docker + Compose (for full stack)
- Git (Kronos is a submodule)

## Quick start (Docker)

```bash
git clone --recurse-submodules https://github.com/robintrepte/kronostrader.git
cd kronostrader
cp .env.example .env
# Optional: add ALPACA_API_KEY / ALPACA_SECRET_KEY
# MOCK_MARKET_DATA=true works without Alpaca keys

docker compose -f infra/docker-compose.yml --env-file .env up --build
```

Requires **Docker Desktop** (or a running Docker daemon). First inference start downloads the Hugging Face model (can take several minutes).

If `docker compose build` fails on PyPI with `CERTIFICATE_VERIFY_FAILED`, your host/network is intercepting TLS (common with corporate proxies). Fix the Docker Desktop CA trust or build on a network without TLS inspection.

- Dashboard: http://localhost:3033
- Trader API / WS: http://localhost:8001 (`/api/snapshot`, `/ws`)
- Inference: http://localhost:8000/health

## Local development (without full Compose)

Postgres + Redis should already be running via Docker. Apps read the **root** `.env` automatically — no manual `export` / `$env:...` needed.

**One-time / each service** (opens its own terminal):

```powershell
cd C:\Users\Robin\Desktop\Code\kronostrader

.\scripts\dev.ps1 infra       # postgres + redis (once)
.\scripts\download-kronos.ps1 -Model base   # once — downloads weights (~400MB) via PowerShell
.\scripts\dev.ps1 inference   # Kronos API :8000
.\scripts\dev.ps1 trader      # trading loop + WS :8001
.\scripts\dev.ps1 dashboard   # UI http://localhost:3033
```

If Hugging Face downloads fail inside Python (common TLS issue on some Windows networks), `download-kronos.ps1` is the reliable path. Inference loads from `apps/inference/models/` when present.

Smoke prediction (after inference shows loaded):

```bash
python apps/inference/scripts/smoke_predict.py --url http://127.0.0.1:8000
```

## Environment

See [`.env.example`](.env.example). Important flags:

| Variable | Default | Meaning |
|----------|---------|---------|
| `ALPACA_PAPER` | `true` | Use Alpaca paper endpoint |
| `ALPACA_LIVE` | `false` | Live only if `true` **and** `ALPACA_PAPER=false` |
| `DRY_RUN` | `true` | Log orders without submitting |
| `MOCK_MARKET_DATA` | `true` | Synthetic OHLCV (no Alpaca keys needed) |
| `KRONOS_MODEL_SIZE` | `small` | `small` / `base` / `mini` |
| `MAX_POSITION_SIZE` | `2000` | Per-symbol notional cap (USD) |
| `MAX_PORTFOLIO_EXPOSURE` | `25000` | Portfolio notional cap |
| `STRATEGY` | `strict_forecast` | `strict_forecast` or `forecast_momentum` |
| `SAMPLE_COUNT` | `4` | Kronos samples per forecast (confidence bands) |
| `TOP_K_ENTRIES` | `3` | Max new buys per loop cycle |
| `STOP_LOSS_PCT` | `2.0` | Hard flatten when unrealized PnL ≤ −threshold |

### Live trading checklist (do not skip)

1. Confirm you understand real capital is at risk.  
2. Set `DRY_RUN=false`.  
3. Set `ALPACA_PAPER=false` **and** `ALPACA_LIVE=true`.  
4. Double-check risk limits.  
5. Restart trader and verify logs show `LIVE TRADING ENABLED`.

## Versions

Install **latest stable** packages at setup time (`next@latest`, current `alpaca-py`, FastAPI, etc.).

**Kronos exception:** inference follows [shiyu-coder/Kronos `requirements.txt`](https://github.com/shiyu-coder/Kronos) (`torch>=2.0`, `einops`/`huggingface_hub`/`safetensors` pins). On Python 3.13, `pandas` is `>=2.2.3,<2.3` instead of exact `2.2.2` because 2.2.2 has no Windows 3.13 wheel and fails to compile from source. Kronos is **not** a `transformers` pipeline — it uses `huggingface_hub.PyTorchModelHubMixin`.

## Hetzner production

See [`infra/hetzner/DEPLOY.md`](infra/hetzner/DEPLOY.md) and `infra/docker-compose.prod.yml` (nginx + TLS; inference stays private on the Docker network).

## Monorepo layout

```
apps/dashboard   Next.js desk
apps/inference   Kronos FastAPI
apps/trader      Trading loop + WS
packages/shared-types
packages/ui
infra/           Docker + Hetzner
```

## License

Application code: see repository license. Kronos model code under `apps/inference/vendor/kronos` follows its upstream license.
