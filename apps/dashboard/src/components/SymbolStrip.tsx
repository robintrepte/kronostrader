"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { AssetClass, Candle } from "@kronos/shared-types";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxStatus,
  ComboboxTrigger,
} from "@/components/ui/combobox";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  formatPrice,
  isCryptoSymbol,
  normalizeSymbol,
} from "@/lib/assets";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type Suggestion = { symbol: string; name: string; assetClass?: AssetClass };

const POPULAR: Suggestion[] = [
  { symbol: "BTC/USD", name: "Bitcoin", assetClass: "crypto" },
  { symbol: "ETH/USD", name: "Ethereum", assetClass: "crypto" },
  { symbol: "SOL/USD", name: "Solana", assetClass: "crypto" },
  { symbol: "DOGE/USD", name: "Dogecoin", assetClass: "crypto" },
  { symbol: "LINK/USD", name: "Chainlink", assetClass: "crypto" },
  { symbol: "SPY", name: "SPDR S&P 500 ETF", assetClass: "us_equity" },
  { symbol: "QQQ", name: "Invesco QQQ Trust", assetClass: "us_equity" },
  { symbol: "IWM", name: "iShares Russell 2000 ETF", assetClass: "us_equity" },
  { symbol: "SMH", name: "VanEck Semiconductor ETF", assetClass: "us_equity" },
  { symbol: "NVDA", name: "NVIDIA Corporation", assetClass: "us_equity" },
  { symbol: "TSLA", name: "Tesla Inc.", assetClass: "us_equity" },
  { symbol: "AAPL", name: "Apple Inc.", assetClass: "us_equity" },
  { symbol: "MSFT", name: "Microsoft Corporation", assetClass: "us_equity" },
  { symbol: "AMZN", name: "Amazon.com Inc.", assetClass: "us_equity" },
  { symbol: "META", name: "Meta Platforms Inc.", assetClass: "us_equity" },
  { symbol: "GOOGL", name: "Alphabet Inc.", assetClass: "us_equity" },
  { symbol: "AMD", name: "Advanced Micro Devices", assetClass: "us_equity" },
  { symbol: "AVGO", name: "Broadcom Inc.", assetClass: "us_equity" },
  { symbol: "NFLX", name: "Netflix Inc.", assetClass: "us_equity" },
  { symbol: "PLTR", name: "Palantir Technologies", assetClass: "us_equity" },
  { symbol: "COIN", name: "Coinbase Global", assetClass: "us_equity" },
  { symbol: "JPM", name: "JPMorgan Chase", assetClass: "us_equity" },
  { symbol: "ORCL", name: "Oracle", assetClass: "us_equity" },
];

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

function AssetTag({ assetClass }: { assetClass: AssetClass }) {
  const crypto = assetClass === "crypto";
  return (
    <span
      className="mono text-[9px] uppercase tracking-wider"
      style={{ color: crypto ? "var(--sky)" : "var(--muted)" }}
    >
      {crypto ? "CRYPTO" : "EQ"}
    </span>
  );
}

export function SymbolStrip({
  symbols,
  active,
  candles,
  onSelect,
  onChangeSymbols,
}: {
  symbols: string[];
  active: string;
  candles: Record<string, Candle[]>;
  onSelect: (s: string) => void;
  onChangeSymbols: (next: string[]) => Promise<string[]>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>(POPULAR);
  const [loadingSuggest, setLoadingSuggest] = useState(false);

  useEffect(() => {
    if (!open) return;
    const q = draft.trim();
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setLoadingSuggest(true);
      try {
        const params = new URLSearchParams({
          q,
          limit: "12",
          exclude: symbols.join(","),
        });
        const res = await fetch(`${API_URL}/api/symbols/search?${params}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { results: Suggestion[] };
        if (cancelled) return;
        setSuggestions(data.results ?? []);
      } catch {
        if (!cancelled) {
          setSuggestions(
            POPULAR.filter(
              (s) =>
                !symbols.includes(s.symbol) &&
                (!q ||
                  s.symbol.includes(q.toUpperCase()) ||
                  s.name.toUpperCase().includes(q.toUpperCase())),
            ),
          );
        }
      } finally {
        if (!cancelled) setLoadingSuggest(false);
      }
    }, q ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [open, draft, symbols]);

  const pick = async (ticker: string) => {
    const sym = normalizeSymbol(ticker);
    if (!sym) return;
    if (symbols.includes(sym)) {
      setError(`${sym} is already watched`);
      onSelect(sym);
      setOpen(false);
      setDraft("");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onChangeSymbols([...symbols, sym]);
      onSelect(sym);
      setOpen(false);
      setDraft("");
      setSuggestions(POPULAR);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add symbol");
    } finally {
      setBusy(false);
    }
  };

  const removeSymbol = async (s: string) => {
    if (symbols.length <= 1) {
      setError("Keep at least one symbol");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await onChangeSymbols(symbols.filter((x) => x !== s));
      if (active === s) onSelect(next[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove symbol");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="-mx-1 flex items-stretch gap-2 overflow-x-auto px-1 pb-1">
        {symbols.map((s) => {
          const isActive = s === active;
          const crypto = isCryptoSymbol(s);
          const c = candles[s];
          const px = c?.[c.length - 1]?.close;
          const accent = crypto ? "var(--sky)" : "var(--gold)";
          return (
            <div
              key={s}
              className="group relative mono shrink-0 rounded-md border text-left transition"
              style={{
                borderColor: isActive ? accent : "var(--border)",
                background: isActive
                  ? `color-mix(in srgb, ${accent} 12%, var(--panel))`
                  : "var(--panel)",
                color: "var(--foreground)",
                minWidth: 104,
                boxShadow: crypto
                  ? `inset 3px 0 0 ${isActive ? accent : "color-mix(in srgb, var(--sky) 55%, transparent)"}`
                  : undefined,
              }}
            >
              <button
                type="button"
                onClick={() => onSelect(s)}
                disabled={busy}
                className="w-full px-3 py-2.5 pr-8 text-left sm:py-2"
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-[var(--muted)] sm:text-xs">
                    {s}
                  </span>
                  <AssetTag assetClass={crypto ? "crypto" : "us_equity"} />
                </div>
                <div className="text-sm">
                  {px != null ? formatPrice(px, s) : "—"}
                </div>
              </button>
              <Hint label={`Remove ${s} from watchlist`}>
                <button
                  type="button"
                  aria-label={`Remove ${s}`}
                  disabled={busy || symbols.length <= 1}
                  onClick={(e) => {
                    e.stopPropagation();
                    void removeSymbol(s);
                  }}
                  className="absolute right-1 top-1 flex size-6 items-center justify-center rounded text-[var(--muted)] opacity-70 transition hover:bg-[color-mix(in_srgb,var(--coral)_18%,transparent)] hover:text-[var(--coral)] hover:opacity-100 disabled:opacity-30 sm:opacity-0 sm:group-hover:opacity-100"
                >
                  <span className="text-sm leading-none">×</span>
                </button>
              </Hint>
            </div>
          );
        })}

        <Combobox<Suggestion>
          items={suggestions}
          filteredItems={suggestions}
          filter={null}
          itemToStringValue={(item) => `${item.symbol} ${item.name}`}
          inputValue={draft}
          onInputValueChange={(value) => {
            setDraft(
              String(value)
                .toUpperCase()
                .replace(/[^A-Z0-9.\-\/ ]/g, ""),
            );
          }}
          onValueChange={(item) => {
            if (item?.symbol) void pick(item.symbol);
          }}
          isItemEqualToValue={(a, b) => a.symbol === b.symbol}
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) {
              setDraft("");
              setError(null);
            } else {
              setError(null);
            }
          }}
          autoHighlight
          disabled={busy}
        >
          <Hint label="Search stocks, ETFs, or crypto pairs (e.g. BTC/USD)">
            <ComboboxTrigger
              showIcon={false}
              disabled={busy}
              className="mono flex min-h-[58px] min-w-[96px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-md border border-dashed border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-[var(--muted)] transition hover:border-[var(--gold)] hover:text-[var(--foreground)] disabled:opacity-50"
            >
              <span className="text-lg leading-none">+</span>
              <span className="text-[10px] uppercase tracking-wide">Add</span>
            </ComboboxTrigger>
          </Hint>

          <ComboboxContent side="bottom" align="start" className="mono">
            <ComboboxInput
              placeholder="Search ticker, BTC, or name…"
              disabled={busy}
              autoComplete="off"
              maxLength={32}
            />
            <ComboboxStatus>
              {loadingSuggest
                ? "Searching…"
                : "↑↓ move · Enter add · Esc close · crypto = slash pairs"}
            </ComboboxStatus>
            <ComboboxEmpty>
              {loadingSuggest ? "Searching…" : "No matches — try BTC or BTC/USD"}
            </ComboboxEmpty>
            <ComboboxList>
              {(item: Suggestion) => {
                const cls =
                  item.assetClass ??
                  (isCryptoSymbol(item.symbol) ? "crypto" : "us_equity");
                return (
                  <ComboboxItem key={item.symbol} value={item}>
                    <span className="flex items-center gap-2 pr-6">
                      <span className="text-sm text-[var(--foreground)]">
                        {item.symbol}
                      </span>
                      <AssetTag assetClass={cls} />
                    </span>
                    <span className="line-clamp-1 pr-6 text-[10px] text-[var(--muted)]">
                      {item.name}
                    </span>
                  </ComboboxItem>
                );
              }}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      </div>
      {error && (
        <p className="mono px-1 text-[11px] text-[var(--coral)]">{error}</p>
      )}
    </div>
  );
}
