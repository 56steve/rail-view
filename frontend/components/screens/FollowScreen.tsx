"use client";

import { useRef } from "react";
import { ArrowLeft, ArrowUp, Layers, Navigation } from "lucide-react";
import { useMobileInset } from "@/hooks/useLayout";
import { formatClock, formatEta, formatSpeed, trainTypeLabel } from "@/lib/format";
import { navigate, navigateBack } from "@/lib/navigation";
import { doorLabel, livePlatform, platformLabel } from "@/lib/platform";
import { useRailView } from "@/lib/store";
import { DelayText, IconButton } from "../ui/primitives";

export function FollowScreen({ trainId }: { trainId: string }) {
  const train = useRailView((s) => s.trainPairs[trainId]?.to ?? null);
  const view2D = useRailView((s) => s.view2D);
  const showBuildings = useRailView((s) => s.showBuildings);
  const topRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useMobileInset("top", topRef);
  useMobileInset("bottom", bottomRef);

  if (!train) {
    return (
      <div className="flex flex-col gap-3 px-4 pt-safe md:px-0 md:pt-0">
        <IconButton label="Back" onClick={navigateBack}>
          <ArrowLeft className="h-5 w-5" />
        </IconButton>
        <div className="glass pointer-events-auto rounded-2xl px-4 py-3 text-[14px] text-fg-muted">
          This train isn&apos;t reporting right now.
        </div>
      </div>
    );
  }

  const stale = train.status === "stale";
  const openDetails = () => navigate({ name: "train", trainId });
  const etaAtNext =
    train.next_station && train.eta_seconds !== null ? train.last_updated_epoch + train.eta_seconds : null;
  const platform = livePlatform(train.next_platform, train.next_platform_certain, train.next_platform_door);

  return (
    <>
      <div ref={topRef} className="flex items-center gap-2.5 px-4 pt-safe md:px-0 md:pt-0">
        <IconButton label="Back" onClick={navigateBack}>
          <ArrowLeft className="h-5 w-5" />
        </IconButton>
        <button
          type="button"
          onClick={openDetails}
          className="glass pointer-events-auto flex min-w-0 flex-1 items-center gap-3 rounded-2xl px-4 py-2.5 text-left shadow-float"
        >
          <span
            className={`h-2.5 w-2.5 shrink-0 rounded-full ${stale ? "bg-warning" : "bg-success shadow-[0_0_10px_rgb(61_214_140/0.8)]"}`}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[15px] font-semibold text-fg">{trainTypeLabel(train)}</span>
            <span className="block truncate text-[12px] text-fg-muted">{train.direction_label}</span>
          </span>
          {stale ? (
            <span className="text-[13px] font-medium text-warning">Signal lost</span>
          ) : (
            <DelayText seconds={train.delay_seconds} className="shrink-0 text-[13.5px] font-medium" />
          )}
        </button>
      </div>

      <div className="absolute left-4 top-1/2 flex -translate-y-1/2 flex-col gap-2.5 md:left-0">
        <IconButton
          label="Recenter on train"
          onClick={() => useRailView.getState().requestCamera({ kind: "recenter-follow" })}
        >
          <Navigation className="h-[18px] w-[18px]" />
        </IconButton>
        <IconButton
          label={view2D ? "Switch to 3D view" : "Switch to 2D view"}
          active={view2D}
          onClick={() => useRailView.getState().setView2D(!view2D)}
        >
          <span className="text-[13px] font-semibold">{view2D ? "3D" : "2D"}</span>
        </IconButton>
        <IconButton
          label={showBuildings ? "Hide buildings" : "Show buildings"}
          active={!showBuildings}
          onClick={() => useRailView.getState().setShowBuildings(!showBuildings)}
        >
          <Layers className="h-[18px] w-[18px]" />
        </IconButton>
      </div>

      <div ref={bottomRef} className="mt-auto flex flex-col gap-3">
        {train.next_station && (
          <div className="px-4 md:px-0">
            <div className="glass pointer-events-auto inline-flex items-center gap-3 rounded-2xl py-2.5 pl-3 pr-4 shadow-float">
              <ArrowUp className="h-6 w-6 text-fg" strokeWidth={2.4} />
              <span className="leading-tight">
                <span className="block text-[11px] text-fg-muted">Next</span>
                <span className="block text-[15px] font-semibold text-fg">{train.next_station.name}</span>
                <span className="block text-[12px] text-fg-muted">
                  {train.eta_seconds !== null && train.eta_seconds < 45 ? "arriving" : `in ${formatEta(train.eta_seconds)}`}
                </span>
                {platform && (
                  <span className="block text-[12px] text-fg-muted">
                    {[platformLabel(platform), doorLabel(platform.door)].filter(Boolean).join(" · ")}
                  </span>
                )}
              </span>
            </div>
          </div>
        )}

        <button
          type="button"
          onClick={openDetails}
          className="glass pointer-events-auto pb-safe w-full rounded-t-3xl px-5 pt-3 text-left shadow-float md:rounded-3xl md:pb-4"
        >
          <span className="mx-auto mb-3 block h-1 w-10 rounded-full bg-white/25" />
          <span className="grid grid-cols-3 divide-x divide-white/10">
            <Stat value={formatSpeed(train.speed_kmh)} unit="km/h" label="Current speed" />
            <Stat value={formatEta(train.eta_seconds)} label="To next station" />
            <Stat
              value={etaAtNext !== null ? formatClock(etaAtNext) : "—"}
              label={train.next_station ? `ETA at ${train.next_station.name}` : "Arrived"}
            />
          </span>
        </button>
      </div>
    </>
  );
}

function Stat({ value, unit, label }: { value: string; unit?: string; label: string }) {
  return (
    <span className="flex flex-col items-center gap-1 px-2 text-center">
      <span className="text-[20px] font-semibold tabular-nums text-fg">
        {value}
        {unit && <span className="ml-1 text-[12px] font-medium text-fg-muted">{unit}</span>}
      </span>
      <span className="truncate text-[11.5px] text-fg-muted">{label}</span>
    </span>
  );
}
