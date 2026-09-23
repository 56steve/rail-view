// Client-side motion smoothing. The server sends one filtered position per
// train per tick (~1s). Rendering only those samples would stutter, so
// each frame interpolates between a train's last two snapshots - in
// chainage, i.e. *along the track*, which keeps a train on its curves
// instead of cutting straight chords between samples.

import type { TrainSnapshotPair } from "./store";
import type { TrainStatus } from "./types";

// Matches the backend's simulation_tick_seconds default; if the server
// ticks at a different rate, the interpolation window should follow.
export const EXPECTED_TICK_MS = 1000;

// A jump larger than this between snapshots isn't motion (e.g. a train
// forming its return working), so snap instead of sliding across it.
const MAX_INTERPOLATED_JUMP_M = 400;

export interface TrainPose {
  routeCode: string;
  /** Chainage of the train's centre, in metres along its route. */
  chainage: number;
  /** Travelling towards increasing chainage. */
  forward: boolean;
  status: TrainStatus;
}

export function trainPose(pair: TrainSnapshotPair, nowMs: number): TrainPose {
  const { from, to } = pair;
  const t = Math.min(Math.max((nowMs - pair.receivedAtMs) / EXPECTED_TICK_MS, 0), 1);
  const continuous =
    from.route_code === to.route_code && Math.abs(to.chainage_m - from.chainage_m) < MAX_INTERPOLATED_JUMP_M;
  return {
    routeCode: to.route_code,
    chainage: continuous ? from.chainage_m + (to.chainage_m - from.chainage_m) * t : to.chainage_m,
    forward: to.direction_forward,
    status: to.status,
  };
}
