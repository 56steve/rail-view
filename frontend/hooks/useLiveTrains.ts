"use client";

import { useEffect } from "react";
import { WS_URL } from "@/lib/api";
import { useRailView } from "@/lib/store";
import type { SnapshotMessage } from "@/lib/types";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;

/**
 * Owns the single WebSocket connection to `/ws/live`, reconnecting with
 * backoff. It never clears known trains on disconnect: the last snapshot
 * stays on screen and the UI flags it (connection banner, stale trains)
 * rather than making trains vanish or inventing positions.
 */
export function useLiveTrains(): void {
  const applySnapshot = useRailView((s) => s.applySnapshot);
  const setConnectionStatus = useRailView((s) => s.setConnectionStatus);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let cancelled = false;

    const connect = () => {
      setConnectionStatus(attempt === 0 ? "connecting" : "reconnecting");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => {
        attempt = 0;
        setConnectionStatus("live");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const message = JSON.parse(event.data) as SnapshotMessage;
          if (message.type === "snapshot") applySnapshot(message.trains);
        } catch {
          // Malformed frame: skip it; the next snapshot re-syncs state.
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnectionStatus("reconnecting");
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => socket?.close();
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [applySnapshot, setConnectionStatus]);
}
