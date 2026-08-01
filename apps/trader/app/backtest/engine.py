from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.assets import is_crypto_symbol
from app.config import Settings
from app.exits import bump_bars_held, default_position_meta, evaluate_exit
from app.forecast_metrics import compute_symbol_metrics
from app.market_data import fetch_candles
from app.portfolio import EntryCandidate, select_entries
from app.regime import evaluate_regime
from app.strategies import get_strategy
from app.strategies.base import Candle, ForecastPoint

logger = logging.getLogger(__name__)

BACKTEST_RESULT_PATH = Path(__file__).resolve().parents[2] / "data" / "backtest_last.json"


@dataclass
class BacktestConfig:
    symbols: list[str]
    starting_cash: float = 100_000.0
    equity_fee_bps: float = 2.0
    crypto_fee_bps: float = 25.0
    max_steps: int = 40
    step: int = 6  # bars between decisions
    lookback: int = 256
    pred_len: int = 12
    sample_count: int = 2
    top_k: int = 2
    use_inference: bool = True


@dataclass
class SimPosition:
    qty: float
    entry: float
    meta: dict[str, Any]


@dataclass
class BacktestResult:
    ok: bool
    generatedAt: str
    startingCash: float
    endingEquity: float
    netPnl: float
    netPnlPct: float
    maxDrawdownPct: float
    sharpeLike: float
    winRate: float
    tradeCount: int
    avgEdgeBps: float
    perSymbol: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _fee_bps(symbol: str, cfg: BacktestConfig) -> float:
    return cfg.crypto_fee_bps if is_crypto_symbol(symbol) else cfg.equity_fee_bps


def _apply_fee(notional: float, bps: float) -> float:
    return notional * (bps / 10_000.0)


async def _predict(
    settings: Settings,
    symbol: str,
    window: list[Candle],
    sample_count: int,
) -> list[ForecastPoint]:
    from app.inference_client import request_forecast

    points, _ = await request_forecast(settings, symbol, window, sample_count=sample_count)
    return points


def _naive_forecast(window: list[Candle], pred_len: int) -> list[ForecastPoint]:
    """Fallback when inference is down — momentum extrapolation (labeled in notes)."""
    if len(window) < 5:
        return []
    last = window[-1]
    ret = (window[-1].close - window[-5].close) / window[-5].close
    step = ret / max(pred_len, 1)
    out: list[ForecastPoint] = []
    px = last.close
    for i in range(pred_len):
        px = px * (1 + step)
        band = abs(px * step) * 2
        out.append(
            ForecastPoint(
                timestamp=last.timestamp,
                open=px,
                high=px * 1.001,
                low=px * 0.999,
                close=px,
                volume=0.0,
                close_low=px - band,
                close_high=px + band,
            )
        )
    return out


async def run_backtest(settings: Settings, cfg: BacktestConfig) -> BacktestResult:
    notes: list[str] = []
    series: dict[str, list[Candle]] = {}
    for sym in cfg.symbols:
        # Temporarily widen lookback for history
        old_lb = settings.lookback_bars
        settings.lookback_bars = max(old_lb, cfg.lookback + cfg.max_steps * cfg.step + cfg.pred_len + 10)
        try:
            bars = fetch_candles(settings, sym)
        finally:
            settings.lookback_bars = old_lb
        if len(bars) < cfg.lookback + 20:
            notes.append(f"{sym}: insufficient bars ({len(bars)})")
            continue
        series[sym] = bars

    if not series:
        return BacktestResult(
            ok=False,
            generatedAt=datetime.now(timezone.utc).isoformat(),
            startingCash=cfg.starting_cash,
            endingEquity=cfg.starting_cash,
            netPnl=0.0,
            netPnlPct=0.0,
            maxDrawdownPct=0.0,
            sharpeLike=0.0,
            winRate=0.0,
            tradeCount=0,
            avgEdgeBps=0.0,
            notes=notes + ["no series loaded"],
            config=asdict(cfg),
        )

    min_len = min(len(v) for v in series.values())
    strategy = get_strategy(
        getattr(settings, "strategy", None) or "strict_forecast",
        settings.signal_threshold_pct,
        settings=settings,
    )
    cash = cfg.starting_cash
    positions: dict[str, SimPosition] = {}
    equity_curve: list[float] = []
    trades: list[dict[str, Any]] = []
    forecast_hist: dict[str, list[dict[str, Any]]] = {s: [] for s in series}
    used_naive = False

    # Align indices from the end
    start_i = cfg.lookback
    end_i = min(min_len - cfg.pred_len - 1, start_i + cfg.max_steps * cfg.step)
    i = start_i
    steps = 0
    while i < end_i and steps < cfg.max_steps:
        steps += 1
        mark: dict[str, float] = {}
        candidates: list[EntryCandidate] = []

        for sym, bars in series.items():
            window = bars[i - cfg.lookback : i]
            if len(window) < 32:
                continue
            px = window[-1].close
            mark[sym] = px

            # Exits
            if sym in positions:
                pos = positions[sym]
                pos.meta = bump_bars_held(pos.meta)
                # build short forecast for flip check later
            try:
                if cfg.use_inference:
                    points = await _predict(settings, sym, window, cfg.sample_count)
                else:
                    points = []
            except Exception as exc:
                logger.warning("inference failed in backtest %s: %s", sym, exc)
                points = []
            if not points:
                points = _naive_forecast(window, cfg.pred_len)
                used_naive = True

            # store hist for metrics
            entry = {
                "points": [
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "close": p.close,
                        "closeLow": p.close_low,
                        "closeHigh": p.close_high,
                    }
                    for p in points
                ],
                "anchorClose": window[-1].close,
                "anchorTimestamp": window[-1].timestamp.isoformat(),
                "generatedAt": datetime.now(timezone.utc).isoformat(),
            }
            forecast_hist[sym].append(entry)
            candle_dicts = [
                {
                    "timestamp": c.timestamp.isoformat(),
                    "close": c.close,
                }
                for c in bars[: i + cfg.pred_len]
            ]
            metrics = compute_symbol_metrics(
                forecast_hist[sym],
                candle_dicts,
                min_hit_rate=settings.min_hit_rate,
                max_mape=settings.max_mape,
            )
            # Warmup: don't require tradeable until n>=3
            if metrics["n"] < 3:
                metrics["tradeable"] = True

            if sym in positions:
                pos = positions[sym]
                dec = evaluate_exit(
                    meta=pos.meta,
                    current_price=px,
                    forecast=points,
                    stop_loss_pct=settings.stop_loss_pct,
                )
                signal = strategy.evaluate(window, points, metrics=metrics)
                if dec.should_exit or signal.side == "sell":
                    notional = pos.qty * px
                    fee = _apply_fee(notional, _fee_bps(sym, cfg))
                    pnl = (px - pos.entry) * pos.qty - fee
                    cash += notional - fee
                    trades.append({"symbol": sym, "side": "sell", "pnl": pnl, "price": px})
                    del positions[sym]
                    continue

            regime = evaluate_regime(
                window,
                sym,
                equity_session_open=True,
                max_vol_pct=settings.regime_max_vol_pct,
                min_trend_pct=settings.regime_min_trend_pct,
            )
            signal = strategy.evaluate(window, points, metrics=metrics)
            if signal.side == "buy" and regime.ok and sym not in positions:
                conf = 0.55
                if "conf=" in signal.reason:
                    try:
                        conf = float(signal.reason.split("conf=")[1].split()[0])
                    except Exception:
                        pass
                f_ret = (
                    ((signal.forecast_horizon_close or px) - px) / px * 100.0
                )
                candidates.append(
                    EntryCandidate(
                        symbol=sym,
                        strength=signal.strength,
                        confidence=conf,
                        hit_rate=float(metrics["hitRate"] or 0.5),
                        price=px,
                        reason=signal.reason,
                        signal=signal,
                        forecast_return_pct=f_ret,
                    )
                )

        # Mark equity
        equity = cash + sum(p.qty * mark.get(s, p.entry) for s, p in positions.items())
        equity_curve.append(equity)

        exposure = sum(p.qty * mark.get(s, p.entry) for s, p in positions.items())
        picked = select_entries(
            candidates,
            top_k=cfg.top_k,
            max_position_size=settings.max_position_size,
            max_portfolio_exposure=settings.max_portfolio_exposure,
            current_exposure=exposure,
        )
        for cand, notional in picked:
            if cand.symbol in positions:
                continue
            fee = _apply_fee(notional, _fee_bps(cand.symbol, cfg))
            if cash < notional + fee:
                continue
            qty = notional / cand.price
            cash -= notional + fee
            positions[cand.symbol] = SimPosition(
                qty=qty,
                entry=cand.price,
                meta=default_position_meta(
                    entry_price=cand.price,
                    qty=qty,
                    pred_len=cfg.pred_len,
                    forecast_return_pct=cand.forecast_return_pct,
                    take_profit_fraction=settings.take_profit_fraction,
                    stop_loss_pct=settings.stop_loss_pct,
                ),
            )
            trades.append(
                {"symbol": cand.symbol, "side": "buy", "pnl": -fee, "price": cand.price}
            )

        i += cfg.step

    # Liquidate
    last_marks = {s: series[s][min(i, len(series[s]) - 1)].close for s in series}
    for sym, pos in list(positions.items()):
        px = last_marks[sym]
        notional = pos.qty * px
        fee = _apply_fee(notional, _fee_bps(sym, cfg))
        pnl = (px - pos.entry) * pos.qty - fee
        cash += notional - fee
        trades.append({"symbol": sym, "side": "sell", "pnl": pnl, "price": px})
        del positions[sym]

    ending = cash
    equity_curve.append(ending)
    net = ending - cfg.starting_cash
    peak = equity_curve[0] if equity_curve else cfg.starting_cash
    max_dd = 0.0
    rets: list[float] = []
    for e in equity_curve:
        peak = max(peak, e)
        dd = (peak - e) / peak if peak else 0.0
        max_dd = max(max_dd, dd)
    for a, b in zip(equity_curve, equity_curve[1:]):
        if a:
            rets.append((b - a) / a)
    sharpe = 0.0
    if len(rets) > 1:
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        sharpe = (mu / math.sqrt(var)) * math.sqrt(len(rets)) if var > 0 else 0.0

    closed = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in closed if t["pnl"] > 0]
    win_rate = len(wins) / len(closed) if closed else 0.0
    avg_edge = (
        (sum(t["pnl"] for t in closed) / len(closed) / cfg.starting_cash) * 10_000
        if closed
        else 0.0
    )
    per: dict[str, Any] = {}
    for t in trades:
        per.setdefault(t["symbol"], {"trades": 0, "pnl": 0.0})
        per[t["symbol"]]["trades"] += 1
        per[t["symbol"]]["pnl"] += float(t["pnl"])

    if used_naive:
        notes.append("used naive momentum forecast for some steps (inference unavailable)")

    result = BacktestResult(
        ok=True,
        generatedAt=datetime.now(timezone.utc).isoformat(),
        startingCash=cfg.starting_cash,
        endingEquity=ending,
        netPnl=net,
        netPnlPct=(net / cfg.starting_cash) * 100.0,
        maxDrawdownPct=max_dd * 100.0,
        sharpeLike=sharpe,
        winRate=win_rate,
        tradeCount=len(closed),
        avgEdgeBps=avg_edge,
        perSymbol=per,
        config={
            "symbols": cfg.symbols,
            "maxSteps": cfg.max_steps,
            "step": cfg.step,
            "equityFeeBps": cfg.equity_fee_bps,
            "cryptoFeeBps": cfg.crypto_fee_bps,
            "useInference": cfg.use_inference,
        },
        notes=notes,
    )
    save_backtest_result(result)
    return result


def save_backtest_result(result: BacktestResult) -> Path:
    BACKTEST_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    BACKTEST_RESULT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return BACKTEST_RESULT_PATH


def load_backtest_result() -> dict[str, Any] | None:
    if not BACKTEST_RESULT_PATH.is_file():
        return None
    try:
        return json.loads(BACKTEST_RESULT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
