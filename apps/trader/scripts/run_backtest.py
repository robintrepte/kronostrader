#!/usr/bin/env python3
"""Cost-aware walk-forward backtest using strict_forecast + fees."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.backtest.engine import BacktestConfig, run_backtest  # noqa: E402
from app.config import get_settings  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser(description="Kronos trader backtest")
    p.add_argument(
        "--symbols",
        default="BTC/USD,SPY",
        help="Comma-separated symbols",
    )
    p.add_argument("--max-steps", type=int, default=24)
    p.add_argument("--step", type=int, default=6)
    p.add_argument("--no-inference", action="store_true", help="Use naive forecast only")
    p.add_argument("--cash", type=float, default=100_000.0)
    args = p.parse_args()

    settings = get_settings()
    settings.strategy = "strict_forecast"
    cfg = BacktestConfig(
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        starting_cash=args.cash,
        max_steps=args.max_steps,
        step=args.step,
        use_inference=not args.no_inference,
    )
    print(f"Running backtest on {cfg.symbols} (inference={cfg.use_inference})…")
    result = await run_backtest(settings, cfg)
    print(json.dumps(
        {
            "ok": result.ok,
            "netPnl": round(result.netPnl, 2),
            "netPnlPct": round(result.netPnlPct, 3),
            "maxDrawdownPct": round(result.maxDrawdownPct, 3),
            "sharpeLike": round(result.sharpeLike, 3),
            "winRate": round(result.winRate, 3),
            "tradeCount": result.tradeCount,
            "avgEdgeBps": round(result.avgEdgeBps, 2),
            "perSymbol": result.perSymbol,
            "notes": result.notes,
        },
        indent=2,
    ))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
