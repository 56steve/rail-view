"use client";

import { useMemo } from "react";
import { useRailView } from "@/lib/store";
import { LineChips } from "../ui/LineChips";
import { PanelScreen } from "../ui/PanelScreen";
import { EmptyState } from "../ui/primitives";
import { TrainRow } from "../ui/TrainRow";

export function TrainsScreen() {
  const trainPairs = useRailView((s) => s.trainPairs);
  const lineFilter = useRailView((s) => s.lineFilter);
  const lines = useRailView((s) => s.lines);

  const trains = useMemo(
    () =>
      Object.values(trainPairs)
        .map((p) => p.to)
        .filter((t) => lineFilter === null || t.line_code === lineFilter)
        .sort(
          (a, b) =>
            a.line_code.localeCompare(b.line_code) || a.train_id.localeCompare(b.train_id, undefined, { numeric: true }),
        ),
    [trainPairs, lineFilter],
  );

  return (
    <PanelScreen title="Live trains" subtitle={`${trains.length} trains on the network right now`}>
      <LineChips className="-mx-1 px-1" />
      <ul className="mt-4 flex flex-col gap-2">
        {trains.map((train) => (
          <li key={train.train_id}>
            <TrainRow train={train} color={lines[train.line_code]?.color_hex ?? "#888"} />
          </li>
        ))}
      </ul>
      {trains.length === 0 && <EmptyState title="No trains yet" body="Live trains appear here as soon as they report in." />}
    </PanelScreen>
  );
}
