"use client";

import { delayTone, formatDelay, formatEta, formatLastUpdated, formatSpeed } from "@/lib/format";
import { useRailPulseStore } from "@/lib/store";

const TONE_CLASSES: Record<ReturnType<typeof delayTone>, string> = {
  "on-time": "text-emerald-400",
  late: "text-amber-400",
  early: "text-sky-400",
};

export function TrainInfoPanel() {
  const selectedTrainId = useRailPulseStore((state) => state.selectedTrainId);
  const pair = useRailPulseStore((state) =>
    state.selectedTrainId ? state.trainPairs[state.selectedTrainId] : undefined,
  );
  const followSelected = useRailPulseStore((state) => state.followSelected);
  const setFollowSelected = useRailPulseStore((state) => state.setFollowSelected);
  const selectTrain = useRailPulseStore((state) => state.selectTrain);

  if (!selectedTrainId || !pair) return null;
  const train = pair.to;
  const isStale = train.status === "stale";

  return (
    <div className="pointer-events-auto flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-white/10 bg-[#12151bcc] p-5 backdrop-blur-xl">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-widest text-teal-300">
            {train.train_type === "FAST" ? "Fast Local" : "Slow Local"}
          </div>
          <div className="mt-1 text-lg font-semibold text-white">{train.direction_label}</div>
        </div>
        <button
          type="button"
          onClick={() => selectTrain(null)}
          aria-label="Close"
          className="rounded-full p-1 text-white/40 transition hover:bg-white/10 hover:text-white"
        >
          &times;
        </button>
      </div>

      {isStale && (
        <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-xs text-amber-300">
          Signal lost &mdash; showing last known position as of {formatLastUpdated(train.last_updated_iso)}.
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Speed" value={formatSpeed(train.speed_kmh)} />
        <Stat label="ETA" value={formatEta(train.eta_seconds)} />
        <Stat label="Current" value={train.current_station?.name ?? "Between stations"} />
        <Stat label="Next" value={train.next_station?.name ?? train.destination.name} />
      </div>

      <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
        <span className={`text-sm font-medium ${TONE_CLASSES[delayTone(train.delay_seconds)]}`}>
          {formatDelay(train.delay_seconds)}
        </span>
        <span className="text-xs text-white/40">Updated {formatLastUpdated(train.last_updated_iso)}</span>
      </div>

      <button
        type="button"
        onClick={() => setFollowSelected(!followSelected)}
        className={`rounded-xl border px-3 py-2.5 text-sm font-medium transition ${
          followSelected
            ? "border-teal-400/50 bg-teal-400/15 text-teal-200"
            : "border-white/10 bg-white/5 text-white/70 hover:border-white/20 hover:text-white"
        }`}
      >
        {followSelected ? "Following this train" : "Follow this train"}
      </button>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2.5">
      <div className="text-[10px] font-medium uppercase tracking-wide text-white/40">{label}</div>
      <div className="mt-0.5 truncate text-sm font-semibold text-white">{value}</div>
    </div>
  );
}
