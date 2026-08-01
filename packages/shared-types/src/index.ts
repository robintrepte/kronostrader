export type Side = "buy" | "sell" | "hold";

export type OrderStatus =
  | "new"
  | "accepted"
  | "filled"
  | "partially_filled"
  | "canceled"
  | "rejected"
  | "dry_run";

export interface Candle {
  symbol: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount?: number;
}

export interface ForecastPoint {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  amount?: number;
  /** Optional lower bound of confidence band */
  closeLow?: number;
  /** Optional upper bound of confidence band */
  closeHigh?: number;
}

export interface Forecast {
  symbol: string;
  generatedAt: string;
  points: ForecastPoint[];
  model: string;
  sampleCount: number;
  /** Last real candle timestamp when this forecast was made */
  anchorTimestamp?: string;
  /** Last real candle close when this forecast was made */
  anchorClose?: number;
}

/** A stored forecast kept for accuracy review once time catches up. */
export interface ForecastHistoryEntry extends Forecast {
  id: string;
}

export interface Signal {
  id: string;
  symbol: string;
  side: Side;
  strength: number;
  reason: string;
  strategy: string;
  timestamp: string;
  forecastHorizonClose?: number;
  lastClose?: number;
}

export type AssetClass = "us_equity" | "crypto";

export interface Position {
  symbol: string;
  qty: number;
  side: "long" | "short";
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
  assetClass?: AssetClass;
  updatedAt: string;
}

export interface Order {
  id: string;
  clientOrderId?: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  type: "market" | "limit";
  status: OrderStatus;
  filledAvgPrice?: number;
  submittedAt: string;
  filledAt?: string;
  dryRun: boolean;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  cash: number;
  buyingPower?: number;
}

export type ActivityKind =
  | "signal"
  | "order"
  | "fill"
  | "risk_reject"
  | "forecast"
  | "system"
  | "error";

export interface ActivityLogEntry {
  id: string;
  kind: ActivityKind;
  message: string;
  symbol?: string;
  timestamp: string;
  meta?: Record<string, unknown>;
}

export interface RiskLimits {
  maxPositionSize: number;
  maxPortfolioExposure: number;
  stopLossPct: number;
}

export interface SymbolForecastMetrics {
  symbol?: string;
  n: number;
  hitRate: number | null;
  mape: number | null;
  mae: number | null;
  bandCoverage: number | null;
  errorStreak: number;
  tradeable: boolean;
  updatedAt: string;
}

export interface ForecastMetricsResponse {
  updatedAt: string;
  minHitRate: number;
  maxMape: number;
  bySymbol: Record<string, SymbolForecastMetrics>;
}

export interface BacktestResult {
  ok: boolean;
  generatedAt?: string;
  startingCash?: number;
  endingEquity?: number;
  netPnl?: number;
  netPnlPct?: number;
  maxDrawdownPct?: number;
  sharpeLike?: number;
  winRate?: number;
  tradeCount?: number;
  avgEdgeBps?: number;
  perSymbol?: Record<string, { trades: number; pnl: number }>;
  notes?: string[];
  message?: string;
}

export interface TraderSettings {
  symbols: string[];
  dryRun: boolean;
  paper: boolean;
  live: boolean;
  strategy: string;
  signalThresholdPct: number;
  tradeIntervalSeconds: number;
  barTimeframe: string;
  lookbackBars: number;
  predLen: number;
  mockMarketData: boolean;
  sampleCount?: number;
  minConfidence?: number;
  maxBandWidthPct?: number;
  maxForecastDrawdownPct?: number;
  minHitRate?: number;
  maxMape?: number;
  requireMetricsTradeable?: boolean;
  takeProfitFraction?: number;
  topKEntries?: number;
  regimeMaxVolPct?: number;
  regimeMinTrendPct?: number;
  risk: RiskLimits;
  updatedAt?: string;
}

export interface SettingsPatch {
  symbols?: string[];
  dryRun?: boolean;
  strategy?: string;
  signalThresholdPct?: number;
  tradeIntervalSeconds?: number;
  barTimeframe?: string;
  lookbackBars?: number;
  predLen?: number;
  mockMarketData?: boolean;
  sampleCount?: number;
  minConfidence?: number;
  maxBandWidthPct?: number;
  maxForecastDrawdownPct?: number;
  minHitRate?: number;
  maxMape?: number;
  requireMetricsTradeable?: boolean;
  takeProfitFraction?: number;
  topKEntries?: number;
  regimeMaxVolPct?: number;
  regimeMinTrendPct?: number;
  risk?: Partial<RiskLimits>;
}

export interface Snapshot {
  symbols: string[];
  selectedSymbol: string;
  candles: Record<string, Candle[]>;
  forecasts: Record<string, Forecast | null>;
  /** Recent past forecasts per symbol (oldest → newest), for accuracy overlays */
  forecastHistory?: Record<string, ForecastHistoryEntry[]>;
  positions: Position[];
  orders: Order[];
  equity: EquityPoint[];
  activity: ActivityLogEntry[];
  risk: RiskLimits;
  paper: boolean;
  dryRun: boolean;
  live: boolean;
  strategy?: string;
  signalThresholdPct?: number;
  tradeIntervalSeconds?: number;
  barTimeframe?: string;
  lookbackBars?: number;
  predLen?: number;
  mockMarketData?: boolean;
  marketDataFeed?: string;
  /** Per-symbol asset class for mixed equity + crypto books */
  assetClasses?: Record<string, AssetClass>;
  forecastMetrics?: Record<string, SymbolForecastMetrics>;
  edge?: {
    strategy: string;
    strict: boolean;
    sampleCount: number;
    topKEntries: number;
    minConfidence: number;
    minHitRate: number;
    takeProfitFraction: number;
  };
  lastBacktest?: BacktestResult | null;
  sampleCount?: number;
  minConfidence?: number;
  topKEntries?: number;
  marketErrors?: Record<string, string>;
  inferenceErrors?: Record<string, string>;
}

export interface HardwareStats {
  device?: string;
  cpuPercent?: number | null;
  cpuCount?: number | null;
  ramUsedGb?: number | null;
  ramTotalGb?: number | null;
  processRssGb?: number | null;
  cudaAvailable?: boolean;
  cudaDeviceName?: string | null;
  cudaMemoryAllocatedGb?: number | null;
  cudaMemoryReservedGb?: number | null;
}

export interface SystemStatus {
  level: "ok" | "degraded" | "error";
  summary: string;
  checkedAt: string;
  issues: string[];
  trader: {
    ok: boolean;
    dryRun: boolean;
    paper: boolean;
    live: boolean;
    symbols: string[];
    mockMarketData: boolean;
    intervalSeconds: number;
    strategy: string;
    marketOpen?: boolean;
    hasEquity?: boolean;
    hasCrypto?: boolean;
  };
  marketData: {
    ok: boolean;
    provider: string;
    feed: string;
    mock: boolean;
    keysConfigured: boolean;
    lastSuccessBySymbol: Record<string, string>;
    errorsBySymbol: Record<string, string>;
    delayMinutes: number;
    session?: {
      isOpen: boolean;
      nextOpen?: string | null;
      nextClose?: string | null;
      source?: string;
      equity?: {
        isOpen: boolean;
        nextOpen?: string | null;
        nextClose?: string | null;
        source?: string;
        watched?: boolean;
      };
      crypto?: {
        isOpen: boolean;
        nextOpen?: string | null;
        nextClose?: string | null;
        source?: string;
        watched?: boolean;
      };
    };
  };
  inference: {
    ok: boolean;
    reachable: boolean;
    loaded: boolean;
    status: string;
    url: string;
    model?: string | null;
    tokenizer?: string | null;
    device?: string | null;
    uptimeSeconds?: number | null;
    maxContext?: number | null;
    hardware?: HardwareStats | null;
    error?: string | null;
  };
}

export type WsEventType =
  | "candle"
  | "forecast"
  | "signal"
  | "order"
  | "position"
  | "equity"
  | "activity"
  | "snapshot";

export interface WsEventBase {
  type: WsEventType;
  timestamp: string;
}

export interface CandleEvent extends WsEventBase {
  type: "candle";
  payload: Candle;
}

export interface ForecastEvent extends WsEventBase {
  type: "forecast";
  payload: Forecast;
}

export interface SignalEvent extends WsEventBase {
  type: "signal";
  payload: Signal;
}

export interface OrderEvent extends WsEventBase {
  type: "order";
  payload: Order;
}

export interface PositionEvent extends WsEventBase {
  type: "position";
  payload: Position[];
}

export interface EquityEvent extends WsEventBase {
  type: "equity";
  payload: EquityPoint;
}

export interface ActivityEvent extends WsEventBase {
  type: "activity";
  payload: ActivityLogEntry;
}

export interface SnapshotEvent extends WsEventBase {
  type: "snapshot";
  payload: Snapshot;
}

export type WsEvent =
  | CandleEvent
  | ForecastEvent
  | SignalEvent
  | OrderEvent
  | PositionEvent
  | EquityEvent
  | ActivityEvent
  | SnapshotEvent;
