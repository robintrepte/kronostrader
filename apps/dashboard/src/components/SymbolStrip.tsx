"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Candle } from "@kronos/shared-types";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type Suggestion = { symbol: string; name: string };

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
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [loadingSuggest, setLoadingSuggest] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [openList, setOpenList] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  useEffect(() => {
    if (!adding) return;
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
        setHighlight(0);
        setOpenList(true);
      } catch {
        if (!cancelled) {
          // Local fallback when trader is old / search unavailable
          const popular: Suggestion[] = [
            { symbol: "AAPL", name: "Apple Inc." },
            { symbol: "MSFT", name: "Microsoft Corporation" },
            { symbol: "NVDA", name: "NVIDIA Corporation" },
            { symbol: "AMZN", name: "Amazon.com Inc." },
            { symbol: "GOOGL", name: "Alphabet Inc." },
            { symbol: "META", name: "Meta Platforms Inc." },
            { symbol: "TSLA", name: "Tesla Inc." },
            { symbol: "AMD", name: "Advanced Micro Devices" },
            { symbol: "SPY", name: "SPDR S&P 500 ETF" },
            { symbol: "QQQ", name: "Invesco QQQ Trust" },
          ].filter(
            (s) =>
              !symbols.includes(s.symbol) &&
              (!q ||
                s.symbol.includes(q.toUpperCase()) ||
                s.name.toUpperCase().includes(q.toUpperCase())),
          );
          setSuggestions(popular);
          setOpenList(true);
        }
      } finally {
        if (!cancelled) setLoadingSuggest(false);
      }
    }, q ? 180 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [adding, draft, symbols]);

  const pick = async (ticker: string) => {
    const sym = ticker.trim().toUpperCase();
    if (!sym) return;
    if (symbols.includes(sym)) {
      setError(`${sym} is already watched`);
      onSelect(sym);
      setAdding(false);
      setDraft("");
      setOpenList(false);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onChangeSymbols([...symbols, sym]);
      onSelect(sym);
      setAdding(false);
      setDraft("");
      setOpenList(false);
      setSuggestions([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add symbol");
    } finally {
      setBusy(false);
    }
  };

  const commitAdd = async () => {
    const fromList = suggestions[highlight]?.symbol;
    const ticker = (fromList && openList ? fromList : draft).trim().toUpperCase();
    if (!ticker) {
      setAdding(false);
      setDraft("");
      setOpenList(false);
      return;
    }
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(ticker)) {
      setError("Pick a suggestion or enter a valid ticker");
      return;
    }
    await pick(ticker);
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

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setAdding(false);
      setDraft("");
      setError(null);
      setOpenList(false);
      return;
    }
    if (!openList || !suggestions.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      void commitAdd();
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="-mx-1 flex items-stretch gap-2 overflow-x-auto px-1 pb-1">
        {symbols.map((s) => {
          const isActive = s === active;
          const c = candles[s];
          const px = c?.[c.length - 1]?.close;
          return (
            <div
              key={s}
              className="group relative mono shrink-0 rounded-md border text-left transition"
              style={{
                borderColor: isActive ? "var(--gold)" : "var(--border)",
                background: isActive
                  ? "color-mix(in srgb, var(--gold) 12%, var(--panel))"
                  : "var(--panel)",
                color: "var(--foreground)",
                minWidth: 96,
              }}
            >
              <button
                type="button"
                onClick={() => onSelect(s)}
                disabled={busy}
                className="w-full px-3 py-2.5 pr-8 text-left sm:py-2"
              >
                <div className="text-[10px] text-[var(--muted)] sm:text-xs">
                  {s}
                </div>
                <div className="text-sm">
                  {px != null ? px.toFixed(2) : "—"}
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

        {adding ? (
          <div
            className="relative z-20 mono shrink-0 rounded-md border border-[var(--gold)] bg-[var(--panel)] p-2 shadow-lg"
            style={{ minWidth: "min(100%, 280px)", width: 280 }}
          >
            <form
              className="flex items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                void commitAdd();
              }}
            >
              <input
                ref={inputRef}
                role="combobox"
                aria-expanded={openList}
                aria-controls={listId}
                aria-autocomplete="list"
                aria-activedescendant={
                  suggestions[highlight]
                    ? `${listId}-${suggestions[highlight].symbol}`
                    : undefined
                }
                className="desk-input !min-h-9 flex-1 uppercase"
                value={draft}
                disabled={busy}
                placeholder="Search ticker or name…"
                maxLength={32}
                onChange={(e) => {
                  setDraft(
                    e.target.value.toUpperCase().replace(/[^A-Z0-9.\- ]/g, ""),
                  );
                  setOpenList(true);
                }}
                onKeyDown={onKeyDown}
                onFocus={() => setOpenList(true)}
                autoComplete="off"
              />
              <button
                type="button"
                className="desk-btn !min-h-9 !px-2"
                disabled={busy}
                onClick={() => {
                  setAdding(false);
                  setDraft("");
                  setError(null);
                  setOpenList(false);
                }}
              >
                Esc
              </button>
            </form>

            {openList && (
              <ul
                id={listId}
                role="listbox"
                className="mt-2 max-h-56 overflow-y-auto rounded border border-[var(--border)] bg-[var(--input)]"
              >
                {loadingSuggest && !suggestions.length && (
                  <li className="px-3 py-2 text-[11px] text-[var(--muted)]">
                    Searching…
                  </li>
                )}
                {!loadingSuggest && !suggestions.length && (
                  <li className="px-3 py-2 text-[11px] text-[var(--muted)]">
                    No matches — try another query
                  </li>
                )}
                {suggestions.map((s, i) => (
                  <li key={s.symbol} role="option" aria-selected={i === highlight}>
                    <button
                      type="button"
                      id={`${listId}-${s.symbol}`}
                      disabled={busy}
                      className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left transition"
                      style={{
                        background:
                          i === highlight
                            ? "color-mix(in srgb, var(--gold) 16%, transparent)"
                            : "transparent",
                      }}
                      onMouseEnter={() => setHighlight(i)}
                      onClick={() => void pick(s.symbol)}
                    >
                      <span className="text-sm text-[var(--foreground)]">
                        {s.symbol}
                      </span>
                      <span className="line-clamp-1 text-[10px] text-[var(--muted)]">
                        {s.name}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-1.5 text-[10px] text-[var(--muted)]">
              ↑↓ to move · Enter to add · Esc to close
            </p>
          </div>
        ) : (
          <Hint label="Search and add a ticker">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setAdding(true);
                setError(null);
                setDraft("");
              }}
              className="mono flex min-h-[58px] min-w-[96px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-md border border-dashed border-[var(--border)] bg-[var(--panel)] px-3 py-2 text-[var(--muted)] transition hover:border-[var(--gold)] hover:text-[var(--foreground)]"
            >
              <span className="text-lg leading-none">+</span>
              <span className="text-[10px] uppercase tracking-wide">Add</span>
            </button>
          </Hint>
        )}
      </div>
      {error && (
        <p className="mono px-1 text-[11px] text-[var(--coral)]">{error}</p>
      )}
    </div>
  );
}
