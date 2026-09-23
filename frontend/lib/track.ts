import { latLonToScene } from "./geo";

export interface TrackSample {
  x: number;
  z: number;
  /**
   * Three.js rotation.y that points an object's local forward axis (-Z)
   * along the direction of increasing chainage.
   */
  yaw: number;
}

/**
 * A line's track in scene space, addressable by chainage (metres along the
 * track from the line's first station) - the same parametrisation the
 * backend matches positions onto, built from the same polyline and the
 * same projection, so a server chainage maps to the identical point here.
 */
export class TrackPath {
  readonly length: number;
  private readonly xs: Float64Array;
  private readonly zs: Float64Array;
  private readonly cumulative: Float64Array;

  constructor(polyline: [number, number][]) {
    if (polyline.length < 2) throw new Error("TrackPath needs at least two points");
    const n = polyline.length;
    this.xs = new Float64Array(n);
    this.zs = new Float64Array(n);
    this.cumulative = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const [lat, lon] = polyline[i]!;
      const p = latLonToScene(lat, lon);
      this.xs[i] = p.x;
      this.zs[i] = p.z;
      if (i > 0) {
        this.cumulative[i] =
          this.cumulative[i - 1]! + Math.hypot(p.x - this.xs[i - 1]!, p.z - this.zs[i - 1]!);
      }
    }
    this.length = this.cumulative[n - 1]!;
  }

  private segmentIndex(chainage: number): number {
    let lo = 0;
    let hi = this.cumulative.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.cumulative[mid]! <= chainage) lo = mid;
      else hi = mid;
    }
    return lo;
  }

  sample(chainage: number): TrackSample {
    const c = Math.min(Math.max(chainage, 0), this.length);
    const i = this.segmentIndex(c);
    const x0 = this.xs[i]!;
    const z0 = this.zs[i]!;
    const dx = this.xs[i + 1]! - x0;
    const dz = this.zs[i + 1]! - z0;
    const span = this.cumulative[i + 1]! - this.cumulative[i]!;
    const t = span > 0 ? (c - this.cumulative[i]!) / span : 0;
    return { x: x0 + dx * t, z: z0 + dz * t, yaw: Math.atan2(-dx, -dz) };
  }

  /** Scene points covering [from, to] (either order), including every
   * interior vertex so curves are kept. */
  slice(from: number, to: number): { x: number; z: number }[] {
    const lo = Math.min(Math.max(Math.min(from, to), 0), this.length);
    const hi = Math.min(Math.max(Math.max(from, to), 0), this.length);
    const points = [this.sample(lo)];
    for (let i = this.segmentIndex(lo) + 1; i < this.cumulative.length && this.cumulative[i]! < hi; i++) {
      points.push({ x: this.xs[i]!, z: this.zs[i]!, yaw: 0 });
    }
    points.push(this.sample(hi));
    return points.map(({ x, z }) => ({ x, z }));
  }

  /** Every vertex, for drawing the whole line. */
  points(): { x: number; z: number }[] {
    return Array.from(this.xs, (x, i) => ({ x, z: this.zs[i]! }));
  }
}
