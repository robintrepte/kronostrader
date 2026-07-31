"""Smoke test: synthetic OHLCV bars → /predict (requires running server + loaded model)."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--bars", type=int, default=64)
    parser.add_argument("--pred-len", type=int, default=8)
    args = parser.parse_args()

    start = datetime.now(timezone.utc) - timedelta(minutes=5 * args.bars)
    bars = []
    price = 100.0
    for i in range(args.bars):
        ts = start + timedelta(minutes=5 * i)
        o = price
        c = price * (1 + ((i % 7) - 3) * 0.001)
        h = max(o, c) * 1.002
        l = min(o, c) * 0.998
        bars.append(
            {
                "timestamp": ts.isoformat(),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000 + i,
            }
        )
        price = c

    health = httpx.get(f"{args.url}/health", timeout=30.0)
    health.raise_for_status()
    print("health:", health.json())

    resp = httpx.post(
        f"{args.url}/predict",
        json={"symbol": "TEST", "bars": bars, "pred_len": args.pred_len, "sample_count": 1},
        timeout=300.0,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"forecast points: {len(data['forecast'])}")
    print("first:", data["forecast"][0] if data["forecast"] else None)
    print("last:", data["forecast"][-1] if data["forecast"] else None)


if __name__ == "__main__":
    main()
