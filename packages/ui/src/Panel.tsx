import type { ReactNode } from "react";

export function Panel({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section
      style={{
        background: "var(--kronos-panel)",
        border: "1px solid var(--kronos-border)",
        borderRadius: 8,
        padding: 16,
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: "var(--kronos-font-display)",
            fontSize: 14,
            fontWeight: 600,
            color: "var(--kronos-text)",
          }}
        >
          {title}
        </h2>
        {action}
      </header>
      <div style={{ minHeight: 0, flex: 1 }}>{children}</div>
    </section>
  );
}
