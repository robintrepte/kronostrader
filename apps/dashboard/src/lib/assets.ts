import type { AssetClass } from "@kronos/shared-types";

/** Alpaca crypto pairs use slash form (BTC/USD). */
export function isCryptoSymbol(symbol: string): boolean {
  return symbol.includes("/");
}

export function assetClassOf(symbol: string): AssetClass {
  return isCryptoSymbol(symbol) ? "crypto" : "us_equity";
}

/** Normalize free-typed tickers; BTCUSD → BTC/USD. */
export function normalizeSymbol(raw: string): string {
  const s = raw.trim().toUpperCase().replace(/\s+/g, "");
  if (!s) return s;
  if (s.includes("/")) {
    const parts = s.split("/").filter(Boolean);
    if (parts.length === 2) return `${parts[0]}/${parts[1]}`;
    return s;
  }
  const quotes = ["USDT", "USDC", "USD", "BTC", "ETH"] as const;
  for (const quote of quotes) {
    if (s.endsWith(quote) && s.length > quote.length + 1) {
      const base = s.slice(0, -quote.length);
      if (/^[A-Z]{2,6}$/.test(base)) return `${base}/${quote}`;
    }
  }
  return s;
}

export function formatPrice(px: number, symbol?: string): string {
  if (!Number.isFinite(px)) return "—";
  if (symbol && isCryptoSymbol(symbol)) {
    if (px >= 1000) return px.toFixed(2);
    if (px >= 1) return px.toFixed(4);
    return px.toFixed(6);
  }
  return px.toFixed(2);
}
