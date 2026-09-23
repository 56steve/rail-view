"use client";

import { useEffect, useState } from "react";

/** Current time in epoch seconds, refreshed every `intervalMs`, for
 * countdowns like "3 min away" that must tick without new server data. */
export function useNowSeconds(intervalMs = 5000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now() / 1000), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
