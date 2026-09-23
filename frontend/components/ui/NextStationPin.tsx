"use client";

import { useCallback, useEffect, useState } from "react";
import { formatDistance } from "@/lib/format";
import { trainPose } from "@/lib/motion";
import { moveAnchor, registerAnchor, unregisterAnchor } from "@/lib/overlay";
import { useRailView } from "@/lib/store";

const ANCHOR_ID = "next-station-pin";

/** A pin standing on the followed train's next station, with the live
 * distance to it along the track. */
export function NextStationPin({ trainId }: { trainId: string }) {
  const next = useRailView((s) => s.trainPairs[trainId]?.to.next_station ?? null);
  const routeCode = useRailView((s) => s.trainPairs[trainId]?.to.route_code ?? null);
  const track = useRailView((s) => (routeCode ? s.tracks[routeCode] : undefined));
  const [distance, setDistance] = useState<number | null>(null);

  const anchor = useCallback((element: HTMLDivElement | null) => {
    if (element) registerAnchor(ANCHOR_ID, { element, x: 0, y: 4, z: 0, maxDistance: 60_000 });
    else unregisterAnchor(ANCHOR_ID);
  }, []);

  useEffect(() => {
    if (!next || !track) return;
    const p = track.sample(next.chainage_m);
    moveAnchor(ANCHOR_ID, p.x, 4, p.z);
  }, [next, track]);

  useEffect(() => {
    if (!next) return;
    const update = () => {
      const pair = useRailView.getState().trainPairs[trainId];
      if (pair) setDistance(Math.abs(next.chainage_m - trainPose(pair, performance.now()).chainage));
    };
    update();
    const timer = setInterval(update, 500);
    return () => clearInterval(timer);
  }, [next, trainId]);

  if (!next) return null;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      <div ref={anchor} className="absolute left-0 top-0 will-change-transform" style={{ visibility: "hidden" }}>
        <span className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-primary" />
        <span className="absolute bottom-1 h-10 w-px -translate-x-1/2 bg-gradient-to-t from-white/80 to-white/10 day:from-ink-900/80 day:to-ink-900/10" />
        <div className="glass absolute bottom-11 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full py-1.5 pl-2 pr-3.5 shadow-float">
          <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-white">
            <span className="h-1.5 w-1.5 rounded-full bg-white" />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="text-[14px] font-semibold text-fg">{next.name}</span>
            {distance !== null && <span className="text-[11px] text-fg-muted">{formatDistance(distance)}</span>}
          </span>
        </div>
      </div>
    </div>
  );
}
