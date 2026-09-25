import { describe, expect, it } from "vitest";
import type { ScenePoint } from "../geo";
import { BALLAST_PROFILE, RAIL_HEAD_PROFILE, RAIL_SIDE_PROFILE } from "./profiles";
import { chainPath, MeshBuffers, pathTangents, sweepProfile, sweepSize, type ChainedPath, type Profile } from "./sweep";

const chained = chainPath;

function sweepOne(path: ChainedPath, profile: Profile, caps = { start: false, end: false }): MeshBuffers {
  const size = sweepSize(path.points.length, profile, caps);
  const out = new MeshBuffers(size.vertices, size.indices, true);
  sweepProfile(out, path, profile, { lateral: 0, y: 0, uvRepeatM: 1.5, caps });
  return out;
}

function vertex(out: MeshBuffers, i: number): [number, number, number] {
  return [out.positions[i * 3]!, out.positions[i * 3 + 1]!, out.positions[i * 3 + 2]!];
}

// A right-angle corner: east 10 m, then south (scene +z) 10 m.
const CORNER = chained([
  { x: 0, z: 0 },
  { x: 10, z: 0 },
  { x: 10, z: 10 },
]);
const FLAT: Profile = [
  [
    { x: -1, y: 0 },
    { x: 1, y: 0 },
  ],
];

describe("pathTangents", () => {
  it("bisects the corner and follows the segments at the ends", () => {
    const t = pathTangents(CORNER.points);
    expect([t[0], t[1]]).toEqual([1, 0]);
    expect(t[2]).toBeCloseTo(Math.SQRT1_2, 12);
    expect(t[3]).toBeCloseTo(Math.SQRT1_2, 12);
    expect([t[4], t[5]]).toEqual([0, 1]);
  });

  it("is unchanged by a point added mid-segment, as tile cuts do", () => {
    const t = pathTangents([
      { x: 0, z: 0 },
      { x: 4, z: 0 },
      { x: 10, z: 0 },
      { x: 10, z: 10 },
    ]);
    expect([t[2], t[3]]).toEqual([1, 0]);
  });

  it("rejects a path with no length", () => {
    expect(() =>
      pathTangents([
        { x: 1, z: 1 },
        { x: 1, z: 1 },
      ]),
    ).toThrow(/every point coincides/);
  });
});

describe("sweepProfile", () => {
  it("writes exactly the vertices and indices sweepSize reports", () => {
    for (const profile of [BALLAST_PROFILE, RAIL_SIDE_PROFILE, RAIL_HEAD_PROFILE]) {
      for (const caps of [
        { start: false, end: false },
        { start: true, end: true },
      ]) {
        const out = sweepOne(CORNER, profile, caps);
        expect(out.full).toBe(true);
        expect(Math.max(...out.indices)).toBeLessThan(out.vertexCount);
      }
    }
    // Ballast: 3 faces x 2 vertices x 3 path points, plus 4 per cap.
    expect(sweepSize(3, BALLAST_PROFILE)).toEqual({ vertices: 18, indices: 36 });
    expect(sweepSize(3, BALLAST_PROFILE, { start: true, end: true })).toEqual({ vertices: 26, indices: 48 });
  });

  it("stays continuous through a corner: both segments share the corner's vertices", () => {
    const out = sweepOne(CORNER, FLAT);
    // Vertex rows are (profile x = -1, x = +1) per path point; row 1 is the
    // corner. Heading east then south is a right turn, so -1 (right of
    // travel) is the inside of the corner.
    const [inner, outer] = [2, 3];
    for (const segment of [out.indices.slice(0, 6), out.indices.slice(6, 12)]) {
      expect(Array.from(segment)).toContain(inner);
      expect(Array.from(segment)).toContain(outer);
    }

    // The corner row lies across the bisector, one half-width either side.
    const a = vertex(out, inner);
    const b = vertex(out, outer);
    expect(Math.hypot(a[0] - 10, a[2])).toBeCloseTo(1, 6);
    expect(Math.hypot(b[0] - 10, b[2])).toBeCloseTo(1, 6);
    expect((b[0] - a[0]) * Math.SQRT1_2 + (b[2] - a[2]) * Math.SQRT1_2).toBeCloseTo(0, 6);
    expect(a[0]).toBeLessThan(10);
    expect(a[2]).toBeGreaterThan(0);
    expect(b[0]).toBeGreaterThan(10);
    expect(b[2]).toBeLessThan(0);
  });

  it("winds every triangle to face the way its vertex normals point", () => {
    const curve: ScenePoint[] = [];
    for (let i = 0; i <= 12; i++) {
      const a = (i / 12) * Math.PI * 0.6;
      curve.push({ x: 300 * Math.sin(a), z: -300 * (1 - Math.cos(a)) });
    }
    for (const profile of [BALLAST_PROFILE, RAIL_SIDE_PROFILE, RAIL_HEAD_PROFILE]) {
      const out = sweepOne(chained(curve), profile, { start: profile === BALLAST_PROFILE, end: profile === BALLAST_PROFILE });
      for (let k = 0; k < out.indexCount; k += 3) {
        const [a, b, c] = [out.indices[k]!, out.indices[k + 1]!, out.indices[k + 2]!];
        const [pa, pb, pc] = [vertex(out, a), vertex(out, b), vertex(out, c)];
        const e1 = [pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]];
        const e2 = [pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]];
        const face = [e1[1]! * e2[2]! - e1[2]! * e2[1]!, e1[2]! * e2[0]! - e1[0]! * e2[2]!, e1[0]! * e2[1]! - e1[1]! * e2[0]!];
        const normal = [out.normals[a * 3]!, out.normals[a * 3 + 1]!, out.normals[a * 3 + 2]!];
        expect(Math.hypot(...normal)).toBeCloseTo(1, 5);
        expect(face[0]! * normal[0]! + face[1]! * normal[1]! + face[2]! * normal[2]!).toBeGreaterThan(0);
      }
    }
  });

  it("points the ballast top up and its slopes outward, with profile x to the left of travel", () => {
    // Travelling north (scene -z), so profile +x is west (scene -x).
    const out = sweepOne(chained([{ x: 0, z: 0 }, { x: 0, z: -10 }]), BALLAST_PROFILE);
    // Two path points per face, (a, b) per point: face f starts at vertex 4f.
    const face = (f: number): { normal: number[]; x: number } => {
      const v = f * 4;
      return { normal: [out.normals[v * 3]!, out.normals[v * 3 + 1]!, out.normals[v * 3 + 2]!], x: out.positions[v * 3]! };
    };
    // Profile starts at its -x foot, which lies east of the path.
    expect(face(0).x).toBeGreaterThan(0);
    expect(face(0).normal[0]).toBeGreaterThan(0);
    expect(face(0).normal[1]).toBeGreaterThan(0);
    expect(face(1).normal).toEqual([0, 1, 0]);
    expect(face(2).normal[0]).toBeLessThan(0);
    expect(face(2).normal[1]).toBeGreaterThan(0);
  });

  it("maps texture v to chainage, so pieces cut at a tile edge continue the pattern", () => {
    const path: ChainedPath = { ...chained([{ x: 0, z: 0 }, { x: 3, z: 0 }]), along: [120, 123] };
    const out = sweepOne(path, FLAT);
    expect(out.uvs![1]).toBeCloseTo(120 / 1.5, 6);
    expect(out.uvs![5]).toBeCloseTo(123 / 1.5, 6);
  });

  it("stores positions relative to the buffers' origin", () => {
    const size = sweepSize(2, FLAT);
    const out = new MeshBuffers(size.vertices, size.indices, false, { x: 20_000, z: -15_000 });
    const path = chained([
      { x: 20_010, z: -15_000 },
      { x: 20_020, z: -15_000 },
    ]);
    sweepProfile(out, path, FLAT, { lateral: 0.5, y: 0.3, uvRepeatM: 1 });
    // Heading east, left of travel is north (scene -z): x = -1 + 0.5 lands
    // half a metre south.
    const [x, y, z] = vertex(out, 0);
    expect([x, z]).toEqual([10, 0.5]);
    expect(y).toBeCloseTo(0.3, 6);
  });

  it("refuses to write past its buffers", () => {
    const out = new MeshBuffers(4, 6, false);
    expect(() => sweepProfile(out, CORNER, FLAT, { lateral: 0, y: 0, uvRepeatM: 1 })).toThrow(/overruns/);
  });
});
