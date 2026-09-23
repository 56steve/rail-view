"use client";

import { ChevronRight } from "lucide-react";
import { formatNextStop, trainIdentity, trainTypeLabel } from "@/lib/format";
import { navigate } from "@/lib/navigation";
import type { TrainPositionUpdate } from "@/lib/types";
import { DelayText, LineSwatch } from "./primitives";

export function TrainRow({ train, color }: { train: TrainPositionUpdate; color: string }) {
  const stale = train.status === "stale";
  return (
    <button
      type="button"
      onClick={() => navigate({ name: "train", trainId: train.train_id })}
      className="flex w-full items-center gap-3 rounded-2xl border hairline bg-ink-800 px-4 py-3 text-left transition hover:bg-ink-750"
    >
      <LineSwatch color={color} className="h-9 w-1 rounded-full" />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-2">
          <span className="text-[14.5px] font-semibold text-fg">{trainTypeLabel(train)}</span>
          <span className="text-[11.5px] text-fg-subtle">{trainIdentity(train)}</span>
        </span>
        <span className="block truncate text-[13px] text-fg-muted">{train.direction_label}</span>
        <span className="mt-0.5 block truncate text-[12px] text-fg-subtle">
          {train.current_station
            ? `At ${train.current_station.name}`
            : train.next_station
              ? formatNextStop(train.next_station.name, train.eta_seconds)
              : "Terminating"}
        </span>
      </span>
      {stale ? (
        <span className="text-[12.5px] font-medium text-warning">Signal lost</span>
      ) : (
        <DelayText seconds={train.delay_seconds} className="shrink-0 text-[12.5px] font-medium" />
      )}
      <ChevronRight className="h-4 w-4 shrink-0 text-fg-subtle" />
    </button>
  );
}
