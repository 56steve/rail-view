"use client";

import { useEffect, useState } from "react";
import { fetchNetwork, fetchStations } from "@/lib/api";
import { useRailView } from "@/lib/store";

const RETRY_MS = 3000;

/** Loads the static network (lines, tracks, stations) once, retrying
 * until the API is reachable. Returns whether the last attempt failed so
 * the UI can say so instead of sitting on a blank map. */
export function useNetworkData(): { failed: boolean } {
  const setNetwork = useRailView((s) => s.setNetwork);
  const setStations = useRailView((s) => s.setStations);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;

    const load = async () => {
      try {
        const [network, stations] = await Promise.all([
          fetchNetwork(controller.signal),
          fetchStations(controller.signal),
        ]);
        setNetwork(network);
        setStations(stations);
        setFailed(false);
      } catch {
        if (controller.signal.aborted) return;
        setFailed(true);
        timer = setTimeout(load, RETRY_MS);
      }
    };

    void load();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [setNetwork, setStations]);

  return { failed };
}
