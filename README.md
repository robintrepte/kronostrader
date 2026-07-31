# Kronos Trader

Automated paper-trading stack: **Kronos** price forecasts → strategy/risk layer → **Alpaca** orders → live **Next.js** desk.

> Default is paper / dry-run. Live trading requires an explicit, conscious env change.

## Architecture

| Service | Role |
|---------|------|
| `apps/inference` | FastAPI + Kronos (`NeoQuasar/Kronos-small\|base`) |
| `apps/trader` | Loop: market data → forecast → strategy → risk → Alpaca; WS fanout |
| `apps/dashboard` | Next.js live UI (candles + gold forecast overlay) |
| Postgres / Redis | Persistence + pub/sub |

Strategy code lives in `apps/trader/app/strategies/` and is deliberately separate from model inference.

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
.\scripts\dev.ps1 inference   # Kronos API :8000  (first run installs deps + downloads model)
.\scripts\dev.ps1 trader      # trading loop + WS :8001
.\scripts\dev.ps1 dashboard   # UI http://localhost:3033
```

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
| `MAX_POSITION_SIZE` | `1000` | Per-symbol notional cap (USD) |
| `MAX_PORTFOLIO_EXPOSURE` | `5000` | Portfolio notional cap |
| `STOP_LOSS_PCT` | `2.0` | Blocks new buys when unrealized PnL ≤ −threshold |

### Live trading checklist (do not skip)

1. Confirm you understand real capital is at risk.  
2. Set `DRY_RUN=false`.  
3. Set `ALPACA_PAPER=false` **and** `ALPACA_LIVE=true`.  
4. Double-check risk limits.  
5. Restart trader and verify logs show `LIVE TRADING ENABLED`.

## Versions

Install **latest stable** packages at setup time (`next@latest`, current `alpaca-py`, FastAPI, etc.).

**Kronos exception:** inference pins deps from [shiyu-coder/Kronos `requirements.txt`](https://github.com/shiyu-coder/Kronos) (`pandas==2.2.2`, `huggingface_hub==0.33.1`, `einops==0.8.1`, `safetensors==0.6.2`, `torch>=2.0`) so the vendored model code stays compatible. Kronos is **not** a `transformers` pipeline — it uses `huggingface_hub.PyTorchModelHubMixin`.

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
