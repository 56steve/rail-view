// Which physical track a train is drawn on. Mumbai's railways run on the
// left, so the two directions of a route keep to different tracks: the
// backend's running-lane profiles give, per direction, the sideways offset
// from the route centreline (which chainage is measured along) to that
// direction's track.

import type { TrackPath, TrackSample } from "./track";
import type { RouteOut } from "./types";

// Half-span used to take a heading from the offset path itself, so a
// train crossing over between tracks points along its actual path.
const HEADING_PROBE_M = 2;

/** Piecewise-linear sideways offset (metres, positive = left facing
 * increasing chainage) as a function of chainage. */
export class LaneProfile {
  private readonly chainages: Float64Array;
  private readonly offsets: Float64Array;

  constructor(breakpoints: [number, number][]) {
    if (breakpoints.length === 0) throw new Error("LaneProfile needs at least one breakpoint");
    this.chainages = Float64Array.from(breakpoints, ([c]) => c);
    this.offsets = Float64Array.from(breakpoints, ([, d]) => d);
  }

  offsetAt(chainage: number): number {
    const cs = this.chainages;
    const last = cs.length - 1;
    if (chainage <= cs[0]!) return this.offsets[0]!;
    if (chainage >= cs[last]!) return this.offsets[last]!;
    let lo = 0;
    let hi = last;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (cs[mid]! <= chainage) lo = mid;
      else hi = mid;
    }
    const t = (chainage - cs[lo]!) / (cs[hi]! - cs[lo]! || 1);
    return this.offsets[lo]! + (this.offsets[hi]! - this.offsets[lo]!) * t;
  }
}

export interface RouteLanes {
  forward: LaneProfile;
  backward: LaneProfile;
}

export function routeLanes(route: RouteOut): RouteLanes {
  return {
    forward: new LaneProfile(route.running_lanes.forward),
    backward: new LaneProfile(route.running_lanes.backward),
  };
}

function offsetPoint(track: TrackPath, lane: LaneProfile, chainage: number): { x: number; z: number } {
  const s = track.sample(chainage);
  const d = lane.offsetAt(chainage);
  // Left of increasing chainage in scene space is (-cos yaw, sin yaw).
  return { x: s.x - d * Math.cos(s.yaw), z: s.z + d * Math.sin(s.yaw) };
}

/** A point on the track a train travelling in `forward` direction runs
 * on, with the heading (yaw) of increasing chainage along that track. */
export function laneSample(track: TrackPath, lanes: RouteLanes, forward: boolean, chainage: number): TrackSample {
  const lane = forward ? lanes.forward : lanes.backward;
  const p = offsetPoint(track, lane, chainage);
  const a = offsetPoint(track, lane, chainage - HEADING_PROBE_M);
  const b = offsetPoint(track, lane, chainage + HEADING_PROBE_M);
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const yaw = dx === 0 && dz === 0 ? track.sample(chainage).yaw : Math.atan2(-dx, -dz);
  return { x: p.x, z: p.z, yaw };
}
