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
import type { Candle, ForecastPoint } from "@kronos/shared-types";

const DEFAULT_VISIBLE = 120;
const MIN_VISIBLE = 20;

export function CandlestickChart({
  candles,
  forecast = [],
  height = 420,
  showVolume = true,
  visibleBars,
  onVisibleBarsChange,
}: {
  candles: Candle[];
  forecast?: ForecastPoint[];
  height?: number;
  showVolume?: boolean;
  /** Number of candles in the visible window (controlled). */
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

  const maxVol = Math.max(...view.map((c) => c.volume), 1);
  const lastIdx = view.length - 1;

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
    if (!showForecast || !forecast.some((f) => f.closeHigh != null && f.closeLow != null)) {
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
      // zooming out — keep right edge pinned when at live edge
      setOffsetFromEnd((o) => Math.min(o, Math.max(0, candles.length - next)));
    }
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { x: e.clientX, offset: offsetFromEnd };
  };
  const onPointerMove = (e: ReactPointerEvent) => {
    if (!dragRef.current) {
      // hover crosshair
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
            background: "color-mix(in srgb, var(--panel, #12161f) 88%, transparent)",
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
              <span style={{ color: gold }}>Forecast</span>
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
        aria-label="Candlestick chart with Kronos forecast"
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

        {bandPath && <path d={bandPath} fill={`${gold}`} opacity={0.12} />}

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
        }}
      >
        {start + 1}–{end} / {candles.length}
        {showForecast ? ` · +${forecast.length} fc` : ""}
        {" · scroll zoom · drag pan"}
      </div>
    </div>
  );
}
