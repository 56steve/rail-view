"use client";

import { useMemo, useState } from "react";
import { formatDelay, formatEta, formatSpeed } from "@/lib/format";
import { useRailPulseStore } from "@/lib/store";
import type { StationOut, TrainPositionUpdate } from "@/lib/types";

export function JourneyPanel() {
  const route = useRailPulseStore((state) => state.route);
  const trainPairs = useRailPulseStore((state) => state.trainPairs);
  const selectTrain = useRailPulseStore((state) => state.selectTrain);
  const [fromCode, setFromCode] = useState("");
  const [toCode, setToCode] = useState("");

  const stations = route?.stations ?? [];
  const fromStation = stations.find((s) => s.code === fromCode) ?? null;
  const toStation = stations.find((s) => s.code === toCode) ?? null;

  const matches = useMemo<TrainPositionUpdate[]>(() => {
    if (!fromStation || !toStation || fromStation.code === toStation.code) return [];
    const directionForward = fromStation.sequence < toStation.sequence;
    const distanceToFrom = (t: TrainPositionUpdate) => Math.abs(t.chainage_m - fromStation.chainage_m);

    return Object.values(trainPairs)
      .map((pair) => pair.to)
      .filter((t) => t.direction_forward === directionForward)
      .sort((a, b) => distanceToFrom(a) - distanceToFrom(b))
      .slice(0, 6);
  }, [trainPairs, fromStation, toStation]);

  if (!route) return null;

  return (
    <div className="pointer-events-auto flex w-full max-w-sm flex-col gap-3 rounded-2xl border border-white/10 bg-[#12151bcc] p-4 backdrop-blur-xl">
      <div className="text-xs font-medium uppercase tracking-wide text-white/45">Plan a journey</div>

      <div className="flex items-center gap-2">
        <StationSelect
          stations={stations}
          value={fromCode}
          onChange={setFromCode}
          placeholder="From"
          exclude={toCode}
        />
        <span className="text-white/30">&rarr;</span>
        <StationSelect
          stations={stations}
          value={toCode}
          onChange={setToCode}
          placeholder="To"
          exclude={fromCode}
        />
      </div>

      {fromStation && toStation && (
        <div className="flex flex-col gap-2">
          {matches.length === 0 && (
            <p className="text-sm text-white/40">No trains heading that way right now.</p>
          )}
          {matches.map((train) => (
            <button
              key={train.train_id}
              type="button"
              onClick={() => selectTrain(train.train_id)}
              className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-left transition hover:border-teal-400/40 hover:bg-white/10"
            >
              <div>
                <div className="text-sm font-semibold text-white">
                  {train.train_type === "FAST" ? "Fast Local" : "Slow Local"}
                </div>
                <div className="text-xs text-white/50">
                  {formatSpeed(train.speed_kmh)} &middot; {formatDelay(train.delay_seconds)}
                </div>
              </div>
              <div className="text-xs font-medium text-teal-300">{formatEta(train.eta_seconds)}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function StationSelect({
  stations,
  value,
  onChange,
  placeholder,
  exclude,
}: {
  stations: StationOut[];
  value: string;
  onChange: (code: string) => void;
  placeholder: string;
  exclude: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="flex-1 rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-sm text-white outline-none focus:border-teal-400/50"
    >
      <option value="">{placeholder}</option>
      {stations
        .filter((s) => s.code !== exclude)
        .map((s) => (
          <option key={s.code} value={s.code} className="bg-[#12151b]">
            {s.name}
          </option>
        ))}
    </select>
  );
}
