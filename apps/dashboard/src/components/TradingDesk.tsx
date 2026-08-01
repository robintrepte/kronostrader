"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import type {
  ActivityLogEntry,
  AssetClass,
  Candle,
  EquityPoint,
  Forecast,
  ForecastHistoryEntry,
  Order,
  Position,
  SettingsPatch,
  Snapshot,
  WsEvent,
} from "@kronos/shared-types";
import { Badge, CandlestickChart, Panel } from "@kronos/ui";
import { useTraderSocket } from "@/hooks/useTraderSocket";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { useTheme } from "@/components/ThemeProvider";
import { SystemStatusLight } from "@/components/SystemStatusLight";
import { SymbolStrip } from "@/components/SymbolStrip";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  formatPrice,
  isCryptoSymbol,
  normalizeSymbol,
} from "@/lib/assets";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8001/ws";

const emptySnapshot: Snapshot = {
  symbols: [
    "SPY",
    "QQQ",
    "IWM",
    "SMH",
    "XLF",
    "NVDA",
    "TSLA",
    "AAPL",
    "MSFT",
    "AMZN",
    "META",
    "GOOGL",
    "AMD",
    "AVGO",
    "NFLX",
    "PLTR",
    "COIN",
    "MU",
    "ARM",
    "INTC",
    "HOOD",
    "JPM",
    "BAC",
    "CRM",
    "ORCL",
  ],
  selectedSymbol: "SPY",
  candles: {},
  forecasts: {},
  forecastHistory: {},
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
  strategy: "forecast_momentum",
  signalThresholdPct: 0.5,
  tradeIntervalSeconds: 60,
  barTimeframe: "5Min",
  lookbackBars: 512,
  predLen: 24,
  mockMarketData: false,
};

const CHART_HEIGHTS = [280, 360, 440, 560, 720] as const;
const TIMEFRAMES = ["1Min", "5Min", "15Min", "1Hour", "1Day"] as const;

function formatUsd(n: number) {
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

function formatAge(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const mins = Math.floor(ms / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function formatPct(n: number) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function TradingDesk() {
  const { theme, toggle: toggleTheme } = useTheme();
  const [snap, setSnap] = useState<Snapshot>(emptySnapshot);
  const [symbol, setSymbol] = useState("SPY");
  const [bootstrapped, setBootstrapped] = useState(false);
  const [chartHeight, setChartHeight] = useState(440);
  const [visibleBars, setVisibleBars] = useState(120);
  const [viewResetKey, setViewResetKey] = useState(0);
  const [showVolume, setShowVolume] = useState(true);
  const [showHistory, setShowHistory] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [form, setForm] = useState({
    dryRun: true,
    strategy: "forecast_momentum",
    signalThresholdPct: 0.5,
    tradeIntervalSeconds: 60,
    barTimeframe: "5Min",
    lookbackBars: 512,
    predLen: 24,
    maxPositionSize: 1000,
    maxPortfolioExposure: 5000,
    stopLossPct: 2,
  });

  const syncForm = useCallback((data: Snapshot) => {
    setForm({
      dryRun: data.dryRun,
      strategy: data.strategy ?? "forecast_momentum",
      signalThresholdPct: data.signalThresholdPct ?? 0.5,
      tradeIntervalSeconds: data.tradeIntervalSeconds ?? 60,
      barTimeframe: data.barTimeframe ?? "5Min",
      lookbackBars: data.lookbackBars ?? 512,
      predLen: data.predLen ?? 24,
      maxPositionSize: data.risk.maxPositionSize,
      maxPortfolioExposure: data.risk.maxPortfolioExposure,
      stopLossPct: data.risk.stopLossPct,
    });
  }, []);

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
        syncForm(data);
        setBootstrapped(true);
      } catch {
        setBootstrapped(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [syncForm]);

  const onEvent = useCallback(
    (event: WsEvent) => {
      setSnap((prev) => {
        const next = applyEvent(prev, event);
        if (event.type === "snapshot") syncForm(next);
        return next;
      });
    },
    [syncForm],
  );

  const { connected } = useTraderSocket(WS_URL, onEvent);

  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const candles: Candle[] = snap.candles[symbol] ?? [];
  const forecast: Forecast | null = snap.forecasts[symbol] ?? null;
  const forecastHistory = snap.forecastHistory?.[symbol] ?? [];
  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const changePct =
    last && prev ? ((last.close - prev.close) / prev.close) * 100 : 0;
  const lastCandleAge = last
    ? formatAge(nowMs - new Date(last.timestamp).getTime())
    : null;

  const equityPath = useMemo(() => buildEquityPath(snap.equity), [snap.equity]);

  const saveSettings = async (e?: FormEvent) => {
    e?.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    const patch: SettingsPatch = {
      dryRun: form.dryRun,
      strategy: form.strategy,
      signalThresholdPct: form.signalThresholdPct,
      tradeIntervalSeconds: form.tradeIntervalSeconds,
      barTimeframe: form.barTimeframe,
      lookbackBars: form.lookbackBars,
      predLen: form.predLen,
      risk: {
        maxPositionSize: form.maxPositionSize,
        maxPortfolioExposure: form.maxPortfolioExposure,
        stopLossPct: form.stopLossPct,
      },
    };
    try {
      const res = await fetch(`${API_URL}/api/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : body.message || `HTTP ${res.status}`,
        );
      }
      if (body.settings) {
        setSnap((prev) => ({
          ...prev,
          symbols: body.settings.symbols,
          dryRun: body.settings.dryRun,
          strategy: body.settings.strategy,
          signalThresholdPct: body.settings.signalThresholdPct,
          tradeIntervalSeconds: body.settings.tradeIntervalSeconds,
          barTimeframe: body.settings.barTimeframe,
          lookbackBars: body.settings.lookbackBars,
          predLen: body.settings.predLen,
          risk: body.settings.risk,
          paper: body.settings.paper,
          live: body.settings.live,
        }));
        if (!body.settings.symbols.includes(symbol)) {
          setSymbol(body.settings.symbols[0] || symbol);
        }
      }
      setSaveMsg(
        body.changed?.length
          ? `Saved: ${body.changed.join(", ")}`
          : "No changes",
      );
    } catch (err) {
      setSaveMsg(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const applySymbolList = useCallback(
    async (next: string[]) => {
      const cleaned = [
        ...new Set(
          next
            .map((s) => normalizeSymbol(s))
            .filter(
              (s) =>
                /^[A-Z][A-Z0-9.\-]{0,9}$/.test(s) ||
                /^[A-Z0-9]{2,10}\/[A-Z0-9]{2,10}$/.test(s),
            ),
        ),
      ];
      if (!cleaned.length) {
        throw new Error("Keep at least one valid ticker or crypto pair");
      }
      const res = await fetch(`${API_URL}/api/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: cleaned } satisfies SettingsPatch),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : body.message || `HTTP ${res.status}`,
        );
      }
      const symbols: string[] = body.settings?.symbols ?? cleaned;
      setSnap((prev) => ({
        ...prev,
        symbols,
        assetClasses: Object.fromEntries(
          symbols.map((s) => [
            s,
            (isCryptoSymbol(s) ? "crypto" : "us_equity") as AssetClass,
          ]),
        ),
        candles: Object.fromEntries(
          symbols.map((s) => [s, prev.candles[s] ?? []]),
        ),
        forecasts: Object.fromEntries(
          symbols.map((s) => [s, prev.forecasts[s] ?? null]),
        ),
        forecastHistory: Object.fromEntries(
          symbols.map((s) => [s, prev.forecastHistory?.[s] ?? []]),
        ),
      }));
      if (!symbols.includes(symbol)) {
        setSymbol(symbols[0]);
      }
      return symbols;
    },
    [symbol],
  );

  return (
    <TooltipProvider>
      <div className="flex min-h-full w-full flex-col gap-3 p-3 sm:gap-4 sm:p-4 md:p-5">
        <header className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="mono text-[10px] tracking-[0.2em] text-[var(--gold)] sm:text-xs">
              KRONOS
            </p>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl md:text-3xl">
              Trading Desk
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SystemStatusLight wsConnected={connected} />
            <MarketSessionBadge />
            <Hint
              label={
                snap.live
                  ? "LIVE: real money via Alpaca."
                  : "PAPER: simulated trading with fake money."
              }
            >
              <Badge tone={snap.paper ? "mint" : "coral"}>
                {snap.live ? "LIVE" : "PAPER"}
              </Badge>
            </Hint>
            {snap.dryRun && (
              <Hint label="DRY RUN: signals computed, no Alpaca orders submitted.">
                <Badge tone="gold">DRY RUN</Badge>
              </Hint>
            )}
            <FeedBadge
              symbol={symbol}
              feed={snap.marketDataFeed}
              symbols={snap.symbols}
            />
            <Hint label="Largest dollar notional allowed for one symbol.">
              <Badge tone="neutral">
                max pos {formatUsd(snap.risk.maxPositionSize)}
              </Badge>
            </Hint>
            <Hint
              label={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              <Button
                type="button"
                size="icon"
                onClick={toggleTheme}
                aria-label="Toggle color theme"
              >
                {theme === "dark" ? <SunIcon /> : <MoonIcon />}
              </Button>
            </Hint>
          </div>
        </header>

        <ErrorBanner connected={connected} />
        <SymbolStrip
          symbols={snap.symbols.length ? snap.symbols : emptySnapshot.symbols}
          active={symbol}
          candles={snap.candles}
          onSelect={setSymbol}
          onChangeSymbols={applySymbolList}
        />

        <div className="grid grid-cols-1 gap-3 lg:gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]">
          <Panel
            title={`${symbol}${isCryptoSymbol(symbol) ? " · CRYPTO" : ""} · Candles + Kronos forecast`}
            action={
              last ? (
                <div className="mono text-right text-xs sm:text-sm">
                  <div
                    style={{
                      color: changePct >= 0 ? "var(--mint)" : "var(--coral)",
                    }}
                  >
                    {formatPrice(last.close, symbol)} ({formatPct(changePct)})
                  </div>
                  <Hint
                    label={
                      isCryptoSymbol(symbol)
                        ? `Last bar ${new Date(last.timestamp).toLocaleString()}. Alpaca crypto spot is 24/7 — bars keep printing nights and weekends.`
                        : `Last bar ${new Date(last.timestamp).toLocaleString()}. Free Alpaca IEX is delayed (~${snap.marketDataFeed === "iex" ? "15–20" : "0"} min) and does not print new bars while the US equity session is closed (nights/weekends).`
                    }
                  >
                    <span className="text-[10px] text-[var(--muted)]">
                      bar {lastCandleAge}
                      {isCryptoSymbol(symbol) ? " · crypto 24/7" : ""}
                      {snap.dryRun ? " · dry marks use bar close" : ""}
                    </span>
                  </Hint>
                </div>
              ) : (
                <span className="mono text-xs text-[var(--muted)]">
                  {bootstrapped ? "waiting for data" : "loading…"}
                </span>
              )
            }
          >
            <div className="mb-2 flex flex-wrap items-center gap-1.5 sm:gap-2">
              <span className="mono hidden text-[10px] text-[var(--muted)] lg:inline">
                Drag zoom · Shift pan · Scroll · Dbl-click reset
              </span>
              <ToolbarBtn
                label="Zoom in (fewer bars)"
                onClick={() =>
                  setVisibleBars((v) => Math.max(20, Math.round(v * 0.7)))
                }
              >
                In
              </ToolbarBtn>
              <ToolbarBtn
                label="Zoom out (more bars)"
                onClick={() =>
                  setVisibleBars((v) =>
                    Math.min(
                      Math.max(candles.length, 20),
                      Math.round(v * 1.35),
                    ),
                  )
                }
              >
                Out
              </ToolbarBtn>
              <ToolbarBtn
                label="Show all candles"
                onClick={() => {
                  setVisibleBars(Math.max(candles.length, 20));
                  setViewResetKey((k) => k + 1);
                }}
              >
                Fit
              </ToolbarBtn>
              <ToolbarBtn
                label="Reset to last 120 bars (live edge)"
                onClick={() => {
                  setVisibleBars(120);
                  setViewResetKey((k) => k + 1);
                }}
              >
                Reset
              </ToolbarBtn>
              <label className="mono flex items-center gap-1.5 text-[10px] text-[var(--muted)] sm:text-[11px]">
                Height
                <Select
                  value={String(chartHeight)}
                  onValueChange={(v) => setChartHeight(Number(v))}
                >
                  <SelectTrigger size="sm" className="w-[5.5rem]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CHART_HEIGHTS.map((h) => (
                      <SelectItem key={h} value={String(h)}>
                        {h}px
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="mono flex items-center gap-2 text-[10px] text-[var(--muted)] sm:text-[11px]">
                Volume
                <Switch
                  checked={showVolume}
                  onCheckedChange={setShowVolume}
                  aria-label="Toggle volume bars"
                />
              </label>
              <label className="mono flex items-center gap-2 text-[10px] text-[var(--muted)] sm:text-[11px]">
                Past FC
                <Switch
                  checked={showHistory}
                  onCheckedChange={setShowHistory}
                  aria-label="Toggle past forecast history"
                />
              </label>
              <Hint label="Gold dashed = live Kronos forecast. Grey dashed = past forecasts overlaid on realized candles for accuracy.">
                <span className="mono text-[10px] text-[var(--muted)]">
                  {forecastHistory.length} saved
                </span>
              </Hint>
              <span className="mono text-[10px] text-[var(--muted)]">
                {visibleBars} bars
              </span>
            </div>
            <div className="overflow-hidden rounded-md border border-[var(--border)]">
              {(snap.marketErrors?.[symbol] || snap.inferenceErrors?.[symbol]) && (
                <div className="border-b border-[var(--coral)]/40 bg-[color-mix(in_srgb,var(--coral)_12%,transparent)] px-3 py-2">
                  <p className="mono text-[11px] text-[var(--coral)]">
                    {snap.marketErrors?.[symbol] ||
                      snap.inferenceErrors?.[symbol]}
                  </p>
                </div>
              )}
              <CandlestickChart
                candles={candles}
                forecast={forecast?.points ?? []}
                forecastHistory={forecastHistory}
                showHistory={showHistory}
                height={chartHeight}
                showVolume={showVolume}
                visibleBars={visibleBars}
                onVisibleBarsChange={setVisibleBars}
                viewResetKey={viewResetKey}
              />
            </div>
          </Panel>

          <div className="flex flex-col gap-3 sm:gap-4">
            <Panel title="Positions">
              {!snap.positions.length ? (
                <p className="mono text-xs text-[var(--muted)]">
                  No open positions
                </p>
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
                <p className="mono text-xs text-[var(--muted)]">
                  No equity points yet
                </p>
              ) : (
                <>
                  <p className="mono text-lg text-[var(--mint)]">
                    {formatUsd(snap.equity[snap.equity.length - 1].equity)}
                  </p>
                  <svg
                    viewBox="0 0 300 80"
                    className="mt-2 w-full"
                    height={80}
                  >
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

        <div className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-2 lg:gap-4">
          <ActivityPanel activity={snap.activity} />

          <Panel title="Settings" className="h-full">
              <form
                className="flex flex-col gap-3"
                onSubmit={saveSettings}
              >
                <p className="mono text-[10px] text-[var(--muted)]">
                  Symbols are managed in the strip above — add or remove tickers
                  there.
                </p>

                <ToggleField
                  label="Dry run"
                  hint="When on, no orders are sent to Alpaca."
                  checked={form.dryRun}
                  onCheckedChange={(v) =>
                    setForm((f) => ({ ...f, dryRun: v }))
                  }
                />

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Field
                    label="Strategy"
                    hint="Signal strategy used each loop cycle."
                  >
                    <Select
                      value={form.strategy}
                      onValueChange={(v) =>
                        setForm((f) => ({ ...f, strategy: v }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Strategy" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="forecast_momentum">
                          forecast_momentum
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field
                    label="Signal threshold %"
                    hint="Minimum forecast move before buy/sell."
                  >
                    <Input
                      type="number"
                      step="0.1"
                      min={0}
                      value={form.signalThresholdPct}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          signalThresholdPct: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field
                    label="Loop interval (s)"
                    hint="Seconds between full symbol cycles."
                  >
                    <Input
                      type="number"
                      min={5}
                      value={form.tradeIntervalSeconds}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          tradeIntervalSeconds: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field label="Bar timeframe" hint="Candle size from market data.">
                    <Select
                      value={form.barTimeframe}
                      onValueChange={(v) =>
                        setForm((f) => ({ ...f, barTimeframe: v }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Timeframe" />
                      </SelectTrigger>
                      <SelectContent>
                        {TIMEFRAMES.map((tf) => (
                          <SelectItem key={tf} value={tf}>
                            {tf}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                  <Field
                    label="Lookback bars"
                    hint="History window fetched for inference."
                  >
                    <Input
                      type="number"
                      min={32}
                      value={form.lookbackBars}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          lookbackBars: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field
                    label="Forecast length"
                    hint="How many bars Kronos predicts ahead."
                  >
                    <Input
                      type="number"
                      min={1}
                      value={form.predLen}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          predLen: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field
                    label="Max position $"
                    hint="Cap notional per symbol."
                  >
                    <Input
                      type="number"
                      min={1}
                      value={form.maxPositionSize}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          maxPositionSize: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field
                    label="Max exposure $"
                    hint="Cap total portfolio notional."
                  >
                    <Input
                      type="number"
                      min={1}
                      value={form.maxPortfolioExposure}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          maxPortfolioExposure: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                  <Field
                    label="Stop-loss %"
                    hint="Exit if unrealized loss exceeds this."
                  >
                    <Input
                      type="number"
                      step="0.1"
                      min={0.1}
                      value={form.stopLossPct}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          stopLossPct: Number(e.target.value),
                        }))
                      }
                    />
                  </Field>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    className="flex-1 sm:flex-none"
                    disabled={saving}
                  >
                    {saving ? "Saving…" : "Save settings"}
                  </Button>
                  <Button
                    type="button"
                    size="lg"
                    onClick={() => syncForm(snap)}
                  >
                    Reset form
                  </Button>
                  {saveMsg && (
                    <span className="mono text-[10px] text-[var(--muted)] sm:text-xs">
                      {saveMsg}
                    </span>
                  )}
                </div>

                <p className="mono text-[10px] text-[var(--muted)]">
                  API {API_URL} · LIVE brokerage mode stays env-gated and cannot
                  be enabled here.
                </p>
                {snap.orders[0] && <RecentOrder order={snap.orders[0]} />}
              </form>
            </Panel>
        </div>
      </div>
    </TooltipProvider>
  );
}

function ToolbarBtn({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <Hint label={label}>
      <Button type="button" size="sm" onClick={onClick}>
        {children}
      </Button>
    </Hint>
  );
}

function FeedBadge({
  symbol,
  feed,
  symbols,
}: {
  symbol: string;
  feed?: string;
  symbols: string[];
}) {
  const hasCrypto = symbols.some(isCryptoSymbol);
  const hasEquity = symbols.some((s) => !isCryptoSymbol(s));
  if (isCryptoSymbol(symbol)) {
    return (
      <Hint label="Selected symbol uses Alpaca crypto market data (24/7).">
        <Badge tone="sky">CRYPTO FEED</Badge>
      </Hint>
    );
  }
  const label =
    hasCrypto && hasEquity
      ? `REAL ${(feed || "iex").toUpperCase()}+CRYPTO`
      : `REAL ${(feed || "iex").toUpperCase()}`;
  return (
    <Hint label="Live Alpaca market data feed for candles (stocks/ETFs use IEX/SIP; crypto is separate).">
      <Badge tone="mint">{label}</Badge>
    </Hint>
  );
}

function MarketSessionBadge() {
  const { status } = useSystemStatus(5000);
  const session = status?.marketData.session;
  const equity = session?.equity;
  const crypto = session?.crypto;
  const hasEquity = equity?.watched ?? status?.trader.hasEquity;
  const hasCrypto = crypto?.watched ?? status?.trader.hasCrypto;

  if (!session) {
    return (
      <Hint label="Waiting for Alpaca market clock…">
        <Badge tone="neutral">SESSION …</Badge>
      </Hint>
    );
  }

  if (hasCrypto && !hasEquity) {
    return (
      <Hint label="Crypto spot trades 24/7 on Alpaca. No US cash-session pause.">
        <Badge tone="sky">CRYPTO 24/7</Badge>
      </Hint>
    );
  }

  if (hasCrypto && hasEquity && equity && !equity.isOpen) {
    const next = equity.nextOpen
      ? new Date(equity.nextOpen).toLocaleString()
      : "next equity session";
    return (
      <Hint
        label={`US stocks/ETFs paused until ${next}. Crypto pairs keep trading.`}
      >
        <Badge tone="sky">EQUITY CLOSED · CRYPTO LIVE</Badge>
      </Hint>
    );
  }

  if (equity?.isOpen || session.isOpen) {
    const until = (equity?.nextClose || session.nextClose)
      ? new Date(String(equity?.nextClose || session.nextClose)).toLocaleString()
      : "session close";
    return (
      <Hint
        label={
          hasCrypto
            ? `US equity session open (closes ${until}). Crypto also live 24/7.`
            : `US equity session is open. Closes ${until}.`
        }
      >
        <Badge tone="mint">SESSION OPEN</Badge>
      </Hint>
    );
  }

  const next = (equity?.nextOpen || session.nextOpen)
    ? new Date(String(equity?.nextOpen || session.nextOpen)).toLocaleString()
    : "next session";
  return (
    <Hint label={`Trading loop paused for equities. Next open ${next}.`}>
      <Badge tone="gold">SESSION CLOSED</Badge>
    </Hint>
  );
}

function ErrorBanner({ connected }: { connected: boolean }) {
  const { status, fetchError } = useSystemStatus(5000);
  const issues: string[] = [];
  if (!connected) issues.push("WebSocket disconnected — start/restart the trader.");
  if (fetchError) {
    issues.push(
      fetchError.includes("404")
        ? "Status API 404 — restart the trader (.\scripts\dev.ps1 trader) so /api/status loads."
        : `Status API unreachable: ${fetchError}`,
    );
  }
  if (status?.marketData.mock) {
    issues.push("Mock market data is enabled — turn it off in settings.");
  }
  if (status && !status.marketData.keysConfigured) {
    issues.push("Alpaca API keys are missing.");
  }
  for (const issue of status?.issues ?? []) {
    const low = issue.toLowerCase();
    if (low.includes("market closed") || low.includes("equity market closed")) {
      continue;
    }
    if (!issues.includes(issue)) issues.push(issue);
  }
  const equity = status?.marketData.session?.equity;
  const crypto = status?.marketData.session?.crypto;
  const hasEquity = equity?.watched ?? status?.trader.hasEquity ?? true;
  const hasCrypto = crypto?.watched ?? status?.trader.hasCrypto ?? false;
  const equityClosed = hasEquity && equity?.isOpen === false;
  const sessionClosedOnly =
    status?.marketData.session?.isOpen === false && !hasCrypto;
  const showEquityPaused = equityClosed || sessionClosedOnly;
  if (!issues.length && !showEquityPaused) return null;
  return (
    <div className="space-y-2">
      {showEquityPaused && (
        <div
          role="status"
          className={
            hasCrypto
              ? "rounded-md border border-[var(--sky)]/40 bg-[color-mix(in_srgb,var(--sky)_10%,var(--panel))] px-3 py-2.5"
              : "rounded-md border border-[var(--gold)]/40 bg-[color-mix(in_srgb,var(--gold)_10%,var(--panel))] px-3 py-2.5"
          }
        >
          <p
            className="mono mb-0.5 text-[10px] uppercase tracking-wider"
            style={{ color: hasCrypto ? "var(--sky)" : "var(--gold)" }}
          >
            {hasCrypto ? "Equity session closed · crypto live" : "Market closed"}
          </p>
          <p className="text-sm text-[var(--foreground)]">
            {hasCrypto ? (
              <>
                Stocks and ETFs are paused until{" "}
                {equity?.nextOpen || status?.marketData.session?.nextOpen
                  ? new Date(
                      String(
                        equity?.nextOpen || status?.marketData.session?.nextOpen,
                      ),
                    ).toLocaleString()
                  : "the next US equity session"}
                . Crypto pairs keep forecasting and trading 24/7.
              </>
            ) : (
              <>
                Trading loop is paused until{" "}
                {status?.marketData.session?.nextOpen
                  ? new Date(status.marketData.session.nextOpen).toLocaleString()
                  : "the next US equity session"}
                . Forecasts and chart stay live; no new orders.
              </>
            )}
          </p>
        </div>
      )}
      {issues.length > 0 && (
        <div
          role="alert"
          className="rounded-md border border-[var(--coral)]/50 bg-[color-mix(in_srgb,var(--coral)_10%,var(--panel))] px-3 py-2.5"
        >
          <p className="mono mb-1 text-[10px] uppercase tracking-wider text-[var(--coral)]">
            Errors
          </p>
          <ul className="space-y-1">
            {issues.slice(0, 6).map((issue) => (
              <li
                key={issue}
                className="text-sm leading-snug text-[var(--foreground)]"
              >
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.75" />
      <path
        d="M12 2v2.5M12 19.5V22M4.93 4.93l1.77 1.77M17.3 17.3l1.77 1.77M2 12h2.5M19.5 12H22M4.93 19.07l1.77-1.77M17.3 6.7l1.77-1.77"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <Hint label={hint}>
        <span className="mono cursor-help text-[10px] text-[var(--muted)] underline decoration-dotted decoration-[var(--border)] underline-offset-2 sm:text-[11px]">
          {label}
        </span>
      </Hint>
      {children}
    </label>
  );
}

function ToggleField({
  label,
  hint,
  checked,
  onCheckedChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--border)] bg-[var(--input)] px-3 py-2.5">
      <Hint label={hint}>
        <span className="mono cursor-help text-[11px] underline decoration-dotted decoration-[var(--border)] underline-offset-2">
          {label}
        </span>
      </Hint>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

function Hint({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

function PositionRow({ p }: { p: Position }) {
  const positive = p.unrealizedPnl >= 0;
  const crypto =
    p.assetClass === "crypto" || isCryptoSymbol(p.symbol);
  return (
    <li className="flex items-center justify-between gap-2 border-b border-[var(--border)] pb-2 last:border-0">
      <div>
        <div className="flex items-center gap-1.5">
          <span className="mono text-sm">{p.symbol}</span>
          {crypto && (
            <span className="mono text-[9px] uppercase tracking-wider text-[var(--sky)]">
              CRYPTO
            </span>
          )}
        </div>
        <div className="mono text-[10px] text-[var(--muted)]">
          {p.qty} @ {formatPrice(p.avgEntryPrice, p.symbol)}
          {p.currentPrice != null
            ? ` → ${formatPrice(p.currentPrice, p.symbol)}`
            : ""}
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

const ACTIVITY_PAGE = 20;

function ActivityPanel({ activity }: { activity: ActivityLogEntry[] }) {
  const [limit, setLimit] = useState(ACTIVITY_PAGE);
  const visible = Math.min(limit, activity.length);
  const shown = activity.slice(0, visible);
  const hasMore = visible < activity.length;
  const canCollapse = limit > ACTIVITY_PAGE && activity.length > ACTIVITY_PAGE;

  return (
    <Panel
      title="Activity"
      className="h-full min-h-[20rem]"
      action={<CopyActivityButton activity={activity} />}
    >
      <div className="flex h-full min-h-0 flex-1 flex-col gap-2">
        <ScrollArea className="h-full min-h-0 flex-1">
          <ul className="space-y-2 pr-3">
            {activity.length === 0 && (
              <li className="mono text-xs text-[var(--muted)]">
                No events yet
              </li>
            )}
            {shown.map((a) => (
              <ActivityRow key={a.id} entry={a} />
            ))}
          </ul>
        </ScrollArea>
        {activity.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)] pt-2">
            <span className="mono text-[10px] text-[var(--muted)]">
              Showing {shown.length} of {activity.length}
            </span>
            <div className="flex gap-1.5">
              {canCollapse && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() => setLimit(ACTIVITY_PAGE)}
                >
                  Show less
                </Button>
              )}
              {hasMore && (
                <Button
                  type="button"
                  size="sm"
                  onClick={() =>
                    setLimit((n) => Math.min(n + ACTIVITY_PAGE, activity.length))
                  }
                >
                  Load more
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

function formatActivityPlain(activity: ActivityLogEntry[]): string {
  if (!activity.length) return "No activity events.";
  return activity
    .map((a) => {
      const time = new Date(a.timestamp).toISOString();
      const sym = a.symbol ? ` ${a.symbol}` : "";
      return `[${time}] ${a.kind.toUpperCase()}${sym}  ${a.message}`;
    })
    .join("\n");
}

function CopyActivityButton({ activity }: { activity: ActivityLogEntry[] }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    const text = formatActivityPlain(activity);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback for older browsers / denied permission
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <Hint label={copied ? "Copied" : "Copy activity log as plain text"}>
      <Button
        type="button"
        size="icon-sm"
        onClick={onCopy}
        disabled={!activity.length}
        aria-label="Copy activity log"
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </Button>
    </Hint>
  );
}

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect
        x="9"
        y="9"
        width="11"
        height="11"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M5 15V5a2 2 0 0 1 2-2h10"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5 13l4 4L19 7"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
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
    <div className="mono mt-1 rounded border border-[var(--border)] p-3 text-xs">
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
      return {
        ...prev,
        candles: { ...prev.candles, [symbol]: list.slice(-512) },
      };
    }
    case "forecast": {
      const symbol = event.payload.symbol;
      const entry: ForecastHistoryEntry = {
        id: (event.payload as ForecastHistoryEntry).id || event.payload.generatedAt,
        symbol: event.payload.symbol,
        generatedAt: event.payload.generatedAt,
        model: event.payload.model,
        sampleCount: event.payload.sampleCount,
        points: event.payload.points,
        anchorTimestamp: event.payload.anchorTimestamp,
        anchorClose: event.payload.anchorClose,
      };
      const prevHist = prev.forecastHistory?.[symbol] ?? [];
      const nextHist = prevHist.some((h) => h.generatedAt === entry.generatedAt)
        ? prevHist
        : [...prevHist, entry].slice(-48);
      return {
        ...prev,
        forecasts: { ...prev.forecasts, [symbol]: event.payload },
        forecastHistory: { ...prev.forecastHistory, [symbol]: nextHist },
      };
    }
    case "order":
      return { ...prev, orders: [event.payload, ...prev.orders].slice(0, 50) };
    case "position":
      return { ...prev, positions: event.payload };
    case "equity":
      return { ...prev, equity: [...prev.equity, event.payload].slice(-500) };
    case "activity":
      return {
        ...prev,
        activity: [event.payload, ...prev.activity].slice(0, 100),
      };
    case "signal":
      // Activity log already receives signal rows via the "activity" event —
      // don't duplicate them here.
      return prev;
    default:
      return prev;
  }
}
