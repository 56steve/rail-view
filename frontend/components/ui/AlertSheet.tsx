"use client";

import { Bell, X } from "lucide-react";
import { formatClock } from "@/lib/format";
import { useRailView } from "@/lib/store";
import type { StopTime } from "@/lib/types";

const LEAD_SECONDS = 120;

export function AlertSheet({
  trainId,
  stops,
  onClose,
}: {
  trainId: string;
  stops: StopTime[];
  onClose: () => void;
}) {
  const upcoming = stops.filter((s) => s.state === "next" || s.state === "upcoming");

  const choose = async (stop: StopTime) => {
    const state = useRailView.getState();
    state.addAlert({ trainId, stationCode: stop.station.code, stationName: stop.station.name, leadSeconds: LEAD_SECONDS });
    onClose();
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      await Notification.requestPermission();
    }
    state.pushToast({
      title: `Alert set for ${stop.station.name}`,
      body: "We'll let you know 2 minutes before it arrives",
      tone: "info",
    });
  };

  return (
    <div className="pointer-events-auto fixed inset-0 z-40 flex items-end justify-center bg-black/55 md:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-label="Set an arrival alert"
        onClick={(e) => e.stopPropagation()}
        className="animate-rise pb-safe max-h-[75vh] w-full overflow-hidden rounded-t-3xl border hairline bg-ink-850 md:max-w-md md:rounded-3xl"
      >
        <div className="flex items-center justify-between px-5 pb-2 pt-4">
          <div>
            <p className="text-[16px] font-semibold text-fg">Alert me before arriving at</p>
            <p className="text-[12.5px] text-fg-muted">2 minutes ahead, in the app and as a notification</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-full p-2 text-fg-subtle hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>
        <ul className="max-h-[55vh] overflow-y-auto px-2 pb-3">
          {upcoming.map((stop) => (
            <li key={stop.station.code}>
              <button
                type="button"
                onClick={() => void choose(stop)}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-white/5"
              >
                <Bell className="h-4 w-4 text-primary" />
                <span className="flex-1 text-[14.5px] text-fg">{stop.station.name}</span>
                <span className="text-[13px] tabular-nums text-fg-muted">{formatClock(stop.expected_epoch)}</span>
              </button>
            </li>
          ))}
          {upcoming.length === 0 && (
            <li className="px-3 py-4 text-[13.5px] text-fg-subtle">This train has no stops left on this run.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
