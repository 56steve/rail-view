import { describe, expect, it } from "vitest";
import type { ScenePoint } from "../geo";
import { SLEEPER_SPACING_M } from "./profiles";
import { SLEEPER_STRIDE, sleepersAlong } from "./sleepers";
import { chainPath } from "./sweep";
import { splitIntoTiles } from "./tiles";

const RADIUS = 250;

/** A quarter-circle curve of radius RADIUS about the origin, as a
 * polyline with a point every degree. */
function arc(): ScenePoint[] {
  const points: ScenePoint[] = [];
  for (let d = 0; d <= 90; d++) {
    const a = (d * Math.PI) / 180;
    points.push({ x: RADIUS * Math.cos(a), z: RADIUS * Math.sin(a) });
  }
  return points;
}

function sleepers(points: ScenePoint[], along?: number[]): Float32Array {
  const path = chainPath(points);
  return sleepersAlong(along ? { ...path, along } : path, SLEEPER_SPACING_M);
}

describe("sleepersAlong", () => {
  it("spaces sleepers evenly round a curve and turns each across the track", () => {
    const points = arc();
    const out = sleepers(points);
    const along = chainPath(points).along;
    const length = along[along.length - 1]!;
    const count = out.length / SLEEPER_STRIDE;
    expect(count).toBe(Math.round(length / SLEEPER_SPACING_M));

    for (let i = 0; i < count; i++) {
      const x = out[i * SLEEPER_STRIDE]!;
      const z = out[i * SLEEPER_STRIDE + 1]!;
      const heading = out[i * SLEEPER_STRIDE + 2]!;
      // On the curve (the polyline's chords sag at most ~1 cm inside it).
      expect(Math.abs(Math.hypot(x, z) - RADIUS)).toBeLessThan(0.02);
      // Facing along the curve: the heading's direction is perpendicular
      // to the radius.
      expect(Math.abs(Math.sin(heading) * x + Math.cos(heading) * z) / RADIUS).toBeLessThan(0.01);
      if (i > 0) {
        const gap = Math.hypot(x - out[(i - 1) * SLEEPER_STRIDE]!, z - out[(i - 1) * SLEEPER_STRIDE + 1]!);
        expect(gap).toBeCloseTo(SLEEPER_SPACING_M, 3);
      }
    }
    // Half a spacing in from the start.
    expect(out[0]).toBeCloseTo(RADIUS, 1);
    expect(out[1]).toBeCloseTo(SLEEPER_SPACING_M / 2, 3);
  });

  it("places the same sleepers whether or not the track is cut into tiles", () => {
    const track = arc().map((p) => ({ x: p.x + 130, z: p.z - 410 }));
    const whole = sleepers(track);
    const pieces = [...splitIntoTiles([track], 100).values()]
      .flatMap((tile) => tile.pieces)
      .sort((a, b) => a.along[0]! - b.along[0]!);
    expect(pieces.length).toBeGreaterThan(3);

    const joined = pieces.flatMap((piece) => Array.from(sleepersAlong(piece, SLEEPER_SPACING_M)));
    expect(joined.length).toBe(whole.length);
    joined.forEach((value, i) => expect(value).toBeCloseTo(whole[i]!, 4));
  });

  it("offsets the pattern by chainage, not by where the path starts", () => {
    const points: ScenePoint[] = [
      { x: 0, z: 0 },
      { x: 10, z: 0 },
    ];
    const out = sleepers(points, [100.1, 110.1]);
    // The first sleeper is at chainage 100.5 (167.5 spacings), 0.4 m along.
    expect(out[0]).toBeCloseTo(0.4, 4);
    expect(out[2]).toBeCloseTo(Math.PI / 2, 6);
  });

  it("rejects a non-positive spacing", () => {
    expect(() => sleepersAlong(chainPath(arc()), 0)).toThrow(RangeError);
  });
});
