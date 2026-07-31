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

export interface Position {
  symbol: string;
  qty: number;
  side: "long" | "short";
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
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
  risk?: Partial<RiskLimits>;
}

export interface Snapshot {
  symbols: string[];
  selectedSymbol: string;
  candles: Record<string, Candle[]>;
  forecasts: Record<string, Forecast | null>;
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
