"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ActivityLogEntry,
  Candle,
  EquityPoint,
  Forecast,
  Order,
  Position,
  Snapshot,
  WsEvent,
} from "@kronos/shared-types";
import { Badge, CandlestickChart, LiveDot, Panel } from "@kronos/ui";
import { useTraderSocket } from "@/hooks/useTraderSocket";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8001/ws";

const emptySnapshot: Snapshot = {
  symbols: ["AAPL", "MSFT", "NVDA"],
  selectedSymbol: "AAPL",
  candles: {},
  forecasts: {},
  positions: [],
  orders: [],
  equity: [],
  activity: [],
  risk: {
    maxPositionSize: 1000,
    maxPortfolioExposure: 5000,
    stopLossPct: 2,
  },
  paper: true,
  dryRun: true,
  live: false,
};

function formatUsd(n: number) {
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatPct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function TradingDesk() {
  const [snap, setSnap] = useState<Snapshot>(emptySnapshot);
  const [symbol, setSymbol] = useState("AAPL");
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_URL}/api/snapshot`);
        if (!res.ok) return;
        const data = (await res.json()) as Snapshot;
        if (cancelled) return;
        setSnap(data);
        setSymbol(data.selectedSymbol || data.symbols[0] || "AAPL");
        setBootstrapped(true);
      } catch {
        setBootstrapped(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onEvent = useCallback((event: WsEvent) => {
    setSnap((prev) => applyEvent(prev, event));
  }, []);

  const { connected } = useTraderSocket(WS_URL, onEvent);

  const candles: Candle[] = snap.candles[symbol] ?? [];
  const forecast: Forecast | null = snap.forecasts[symbol] ?? null;
  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const changePct =
    last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;

  const equityPath = useMemo(() => buildEquityPath(snap.equity), [snap.equity]);

  return (
    <div className="mx-auto flex min-h-full max-w-[1600px] flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mono text-xs tracking-[0.2em] text-[var(--gold)]">
            KRONOS
          </p>
          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            Trading Desk
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LiveDot live={connected} />
          <Badge tone={snap.paper ? "mint" : "coral"}>
            {snap.live ? "LIVE" : "PAPER"}
          </Badge>
          {snap.dryRun && <Badge tone="gold">DRY RUN</Badge>}
          <Badge tone="neutral">
            max pos {formatUsd(snap.risk.maxPositionSize)}
          </Badge>
        </div>
      </header>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {(snap.symbols.length ? snap.symbols : emptySnapshot.symbols).map(
          (s) => {
            const active = s === symbol;
            const c = snap.candles[s];
            const px = c?.[c.length - 1]?.close;
            return (
              <button
                key={s}
                type="button"
                onClick={() => setSymbol(s)}
                className="mono shrink-0 rounded-md border px-3 py-2 text-left transition"
                style={{
                  borderColor: active ? "var(--gold)" : "var(--border)",
                  background: active ? "#1a1f2b" : "var(--panel)",
                  color: "var(--foreground)",
                }}
              >
                <div className="text-xs text-[var(--muted)]">{s}</div>
                <div className="text-sm">
                  {px != null ? px.toFixed(2) : "—"}
                </div>
              </button>
            );
          },
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel
          title={`${symbol} · Candles + Kronos forecast`}
          action={
            last ? (
              <span
                className="mono text-sm"
                style={{ color: changePct >= 0 ? "var(--mint)" : "var(--coral)" }}
              >
                {last.close.toFixed(2)} ({formatPct(changePct)})
              </span>
            ) : (
              <span className="mono text-xs text-[var(--muted)]">
                {bootstrapped ? "waiting for data" : "loading…"}
              </span>
            )
          }
        >
          <CandlestickChart
            candles={candles}
            forecast={forecast?.points ?? []}
            height={440}
          />
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title="Positions">
            {!snap.positions.length ? (
              <p className="mono text-xs text-[var(--muted)]">No open positions</p>
            ) : (
              <ul className="space-y-2">
                {snap.positions.map((p) => (
                  <PositionRow key={p.symbol} p={p} />
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Equity">
            {!snap.equity.length ? (
              <p className="mono text-xs text-[var(--muted)]">No equity points yet</p>
            ) : (
              <>
                <p className="mono text-lg text-[var(--mint)]">
                  {formatUsd(snap.equity[snap.equity.length - 1].equity)}
                </p>
                <svg viewBox="0 0 300 80" className="mt-2 w-full" height={80}>
                  <path
                    d={equityPath}
                    fill="none"
                    stroke="var(--mint)"
                    strokeWidth="2"
                  />
                </svg>
              </>
            )}
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Activity">
          <ul className="max-h-64 space-y-2 overflow-y-auto">
            {snap.activity.length === 0 && (
              <li className="mono text-xs text-[var(--muted)]">No events yet</li>
            )}
            {snap.activity.map((a) => (
              <ActivityRow key={a.id} entry={a} />
            ))}
          </ul>
        </Panel>

        <Panel title="Settings (read-only)">
          <dl className="mono grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <dt className="text-[var(--muted)]">Strategy threshold</dt>
            <dd>± signal via trader env</dd>
            <dt className="text-[var(--muted)]">Max position</dt>
            <dd>{formatUsd(snap.risk.maxPositionSize)}</dd>
            <dt className="text-[var(--muted)]">Max exposure</dt>
            <dd>{formatUsd(snap.risk.maxPortfolioExposure)}</dd>
            <dt className="text-[var(--muted)]">Stop-loss</dt>
            <dd>{snap.risk.stopLossPct}%</dd>
            <dt className="text-[var(--muted)]">API</dt>
            <dd className="truncate">{API_URL}</dd>
            <dt className="text-[var(--muted)]">Recent orders</dt>
            <dd>{snap.orders.length}</dd>
          </dl>
          {snap.orders[0] && <RecentOrder order={snap.orders[0]} />}
        </Panel>
      </div>
    </div>
  );
}

function PositionRow({ p }: { p: Position }) {
  const positive = p.unrealizedPnl >= 0;
  return (
    <li className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-2 last:border-0">
      <div>
        <div className="mono text-sm">{p.symbol}</div>
        <div className="mono text-[10px] text-[var(--muted)]">
          {p.qty} @ {p.avgEntryPrice.toFixed(2)}
        </div>
      </div>
      <div
        className="mono text-right text-sm"
        style={{ color: positive ? "var(--mint)" : "var(--coral)" }}
      >
        <div>{formatUsd(p.unrealizedPnl)}</div>
        <div className="text-[10px]">{formatPct(p.unrealizedPnlPct)}</div>
      </div>
    </li>
  );
}

function ActivityRow({ entry }: { entry: ActivityLogEntry }) {
  const tone =
    entry.kind === "risk_reject" || entry.kind === "error"
      ? "var(--coral)"
      : entry.kind === "signal"
        ? "var(--gold)"
        : entry.kind === "order" || entry.kind === "fill"
          ? "var(--mint)"
          : "var(--muted)";
  return (
    <li className="border-b border-[var(--border)] pb-2 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="mono text-[10px] uppercase" style={{ color: tone }}>
          {entry.kind}
        </span>
        <span className="mono text-[10px] text-[var(--muted)]">
          {new Date(entry.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <p className="mt-1 text-sm leading-snug">{entry.message}</p>
    </li>
  );
}

function RecentOrder({ order }: { order: Order }) {
  return (
    <div className="mono mt-4 rounded border border-[var(--border)] p-3 text-xs">
      <div className="text-[var(--muted)]">Last order</div>
      <div className="mt-1">
        {order.side.toUpperCase()} {order.qty} {order.symbol} · {order.status}
      </div>
    </div>
  );
}

function buildEquityPath(points: EquityPoint[]): string {
  if (points.length < 2) return "";
  const w = 300;
  const h = 80;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p.equity - min) / span) * (h - 8) - 4;
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

function applyEvent(prev: Snapshot, event: WsEvent): Snapshot {
  switch (event.type) {
    case "snapshot":
      return event.payload;
    case "candle": {
      const symbol = event.payload.symbol;
      const list = [...(prev.candles[symbol] ?? [])];
      const idx = list.findIndex((c) => c.timestamp === event.payload.timestamp);
      if (idx >= 0) list[idx] = event.payload;
      else list.push(event.payload);
      return { ...prev, candles: { ...prev.candles, [symbol]: list.slice(-512) } };
    }
    case "forecast":
      return {
        ...prev,
        forecasts: { ...prev.forecasts, [event.payload.symbol]: event.payload },
      };
    case "order":
      return { ...prev, orders: [event.payload, ...prev.orders].slice(0, 50) };
    case "position":
      return { ...prev, positions: event.payload };
    case "equity":
      return { ...prev, equity: [...prev.equity, event.payload].slice(-500) };
    case "activity":
      return { ...prev, activity: [event.payload, ...prev.activity].slice(0, 100) };
    case "signal": {
      const entry: ActivityLogEntry = {
        id: event.payload.id,
        kind: "signal",
        message: `${event.payload.side.toUpperCase()} ${event.payload.symbol}: ${event.payload.reason}`,
        symbol: event.payload.symbol,
        timestamp: event.payload.timestamp,
        meta: event.payload as unknown as Record<string, unknown>,
      };
      return {
        ...prev,
        activity: [entry, ...prev.activity].slice(0, 100),
      };
    }
    default:
      return prev;
  }
}
