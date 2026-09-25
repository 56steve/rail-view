"use client";

import { useEffect } from "react";
import { WS_URL } from "@/lib/api";
import { canInflate, decodeSnapshot, inflateMessage } from "@/lib/liveWire";
import { useRailView } from "@/lib/store";

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
// Hidden this long (another tab, another app, phone locked), the feed is
// dropped: every open copy of the app costs the host ~5 KB a second, and
// nobody is watching. Short enough that switching apps briefly doesn't.
const HIDDEN_PAUSE_MS = 15000;

/** The feed's URL: the lean format, compressed where the browser can
 * inflate it (see backend/app/api/ws.py). */
function liveUrl(): string {
  const url = new URL(WS_URL);
  url.searchParams.set("v", "2");
  if (canInflate()) url.searchParams.set("encoding", "deflate");
  return url.toString();
}

/**
 * Owns the single WebSocket connection to `/ws/live`, reconnecting with
 * backoff, and closing it while the app is in the background. It never
 * clears known trains on disconnect: the last snapshot stays on screen
 * and the UI flags it (connection banner, stale trains) rather than
 * making trains vanish or inventing positions.
 */
export function useLiveTrains(): void {
  const applySnapshot = useRailView((s) => s.applySnapshot);
  const setConnectionStatus = useRailView((s) => s.setConnectionStatus);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pauseTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;
    let stopped = false; // unmounted, or paused in the background

    const connect = () => {
      setConnectionStatus(attempt === 0 ? "connecting" : "reconnecting");
      const ws = new WebSocket(liveUrl());
      ws.binaryType = "arraybuffer";
      socket = ws;
      // Frames inflate asynchronously; chaining keeps them in order.
      let pending: Promise<void> = Promise.resolve();

      ws.onopen = () => {
        attempt = 0;
        setConnectionStatus("live");
      };

      ws.onmessage = (event: MessageEvent<string | ArrayBuffer>) => {
        pending = pending.then(async () => {
          try {
            const snapshot = decodeSnapshot(JSON.parse(await inflateMessage(event.data)));
            if (snapshot && socket === ws) applySnapshot(snapshot);
          } catch (error) {
            // Malformed frame: skip it; the next full snapshot re-syncs state.
            console.warn(error);
          }
        });
      };

      ws.onclose = () => {
        if (stopped || socket !== ws) return;
        setConnectionStatus("reconnecting");
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    };

    const disconnect = () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      const ws = socket;
      socket = null;
      ws?.close();
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        pauseTimer ??= setTimeout(() => {
          pauseTimer = null;
          stopped = true;
          disconnect();
          setConnectionStatus("paused");
        }, HIDDEN_PAUSE_MS);
        return;
      }
      if (pauseTimer) clearTimeout(pauseTimer);
      pauseTimer = null;
      if (stopped) {
        stopped = false;
        attempt = 0;
        connect();
      }
    };

    connect();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stopped = true;
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (pauseTimer) clearTimeout(pauseTimer);
      disconnect();
    };
  }, [applySnapshot, setConnectionStatus]);
}
