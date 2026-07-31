"use client";

import { useEffect, useRef, useState } from "react";
import type { WsEvent } from "@kronos/shared-types";

export function useTraderSocket(
  url: string,
  onEvent: (event: WsEvent) => void,
) {
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      ws = new WebSocket(url);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data as string) as WsEvent;
          onEventRef.current(data);
        } catch {
          // ignore malformed
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [url]);

  return { connected };
}
