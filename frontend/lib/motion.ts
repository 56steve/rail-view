// Client-side motion smoothing. The server sends one filtered position per
// train per tick (~1s). Rendering only those samples would stutter, so
// each frame interpolates between where a train was shown when the latest
// snapshot arrived and that snapshot's position - in chainage, i.e.
// *along the track*, which keeps a train on its curves instead of cutting
// straight chords between samples.
//
// The glide lasts as long as snapshots actually take to arrive, measured
// here, not an assumed second: a server that runs slow (a small cloud
// instance) or a patchy mobile connection would otherwise leave trains
// parked at each position until the next one lands.

import type { TrainSnapshotPair } from "./store";
import type { TrainPositionUpdate, TrainStatus } from "./types";

// The backend's simulation_tick_seconds default: the glide before any
// snapshot interval has been measured.
export const EXPECTED_TICK_MS = 1000;

// Glide a little longer than the typical interval, so a snapshot that
// comes a bit late finds the train still moving rather than stopped. A
// train then trails its newest position by a fraction of one tick.
const GLIDE_HEADROOM = 1.15;
const MIN_GLIDE_MS = 500;
const MAX_GLIDE_MS = 3000;
// Gaps longer than this are a reconnect or a backgrounded tab, not the
// server's rhythm, so they don't count towards it.
const MAX_MEASURED_INTERVAL_MS = 5000;
const INTERVAL_SMOOTHING = 0.2;

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
  const t = Math.min(Math.max((nowMs - pair.receivedAtMs) / pair.glideMs, 0), 1);
  const continuous =
    from.route_code === to.route_code && Math.abs(to.chainage_m - from.chainage_m) < MAX_INTERPOLATED_JUMP_M;
  return {
    routeCode: to.route_code,
    chainage: continuous ? from.chainage_m + (to.chainage_m - from.chainage_m) * t : to.chainage_m,
    forward: to.direction_forward,
    status: to.status,
  };
}

/** Measures how often snapshots arrive, to set how long each glide lasts. */
export class SnapshotRhythm {
  private intervalMs = EXPECTED_TICK_MS;
  private lastArrivalMs: number | null = null;

  /** Records a snapshot arriving at `nowMs`; returns the glide to use for it. */
  arrived(nowMs: number): number {
    if (this.lastArrivalMs !== null) {
      const gap = nowMs - this.lastArrivalMs;
      if (gap > 0 && gap <= MAX_MEASURED_INTERVAL_MS) {
        this.intervalMs += (gap - this.intervalMs) * INTERVAL_SMOOTHING;
      }
    }
    this.lastArrivalMs = nowMs;
    return Math.min(Math.max(this.intervalMs * GLIDE_HEADROOM, MIN_GLIDE_MS), MAX_GLIDE_MS);
  }
}

/** The pair for a new snapshot of a train: it glides on from wherever it
 * is on screen now, so an early or late snapshot never makes it jump. */
export function nextPair(
  previous: TrainSnapshotPair | undefined,
  train: TrainPositionUpdate,
  nowMs: number,
  glideMs: number,
): TrainSnapshotPair {
  if (!previous) return { from: train, to: train, receivedAtMs: nowMs, glideMs };
  const shown = trainPose(previous, nowMs);
  const from: TrainPositionUpdate =
    shown.routeCode === previous.to.route_code ? { ...previous.to, chainage_m: shown.chainage } : previous.to;
  return { from, to: train, receivedAtMs: nowMs, glideMs };
}
