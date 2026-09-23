"use client";

import { useRef, useState } from "react";
import { BarChart3, CalendarDays, LocateFixed, Route } from "lucide-react";
import { useMobileInset } from "@/hooks/useLayout";
import { useServiceDay } from "@/hooks/useServiceDay";
import { latLonToScene } from "@/lib/geo";
import { navigate } from "@/lib/navigation";
import { useRailView } from "@/lib/store";
import { LineChips } from "../ui/LineChips";
import { IconButton } from "../ui/primitives";
import { SearchBar } from "../ui/SearchBar";
import { ConnectionBanner } from "../ui/Toasts";

// Mumbai region the network covers; a location outside it isn't useful
// to fly to.
const MUMBAI_BOUNDS = { south: 18.85, north: 19.35, west: 72.7, east: 73.2 };

export function ExploreScreen() {
  const topRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useMobileInset("top", topRef);
  useMobileInset("bottom", bottomRef);

  return (
    <>
      <div ref={topRef} className="flex flex-col gap-3 px-4 pt-safe md:px-0 md:pt-0">
        <div className="flex items-center gap-2.5">
          <SearchBar />
          <LocateButton />
        </div>
        <LineChips />
        <ConnectionBanner />
      </div>

      <div ref={bottomRef} className="mt-auto flex flex-col gap-3">
        <div className="flex justify-end px-4 md:px-0">
          <button
            type="button"
            onClick={() => navigate({ name: "journey", fromId: null, toId: null })}
            className="glass pointer-events-auto flex items-center gap-2 rounded-full py-2.5 pl-3.5 pr-4 text-[13.5px] font-semibold text-fg shadow-float transition hover:bg-ink-700 active:scale-95"
          >
            <Route className="h-4 w-4 text-primary" />
            Plan journey
          </button>
        </div>
        <NetworkStats />
      </div>
    </>
  );
}

function LocateButton() {
  const [locating, setLocating] = useState(false);

  const locate = () => {
    const state = useRailView.getState();
    if (!("geolocation" in navigator)) {
      state.requestCamera({ kind: "frame-network", lineCode: state.lineFilter });
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        const inMumbai =
          coords.latitude > MUMBAI_BOUNDS.south &&
          coords.latitude < MUMBAI_BOUNDS.north &&
          coords.longitude > MUMBAI_BOUNDS.west &&
          coords.longitude < MUMBAI_BOUNDS.east;
        if (inMumbai) {
          const p = latLonToScene(coords.latitude, coords.longitude);
          state.requestCamera({ kind: "focus-point", x: p.x, z: p.z, distance: 3500 });
        } else {
          state.pushToast({
            title: "You're outside Mumbai",
            body: "Showing the whole network instead",
            tone: "info",
          });
          state.requestCamera({ kind: "frame-network", lineCode: state.lineFilter });
        }
      },
      () => {
        setLocating(false);
        state.requestCamera({ kind: "frame-network", lineCode: state.lineFilter });
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 },
    );
  };

  return (
    <IconButton label="Show my location" onClick={locate}>
      <LocateFixed className={`h-5 w-5 ${locating ? "animate-soft-pulse text-primary" : ""}`} />
    </IconButton>
  );
}

function NetworkStats() {
  const trains = useRailView((s) => s.trainPairs);
  const lineFilter = useRailView((s) => s.lineFilter);
  const live = Object.values(trains)
    .map((p) => p.to)
    .filter((t) => t.status === "live" && (lineFilter === null || t.line_code === lineFilter));
  const onTime = live.filter((t) => Math.abs(t.delay_seconds) < 60).length;
  const onTimePct = live.length ? Math.round((onTime / live.length) * 100) : null;

  return (
    <div className="flex flex-col gap-2.5 px-4 md:px-0">
      <ServiceDayNotice />
      <div className="grid grid-cols-2 gap-2.5">
        <div className="glass pointer-events-auto rounded-2xl px-4 py-3 shadow-float">
          <p className="text-[12.5px] text-fg-muted">Live trains</p>
          <p className="mt-1 flex items-center gap-2 text-[22px] font-semibold tabular-nums text-fg">
            <span className="h-2 w-2 rounded-full bg-success shadow-[0_0_10px_rgb(61_214_140/0.8)]" />
            {live.length}
          </p>
        </div>
        <div className="glass pointer-events-auto rounded-2xl px-4 py-3 shadow-float">
          <p className="text-[12.5px] text-fg-muted" title="Share of live trains within 1 minute of their timetable">
            On-time
          </p>
          <p className="mt-1 flex items-center gap-2 text-[22px] font-semibold tabular-nums text-fg">
            <BarChart3 className="h-4 w-4 text-success" />
            {onTimePct === null ? "—" : `${onTimePct}%`}
          </p>
        </div>
      </div>
    </div>
  );
}

/** Tells commuters why there are fewer trains than usual: on Sundays and
 * the listed holidays the network runs its Sunday timetable. */
function ServiceDayNotice() {
  const serviceDay = useServiceDay();
  if (!serviceDay?.sunday_schedule) return null;
  return (
    <div className="glass pointer-events-auto flex items-center gap-2 self-start rounded-full px-3.5 py-2 text-[12.5px] shadow-float">
      <CalendarDays className="h-3.5 w-3.5 text-primary" />
      <span className="font-medium text-fg">Sunday timetable</span>
      {serviceDay.holiday_name && <span className="text-fg-muted">· {serviceDay.holiday_name}</span>}
    </div>
  );
}
