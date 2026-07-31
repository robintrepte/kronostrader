"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import type {
  Candle,
  ForecastHistoryEntry,
  ForecastPoint,
} from "@kronos/shared-types";

const DEFAULT_VISIBLE = 120;
const MIN_VISIBLE = 20;
const HISTORY_DRAW_LIMIT = 16;

function tsMs(value: string): number {
  return new Date(value).getTime();
}

/** Map a timestamp onto the candle slot axis (linear between neighbors). */
function xForTime(
  t: number,
  candleTimes: number[],
  xCandle: (i: number) => number,
): number | null {
  if (!candleTimes.length) return null;
  if (t < candleTimes[0] || t > candleTimes[candleTimes.length - 1]) {
    // allow slight extrapolation past last candle for still-open forecast tips
    if (t > candleTimes[candleTimes.length - 1] && candleTimes.length >= 2) {
      const i = candleTimes.length - 1;
      const dt = candleTimes[i] - candleTimes[i - 1] || 1;
      const frac = (t - candleTimes[i]) / dt;
      if (frac > 2) return null;
      return xCandle(i) + frac * (xCandle(i) - xCandle(i - 1));
    }
    return null;
  }
  let lo = 0;
  let hi = candleTimes.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const v = candleTimes[mid];
    if (v === t) return xCandle(mid);
    if (v < t) lo = mid + 1;
    else hi = mid - 1;
  }
  const i1 = Math.max(1, lo);
  const i0 = i1 - 1;
  const t0 = candleTimes[i0];
  const t1 = candleTimes[i1];
  const frac = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
  return xCandle(i0) + frac * (xCandle(i1) - xCandle(i0));
}

export function forecastAccuracy(
  history: ForecastHistoryEntry[],
  candles: Candle[],
): { samples: number; maePct: number; mapeHint: string } | null {
  if (!history.length || !candles.length) return null;
  const byTs = new Map(candles.map((c) => [tsMs(c.timestamp), c.close]));
  // allow ±1 bar match within 2 minutes for timestamp drift
  const closes = [...byTs.entries()].sort((a, b) => a[0] - b[0]);
  const errors: number[] = [];

  const nearestClose = (t: number): number | null => {
    if (byTs.has(t)) return byTs.get(t)!;
    let best: number | null = null;
    let bestDt = Infinity;
    for (const [ct, close] of closes) {
      const dt = Math.abs(ct - t);
      if (dt < bestDt) {
        bestDt = dt;
        best = close;
      }
    }
    return bestDt <= 3 * 60_000 ? best : null;
  };

  for (const entry of history) {
    for (const p of entry.points) {
      const actual = nearestClose(tsMs(p.timestamp));
      if (actual == null || actual === 0) continue;
      // only score once the bar time is in the past relative to "now"
      if (tsMs(p.timestamp) > Date.now()) continue;
      errors.push((Math.abs(p.close - actual) / actual) * 100);
    }
  }
  if (!errors.length) return null;
  const maePct = errors.reduce((a, b) => a + b, 0) / errors.length;
  return {
    samples: errors.length,
    maePct,
    mapeHint: `MAE ${maePct.toFixed(2)}% · n=${errors.length}`,
  };
}

export function CandlestickChart({
  candles,
  forecast = [],
  forecastHistory = [],
  showHistory = true,
  height = 420,
  showVolume = true,
  visibleBars,
  onVisibleBarsChange,
}: {
  candles: Candle[];
  forecast?: ForecastPoint[];
  forecastHistory?: ForecastHistoryEntry[];
  showHistory?: boolean;
  height?: number;
  showVolume?: boolean;
  visibleBars?: number;
  onVisibleBarsChange?: (n: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(960);
  const [offsetFromEnd, setOffsetFromEnd] = useState(0);
  const [hover, setHover] = useState<{
    i: number;
    kind: "candle" | "forecast";
  } | null>(null);
  const dragRef = useRef<{ x: number; offset: number } | null>(null);

  const internalVisible = visibleBars ?? DEFAULT_VISIBLE;
  const setVisible = useCallback(
    (n: number) => {
      const clamped = Math.max(
        MIN_VISIBLE,
        Math.min(n, Math.max(candles.length, MIN_VISIBLE)),
      );
      onVisibleBarsChange?.(clamped);
    },
    [candles.length, onVisibleBarsChange],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    ro.observe(el);
    setWidth(el.clientWidth || 960);
    return () => ro.disconnect();
  }, []);

  const windowSize = Math.min(
    Math.max(MIN_VISIBLE, internalVisible),
    Math.max(candles.length, 1),
  );
  const maxOffset = Math.max(0, candles.length - windowSize);
  const end = candles.length - Math.min(offsetFromEnd, maxOffset);
  const start = Math.max(0, end - windowSize);
  const view = candles.slice(start, end);

  const mint = "var(--mint, #3DDC97)";
  const coral = "var(--coral, #FF5C5C)";
  const gold = "var(--gold, #D4A54A)";
  const historyStroke = "var(--muted, #8B949E)";
  const grid = "var(--border, #1F2530)";
  const muted = "var(--muted, #8B949E)";
  const fg = "var(--foreground, #E8ECF1)";

  const pad = useMemo(
    () => ({ top: 16, right: 12, bottom: showVolume ? 72 : 28, left: 52 }),
    [showVolume],
  );
  const volH = showVolume ? 48 : 0;
  const chartH = height - pad.top - pad.bottom;
  const chartW = Math.max(40, width - pad.left - pad.right);

  const accuracy = useMemo(
    () => forecastAccuracy(forecastHistory, candles),
    [forecastHistory, candles],
  );

  if (!candles.length) {
    return (
      <div
        ref={containerRef}
        style={{
          height,
          display: "grid",
          placeItems: "center",
          color: muted,
          fontFamily: "var(--kronos-font-mono, monospace)",
          fontSize: 12,
        }}
      >
        No candle data
      </div>
    );
  }

  const liveGeneratedAt = forecast.length
    ? forecastHistory.find((h) => h.points === forecast)?.generatedAt
    : undefined;
  // Prefer matching by last history entry equaling current live points length/time
  const currentGenerated =
    forecastHistory.length > 0
      ? forecastHistory[forecastHistory.length - 1]?.generatedAt
      : undefined;

  const historyToDraw = showHistory
    ? forecastHistory
        .filter((h) => h.generatedAt !== currentGenerated || end < candles.length)
        .slice(-HISTORY_DRAW_LIMIT)
    : [];

  // When at live edge, still draw older history (exclude newest = live)
  const histEntries =
    end === candles.length
      ? historyToDraw.filter((h) => h.generatedAt !== currentGenerated)
      : historyToDraw;

  void liveGeneratedAt;

  const histPrices = histEntries.flatMap((h) => h.points.map((p) => p.close));

  const allCloses = [
    ...view.flatMap((c) => [c.high, c.low]),
    ...(end === candles.length
      ? forecast.flatMap((f) => [
          f.high,
          f.low,
          f.closeHigh ?? f.close,
          f.closeLow ?? f.close,
        ])
      : []),
    ...histPrices,
  ];
  const minP = Math.min(...allCloses);
  const maxP = Math.max(...allCloses);
  const pricePad = (maxP - minP) * 0.05 || 1;
  const yMin = minP - pricePad;
  const yMax = maxP + pricePad;

  const showForecast = end === candles.length && forecast.length > 0;
  const totalSlots = view.length + (showForecast ? forecast.length : 0);
  const slot = chartW / Math.max(totalSlots, 1);
  const bodyW = Math.max(1.5, slot * 0.62);

  const y = (price: number) =>
    pad.top + ((yMax - price) / (yMax - yMin || 1)) * chartH;
  const xCandle = (i: number) => pad.left + i * slot + slot / 2;
  const candleTimes = view.map((c) => tsMs(c.timestamp));

  const maxVol = Math.max(...view.map((c) => c.volume), 1);
  const lastIdx = view.length - 1;

  const historyPaths = histEntries.map((entry, hi) => {
    const coords: { x: number; y: number }[] = [];
    for (const p of entry.points) {
      const x = xForTime(tsMs(p.timestamp), candleTimes, xCandle);
      if (x == null) continue;
      coords.push({ x, y: y(p.close) });
    }
    if (coords.length < 2) return null;
    const d = coords
      .map((c, i) => `${i === 0 ? "M" : "L"} ${c.x} ${c.y}`)
      .join(" ");
    const age = histEntries.length <= 1 ? 1 : hi / (histEntries.length - 1);
    const opacity = 0.25 + age * 0.35;
    return { id: entry.id, d, opacity, generatedAt: entry.generatedAt };
  });

  const forecastPath = showForecast
    ? forecast
        .map((f, i) => {
          const x = xCandle(view.length + i);
          const yy = y(f.close);
          return `${i === 0 ? "M" : "L"} ${x} ${yy}`;
        })
        .join(" ")
    : "";

  const bandPath = (() => {
    if (
      !showForecast ||
      !forecast.some((f) => f.closeHigh != null && f.closeLow != null)
    ) {
      return null;
    }
    const top = forecast
      .map((f, i) => {
        const x = xCandle(view.length + i);
        return `${i === 0 ? "M" : "L"} ${x} ${y(f.closeHigh ?? f.close)}`;
      })
      .join(" ");
    const bottom = [...forecast]
      .reverse()
      .map((f, i) => {
        const idx = forecast.length - 1 - i;
        const x = xCandle(view.length + idx);
        return `L ${x} ${y(f.closeLow ?? f.close)}`;
      })
      .join(" ");
    return `${top} ${bottom} Z`;
  })();

  const joinLine =
    showForecast && view.length
      ? `M ${xCandle(lastIdx)} ${y(view[lastIdx].close)} L ${xCandle(view.length)} ${y(forecast[0].close)}`
      : "";

  const ticks = 4;
  const priceTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const p = yMin + ((yMax - yMin) * i) / ticks;
    return { p, yy: y(p) };
  });

  const onWheel = (e: ReactWheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.12 : 0.88;
    const next = Math.round(windowSize * factor);
    setVisible(next);
    if (e.deltaY > 0) {
      setOffsetFromEnd((o) => Math.min(o, Math.max(0, candles.length - next)));
    }
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { x: e.clientX, offset: offsetFromEnd };
  };
  const onPointerMove = (e: ReactPointerEvent) => {
    if (!dragRef.current) {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const idx = Math.floor((x - pad.left) / slot);
      if (idx >= 0 && idx < view.length) {
        setHover({ i: idx, kind: "candle" });
      } else if (
        showForecast &&
        idx >= view.length &&
        idx < view.length + forecast.length
      ) {
        setHover({ i: idx - view.length, kind: "forecast" });
      } else {
        setHover(null);
      }
      return;
    }
    const dx = e.clientX - dragRef.current.x;
    const bars = Math.round(-dx / Math.max(slot, 1));
    const next = Math.max(
      0,
      Math.min(maxOffset, dragRef.current.offset + bars),
    );
    setOffsetFromEnd(next);
  };
  const onPointerUp = () => {
    dragRef.current = null;
  };

  const hoverCandle =
    hover?.kind === "candle" ? view[hover.i] : undefined;
  const hoverForecast =
    hover?.kind === "forecast" ? forecast[hover.i] : undefined;
  const crossX =
    hover == null
      ? null
      : hover.kind === "candle"
        ? xCandle(hover.i)
        : xCandle(view.length + hover.i);

  return (
    <div
      ref={containerRef}
      style={{
        position: "relative",
        width: "100%",
        height,
        touchAction: "none",
        cursor: dragRef.current ? "grabbing" : "crosshair",
        userSelect: "none",
      }}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={() => {
        dragRef.current = null;
        setHover(null);
      }}
    >
      {(hoverCandle || hoverForecast) && (
        <div
          style={{
            position: "absolute",
            top: 8,
            left: 56,
            right: 12,
            zIndex: 2,
            pointerEvents: "none",
            fontSize: 11,
            fontFamily: "var(--kronos-font-mono, monospace)",
            color: fg,
            background:
              "color-mix(in srgb, var(--panel, #12161f) 88%, transparent)",
            border: `1px solid ${grid}`,
            borderRadius: 6,
            padding: "6px 8px",
            display: "flex",
            flexWrap: "wrap",
            gap: "6px 12px",
          }}
        >
          {hoverCandle && (
            <>
              <span style={{ color: muted }}>
                {new Date(hoverCandle.timestamp).toLocaleString()}
              </span>
              <span>O {hoverCandle.open.toFixed(2)}</span>
              <span>H {hoverCandle.high.toFixed(2)}</span>
              <span>L {hoverCandle.low.toFixed(2)}</span>
              <span>C {hoverCandle.close.toFixed(2)}</span>
              <span style={{ color: muted }}>
                V {Math.round(hoverCandle.volume).toLocaleString()}
              </span>
            </>
          )}
          {hoverForecast && (
            <>
              <span style={{ color: gold }}>Live forecast</span>
              <span style={{ color: muted }}>
                {new Date(hoverForecast.timestamp).toLocaleString()}
              </span>
              <span>C {hoverForecast.close.toFixed(2)}</span>
              {hoverForecast.closeLow != null &&
                hoverForecast.closeHigh != null && (
                  <span style={{ color: muted }}>
                    band {hoverForecast.closeLow.toFixed(2)}–
                    {hoverForecast.closeHigh.toFixed(2)}
                  </span>
                )}
            </>
          )}
        </div>
      )}

      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Candlestick chart with Kronos forecast history"
        style={{ display: "block" }}
      >
        {priceTicks.map((t) => (
          <g key={t.p}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={t.yy}
              y2={t.yy}
              stroke={grid}
              strokeWidth={1}
            />
            <text
              x={pad.left - 8}
              y={t.yy + 3}
              textAnchor="end"
              fill={muted}
              fontSize={10}
              fontFamily="var(--kronos-font-mono, monospace)"
            >
              {t.p.toFixed(2)}
            </text>
          </g>
        ))}

        {historyPaths.map(
          (hp) =>
            hp && (
              <path
                key={hp.id}
                d={hp.d}
                fill="none"
                stroke={historyStroke}
                strokeWidth={1.25}
                strokeDasharray="3 4"
                opacity={hp.opacity}
              />
            ),
        )}

        {bandPath && <path d={bandPath} fill={gold} opacity={0.12} />}

        {view.map((c, i) => {
          const cx = xCandle(i);
          const up = c.close >= c.open;
          const color = up ? mint : coral;
          const yO = y(c.open);
          const yC = y(c.close);
          const yH = y(c.high);
          const yL = y(c.low);
          const top = Math.min(yO, yC);
          const body = Math.max(1, Math.abs(yC - yO));
          return (
            <g key={`${c.timestamp}-${start + i}`}>
              <line
                x1={cx}
                x2={cx}
                y1={yH}
                y2={yL}
                stroke={color}
                strokeWidth={1}
              />
              <rect
                x={cx - bodyW / 2}
                y={top}
                width={bodyW}
                height={body}
                fill={color}
              />
              {start + i === candles.length - 1 && (
                <circle cx={cx} cy={yC} r={4} fill={gold}>
                  <animate
                    attributeName="opacity"
                    values="1;0.35;1"
                    dur="1.4s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
              {showVolume && (
                <rect
                  x={cx - bodyW / 2}
                  y={
                    height -
                    pad.bottom +
                    8 +
                    (volH - (c.volume / maxVol) * volH)
                  }
                  width={bodyW}
                  height={(c.volume / maxVol) * volH}
                  fill={color}
                  opacity={0.35}
                />
              )}
            </g>
          );
        })}

        {joinLine && (
          <path
            d={joinLine}
            fill="none"
            stroke={gold}
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        )}
        {forecastPath && (
          <path
            d={forecastPath}
            fill="none"
            stroke={gold}
            strokeWidth={1.75}
            strokeDasharray="5 4"
          />
        )}

        {crossX != null && (
          <line
            x1={crossX}
            x2={crossX}
            y1={pad.top}
            y2={height - pad.bottom + (showVolume ? volH + 8 : 0)}
            stroke={muted}
            strokeWidth={1}
            strokeDasharray="3 3"
            opacity={0.6}
          />
        )}
      </svg>

      <div
        style={{
          position: "absolute",
          bottom: 4,
          right: 8,
          fontSize: 10,
          fontFamily: "var(--kronos-font-mono, monospace)",
          color: muted,
          pointerEvents: "none",
          display: "flex",
          gap: 10,
        }}
      >
        <span>
          {start + 1}–{end} / {candles.length}
          {showForecast ? ` · +${forecast.length} live fc` : ""}
          {showHistory && histEntries.length
            ? ` · ${histEntries.length} past fc`
            : ""}
        </span>
        {accuracy && <span style={{ color: gold }}>{accuracy.mapeHint}</span>}
      </div>
    </div>
  );
}
