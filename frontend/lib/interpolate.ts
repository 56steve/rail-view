// Client-side motion interpolation: the server broadcasts one position
// snapshot per train per tick (~1s apart, see backend
// app/config.py:simulation_tick_seconds). Rendering trains snapped to
// only those samples would look like a teleporting stutter, so every
// train mesh interpolates smoothly between its last two known snapshots
// on every animation frame instead of waiting for the next one.

import { latLonToScene } from "./geo";
import type { TrainPositionUpdate } from "./types";

// Must match the backend's simulation_tick_seconds default. If the
// server ticks slower/faster, the interpolation window should follow -
// this is the one constant that couples the two.
export const EXPECTED_TICK_INTERVAL_MS = 1000;

export interface InterpolatedTrainPosition {
  x: number;
  z: number;
  headingDeg: number;
  speedKmh: number;
  status: TrainPositionUpdate["status"];
}

export function interpolateTrainPosition(
  from: TrainPositionUpdate,
  to: TrainPositionUpdate,
  toReceivedAtMs: number,
  nowMs: number,
): InterpolatedTrainPosition {
  const elapsed = nowMs - toReceivedAtMs;
  const t = Math.min(Math.max(elapsed / EXPECTED_TICK_INTERVAL_MS, 0), 1);

  const fromScene = latLonToScene(from.lat, from.lon);
  const toScene = latLonToScene(to.lat, to.lon);

  return {
    x: fromScene.x + (toScene.x - fromScene.x) * t,
    z: fromScene.z + (toScene.z - fromScene.z) * t,
    headingDeg: lerpAngleDeg(from.heading_deg, to.heading_deg, t),
    speedKmh: to.speed_kmh,
    status: to.status,
  };
}

/** Shortest-path angle interpolation, so a heading near 359deg -> 2deg
 * eases through 0 instead of spinning the long way around. */
function lerpAngleDeg(a: number, b: number, t: number): number {
  const delta = ((b - a + 540) % 360) - 180;
  return a + delta * t;
}
