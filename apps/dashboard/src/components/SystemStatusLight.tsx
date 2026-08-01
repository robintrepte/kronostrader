"use client";

import type { ReactNode } from "react";
import type { SystemStatus } from "@kronos/shared-types";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const LEVEL_COLOR = {
  ok: "var(--mint)",
  degraded: "var(--gold)",
  error: "var(--coral)",
} as const;

export function SystemStatusLight({
  wsConnected,
}: {
  wsConnected: boolean;
}) {
  const { status, fetchError } = useSystemStatus(5000);

  const level: SystemStatus["level"] = !wsConnected
    ? "error"
    : fetchError
      ? "error"
      : status?.level ?? "degraded";
  const color = LEVEL_COLOR[level];
  const label =
    level === "ok" ? "OK" : level === "degraded" ? "WARN" : "ERR";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--panel)] px-2.5 py-1.5"
          aria-label={`System status: ${label}`}
        >
          <span
            className="relative inline-flex size-2.5 shrink-0 rounded-full"
            style={{
              background: color,
              boxShadow: `0 0 0 0 ${color}`,
              animation:
                level === "ok"
                  ? "kronos-status-pulse 1.8s ease-out infinite"
                  : level === "degraded"
                    ? "kronos-status-pulse 1.1s ease-out infinite"
                    : "none",
            }}
          />
          <span className="mono text-[11px] tracking-wide" style={{ color }}>
            {label}
          </span>
          <style>{`
            @keyframes kronos-status-pulse {
              0% { box-shadow: 0 0 0 0 color-mix(in srgb, ${color} 55%, transparent); }
              70% { box-shadow: 0 0 0 8px transparent; }
              100% { box-shadow: 0 0 0 0 transparent; }
            }
          `}</style>
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        align="end"
        className="max-w-[min(92vw,360px)] space-y-2 p-3 text-left"
      >
        <StatusTooltipBody
          wsConnected={wsConnected}
          status={status}
          fetchError={fetchError}
          level={level}
        />
      </TooltipContent>
    </Tooltip>
  );
}

function StatusTooltipBody({
  wsConnected,
  status,
  fetchError,
  level,
}: {
  wsConnected: boolean;
  status: SystemStatus | null;
  fetchError: string | null;
  level: SystemStatus["level"];
}) {
  const hw = status?.inference.hardware;
  const issues = [
    ...(wsConnected ? [] : ["WebSocket disconnected from trader"]),
    ...(fetchError ? [`Status API: ${fetchError}`] : []),
    ...(status?.issues ?? []),
  ];

  return (
    <div className="mono space-y-2 text-[11px] leading-relaxed">
      <div className="flex items-center justify-between gap-3">
        <span className="font-semibold uppercase tracking-wide">{level}</span>
        <span className="text-[var(--muted)]">
          {status?.checkedAt
            ? new Date(status.checkedAt).toLocaleTimeString()
            : "—"}
        </span>
      </div>
      <p>
        {status?.summary ??
          (fetchError ? "Cannot reach trader status API" : "Loading status…")}
      </p>

      <Section title="Market data">
        {status ? (
          <>
            <Row
              k="Source"
              v={
                status.marketData.mock
                  ? "Mock"
                  : `Alpaca ${status.marketData.feed.toUpperCase()}`
              }
            />
            <Row
              k="Keys"
              v={status.marketData.keysConfigured ? "configured" : "MISSING"}
            />
            <Row k="Healthy" v={status.marketData.ok ? "yes" : "no"} />
            {status.marketData.session?.equity?.watched !== false && (
              <Row
                k="Equity"
                v={
                  status.marketData.session?.equity?.isOpen ??
                  status.marketData.session?.isOpen
                    ? `OPEN · closes ${
                        (
                          status.marketData.session?.equity?.nextClose ||
                          status.marketData.session?.nextClose
                        )
                          ? new Date(
                              String(
                                status.marketData.session?.equity?.nextClose ||
                                  status.marketData.session?.nextClose,
                              ),
                            ).toLocaleString()
                          : "—"
                      }`
                    : `CLOSED · opens ${
                        (
                          status.marketData.session?.equity?.nextOpen ||
                          status.marketData.session?.nextOpen
                        )
                          ? new Date(
                              String(
                                status.marketData.session?.equity?.nextOpen ||
                                  status.marketData.session?.nextOpen,
                              ),
                            ).toLocaleString()
                          : "—"
                      }`
                }
              />
            )}
            {(status.marketData.session?.crypto?.watched ||
              status.trader.hasCrypto) && (
              <Row k="Crypto" v="OPEN · 24/7" />
            )}
            {Object.keys(status.marketData.errorsBySymbol).length > 0 && (
              <Row
                k="Errors"
                v={Object.entries(status.marketData.errorsBySymbol)
                  .map(([s, e]) => `${s}: ${e}`)
                  .join(" · ")}
              />
            )}
          </>
        ) : (
          <Row k="State" v="unknown" />
        )}
      </Section>

      <Section title="Inference / Kronos">
        {status ? (
          <>
            <Row k="Reachable" v={status.inference.reachable ? "yes" : "NO"} />
            <Row k="Model" v={status.inference.model ?? "—"} />
            <Row k="Loaded" v={status.inference.loaded ? "yes" : "NO"} />
            <Row k="Device" v={status.inference.device ?? "—"} />
            {hw && (
              <>
                <Row
                  k="CPU"
                  v={
                    hw.cpuPercent != null
                      ? `${hw.cpuPercent.toFixed(0)}%` +
                        (hw.cpuCount ? ` · ${hw.cpuCount} cores` : "")
                      : "—"
                  }
                />
                <Row
                  k="RAM"
                  v={
                    hw.ramUsedGb != null && hw.ramTotalGb != null
                      ? `${hw.ramUsedGb}/${hw.ramTotalGb} GB`
                      : "—"
                  }
                />
                <Row
                  k="Model RSS"
                  v={
                    hw.processRssGb != null
                      ? `${hw.processRssGb.toFixed(2)} GB`
                      : "—"
                  }
                />
                <Row
                  k="CUDA"
                  v={
                    hw.cudaAvailable
                      ? `${hw.cudaDeviceName ?? "GPU"} · alloc ${hw.cudaMemoryAllocatedGb ?? "?"} GB`
                      : "not available (CPU)"
                  }
                />
              </>
            )}
            {status.inference.error && (
              <Row k="Error" v={status.inference.error} />
            )}
          </>
        ) : (
          <Row k="State" v="unknown" />
        )}
      </Section>

      <Section title="Trader">
        {status ? (
          <>
            <Row
              k="Mode"
              v={[
                status.trader.live ? "LIVE" : "PAPER",
                status.trader.dryRun ? "DRY RUN" : "ORDERS ON",
              ].join(" · ")}
            />
            <Row k="Symbols" v={status.trader.symbols.join(", ")} />
            <Row k="WS" v={wsConnected ? "connected" : "DOWN"} />
          </>
        ) : (
          <Row k="WS" v={wsConnected ? "connected" : "DOWN"} />
        )}
      </Section>

      {issues.length > 0 && (
        <Section title="Issues">
          <ul className="list-disc space-y-1 pl-4 text-[var(--coral)]">
            {issues.slice(0, 6).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="border-t border-[var(--border)] pt-2">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-[var(--muted)]">
        {title}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-2">
      <span className="text-[var(--muted)]">{k}</span>
      <span className="break-words">{v}</span>
    </div>
  );
}
