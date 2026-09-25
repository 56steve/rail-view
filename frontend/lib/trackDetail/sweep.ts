// Sweeps a 2D cross-section along a track polyline into indexed triangle
// buffers. Kept free of three.js so it can be unit-tested and so a whole
// tile's worth of track is written straight into one pre-sized buffer.

import type { ScenePoint } from "../geo";

export interface Vec2 {
  readonly x: number;
  readonly y: number;
}

/**
 * A cross-section: one or more open polylines in (x across, y up), each
 * traversed clockwise so that its outward side is on the left of the
 * direction of traversal. x is positive to the left of travel along the
 * path.
 */
export type Profile = readonly (readonly Vec2[])[];

/** A polyline with the chainage and direction of every point. */
export interface ChainedPath {
  readonly points: readonly ScenePoint[];
  /** Metres from the start of the original track. */
  readonly along: ArrayLike<number>;
  /** Unit tangent (x, z pairs) at every point, from `pathTangents` of the
   * original track. */
  readonly tangents: ArrayLike<number>;
}

export class SweepError extends Error {}

/**
 * Unit tangents (x, z pairs) at every point. At a corner the tangent
 * bisects the two segments' directions, so a profile offset along its
 * perpendicular stays continuous through the corner. Depends only on the
 * directions of the adjacent segments, so a point added mid-segment (where
 * a track is cut at a tile edge) gets exactly the segment's direction on
 * both sides of the cut.
 */
export function pathTangents(points: readonly ScenePoint[]): Float64Array {
  const n = points.length;
  if (n < 2) throw new SweepError(`a path needs at least two points, got ${n}`);
  // Direction of the segment leaving each point; zero-length segments
  // borrow the previous segment's direction.
  const dirs = new Float64Array((n - 1) * 2);
  let haveDirection = false;
  for (let i = 0; i < n - 1; i++) {
    const dx = points[i + 1]!.x - points[i]!.x;
    const dz = points[i + 1]!.z - points[i]!.z;
    const len = Math.hypot(dx, dz);
    if (len > 0) {
      dirs[i * 2] = dx / len;
      dirs[i * 2 + 1] = dz / len;
      if (!haveDirection) {
        for (let k = 0; k < i; k++) {
          dirs[k * 2] = dirs[i * 2]!;
          dirs[k * 2 + 1] = dirs[i * 2 + 1]!;
        }
      }
      haveDirection = true;
    } else if (i > 0) {
      dirs[i * 2] = dirs[(i - 1) * 2]!;
      dirs[i * 2 + 1] = dirs[(i - 1) * 2 + 1]!;
    }
  }
  if (!haveDirection) throw new SweepError("a path needs some length; every point coincides");

  const tangents = new Float64Array(n * 2);
  for (let i = 0; i < n; i++) {
    const before = Math.max(i - 1, 0);
    const after = Math.min(i, n - 2);
    let tx = dirs[before * 2]! + dirs[after * 2]!;
    let tz = dirs[before * 2 + 1]! + dirs[after * 2 + 1]!;
    let len = Math.hypot(tx, tz);
    if (len < 1e-9) {
      // The path doubles back on itself; carry on along the new segment.
      tx = dirs[after * 2]!;
      tz = dirs[after * 2 + 1]!;
      len = 1;
    }
    tangents[i * 2] = tx / len;
    tangents[i * 2 + 1] = tz / len;
  }
  return tangents;
}

/** Chainages from zero and tangents for a whole track. */
export function chainPath(points: readonly ScenePoint[]): ChainedPath {
  const along = new Float64Array(points.length);
  for (let i = 1; i < points.length; i++) {
    along[i] = along[i - 1]! + Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.z - points[i - 1]!.z);
  }
  return { points, along, tangents: pathTangents(points) };
}

/**
 * Output of one or more sweeps, sized up front from `sweepSize` totals.
 * Positions are stored relative to `origin` (the mesh is placed there):
 * scene coordinates run to tens of kilometres, where float32 would round
 * millimetre-scale rail detail to a few millimetres.
 */
export class MeshBuffers {
  readonly positions: Float32Array;
  readonly normals: Float32Array;
  readonly uvs: Float32Array | null;
  readonly indices: Uint32Array;
  readonly origin: ScenePoint;
  vertexCount = 0;
  indexCount = 0;

  constructor(vertexCapacity: number, indexCapacity: number, withUvs: boolean, origin: ScenePoint = { x: 0, z: 0 }) {
    this.origin = origin;
    this.positions = new Float32Array(vertexCapacity * 3);
    this.normals = new Float32Array(vertexCapacity * 3);
    this.uvs = withUvs ? new Float32Array(vertexCapacity * 2) : null;
    this.indices = new Uint32Array(indexCapacity);
  }

  get full(): boolean {
    return this.vertexCount * 3 === this.positions.length && this.indexCount === this.indices.length;
  }
}

export interface SweepCaps {
  /** Close the profile across the start / end of the path (for a profile
   * made of one convex polyline, like the ballast bed). */
  readonly start: boolean;
  readonly end: boolean;
}

const NO_CAPS: SweepCaps = { start: false, end: false };

export interface SweepSize {
  vertices: number;
  indices: number;
}

/** Vertices and indices `sweepProfile` writes for a path of `pathPoints`. */
export function sweepSize(pathPoints: number, profile: Profile, caps: SweepCaps = NO_CAPS): SweepSize {
  let vertices = 0;
  let indices = 0;
  const capCount = (caps.start ? 1 : 0) + (caps.end ? 1 : 0);
  for (const line of profile) {
    const segments = line.length - 1;
    if (segments < 1) continue;
    // Each profile segment gets its own pair of vertices per path point,
    // so edges of the cross-section stay crisp (flat across, smooth along).
    vertices += segments * 2 * pathPoints;
    indices += segments * (pathPoints - 1) * 6;
    if (line.length >= 3) {
      vertices += capCount * line.length;
      indices += capCount * (line.length - 2) * 3;
    }
  }
  return { vertices, indices };
}

export interface SweepOptions {
  /** Sideways offset of the profile's origin from the path, positive to
   * the left of travel. */
  readonly lateral: number;
  /** Scene height of the profile's origin. */
  readonly y: number;
  /** Metres per texture repeat, both across (profile length) and along
   * (chainage). Ignored when the buffers have no UVs. */
  readonly uvRepeatM: number;
  readonly caps?: SweepCaps;
}

/**
 * Sweep `profile` along `path` into `out`. The profile's x axis follows
 * the perpendicular of the per-point tangent, so consecutive path segments
 * share their vertex rows and the surface has no gaps at corners.
 */
export function sweepProfile(out: MeshBuffers, path: ChainedPath, profile: Profile, options: SweepOptions): void {
  const { points, along, tangents } = path;
  const n = points.length;
  if (n < 2) throw new SweepError(`a path needs at least two points, got ${n}`);
  if (tangents.length !== n * 2 || along.length !== n) {
    throw new SweepError("path points, chainages and tangents differ in length");
  }
  const size = sweepSize(n, profile, options.caps);
  if ((out.vertexCount + size.vertices) * 3 > out.positions.length || out.indexCount + size.indices > out.indices.length) {
    throw new SweepError("sweep overruns its buffers; size them with sweepSize");
  }

  const { positions, normals, uvs, indices, origin } = out;
  const { lateral, y, uvRepeatM } = options;
  const caps = options.caps ?? NO_CAPS;

  const writeVertex = (i: number, px: number, py: number, nx: number, ny: number, nz: number, u: number): number => {
    // Left of travel is (tz, -tx): with up and the tangent it makes a
    // right-handed frame (side, up, along).
    const tx = tangents[i * 2]!;
    const tz = tangents[i * 2 + 1]!;
    const p = points[i]!;
    const v = out.vertexCount;
    const offset = lateral + px;
    positions[v * 3] = p.x - origin.x + tz * offset;
    positions[v * 3 + 1] = y + py;
    positions[v * 3 + 2] = p.z - origin.z - tx * offset;
    normals[v * 3] = nx;
    normals[v * 3 + 1] = ny;
    normals[v * 3 + 2] = nz;
    if (uvs) {
      uvs[v * 2] = u / uvRepeatM;
      uvs[v * 2 + 1] = along[i]! / uvRepeatM;
    }
    out.vertexCount = v + 1;
    return v;
  };

  for (const line of profile) {
    let across = 0;
    for (let s = 0; s < line.length - 1; s++) {
      const a = line[s]!;
      const b = line[s + 1]!;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const segmentLength = Math.hypot(dx, dy);
      // Outward normal in the profile plane: left of a clockwise traversal.
      const pnx = -dy / segmentLength;
      const pny = dx / segmentLength;
      const first = out.vertexCount;
      for (let i = 0; i < n; i++) {
        const tx = tangents[i * 2]!;
        const tz = tangents[i * 2 + 1]!;
        const nx = tz * pnx;
        const nz = -tx * pnx;
        writeVertex(i, a.x, a.y, nx, pny, nz, across);
        writeVertex(i, b.x, b.y, nx, pny, nz, across + segmentLength);
      }
      for (let i = 0; i < n - 1; i++) {
        const a0 = first + i * 2;
        const b0 = a0 + 1;
        const a1 = a0 + 2;
        const b1 = a0 + 3;
        const k = out.indexCount;
        indices[k] = a0;
        indices[k + 1] = a1;
        indices[k + 2] = b0;
        indices[k + 3] = b0;
        indices[k + 4] = a1;
        indices[k + 5] = b1;
        out.indexCount = k + 6;
      }
      across += segmentLength;
    }

    if (line.length < 3) continue;
    // A clockwise profile, fanned in order, faces back along the path:
    // right for the start cap, reversed for the end cap.
    for (const [cap, i, sign] of [
      [caps.start, 0, -1],
      [caps.end, n - 1, 1],
    ] as const) {
      if (!cap) continue;
      const tx = tangents[i * 2]!;
      const tz = tangents[i * 2 + 1]!;
      const first = out.vertexCount;
      for (const p of line) writeVertex(i, p.x, p.y, sign * tx, 0, sign * tz, p.x);
      for (let k = 1; k < line.length - 1; k++) {
        const j = out.indexCount;
        indices[j] = first;
        indices[j + 1] = sign < 0 ? first + k : first + k + 1;
        indices[j + 2] = sign < 0 ? first + k + 1 : first + k;
        out.indexCount = j + 3;
      }
    }
  }
}
