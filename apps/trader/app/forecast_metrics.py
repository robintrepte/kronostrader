from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except Exception:
        return None


def score_forecast_against_candles(
    forecast: dict[str, Any],
    candles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Score one historical forecast once enough realized bars exist."""
    points = forecast.get("points") or []
    if not points:
        return None
    anchor_close = forecast.get("anchorClose")
    if anchor_close is None or float(anchor_close) <= 0:
        return None

    horizon = points[-1]
    pred_close = float(horizon.get("close") or 0)
    if pred_close <= 0:
        return None

    # Prefer matching by timestamp; fall back to bar offset = pred_len
    target_ts = _parse_ts(horizon.get("timestamp"))
    realized_close: float | None = None
    if target_ts and candles:
        # Find first candle at or after target
        for c in candles:
            cts = _parse_ts(c.get("timestamp"))
            if cts and cts >= target_ts:
                realized_close = float(c["close"])
                break
    if realized_close is None:
        # Not enough future data yet
        anchor_ts = _parse_ts(forecast.get("anchorTimestamp"))
        if not anchor_ts or not candles:
            return None
        # count bars after anchor
        after = [
            c
            for c in candles
            if (_parse_ts(c.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
            > anchor_ts
        ]
        if len(after) < len(points):
            return None
        realized_close = float(after[len(points) - 1]["close"])

    anchor = float(anchor_close)
    pred_ret = (pred_close - anchor) / anchor
    real_ret = (realized_close - anchor) / anchor
    direction_hit = (pred_ret == 0 and real_ret == 0) or (
        pred_ret != 0 and real_ret != 0 and (pred_ret > 0) == (real_ret > 0)
    )
    ape = abs(realized_close - pred_close) / abs(realized_close) if realized_close else None
    ae = abs(realized_close - pred_close)

    low = horizon.get("closeLow")
    high = horizon.get("closeHigh")
    in_band: bool | None = None
    if low is not None and high is not None:
        in_band = float(low) <= realized_close <= float(high)

    return {
        "directionHit": bool(direction_hit),
        "mape": float(ape) if ape is not None else None,
        "mae": float(ae),
        "inBand": in_band,
        "predReturnPct": pred_ret * 100.0,
        "realizedReturnPct": real_ret * 100.0,
    }


def compute_symbol_metrics(
    history: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    *,
    min_hit_rate: float,
    max_mape: float,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    for fc in history:
        row = score_forecast_against_candles(fc, candles)
        if row:
            scored.append(row)

    n = len(scored)
    if n == 0:
        return {
            "symbol": None,
            "n": 0,
            "hitRate": None,
            "mape": None,
            "mae": None,
            "bandCoverage": None,
            "errorStreak": 0,
            "tradeable": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

    hits = sum(1 for s in scored if s["directionHit"])
    mapes = [s["mape"] for s in scored if s["mape"] is not None]
    maes = [s["mae"] for s in scored]
    bands = [s["inBand"] for s in scored if s["inBand"] is not None]

    hit_rate = hits / n
    mape = sum(mapes) / len(mapes) if mapes else None
    mae = sum(maes) / len(maes) if maes else None
    band_cov = (sum(1 for b in bands if b) / len(bands)) if bands else None

    streak = 0
    for s in reversed(scored):
        if s["directionHit"]:
            break
        streak += 1

    tradeable = n >= 3 and hit_rate >= min_hit_rate and (
        mape is None or mape <= max_mape
    )

    return {
        "n": n,
        "hitRate": hit_rate,
        "mape": mape,
        "mae": mae,
        "bandCoverage": band_cov,
        "errorStreak": streak,
        "tradeable": tradeable,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def refresh_all_metrics(
    forecast_history: dict[str, list[dict[str, Any]]],
    candles: dict[str, list[dict[str, Any]]],
    symbols: list[str],
    *,
    min_hit_rate: float,
    max_mape: float,
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sym in symbols:
        m = compute_symbol_metrics(
            forecast_history.get(sym) or [],
            candles.get(sym) or [],
            min_hit_rate=min_hit_rate,
            max_mape=max_mape,
        )
        m["symbol"] = sym
        out[sym] = m
    return out
