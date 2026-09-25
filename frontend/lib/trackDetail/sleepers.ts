// Where the sleepers go along a track.

import type { ChainedPath } from "./sweep";

/** Floats per sleeper in `sleepersAlong`'s output: x, z, heading. */
export const SLEEPER_STRIDE = 3;

/**
 * One sleeper every `spacing` metres of chainage, at (k + 0.5) * spacing,
 * for those chainages in [first, last) of the path. Anchoring to chainage
 * rather than to the start of the path keeps the spacing even across the
 * points where a track is cut at tile edges, and the half-open range puts
 * a sleeper that falls exactly on a cut into one piece only.
 *
 * Output: x, z and heading per sleeper, where heading is the rotation
 * about +y that turns local +z onto the direction of travel. Headings are
 * interpolated between the path's tangents, so sleepers turn smoothly
 * through a curve with the swept rails rather than in steps.
 */
export function sleepersAlong(path: ChainedPath, spacing: number): Float32Array {
  if (!(spacing > 0)) throw new RangeError(`sleeper spacing must be positive, got ${spacing}`);
  const { points, along, tangents } = path;
  const n = points.length;
  if (n < 2 || along.length !== n || tangents.length !== n * 2) {
    throw new RangeError("sleepersAlong needs at least two points, with a chainage and tangent for each");
  }
  const firstK = Math.ceil(along[0]! / spacing - 0.5);
  const endK = Math.ceil(along[n - 1]! / spacing - 0.5);
  const count = Math.max(endK - firstK, 0);
  const out = new Float32Array(count * SLEEPER_STRIDE);

  let segment = 0;
  for (let i = 0; i < count; i++) {
    const chainage = (firstK + i + 0.5) * spacing;
    while (segment < n - 2 && along[segment + 1]! <= chainage) segment += 1;
    const c0 = along[segment]!;
    const span = along[segment + 1]! - c0;
    const t = span > 0 ? Math.min(Math.max((chainage - c0) / span, 0), 1) : 0;
    const a = points[segment]!;
    const b = points[segment + 1]!;
    const tx = tangents[segment * 2]! * (1 - t) + tangents[(segment + 1) * 2]! * t;
    const tz = tangents[segment * 2 + 1]! * (1 - t) + tangents[(segment + 1) * 2 + 1]! * t;
    out[i * SLEEPER_STRIDE] = a.x + (b.x - a.x) * t;
    out[i * SLEEPER_STRIDE + 1] = a.z + (b.z - a.z) * t;
    out[i * SLEEPER_STRIDE + 2] = Math.atan2(tx, tz);
  }
  return out;
}
