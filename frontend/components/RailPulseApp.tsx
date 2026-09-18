"use client";

import { useEffect } from "react";
import { Scene } from "@/components/three/Scene";
import { ConnectionBadge } from "@/components/ui/ConnectionBadge";
import { JourneyPanel } from "@/components/ui/JourneyPanel";
import { TopBar } from "@/components/ui/TopBar";
import { TrainInfoPanel } from "@/components/ui/TrainInfoPanel";
import { useLiveTrains } from "@/lib/useLiveTrains";
import { useRailPulseStore } from "@/lib/store";
import type { RouteOut } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function RailPulseApp({ initialRoute }: { initialRoute: RouteOut | null }) {
  const route = useRailPulseStore((state) => state.route);
  const setRoute = useRailPulseStore((state) => state.setRoute);
  const selectedTrainId = useRailPulseStore((state) => state.selectedTrainId);
  const viewMode = useRailPulseStore((state) => state.viewMode);

  useLiveTrains();

  useEffect(() => {
    if (initialRoute) {
      setRoute(initialRoute);
    }
  }, [initialRoute, setRoute]);

  // Fallback for when the server-side fetch in app/page.tsx couldn't
  // reach the API (e.g. backend started after the page was built) - the
  // WebSocket will still work once the backend comes up, but the client
  // fetches the static route geometry itself rather than never showing
  // the track at all.
  useEffect(() => {
    if (route) return;
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/routes/CR-thane-dadar`)
      .then((res) => (res.ok ? (res.json() as Promise<RouteOut>) : null))
      .then((data) => {
        if (data && !cancelled) setRoute(data);
      })
      .catch(() => {
        // Backend still unreachable - leave the empty-state screen up.
      });
    return () => {
      cancelled = true;
    };
  }, [route, setRoute]);

  return (
    <div className="fixed inset-0 overflow-hidden bg-[#0a0c10]">
      <div className="absolute inset-0">
        <Scene />
      </div>

      {!route && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="pointer-events-auto flex flex-col items-center gap-3 rounded-2xl border border-white/10 bg-[#12151bcc] px-6 py-5 text-center backdrop-blur-xl">
            <span className="text-sm font-medium text-white/70">Connecting to the railway network&hellip;</span>
            <ConnectionBadge />
          </div>
        </div>
      )}

      <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
        <TopBar />

        <div className="flex flex-col gap-3 p-4 sm:hidden">
          {selectedTrainId ? <TrainInfoPanel /> : viewMode === "journey" ? <JourneyPanel /> : null}
        </div>

        <div className="hidden items-end justify-between p-6 sm:flex">
          <div className="flex flex-col gap-3">
            {viewMode === "journey" && !selectedTrainId && <JourneyPanel />}
          </div>
          {selectedTrainId && <TrainInfoPanel />}
        </div>
      </div>

      {viewMode === "network" && !selectedTrainId && (
        <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 rounded-full border border-white/10 bg-[#12151bcc] px-4 py-2 text-xs font-medium text-white/50 backdrop-blur-xl sm:bottom-8">
          Tap a train to inspect it
        </div>
      )}
    </div>
  );
}
