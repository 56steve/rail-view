// Decoders for the land cover and road layers written by
// backend/scripts/build_osm_data.py. Both start with a header giving the
// area they cover, so the client can fade them out towards its edges:
//   magic (4 bytes), f64 south, west, north, east
// landcover.bin ("RVC2"), pre-triangulated and quantised:
//   f64 origin east, f64 origin north, f64 quantum (metres), u32 class count;
//   per class: u32 vertex count, n x (i16 east, i16 north) offsets from
//   the origin in quanta, u8 index width (2 or 4), u32 index count, indices
// roads.bin ("RVR2"): f64 quantum (metres), u32 class count; per class:
//   u32 polyline count; per polyline u32 n, i32 first (east, north) in
//   quanta, then (n - 1) x i16 (east, north) steps
// Coordinates are local metres from the shared projection origin
// (lib/geo.ts). Classes are in the order of LANDCOVER_CLASSES /
// ROAD_CLASSES in components/three/palette.ts.

import { latLonToScene, type ScenePoint } from "./geo";

export class EnvironmentDataError extends Error {}

/** Scene-space rectangle a layer's data covers. */
export interface SceneBounds {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

export interface LandcoverMesh {
  /** Scene (x, z) pairs. */
  positions: Float32Array;
  indices: Uint32Array;
}

export interface LandcoverData {
  bounds: SceneBounds;
  classes: LandcoverMesh[];
}

export interface RoadData {
  bounds: SceneBounds;
  classes: ScenePoint[][][];
}

class Reader {
  private offset = 0;
  private readonly view: DataView;

  constructor(private readonly buffer: ArrayBuffer, private readonly name: string) {
    this.view = new DataView(buffer);
  }

  private need(bytes: number): void {
    if (this.offset + bytes > this.view.byteLength) throw new EnvironmentDataError(`${this.name} is truncated`);
  }

  magic(expected: string): void {
    this.need(4);
    const found = String.fromCharCode(...new Uint8Array(this.buffer, this.offset, 4));
    if (found !== expected) throw new EnvironmentDataError(`${this.name}: bad magic "${found}"`);
    this.offset += 4;
  }

  u32(): number {
    this.need(4);
    const value = this.view.getUint32(this.offset, true);
    this.offset += 4;
    return value;
  }

  f64(): number {
    this.need(8);
    const value = this.view.getFloat64(this.offset, true);
    this.offset += 8;
    return value;
  }

  i32(): number {
    this.need(4);
    const value = this.view.getInt32(this.offset, true);
    this.offset += 4;
    return value;
  }

  u8(): number {
    this.need(1);
    const value = this.view.getUint8(this.offset);
    this.offset += 1;
    return value;
  }

  /** `count` quantised (east, north) i16 pairs as scene (x, z) pairs. */
  quantisedScenePairs(count: number, originEast: number, originNorth: number, quantum: number): Float32Array {
    this.need(count * 4);
    const out = new Float32Array(count * 2);
    for (let i = 0; i < count; i++) {
      out[i * 2] = originEast + this.view.getInt16(this.offset, true) * quantum;
      out[i * 2 + 1] = -(originNorth + this.view.getInt16(this.offset + 2, true) * quantum);
      this.offset += 4;
    }
    return out;
  }

  /** `count` indices of `width` bytes each (2 or 4), widened to u32. */
  indices(count: number, width: number): Uint32Array {
    if (width !== 2 && width !== 4) throw new EnvironmentDataError(`${this.name}: bad index width ${width}`);
    this.need(count * width);
    // Copy element-wise: the source offset isn't guaranteed to be aligned.
    const out = new Uint32Array(count);
    for (let i = 0; i < count; i++) {
      const at = this.offset + i * width;
      out[i] = width === 2 ? this.view.getUint16(at, true) : this.view.getUint32(at, true);
    }
    this.offset += count * width;
    return out;
  }

  /** A delta-encoded polyline (i32 first point, i16 steps) as scene points. */
  steppedPolyline(count: number, quantum: number): ScenePoint[] {
    let east = this.i32();
    let north = this.i32();
    this.need((count - 1) * 4);
    const points: ScenePoint[] = [{ x: east * quantum, z: -north * quantum }];
    for (let i = 1; i < count; i++) {
      east += this.view.getInt16(this.offset, true);
      north += this.view.getInt16(this.offset + 2, true);
      this.offset += 4;
      points.push({ x: east * quantum, z: -north * quantum });
    }
    return points;
  }

  bounds(): SceneBounds {
    const south = this.f64();
    const west = this.f64();
    const north = this.f64();
    const east = this.f64();
    const sw = latLonToScene(south, west);
    const ne = latLonToScene(north, east);
    return { minX: sw.x, maxX: ne.x, minZ: ne.z, maxZ: sw.z };
  }
}

export function decodeLandcover(buffer: ArrayBuffer): LandcoverData {
  const reader = new Reader(buffer, "landcover.bin");
  reader.magic("RVC2");
  const bounds = reader.bounds();
  const originEast = reader.f64();
  const originNorth = reader.f64();
  const quantum = reader.f64();
  const classCount = reader.u32();
  const classes: LandcoverMesh[] = [];
  for (let c = 0; c < classCount; c++) {
    const positions = reader.quantisedScenePairs(reader.u32(), originEast, originNorth, quantum);
    const width = reader.u8();
    const indices = reader.indices(reader.u32(), width);
    classes.push({ positions, indices });
  }
  return { bounds, classes };
}

export function decodeRoads(buffer: ArrayBuffer): RoadData {
  const reader = new Reader(buffer, "roads.bin");
  reader.magic("RVR2");
  const bounds = reader.bounds();
  const quantum = reader.f64();
  const classCount = reader.u32();
  const classes: ScenePoint[][][] = [];
  for (let c = 0; c < classCount; c++) {
    const lineCount = reader.u32();
    const lines: ScenePoint[][] = [];
    for (let i = 0; i < lineCount; i++) {
      const count = reader.u32();
      if (count < 1) throw new EnvironmentDataError("roads.bin: empty polyline");
      lines.push(reader.steppedPolyline(count, quantum));
    }
    classes.push(lines);
  }
  return { bounds, classes };
}

export async function fetchBinary(path: string, signal: AbortSignal): Promise<ArrayBuffer> {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new EnvironmentDataError(`${path}: HTTP ${response.status}`);
  return response.arrayBuffer();
}
