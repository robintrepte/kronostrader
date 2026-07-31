"use client";

import { useEffect, useState } from "react";
import type { SystemStatus } from "@kronos/shared-types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export function useSystemStatus(pollMs = 5000) {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/status`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as SystemStatus;
        if (cancelled) return;
        setStatus(data);
        setFetchError(null);
      } catch (err) {
        if (cancelled) return;
        setFetchError(err instanceof Error ? err.message : "status fetch failed");
      }
    };
    load();
    const id = window.setInterval(load, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  return { status, fetchError };
}
