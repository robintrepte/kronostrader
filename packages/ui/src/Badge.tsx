import type { ReactNode } from "react";

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "mint" | "coral" | "gold";
}) {
  const colors: Record<string, string> = {
    neutral: "var(--kronos-muted)",
    mint: "var(--kronos-mint)",
    coral: "var(--kronos-coral)",
    gold: "var(--kronos-gold)",
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: "var(--kronos-font-mono)",
        fontSize: 11,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: colors[tone],
        border: `1px solid ${colors[tone]}33`,
        background: `${colors[tone]}14`,
        padding: "2px 8px",
        borderRadius: 4,
      }}
    >
      {children}
    </span>
  );
}
