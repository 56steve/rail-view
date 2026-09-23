// Decoder for frontend/public/city/tracks.bin, written by
// backend/scripts/build_osm_data.py: every individual OSM track (running
// lines, station loops, crossovers) and platform along the routes.
//   "RVT1"
//   u32 track count;    per track:    u32 n, n x (f32 east, f32 north)
//   u32 platform count; per platform: u32 n, n x (f32 east, f32 north)
// Coordinates are local metres from the shared projection origin (see
// lib/geo.ts); platform rings are counter-clockwise and not closed.

import type { ScenePoint } from "./geo";

export interface RailLayout {
  tracks: ScenePoint[][];
  platforms: ScenePoint[][];
}

export class RailLayoutError extends Error {}

export function decodeRailLayout(buffer: ArrayBuffer): RailLayout {
  const view = new DataView(buffer);
  if (view.byteLength < 12) throw new RailLayoutError("tracks.bin is truncated");
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== "RVT1") throw new RailLayoutError(`tracks.bin: bad magic "${magic}"`);

  let offset = 4;
  const readPolylines = (): ScenePoint[][] => {
    const count = view.getUint32(offset, true);
    offset += 4;
    const polylines: ScenePoint[][] = [];
    for (let i = 0; i < count; i++) {
      const n = view.getUint32(offset, true);
      offset += 4;
      if (offset + n * 8 > view.byteLength) throw new RailLayoutError("tracks.bin: polyline overruns the file");
      const points: ScenePoint[] = new Array(n);
      for (let k = 0; k < n; k++) {
        // Scene z is -north.
        points[k] = { x: view.getFloat32(offset, true), z: -view.getFloat32(offset + 4, true) };
        offset += 8;
      }
      polylines.push(points);
    }
    return polylines;
  };

  const tracks = readPolylines();
  const platforms = readPolylines();
  return { tracks, platforms };
}

export async function loadRailLayout(signal: AbortSignal): Promise<RailLayout> {
  const response = await fetch("/city/tracks.bin", { signal });
  if (!response.ok) throw new RailLayoutError(`tracks.bin: HTTP ${response.status}`);
  return decodeRailLayout(await response.arrayBuffer());
}
