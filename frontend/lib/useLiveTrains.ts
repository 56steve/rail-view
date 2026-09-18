"use client";

import { useEffect, useRef } from "react";
import { useRailPulseStore } from "./store";
import type { SnapshotMessage } from "./types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/live";
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;

/**
 * Owns the single WebSocket connection to `/ws/live`. On disconnect it
 * backs off and retries rather than giving up, and it never clears
 * `trainPairs` on disconnect - the store keeps the last known snapshot so
 * the UI can mark trains stale (see components/ui/ConnectionBadge.tsx)
 * instead of making them disappear or inventing new positions.
 */
export function useLiveTrains(): void {
  const applySnapshot = useRailPulseStore((state) => state.applySnapshot);
  const setConnectionStatus = useRailPulseStore((state) => state.setConnectionStatus);
  const attemptRef = useRef(0);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    function connect(): void {
      setConnectionStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");
      socket = new WebSocket(WS_URL);

      socket.onopen = () => {
        attemptRef.current = 0;
        setConnectionStatus("live");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          const message = JSON.parse(event.data) as SnapshotMessage;
          if (message.type === "snapshot") {
            applySnapshot(message.trains);
          }
        } catch {
          // Malformed frame: skip it. The next valid snapshot re-syncs
          // state, so one bad frame shouldn't tear down the connection.
        }
      };

      socket.onclose = () => {
        if (cancelled) return;
        setConnectionStatus("reconnecting");
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS);
        attemptRef.current += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [applySnapshot, setConnectionStatus]);
}
