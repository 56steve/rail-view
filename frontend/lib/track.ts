import { filletCorners, TRACK_FILLET } from "./curves";
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
 * same projection, so a server chainage maps to the same place here.
 *
 * The polyline's corners are rounded into arcs (see `filletCorners`), so a
 * train follows a curve rather than snapping round each OSM node. Chainage
 * still runs along the original polyline: a point on a straight keeps its
 * chainage, and each arc takes the chainage of the chord ends it replaces,
 * so `length` and every station's chainage are unchanged.
 */
export class TrackPath {
  readonly length: number;
  private readonly xs: Float64Array;
  private readonly zs: Float64Array;
  /** Chainage of each point, in increasing order. */
  private readonly chainages: Float64Array;

  constructor(polyline: [number, number][]) {
    if (polyline.length < 2) throw new Error("TrackPath needs at least two points");
    const scene = polyline.map(([lat, lon]) => latLonToScene(lat, lon));
    const { points, sourceAlong } = filletCorners(scene, TRACK_FILLET);
    this.xs = Float64Array.from(points, (p) => p.x);
    this.zs = Float64Array.from(points, (p) => p.z);
    this.chainages = sourceAlong;
    this.length = sourceAlong[sourceAlong.length - 1]!;
  }

  private segmentIndex(chainage: number): number {
    let lo = 0;
    let hi = this.chainages.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.chainages[mid]! <= chainage) lo = mid;
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
    const span = this.chainages[i + 1]! - this.chainages[i]!;
    const t = span > 0 ? (c - this.chainages[i]!) / span : 0;
    return { x: x0 + dx * t, z: z0 + dz * t, yaw: Math.atan2(-dx, -dz) };
  }

  /** Scene points covering [from, to] (either order), including every
   * interior point so curves are kept. */
  slice(from: number, to: number): { x: number; z: number }[] {
    const lo = Math.min(Math.max(Math.min(from, to), 0), this.length);
    const hi = Math.min(Math.max(Math.max(from, to), 0), this.length);
    const points = [this.sample(lo)];
    for (let i = this.segmentIndex(lo) + 1; i < this.chainages.length && this.chainages[i]! < hi; i++) {
      points.push({ x: this.xs[i]!, z: this.zs[i]!, yaw: 0 });
    }
    points.push(this.sample(hi));
    return points.map(({ x, z }) => ({ x, z }));
  }

  /** Every point, for drawing the whole line. */
  points(): { x: number; z: number }[] {
    return Array.from(this.xs, (x, i) => ({ x, z: this.zs[i]! }));
  }
}
