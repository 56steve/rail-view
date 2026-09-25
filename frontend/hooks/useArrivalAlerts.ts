"use client";

import { useEffect } from "react";
import { trainIdentity, trainTypeLabel } from "@/lib/format";
import { doorLabel, livePlatform, platformLabel } from "@/lib/platform";
import { useRailView } from "@/lib/store";

// A train that never reaches the alert station (e.g. it terminated and
// formed a working in the other direction) shouldn't leave a dangling alert.
const ALERT_MAX_AGE_MS = 2 * 60 * 60 * 1000;

function notify(title: string, body: string): void {
  if (typeof Notification !== "undefined" && Notification.permission === "granted") {
    try {
      new Notification(title, { body });
    } catch {
      // Some mobile browsers only allow notifications via a service
      // worker; the in-app toast still fires.
    }
  }
}

/** Fires arrival alerts as live snapshots arrive: once the alerted train
 * is within its lead time of the alert station (or already there). */
export function useArrivalAlerts(): void {
  useEffect(
    () =>
      useRailView.subscribe((state, previous) => {
        if (state.trainPairs === previous.trainPairs || state.alerts.length === 0) return;
        const now = Date.now();
        for (const alert of state.alerts) {
          if (now - alert.createdAtMs > ALERT_MAX_AGE_MS) {
            state.removeAlert(alert.id);
            continue;
          }
          const train = state.trainPairs[alert.trainId]?.to;
          if (!train || train.status !== "live") continue;

          const atStation = train.current_station?.code === alert.stationCode;
          const approaching =
            train.next_station?.code === alert.stationCode &&
            train.eta_seconds !== null &&
            train.eta_seconds <= alert.leadSeconds;
          if (!atStation && !approaching) continue;

          state.removeAlert(alert.id);
          // The live platform is the next stop's, so it only belongs on an
          // approaching alert, and only when certain.
          const platform = livePlatform(train.next_platform, train.next_platform_certain, train.next_platform_door);
          const platformPart = platform?.certain
            ? [platformLabel(platform), doorLabel(platform.door)].filter(Boolean).join(" · ")
            : null;
          const arriving = `Arriving at ${alert.stationName} in ${Math.max(1, Math.round((train.eta_seconds ?? 0) / 60))} min`;
          const title = atStation
            ? `${trainTypeLabel(train)} at ${alert.stationName}`
            : platformPart
              ? `${arriving} · ${platformPart}`
              : arriving;
          const body = `${train.direction_label} · ${trainIdentity(train)}`;
          state.pushToast({ title, body, tone: "success" });
          notify(title, body);
        }
      }),
    [],
  );
}
