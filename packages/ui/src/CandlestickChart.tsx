"use client";

import type { Candle, ForecastPoint } from "@kronos/shared-types";

const MINT = "#3DDC97";
const CORAL = "#FF5C5C";
const GOLD = "#D4A54A";
const GRID = "#1F2530";
const MUTED = "#8B949E";

export function CandlestickChart({
  candles,
  forecast = [],
  height = 420,
  showVolume = true,
}: {
  candles: Candle[];
  forecast?: ForecastPoint[];
  height?: number;
  showVolume?: boolean;
}) {
  if (!candles.length) {
    return (
      <div
        style={{
          height,
          display: "grid",
          placeItems: "center",
          color: MUTED,
          fontFamily: "var(--kronos-font-mono)",
          fontSize: 12,
        }}
      >
        No candle data
      </div>
    );
  }

  const width = 960;
  const pad = { top: 16, right: 16, bottom: showVolume ? 72 : 28, left: 56 };
  const volH = showVolume ? 48 : 0;
  const chartH = height - pad.top - pad.bottom;
  const chartW = width - pad.left - pad.right;

  const allCloses = [
    ...candles.flatMap((c) => [c.high, c.low]),
    ...forecast.flatMap((f) => [
      f.high,
      f.low,
      f.closeHigh ?? f.close,
      f.closeLow ?? f.close,
    ]),
  ];
  const minP = Math.min(...allCloses);
  const maxP = Math.max(...allCloses);
  const pricePad = (maxP - minP) * 0.05 || 1;
  const yMin = minP - pricePad;
  const yMax = maxP + pricePad;

  const totalSlots = candles.length + forecast.length;
  const slot = chartW / Math.max(totalSlots, 1);
  const bodyW = Math.max(2, slot * 0.6);

  const y = (price: number) =>
    pad.top + ((yMax - price) / (yMax - yMin || 1)) * chartH;
  const xCandle = (i: number) => pad.left + i * slot + slot / 2;

  const maxVol = Math.max(...candles.map((c) => c.volume), 1);
  const lastIdx = candles.length - 1;

  const forecastPath = forecast
    .map((f, i) => {
      const x = xCandle(candles.length + i);
      const yy = y(f.close);
      return `${i === 0 ? "M" : "L"} ${x} ${yy}`;
    })
    .join(" ");

  const bandPath = (() => {
    if (!forecast.some((f) => f.closeHigh != null && f.closeLow != null)) {
      return null;
    }
    const top = forecast
      .map((f, i) => {
        const x = xCandle(candles.length + i);
        return `${i === 0 ? "M" : "L"} ${x} ${y(f.closeHigh ?? f.close)}`;
      })
      .join(" ");
    const bottom = [...forecast]
      .reverse()
      .map((f, i) => {
        const idx = forecast.length - 1 - i;
        const x = xCandle(candles.length + idx);
        return `L ${x} ${y(f.closeLow ?? f.close)}`;
      })
      .join(" ");
    return `${top} ${bottom} Z`;
  })();

  const joinLine =
    forecast.length > 0
      ? `M ${xCandle(lastIdx)} ${y(candles[lastIdx].close)} L ${xCandle(candles.length)} ${y(forecast[0].close)}`
      : "";

  const ticks = 4;
  const priceTicks = Array.from({ length: ticks + 1 }, (_, i) => {
    const p = yMin + ((yMax - yMin) * i) / ticks;
    return { p, yy: y(p) };
  });

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
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
            stroke={GRID}
            strokeWidth={1}
          />
          <text
            x={pad.left - 8}
            y={t.yy + 3}
            textAnchor="end"
            fill={MUTED}
            fontSize={10}
            fontFamily="var(--kronos-font-mono)"
          >
            {t.p.toFixed(2)}
          </text>
        </g>
      ))}

      {bandPath && (
        <path d={bandPath} fill={`${GOLD}22`} stroke="none" />
      )}

      {candles.map((c, i) => {
        const cx = xCandle(i);
        const up = c.close >= c.open;
        const color = up ? MINT : CORAL;
        const yO = y(c.open);
        const yC = y(c.close);
        const yH = y(c.high);
        const yL = y(c.low);
        const top = Math.min(yO, yC);
        const body = Math.max(1, Math.abs(yC - yO));
        return (
          <g key={`${c.timestamp}-${i}`}>
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
            {i === lastIdx && (
              <circle cx={cx} cy={yC} r={4} fill={GOLD}>
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
                y={height - pad.bottom + 8 + (volH - (c.volume / maxVol) * volH)}
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
          stroke={GOLD}
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
      )}
      {forecastPath && (
        <path
          d={forecastPath}
          fill="none"
          stroke={GOLD}
          strokeWidth={1.75}
          strokeDasharray="5 4"
        />
      )}
    </svg>
  );
}
