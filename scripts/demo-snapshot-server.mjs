#!/usr/bin/env node
/**
 * Local mock trader API for README / portfolio screenshots.
 * Serves a rich snapshot so the real Next.js desk looks live without Alpaca/Kronos.
 */
import http from "node:http";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.DEMO_API_PORT || 8001);

const SYMBOLS = [
  "SPY",
  "QQQ",
  "NVDA",
  "TSLA",
  "AAPL",
  "MSFT",
  "BTC/USD",
  "ETH/USD",
  "SOL/USD",
  "AMD",
  "META",
  "GOOGL",
];

function iso(ms) {
  return new Date(ms).toISOString();
}

function seeded(seed) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function genCandles(symbol, n, startPrice, seed) {
  const rand = seeded(seed);
  const now = Date.now();
  const step = symbol.includes("/") ? 60 * 60 * 1000 : 60 * 60 * 1000;
  const bars = [];
  let close = startPrice;
  for (let i = n; i >= 0; i--) {
    const drift = (rand() - 0.48) * startPrice * 0.012;
    const open = close;
    close = Math.max(0.01, open + drift);
    const high = Math.max(open, close) * (1 + rand() * 0.006);
    const low = Math.min(open, close) * (1 - rand() * 0.006);
    bars.push({
      symbol,
      timestamp: iso(now - i * step),
      open: +open.toFixed(4),
      high: +high.toFixed(4),
      low: +low.toFixed(4),
      close: +close.toFixed(4),
      volume: Math.floor(800_000 + rand() * 2_500_000),
    });
  }
  return bars;
}

function genForecast(symbol, candles, predLen, seed) {
  const rand = seeded(seed + 99);
  const last = candles[candles.length - 1];
  const step =
    candles.length > 1
      ? new Date(candles[candles.length - 1].timestamp) -
        new Date(candles[candles.length - 2].timestamp)
      : 3_600_000;
  let close = last.close;
  const points = [];
  for (let i = 1; i <= predLen; i++) {
    close = close * (1 + (rand() - 0.42) * 0.008);
    const band = close * (0.008 + rand() * 0.01);
    points.push({
      timestamp: iso(new Date(last.timestamp).getTime() + i * step),
      open: +close.toFixed(4),
      high: +(close + band * 0.6).toFixed(4),
      low: +(close - band * 0.6).toFixed(4),
      close: +close.toFixed(4),
      closeLow: +(close - band).toFixed(4),
      closeHigh: +(close + band).toFixed(4),
      volume: Math.floor(500_000 + rand() * 1_000_000),
    });
  }
  return {
    symbol,
    generatedAt: iso(Date.now()),
    points,
    model: "NeoQuasar/Kronos-base",
    sampleCount: 4,
    anchorTimestamp: last.timestamp,
    anchorClose: last.close,
  };
}

function genHistory(symbol, candles, seed) {
  const rand = seeded(seed + 7);
  const entries = [];
  for (let h = 0; h < 4; h++) {
    const anchorIdx = candles.length - 40 - h * 18;
    if (anchorIdx < 10) continue;
    const anchor = candles[anchorIdx];
    let close = anchor.close;
    const points = [];
    for (let i = 1; i <= 24; i++) {
      close = close * (1 + (rand() - 0.5) * 0.01);
      const t = new Date(anchor.timestamp).getTime() + i * 3_600_000;
      points.push({
        timestamp: iso(t),
        open: +close.toFixed(4),
        high: +(close * 1.004).toFixed(4),
        low: +(close * 0.996).toFixed(4),
        close: +close.toFixed(4),
      });
    }
    entries.push({
      id: `${symbol}-hist-${h}`,
      symbol,
      generatedAt: iso(new Date(anchor.timestamp).getTime() - 60_000),
      points,
      model: "NeoQuasar/Kronos-base",
      sampleCount: 4,
      anchorTimestamp: anchor.timestamp,
      anchorClose: anchor.close,
    });
  }
  return entries;
}

const STARTS = {
  SPY: 512,
  QQQ: 448,
  NVDA: 118,
  TSLA: 248,
  AAPL: 224,
  MSFT: 428,
  "BTC/USD": 68420,
  "ETH/USD": 3420,
  "SOL/USD": 148,
  AMD: 162,
  META: 512,
  GOOGL: 178,
};

const candles = {};
const forecasts = {};
const forecastHistory = {};
const forecastMetrics = {};
const assetClasses = {};

SYMBOLS.forEach((sym, i) => {
  const bars = genCandles(sym, 160, STARTS[sym] ?? 100, 1000 + i * 17);
  candles[sym] = bars;
  forecasts[sym] = genForecast(sym, bars, 48, 2000 + i * 13);
  forecastHistory[sym] = genHistory(sym, bars, 3000 + i * 11);
  assetClasses[sym] = sym.includes("/") ? "crypto" : "us_equity";
  const hit = 0.48 + (i % 5) * 0.05;
  const mape = 0.012 + (i % 4) * 0.004;
  forecastMetrics[sym] = {
    symbol: sym,
    n: 28 + i * 2,
    hitRate: +hit.toFixed(3),
    mape: +mape.toFixed(4),
    mae: +(mape * (STARTS[sym] ?? 100) * 0.4).toFixed(4),
    bandCoverage: +(0.62 + (i % 3) * 0.08).toFixed(3),
    errorStreak: i % 3,
    tradeable: hit >= 0.52 && mape <= 0.03,
    updatedAt: iso(Date.now() - i * 90_000),
  };
});

const btc = candles["BTC/USD"].at(-1).close;
const spy = candles.SPY.at(-1).close;
const nvda = candles.NVDA.at(-1).close;

const positions = [
  {
    symbol: "BTC/USD",
    qty: 0.028,
    side: "long",
    avgEntryPrice: btc * 0.972,
    currentPrice: btc,
    marketValue: 0.028 * btc,
    unrealizedPnl: 0.028 * (btc - btc * 0.972),
    unrealizedPnlPct: 2.8,
    assetClass: "crypto",
    updatedAt: iso(Date.now()),
  },
  {
    symbol: "NVDA",
    qty: 12,
    side: "long",
    avgEntryPrice: nvda * 0.991,
    currentPrice: nvda,
    marketValue: 12 * nvda,
    unrealizedPnl: 12 * (nvda - nvda * 0.991),
    unrealizedPnlPct: 0.9,
    assetClass: "us_equity",
    updatedAt: iso(Date.now()),
  },
  {
    symbol: "SPY",
    qty: 4,
    side: "long",
    avgEntryPrice: spy * 1.004,
    currentPrice: spy,
    marketValue: 4 * spy,
    unrealizedPnl: 4 * (spy - spy * 1.004),
    unrealizedPnlPct: -0.4,
    assetClass: "us_equity",
    updatedAt: iso(Date.now()),
  },
];

const equity = [];
let eq = 98_400;
for (let i = 48; i >= 0; i--) {
  eq += (Math.sin(i / 5) + 0.15) * 85;
  equity.push({
    timestamp: iso(Date.now() - i * 30 * 60_000),
    equity: +eq.toFixed(2),
    cash: 72_100,
    buyingPower: 144_200,
  });
}

const now = Date.now();
const activity = [
  {
    id: "a1",
    kind: "forecast",
    message: "Kronos forecast ready for BTC/USD · +1.8% horizon · bands OK",
    symbol: "BTC/USD",
    timestamp: iso(now - 40_000),
  },
  {
    id: "a2",
    kind: "signal",
    message: "STRICT BUY ranked #1 BTC/USD · confidence 0.71 · hit 61%",
    symbol: "BTC/USD",
    timestamp: iso(now - 35_000),
  },
  {
    id: "a3",
    kind: "order",
    message: "DRY RUN buy 0.004 BTC/USD @ market",
    symbol: "BTC/USD",
    timestamp: iso(now - 30_000),
  },
  {
    id: "a4",
    kind: "risk_reject",
    message: "Risk blocked buy TSLA: max position size or portfolio exposure reached",
    symbol: "TSLA",
    timestamp: iso(now - 120_000),
  },
  {
    id: "a5",
    kind: "system",
    message: "Regime filter: QQQ vol 5.4% > cap — skipped new entries",
    symbol: "QQQ",
    timestamp: iso(now - 180_000),
  },
  {
    id: "a6",
    kind: "forecast",
    message: "Forecast quality gate: NVDA hit-rate 58% · MAPE 1.6% · tradeable",
    symbol: "NVDA",
    timestamp: iso(now - 220_000),
  },
];

const lastBacktest = {
  ok: true,
  generatedAt: iso(now - 3_600_000),
  startingCash: 100_000,
  endingEquity: 101_842.55,
  netPnl: 1842.55,
  netPnlPct: 1.84,
  maxDrawdownPct: 1.12,
  sharpeLike: 1.42,
  winRate: 0.57,
  tradeCount: 14,
  avgEdgeBps: 18.4,
  perSymbol: {
    "BTC/USD": { trades: 6, pnl: 1120.4 },
    SPY: { trades: 5, pnl: 410.2 },
    NVDA: { trades: 3, pnl: 311.95 },
  },
  notes: ["Costs included (spread + slippage)", "Strict gates mostly HOLD"],
};

const snapshot = {
  symbols: SYMBOLS,
  selectedSymbol: "BTC/USD",
  candles,
  forecasts,
  forecastHistory,
  positions,
  orders: [
    {
      id: "ord-1",
      clientOrderId: "dry-btc-1",
      symbol: "BTC/USD",
      side: "buy",
      qty: 0.004,
      type: "market",
      status: "dry_run",
      filledAvgPrice: btc,
      submittedAt: iso(now - 30_000),
      dryRun: true,
    },
  ],
  equity,
  activity,
  risk: {
    maxPositionSize: 2000,
    maxPortfolioExposure: 25000,
    stopLossPct: 2,
  },
  paper: true,
  dryRun: true,
  live: false,
  strategy: "strict_forecast",
  signalThresholdPct: 0.6,
  tradeIntervalSeconds: 60,
  barTimeframe: "1Hour",
  lookbackBars: 400,
  predLen: 48,
  mockMarketData: false,
  marketDataFeed: "iex",
  assetClasses,
  forecastMetrics,
  edge: {
    strategy: "strict_forecast",
    strict: true,
    sampleCount: 4,
    topKEntries: 3,
    minConfidence: 0.35,
    minHitRate: 0.48,
    takeProfitFraction: 0.6,
  },
  lastBacktest,
  sampleCount: 4,
  minConfidence: 0.35,
  topKEntries: 3,
};

const status = {
  level: "ok",
  summary: "All systems nominal · paper / dry-run",
  checkedAt: iso(Date.now()),
  issues: [],
  trader: {
    ok: true,
    dryRun: true,
    paper: true,
    live: false,
    symbols: SYMBOLS,
    mockMarketData: false,
    intervalSeconds: 60,
    strategy: "strict_forecast",
    marketOpen: true,
    hasEquity: true,
    hasCrypto: true,
  },
  marketData: {
    ok: true,
    provider: "alpaca",
    feed: "iex",
    mock: false,
    keysConfigured: true,
    lastSuccessBySymbol: Object.fromEntries(
      SYMBOLS.map((s) => [s, iso(Date.now() - 15_000)]),
    ),
    errorsBySymbol: {},
    delayMinutes: 0,
    session: {
      isOpen: true,
      source: "mixed",
      equity: { isOpen: true, watched: true, source: "us_equity" },
      crypto: { isOpen: true, watched: true, source: "crypto_24_7" },
    },
  },
  inference: {
    ok: true,
    reachable: true,
    loaded: true,
    status: "ready",
    url: "http://localhost:8000",
    model: "NeoQuasar/Kronos-base",
    tokenizer: "NeoQuasar/Kronos-Tokenizer-base",
    device: "cpu",
    uptimeSeconds: 8421,
    maxContext: 512,
    hardware: {
      device: "cpu",
      cpuPercent: 22.4,
      cpuCount: 8,
      ramUsedGb: 6.2,
      ramTotalGb: 16,
      processRssGb: 1.8,
      cudaAvailable: false,
    },
  },
};

function sendJson(res, code, body) {
  const data = JSON.stringify(body);
  res.writeHead(code, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Length": Buffer.byteLength(data),
  });
  res.end(data);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    res.end();
    return;
  }
  if (url.pathname === "/api/snapshot") return sendJson(res, 200, snapshot);
  if (url.pathname === "/api/status") {
    status.checkedAt = iso(Date.now());
    return sendJson(res, 200, status);
  }
  if (url.pathname === "/api/backtest/last") return sendJson(res, 200, lastBacktest);
  if (url.pathname === "/api/backtest/run" && req.method === "POST") {
    return sendJson(res, 200, lastBacktest);
  }
  if (url.pathname === "/api/settings" && req.method === "PATCH") {
    return sendJson(res, 200, {
      changed: [],
      settings: {
        symbols: SYMBOLS,
        dryRun: true,
        strategy: "strict_forecast",
        signalThresholdPct: 0.6,
        tradeIntervalSeconds: 60,
        barTimeframe: "1Hour",
        lookbackBars: 400,
        predLen: 48,
        risk: snapshot.risk,
        paper: true,
        live: false,
      },
    });
  }
  if (url.pathname === "/api/symbols/search") {
    const q = (url.searchParams.get("q") || "").toUpperCase();
    const hits = SYMBOLS.filter((s) => s.includes(q)).map((s) => ({
      symbol: s,
      name: s,
      assetClass: assetClasses[s],
    }));
    return sendJson(res, 200, { results: hits });
  }
  if (url.pathname === "/health") return sendJson(res, 200, { ok: true });
  sendJson(res, 404, { detail: "not found" });
});

const wss = new WebSocketServer({ server, path: "/ws" });
wss.on("connection", (ws) => {
  ws.send(JSON.stringify({ type: "snapshot", timestamp: iso(Date.now()), payload: snapshot }));
  const ping = setInterval(() => {
    if (ws.readyState === 1) {
      ws.send(
        JSON.stringify({
          type: "heartbeat",
          timestamp: iso(Date.now()),
          payload: {},
        }),
      );
    }
  }, 15_000);
  ws.on("close", () => clearInterval(ping));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Demo trader API on http://127.0.0.1:${PORT}`);
});
