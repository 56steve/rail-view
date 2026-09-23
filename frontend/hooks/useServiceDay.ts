"use client";

import { useEffect, useState } from "react";
import { fetchServiceDay } from "@/lib/api";
import type { ServiceDay } from "@/lib/types";

// Rechecked through the day so the notice turns over at midnight.
const REFRESH_MS = 30 * 60 * 1000;

/** Today's service day (Sunday timetable or not), or null until known. */
export function useServiceDay(): ServiceDay | null {
  const [serviceDay, setServiceDay] = useState<ServiceDay | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = () =>
      fetchServiceDay(controller.signal)
        .then(setServiceDay)
        .catch(() => {
          // Informational only: without it the notice just doesn't show.
        });
    void load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, []);

  return serviceDay;
}
