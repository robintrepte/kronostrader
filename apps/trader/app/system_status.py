from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.assets import partition_symbols
from app.market_hours import crypto_session_clock, fetch_market_clock
from app.state import get_state


async def build_system_status() -> dict[str, Any]:
    state = get_state()
    s = state.settings
    issues: list[str] = []
    equity_clock = fetch_market_clock(s)
    crypto_clock = crypto_session_clock()
    equity_syms, crypto_syms = partition_symbols(s.symbols)
    has_equity = bool(equity_syms)
    has_crypto = bool(crypto_syms)
    equity_open = bool(equity_clock.get("isOpen"))

    if s.mock_market_data:
        issues.append("MOCK_MARKET_DATA is on — real market data disabled")
    if not s.alpaca_api_key or not s.alpaca_secret_key:
        issues.append("Alpaca API keys are missing")
    if has_equity and not equity_open:
        nxt = equity_clock.get("nextOpen", "next session")
        if has_crypto:
            issues.append(
                f"US equity market closed — stocks/ETFs paused until {nxt}; crypto still trading"
            )
        else:
            issues.append(f"US equity market closed — trading paused until {nxt}")

    for sym, err in state.market_errors.items():
        issues.append(f"Market data ({sym}): {err}")
    for sym, err in state.inference_errors.items():
        issues.append(f"Inference ({sym}): {err}")

    inference = await _probe_inference(s.inference_url)
    if not inference.get("reachable"):
        issues.append(f"Inference unreachable at {s.inference_url}")
    elif not inference.get("loaded"):
        issues.append("Kronos model is not loaded")
    elif inference.get("status") == "degraded":
        issues.append("Inference reports degraded health")

    market_ok = (
        not s.mock_market_data
        and bool(s.alpaca_api_key)
        and not state.market_errors
    )
    if not state.market_last_ok and not state.market_errors:
        if not any("Market data" in i for i in issues):
            issues.append("Waiting for first successful Alpaca bar fetch")

    if market_ok and state.market_last_ok and not state.market_errors:
        issues = [i for i in issues if not i.startswith("Waiting for first")]

    # Equity-only books: don't nag about first bars while cash session is closed
    if has_equity and not equity_open and not has_crypto:
        issues = [i for i in issues if not i.startswith("Waiting for first")]

    hard = (
        not inference.get("reachable")
        or s.mock_market_data
        or not s.alpaca_api_key
        or bool(state.market_errors)
        or bool(state.inference_errors)
    )

    level = "ok"
    if issues:
        level = "error" if hard else "degraded"
        if level != "error" and any("Waiting for first" in i for i in issues):
            level = "degraded"

    feed = (s.alpaca_data_feed or "iex").lower()
    if has_crypto and has_equity:
        feed_label = f"{feed}+crypto"
    elif has_crypto:
        feed_label = "crypto"
    else:
        feed_label = feed

    summary = {
        "ok": "All systems nominal · real Alpaca data",
        "degraded": "Degraded — see issues",
        "error": "Errors — real trading loop blocked or failing",
    }[level]

    if level == "ok":
        summary = f"Real Alpaca/{feed_label} data · Kronos on {inference.get('device', '?')}"
    elif has_equity and not equity_open and level == "degraded" and not hard:
        if has_crypto:
            summary = "Equity closed · crypto trading 24/7"
        else:
            summary = "Market closed · trading paused"

    # Effective "something is tradeable" for backward-compatible marketOpen
    anything_open = (has_crypto and bool(crypto_clock.get("isOpen"))) or (
        has_equity and equity_open
    ) or (not has_equity and not has_crypto and equity_open)

    return {
        "level": level,
        "summary": summary,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
        "trader": {
            "ok": True,
            "dryRun": s.dry_run,
            "paper": s.use_paper,
            "live": s.live_trading_enabled,
            "symbols": s.symbols,
            "mockMarketData": False,
            "intervalSeconds": s.trade_interval_seconds,
            "strategy": s.strategy,
            "marketOpen": anything_open,
            "hasEquity": has_equity,
            "hasCrypto": has_crypto,
        },
        "marketData": {
            "ok": market_ok and bool(state.market_last_ok) and not state.market_errors,
            "provider": "alpaca",
            "feed": feed_label,
            "mock": False,
            "keysConfigured": bool(s.alpaca_api_key and s.alpaca_secret_key),
            "lastSuccessBySymbol": dict(state.market_last_ok),
            "errorsBySymbol": dict(state.market_errors),
            "delayMinutes": 0 if has_crypto and not has_equity else s.alpaca_data_delay_minutes,
            "session": {
                "isOpen": anything_open,
                "nextOpen": equity_clock.get("nextOpen") if has_equity and not equity_open else None,
                "nextClose": equity_clock.get("nextClose") if has_equity and equity_open else None,
                "source": equity_clock.get("source"),
                "equity": {
                    "isOpen": equity_open,
                    "nextOpen": equity_clock.get("nextOpen"),
                    "nextClose": equity_clock.get("nextClose"),
                    "source": equity_clock.get("source"),
                    "watched": has_equity,
                },
                "crypto": {
                    "isOpen": bool(crypto_clock.get("isOpen")),
                    "nextOpen": crypto_clock.get("nextOpen"),
                    "nextClose": crypto_clock.get("nextClose"),
                    "source": crypto_clock.get("source"),
                    "watched": has_crypto,
                },
            },
        },
        "inference": inference,
    }


async def _probe_inference(url: str) -> dict[str, Any]:
    base = url.rstrip("/")
    out: dict[str, Any] = {
        "ok": False,
        "reachable": False,
        "loaded": False,
        "status": "down",
        "url": base,
        "model": None,
        "tokenizer": None,
        "device": None,
        "uptimeSeconds": None,
        "maxContext": None,
        "hardware": None,
        "error": None,
    }
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{base}/health")
            res.raise_for_status()
            data = res.json()
    except Exception as exc:
        out["error"] = str(exc)
        return out

    out["reachable"] = True
    out["status"] = data.get("status", "unknown")
    out["loaded"] = bool(data.get("loaded"))
    out["model"] = data.get("model")
    out["tokenizer"] = data.get("tokenizer")
    out["device"] = data.get("device")
    out["uptimeSeconds"] = data.get("uptime_seconds")
    out["maxContext"] = data.get("max_context")
    out["hardware"] = data.get("hardware")
    out["ok"] = out["loaded"] and out["status"] in ("ok", "healthy")
    if not out["ok"] and not out["error"]:
        out["error"] = f"Inference status={out['status']} loaded={out['loaded']}"
    return out
