"use client";

import { useCallback, useMemo } from "react";
import { latLonToScene } from "@/lib/geo";
import { registerAnchor, unregisterAnchor } from "@/lib/overlay";
import { focusedTrainId, useRailView } from "@/lib/store";
import type { StationIndexEntry } from "@/lib/types";

const MAJOR_MAX_DISTANCE_M = 90_000;
const MINOR_MAX_DISTANCE_M = 14_000;
const LABEL_HEIGHT_M = 18;

export function StationLabels() {
  const stations = useRailView((s) => s.stations);
  const routes = useRailView((s) => s.routes);
  const show = useRailView((s) => s.showLabels);
  const lineFilter = useRailView((s) => s.lineFilter);
  const focusedStationId = useRailView((s) => s.focusedStationId);
  // The followed train's next station already has a dedicated pin.
  const pinnedName = useRailView((s) => {
    const id = focusedTrainId(s);
    return id ? (s.trainPairs[id]?.to.next_station?.name ?? null) : null;
  });

  // Terminals, interchanges and fast halts are the landmarks commuters
  // orient by, so they stay labelled at network scale.
  const majorNames = useMemo(() => {
    const names = new Set<string>();
    for (const route of Object.values(routes)) {
      names.add(route.stations[0]!.name);
      names.add(route.stations[route.stations.length - 1]!.name);
      for (const station of route.stations) if (station.fast_halt) names.add(station.name);
    }
    return names;
  }, [routes]);

  return (
    <div className={`pointer-events-none absolute inset-0 overflow-hidden ${show ? "" : "hidden"}`}>
      {stations.filter((station) => station.name !== pinnedName).map((station) => (
        <StationLabel
          key={station.id}
          station={station}
          major={majorNames.has(station.name) || station.lines.length > 1}
          dimmed={lineFilter !== null && !station.lines.includes(lineFilter)}
          focused={focusedStationId === station.id}
        />
      ))}
    </div>
  );
}

function StationLabel({
  station,
  major,
  dimmed,
  focused,
}: {
  station: StationIndexEntry;
  major: boolean;
  dimmed: boolean;
  focused: boolean;
}) {
  const anchor = useCallback(
    (element: HTMLDivElement | null) => {
      if (!element) {
        unregisterAnchor(station.id);
        return;
      }
      const p = latLonToScene(station.lat, station.lon);
      registerAnchor(station.id, {
        element,
        x: p.x,
        y: LABEL_HEIGHT_M,
        z: p.z,
        maxDistance: major || focused ? MAJOR_MAX_DISTANCE_M : MINOR_MAX_DISTANCE_M,
      });
    },
    [station, major, focused],
  );

  return (
    <div
      ref={anchor}
      className={`absolute left-0 top-0 will-change-transform transition-opacity ${dimmed ? "opacity-25" : "opacity-100"}`}
      style={{ visibility: "hidden" }}
    >
      <span
        className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-white ${
          focused ? "h-3.5 w-3.5 border-primary" : major ? "h-2.5 w-2.5 border-ink-950" : "h-2 w-2 border-ink-950"
        }`}
      />
      <span
        className={`absolute left-2.5 -translate-y-1/2 whitespace-nowrap font-medium text-white [text-shadow:0_1px_3px_rgb(0_0_0/0.9),0_0_12px_rgb(0_0_0/0.6)] day:text-ink-900 day:[text-shadow:0_0_2px_rgb(255_255_255),0_0_6px_rgb(255_255_255/0.9),0_0_12px_rgb(255_255_255/0.6)] ${
          focused ? "text-[15px]" : major ? "text-[13px]" : "text-[11.5px] text-white/85 day:text-ink-800"
        }`}
      >
        {station.name}
      </span>
    </div>
  );
}
