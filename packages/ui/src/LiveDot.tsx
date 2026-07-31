export function LiveDot({ live = true }: { live?: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontFamily: "var(--kronos-font-mono)",
        fontSize: 11,
        color: live ? "var(--kronos-mint)" : "var(--kronos-muted)",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: live ? "var(--kronos-mint)" : "var(--kronos-muted)",
          boxShadow: live ? "0 0 0 0 var(--kronos-mint)" : "none",
          animation: live ? "kronos-pulse 1.6s ease-out infinite" : "none",
        }}
      />
      {live ? "LIVE" : "OFFLINE"}
      <style>{`
        @keyframes kronos-pulse {
          0% { box-shadow: 0 0 0 0 rgba(61, 220, 151, 0.55); }
          70% { box-shadow: 0 0 0 8px rgba(61, 220, 151, 0); }
          100% { box-shadow: 0 0 0 0 rgba(61, 220, 151, 0); }
        }
      `}</style>
    </span>
  );
}
