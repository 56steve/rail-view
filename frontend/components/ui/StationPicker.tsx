"use client";

import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { useRailView } from "@/lib/store";
import type { StationIndexEntry } from "@/lib/types";

export function StationPicker({
  title,
  excludeId,
  onPick,
  onClose,
}: {
  title: string;
  excludeId: string | null;
  onPick: (station: StationIndexEntry) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const stations = useRailView((s) => s.stations);
  const lines = useRailView((s) => s.lines);
  const q = query.trim().toLowerCase();
  const results = useMemo(
    () => stations.filter((s) => s.id !== excludeId && (!q || s.name.toLowerCase().includes(q))),
    [stations, excludeId, q],
  );

  return (
    <div className="pointer-events-auto fixed inset-0 z-40 flex items-end justify-center bg-black/55 md:items-center" onClick={onClose}>
      <div
        role="dialog"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="animate-rise pb-safe flex max-h-[85vh] w-full flex-col overflow-hidden rounded-t-3xl border hairline bg-ink-850 md:max-w-md md:rounded-3xl"
      >
        <div className="flex items-center justify-between px-5 pb-3 pt-4">
          <p className="text-[16px] font-semibold text-fg">{title}</p>
          <button type="button" aria-label="Close" onClick={onClose} className="rounded-full p-2 text-fg-subtle hover:bg-white/5">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="mx-4 mb-2 flex h-11 items-center gap-2.5 rounded-xl bg-ink-700 px-3.5">
          <Search className="h-4 w-4 text-fg-subtle" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && results[0] && onPick(results[0])}
            placeholder="Station name"
            aria-label="Station name"
            className="min-w-0 flex-1 bg-transparent text-[14.5px] text-fg outline-none placeholder:text-fg-subtle"
          />
        </div>
        <ul className="flex-1 overflow-y-auto px-2 pb-3">
          {results.map((station) => (
            <li key={station.id}>
              <button
                type="button"
                onClick={() => onPick(station)}
                className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-white/5"
              >
                <span className="text-[14.5px] text-fg">{station.name}</span>
                <span className="flex gap-1">
                  {station.lines.map((code) => (
                    <span
                      key={code}
                      title={lines[code]?.name}
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: lines[code]?.color_hex }}
                    />
                  ))}
                </span>
              </button>
            </li>
          ))}
          {results.length === 0 && <li className="px-3 py-4 text-[13.5px] text-fg-subtle">No station matches.</li>}
        </ul>
      </div>
    </div>
  );
}
