import { describe, expect, it } from "vitest";
import { filletCorners, FilletError, TRACK_FILLET } from "./curves";
import type { ScenePoint } from "./geo";

const DEG = Math.PI / 180;

/** Heading of each segment of a polyline, in radians. */
function headings(points: readonly ScenePoint[]): number[] {
  return points.slice(1).map((p, i) => Math.atan2(p.z - points[i]!.z, p.x - points[i]!.x));
}

/** Largest change of heading between consecutive segments, in radians. */
function largestHeadingStep(points: readonly ScenePoint[]): number {
  const h = headings(points);
  let largest = 0;
  for (let i = 1; i < h.length; i++) {
    let d = Math.abs(h[i]! - h[i - 1]!);
    if (d > Math.PI) d = 2 * Math.PI - d;
    largest = Math.max(largest, d);
  }
  return largest;
}

function distanceToPolyline(p: ScenePoint, line: readonly ScenePoint[]): number {
  let best = Infinity;
  for (let i = 0; i + 1 < line.length; i++) {
    const a = line[i]!;
    const b = line[i + 1]!;
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const t = Math.min(Math.max(((p.x - a.x) * dx + (p.z - a.z) * dz) / (dx * dx + dz * dz), 0), 1);
    best = Math.min(best, Math.hypot(p.x - (a.x + dx * t), p.z - (a.z + dz * t)));
  }
  return best;
}

/** A corner at the origin: in from the west along +x, then turning `turn`
 * radians to the left (towards -z), with legs of `leg` metres. */
function corner(turn: number, leg: number): ScenePoint[] {
  return [
    { x: -leg, z: 0 },
    { x: 0, z: 0 },
    { x: leg * Math.cos(turn), z: -leg * Math.sin(turn) },
  ];
}

function expectStrictlyIncreasing(values: ArrayLike<number>): void {
  for (let i = 1; i < values.length; i++) expect(values[i]!).toBeGreaterThan(values[i - 1]!);
}

describe("filletCorners", () => {
  it("leaves a straight line as it is", () => {
    const line = [
      { x: 0, z: 0 },
      { x: 40, z: 30 },
      { x: 80, z: 60 },
      { x: 400, z: 300 },
    ];
    const { points, sourceAlong } = filletCorners(line);
    expect(points).toEqual(line);
    expect(Array.from(sourceAlong)).toEqual([0, 50, 100, 500]);
  });

  it("turns a sharp corner smoothly, keeping both ends", () => {
    const line = corner(30 * DEG, 500);
    const { points, sourceAlong } = filletCorners(line);
    expect(points[0]).toEqual(line[0]);
    expect(points[points.length - 1]).toEqual(line[2]);
    expect(largestHeadingStep(points)).toBeLessThanOrEqual(TRACK_FILLET.maxStepRad + 1e-9);
    // Leaves along the first leg and arrives along the second.
    const h = headings(points);
    expect(h[0]).toBeCloseTo(0, 12);
    expect(h[h.length - 1]).toBeCloseTo(-30 * DEG, 12);
    expectStrictlyIncreasing(sourceAlong);
    expect(sourceAlong[0]).toBe(0);
    expect(sourceAlong[sourceAlong.length - 1]).toBeCloseTo(1000, 9);
  });

  it("rounds a corner with room to spare at the minimum radius", () => {
    const { points } = filletCorners(corner(20 * DEG, 500));
    // Arc of radius R through the corner passes R (sec(turn / 2) - 1) inside it.
    const inset = TRACK_FILLET.minRadiusM * (1 / Math.cos(10 * DEG) - 1);
    expect(distanceToPolyline({ x: 0, z: 0 }, points)).toBeCloseTo(inset, 2);
  });

  it("spreads a gentle corner so it passes within the offset of the node", () => {
    const { points } = filletCorners(corner(2 * DEG, 400));
    const offset = distanceToPolyline({ x: 0, z: 0 }, points);
    expect(offset).toBeLessThanOrEqual(TRACK_FILLET.maxOffsetM + 1e-6);
    expect(offset).toBeGreaterThan(0.5 * TRACK_FILLET.maxOffsetM);
    expect(largestHeadingStep(points)).toBeLessThanOrEqual(TRACK_FILLET.maxStepRad + 1e-9);
  });

  it("follows a circle drawn with sparse nodes", () => {
    // A 300 m radius curve through 90 degrees, one node every 6 degrees.
    const radius = 300;
    const nodes: ScenePoint[] = [];
    for (let a = 0; a <= 90; a += 6) nodes.push({ x: radius * Math.sin(a * DEG), z: radius * (1 - Math.cos(a * DEG)) });
    const { points } = filletCorners(nodes);
    expect(largestHeadingStep(points)).toBeLessThanOrEqual(TRACK_FILLET.maxStepRad + 1e-9);
    for (const p of points) {
      expect(Math.abs(Math.hypot(p.x, p.z - radius) - radius)).toBeLessThan(0.5);
    }
  });

  it("keeps successive arcs from overlapping on short segments", () => {
    const zigzag = [
      { x: 0, z: 0 },
      { x: 20, z: 0 },
      { x: 40, z: 3 },
      { x: 60, z: 3 },
      { x: 80, z: 0 },
    ];
    const { points, sourceAlong } = filletCorners(zigzag);
    expectStrictlyIncreasing(sourceAlong);
    expect(largestHeadingStep(points)).toBeLessThanOrEqual(TRACK_FILLET.maxStepRad + 1e-9);
    // Progress along x never goes backwards.
    for (let i = 1; i < points.length; i++) expect(points[i]!.x).toBeGreaterThan(points[i - 1]!.x);
  });

  it("leaves a reversal as a corner", () => {
    const line = [
      { x: 0, z: 0 },
      { x: 100, z: 0 },
      { x: 0, z: 1 },
    ];
    expect(filletCorners(line).points).toEqual(line);
  });

  it("drops repeated points", () => {
    const { points, sourceAlong } = filletCorners([
      { x: 0, z: 0 },
      { x: 0, z: 0 },
      { x: 10, z: 0 },
      { x: 10, z: 0 },
    ]);
    expect(points).toEqual([
      { x: 0, z: 0 },
      { x: 10, z: 0 },
    ]);
    expect(Array.from(sourceAlong)).toEqual([0, 10]);
  });

  it("rejects bad input", () => {
    expect(() => filletCorners([{ x: 0, z: 0 }, { x: Number.NaN, z: 0 }])).toThrow(FilletError);
    expect(() => filletCorners(corner(DEG, 10), { ...TRACK_FILLET, minRadiusM: 0 })).toThrow(FilletError);
  });
});
