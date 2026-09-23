"use client";

import { useMemo, useRef, useState } from "react";
import { MapPin, Route, Search, TrainFront, X } from "lucide-react";
import { trainIdentity, trainTypeLabel } from "@/lib/format";
import { latLonToScene } from "@/lib/geo";
import { navigate } from "@/lib/navigation";
import { useRailView } from "@/lib/store";
import type { StationIndexEntry, TrainPositionUpdate } from "@/lib/types";

const MAX_STATIONS = 6;
const MAX_TRAINS = 4;

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const stations = useRailView((s) => s.stations);
  const trainPairs = useRailView((s) => s.trainPairs);
  const lines = useRailView((s) => s.lines);

  const q = query.trim().toLowerCase();
  const stationResults = useMemo(
    () => (q ? stations.filter((s) => s.name.toLowerCase().includes(q)).slice(0, MAX_STATIONS) : []),
    [q, stations],
  );
  const trainResults = useMemo(() => {
    if (!q) return [];
    return Object.values(trainPairs)
      .map((p) => p.to)
      .filter((t) => t.train_id.toLowerCase().includes(q) || t.direction_label.toLowerCase().includes(q))
      .slice(0, MAX_TRAINS);
  }, [q, trainPairs]);

  const close = () => {
    setOpen(false);
    inputRef.current?.blur();
  };

  const pickStation = (station: StationIndexEntry) => {
    const p = latLonToScene(station.lat, station.lon);
    const state = useRailView.getState();
    state.focusStation(station.id);
    state.requestCamera({ kind: "focus-point", x: p.x, z: p.z, distance: 3200 });
    setQuery(station.name);
    close();
  };

  const pickTrain = (train: TrainPositionUpdate) => {
    setQuery("");
    close();
    navigate({ name: "follow", trainId: train.train_id });
  };

  const clear = () => {
    setQuery("");
    useRailView.getState().focusStation(null);
  };

  return (
    <div className="pointer-events-auto relative min-w-0 flex-1">
      <div className="glass flex h-11 items-center gap-2.5 rounded-2xl px-3.5 shadow-float">
        <Search className="h-[18px] w-[18px] shrink-0 text-fg-subtle" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "Escape") close();
            if (e.key === "Enter" && stationResults[0]) pickStation(stationResults[0]);
          }}
          placeholder="Search station or train..."
          aria-label="Search station or train"
          className="min-w-0 flex-1 bg-transparent text-[14px] text-fg outline-none placeholder:text-fg-subtle"
        />
        {query && (
          <button type="button" aria-label="Clear search" onClick={clear} className="text-fg-subtle hover:text-fg">
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {open && (
        <div className="glass animate-rise absolute inset-x-0 top-13 z-20 overflow-hidden rounded-2xl py-1.5 shadow-float">
          {!q && (
            <ResultRow
              icon={<Route className="h-4 w-4 text-primary" />}
              title="Plan a journey"
              subtitle="Find trains between two stations"
              onPick={() => {
                close();
                navigate({ name: "journey", fromId: null, toId: null });
              }}
            />
          )}
          {stationResults.map((station) => (
            <ResultRow
              key={station.id}
              icon={<MapPin className="h-4 w-4 text-fg-muted" />}
              title={station.name}
              subtitle={station.lines.map((code) => lines[code]?.name ?? code).join(" · ")}
              onPick={() => pickStation(station)}
            />
          ))}
          {trainResults.map((train) => (
            <ResultRow
              key={train.train_id}
              icon={<TrainFront className="h-4 w-4 text-fg-muted" />}
              title={`${trainTypeLabel(train)} · ${trainIdentity(train)}`}
              subtitle={train.direction_label}
              onPick={() => pickTrain(train)}
            />
          ))}
          {q && stationResults.length === 0 && trainResults.length === 0 && (
            <p className="px-4 py-3 text-[13px] text-fg-subtle">No stations or trains match “{query.trim()}”.</p>
          )}
        </div>
      )}
    </div>
  );
}

function ResultRow({
  icon,
  title,
  subtitle,
  onPick,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
      className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition hover:bg-white/5"
    >
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink-700">{icon}</span>
      <span className="min-w-0">
        <span className="block truncate text-[14px] font-medium text-fg">{title}</span>
        <span className="block truncate text-[12px] text-fg-subtle">{subtitle}</span>
      </span>
    </button>
  );
}
