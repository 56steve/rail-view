// Rounds the corners of a track polyline into circular arcs. OSM draws track
// as straight chords between nodes tens to hundreds of metres apart, each
// turning a few degrees; drawn (or driven) as they are, every node is a
// visible kink. Each corner is replaced by the arc tangent to both of its
// segments, sampled finely enough that nothing looks faceted close up, so
// the line keeps a continuous heading and still passes within about a
// metre of every node.

import type { ScenePoint } from "./geo";

export interface FilletOptions {
  /** Radius a corner gets when its segments leave room for it. Corners
   * whose neighbouring nodes are closer get the largest radius that fits. */
  readonly minRadiusM: number;
  /** A gentle corner may take a radius larger than `minRadiusM`, up to the
   * one whose arc passes this close to the node, so a bend drawn with
   * sparse nodes spreads over its segments instead of turning in a few
   * metres. */
  readonly maxOffsetM: number;
  /** Corners sharper than this are left as they are: track never turns that
   * far at a single node, so it's a reversal (a route running into a
   * platform and back out) or a digitising error, not a curve. */
  readonly maxTurnRad: number;
  /** Largest change of heading between consecutive samples of an arc. */
  readonly maxStepRad: number;
  /** Largest gap between an arc and the chord joining two of its samples. */
  readonly maxSagittaM: number;
}

/** Suburban broad-gauge curves run to hundreds of metres in radius. */
export const TRACK_FILLET: FilletOptions = {
  minRadiusM: 250,
  maxOffsetM: 1,
  maxTurnRad: Math.PI / 4,
  maxStepRad: Math.PI / 180,
  maxSagittaM: 0.02,
};

export interface FilletedPath {
  readonly points: ScenePoint[];
  /**
   * For each point, the distance along the input polyline it stands for:
   * strictly increasing, from 0 to the input's length. Points on the
   * straights keep their own distance; an arc spreads the distance of the
   * two chord ends it replaces evenly over its samples.
   */
  readonly sourceAlong: Float64Array;
}

export class FilletError extends Error {}

// Turns smaller than this are straight for every purpose.
const MIN_TURN_RAD = 1e-6;
// Output points closer than this to the previous one are dropped.
const COINCIDENT_M = 1e-6;

function validateOptions(options: FilletOptions): void {
  for (const [name, value] of Object.entries(options)) {
    if (!(typeof value === "number" && value > 0 && Number.isFinite(value))) {
      throw new FilletError(`fillet option ${name} must be a positive number, got ${String(value)}`);
    }
  }
}

/**
 * The radius a corner turning `turn` radians would like: `minRadiusM`, or
 * more where the arc still passes within `maxOffsetM` of the node. An arc of
 * radius R passes R (sec(turn / 2) - 1) from the node, written here without
 * the cancellation `1 / cos - 1` suffers at small angles.
 */
function wantedRadius(turn: number, options: FilletOptions): number {
  const s = Math.sin(turn / 4);
  const offsetRadius = (options.maxOffsetM * Math.cos(turn / 2)) / (2 * s * s);
  return Math.max(options.minRadiusM, offsetRadius);
}

/**
 * `points` with every corner gentler than `options.maxTurnRad` replaced by
 * a circular arc tangent to both of its segments. The first and last
 * points, and the heading at them, are kept exactly. Repeated points are
 * dropped. A polyline without two distinct points comes back unchanged.
 */
export function filletCorners(points: readonly ScenePoint[], options: FilletOptions = TRACK_FILLET): FilletedPath {
  validateOptions(options);
  for (const p of points) {
    if (!Number.isFinite(p.x) || !Number.isFinite(p.z)) {
      throw new FilletError(`polyline point (${p.x}, ${p.z}) is not finite`);
    }
  }

  const clean: ScenePoint[] = [];
  for (const p of points) {
    const last = clean[clean.length - 1];
    if (!last || last.x !== p.x || last.z !== p.z) clean.push(p);
  }
  const n = clean.length;
  if (n < 2) return { points: points.slice(), sourceAlong: new Float64Array(points.length) };

  // Segment j runs from clean[j] to clean[j + 1].
  const lengths = new Float64Array(n - 1);
  const ux = new Float64Array(n - 1);
  const uz = new Float64Array(n - 1);
  const along = new Float64Array(n);
  for (let j = 0; j < n - 1; j++) {
    const dx = clean[j + 1]!.x - clean[j]!.x;
    const dz = clean[j + 1]!.z - clean[j]!.z;
    const length = Math.hypot(dx, dz);
    lengths[j] = length;
    ux[j] = dx / length;
    uz[j] = dz / length;
    along[j + 1] = along[j]! + length;
  }

  // Turn at each node and the tangent length (node to where the arc meets
  // the segment) it would like; the ends and sharp corners get none.
  const turns = new Float64Array(n);
  const wanted = new Float64Array(n);
  for (let i = 1; i < n - 1; i++) {
    const cos = Math.min(Math.max(ux[i - 1]! * ux[i]! + uz[i - 1]! * uz[i]!, -1), 1);
    const turn = Math.acos(cos);
    if (turn < MIN_TURN_RAD || turn > options.maxTurnRad) continue;
    turns[i] = turn;
    wanted[i] = wantedRadius(turn, options) * Math.tan(turn / 2);
  }

  // Each segment is shared by the arcs at its two ends; where they'd
  // overlap, both shrink in proportion so they meet exactly.
  const tangents = new Float64Array(n);
  for (let i = 1; i < n - 1; i++) {
    if (wanted[i] === 0) continue;
    const before = wanted[i - 1]! + wanted[i]!;
    const after = wanted[i]! + wanted[i + 1]!;
    const shareBefore = before > lengths[i - 1]! ? (lengths[i - 1]! * wanted[i]!) / before : wanted[i]!;
    const shareAfter = after > lengths[i]! ? (lengths[i]! * wanted[i]!) / after : wanted[i]!;
    tangents[i] = Math.min(shareBefore, shareAfter);
  }

  const out: ScenePoint[] = [];
  const outAlong: number[] = [];
  const emit = (x: number, z: number, at: number): void => {
    const last = out[out.length - 1];
    if (last && Math.hypot(x - last.x, z - last.z) < COINCIDENT_M) return;
    out.push({ x, z });
    outAlong.push(at);
  };

  out.push({ x: clean[0]!.x, z: clean[0]!.z });
  outAlong.push(0);
  for (let i = 1; i < n - 1; i++) {
    const p = clean[i]!;
    const t = tangents[i]!;
    if (t === 0) {
      emit(p.x, p.z, along[i]!);
      continue;
    }
    const turn = turns[i]!;
    const radius = t / Math.tan(turn / 2);
    const inX = ux[i - 1]!;
    const inZ = uz[i - 1]!;
    // Unit normal to the incoming segment, towards the inside of the turn.
    const side = inX * uz[i]! - inZ * ux[i]! > 0 ? 1 : -1;
    const nx = -inZ * side;
    const nz = inX * side;
    const ax = p.x - inX * t;
    const az = p.z - inZ * t;

    const sagittaStep = options.maxSagittaM >= radius ? Math.PI : 2 * Math.acos(1 - options.maxSagittaM / radius);
    const steps = Math.max(1, Math.ceil(turn / Math.min(options.maxStepRad, sagittaStep)));
    for (let k = 0; k <= steps; k++) {
      const phi = (turn * k) / steps;
      const forward = radius * Math.sin(phi);
      const inward = radius * (1 - Math.cos(phi));
      emit(ax + inX * forward + nx * inward, az + inZ * forward + nz * inward, along[i]! - t + (2 * t * k) / steps);
    }
  }
  // The end is kept exactly, even where the last arc runs right up to it.
  const end = clean[n - 1]!;
  const last = out[out.length - 1]!;
  if (Math.hypot(end.x - last.x, end.z - last.z) < COINCIDENT_M) {
    out.pop();
    outAlong.pop();
  }
  out.push({ x: end.x, z: end.z });
  outAlong.push(along[n - 1]!);

  return { points: out, sourceAlong: Float64Array.from(outAlong) };
}
