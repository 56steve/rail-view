"use client";

import { useEffect } from "react";
import { useRailView, type Appearance, type SceneLighting } from "@/lib/store";
import { sunDirection, sunPosition } from "@/lib/sun";

const REFRESH_MS = 60_000;
// Day mode from just before sunrise to just after sunset, so the map is
// already light while the sky is.
const DAY_ELEVATION_DEG = -3;
// At night the scene is lit by a fixed, high "moon" rather than the sun
// below the horizon.
const NIGHT_LIGHT: [number, number, number] = [-0.4, 0.8, 0.33];
// A sun right on the horizon would leave every street-facing wall black,
// so light never comes from lower than this.
const MIN_LIGHT_ELEVATION_DEG = 10;
// Day mode chosen while it's dark outside: light the map as at mid-morning.
const MORNING_SUN = { azimuthDeg: 120, elevationDeg: 40 };

function resolveLighting(appearance: Appearance, now: Date): SceneLighting {
  const sun = sunPosition(now);
  const sunIsUp = sun.elevationDeg > DAY_ELEVATION_DEG;
  const mode = appearance === "auto" ? (sunIsUp ? "day" : "night") : appearance;
  if (mode === "night") return { mode, sunDirection: NIGHT_LIGHT, sunElevationDeg: sun.elevationDeg };
  const lit = sunIsUp
    ? { azimuthDeg: sun.azimuthDeg, elevationDeg: Math.max(sun.elevationDeg, MIN_LIGHT_ELEVATION_DEG) }
    : MORNING_SUN;
  return { mode, sunDirection: sunDirection(lit), sunElevationDeg: lit.elevationDeg };
}

/** Keeps the scene's day/night mode and sun direction in step with the
 * user's appearance choice and the real sun over Mumbai. */
export function useSceneLighting(): void {
  const appearance = useRailView((s) => s.appearance);

  useEffect(() => {
    const update = () => useRailView.getState().setLighting(resolveLighting(appearance, new Date()));
    update();
    const timer = setInterval(update, REFRESH_MS);
    return () => clearInterval(timer);
  }, [appearance]);

  const mode = useRailView((s) => s.lighting.mode);
  useEffect(() => {
    document.documentElement.dataset.scene = mode;
  }, [mode]);
}
