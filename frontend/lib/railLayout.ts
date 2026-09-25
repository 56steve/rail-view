// Decoder for frontend/public/city/tracks.bin, written by
// backend/scripts/build_osm_data.py: every individual OSM track (running
// lines, station loops, crossovers) and platform along the routes.
//   "RVT1"
//   u32 track count;    per track:    u32 n, n x (f32 east, f32 north)
//   u32 platform count; per platform: u32 n, n x (f32 east, f32 north)
// Coordinates are local metres from the shared projection origin (see
// lib/geo.ts); platform rings are counter-clockwise and not closed.

import { filletCorners, TRACK_FILLET } from "./curves";
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

/** Unit direction from a polyline's end into the track, or null if every
 * point coincides. */
function endDirection(points: readonly ScenePoint[], atEnd: boolean): ScenePoint | null {
  const n = points.length;
  const end = points[atEnd ? n - 1 : 0]!;
  for (let k = 1; k < n; k++) {
    const p = points[atEnd ? n - 1 - k : k]!;
    const length = Math.hypot(p.x - end.x, p.z - end.z);
    if (length > 0) return { x: (p.x - end.x) / length, z: (p.z - end.z) / length };
  }
  return null;
}

/**
 * Tracks joined end to end wherever one OSM way simply carries on as
 * another: exactly two tracks end at the same point and the line turns
 * there by less than `maxTurnRad`. Left apart, each joint would stay a
 * corner, since a polyline's corners can only be rounded between its ends.
 * Junctions, where three or more tracks meet, are left as they are.
 */
export function joinContinuingTracks(tracks: readonly ScenePoint[][], maxTurnRad: number): ScenePoint[][] {
  // Track ends are numbered track * 2 (its start) and track * 2 + 1 (its end).
  const endsAt = new Map<string, number[]>();
  tracks.forEach((points, track) => {
    if (points.length < 2) return;
    for (const atEnd of [0, 1]) {
      const p = points[atEnd ? points.length - 1 : 0]!;
      const key = `${p.x},${p.z}`;
      const ends = endsAt.get(key);
      if (ends) ends.push(track * 2 + atEnd);
      else endsAt.set(key, [track * 2 + atEnd]);
    }
  });

  const partner = new Map<number, number>();
  const minCos = Math.cos(maxTurnRad);
  for (const ends of endsAt.values()) {
    if (ends.length !== 2) continue;
    const [a, b] = ends as [number, number];
    if (a >> 1 === b >> 1) continue; // a closed loop's own two ends
    const da = endDirection(tracks[a >> 1]!, (a & 1) === 1);
    const db = endDirection(tracks[b >> 1]!, (b & 1) === 1);
    // Arriving along -da and leaving along db.
    if (!da || !db || -(da.x * db.x + da.z * db.z) < minCos) continue;
    partner.set(a, b);
    partner.set(b, a);
  }

  const visited = new Uint8Array(tracks.length);
  const joined: ScenePoint[][] = [];
  const walk = (first: number, entry: number): void => {
    const chain: ScenePoint[] = [];
    let track = first;
    let enter = entry;
    while (!visited[track]) {
      visited[track] = 1;
      const points = enter === 0 ? tracks[track]! : tracks[track]!.slice().reverse();
      for (let k = chain.length === 0 ? 0 : 1; k < points.length; k++) chain.push(points[k]!);
      const next = partner.get(track * 2 + (1 - enter));
      if (next === undefined) break;
      track = next >> 1;
      enter = next & 1;
    }
    joined.push(chain);
  };
  // Chains start at a free end; what's left over is closed loops.
  tracks.forEach((_, track) => {
    if (!visited[track] && !partner.has(track * 2)) walk(track, 0);
  });
  tracks.forEach((_, track) => {
    if (!visited[track] && !partner.has(track * 2 + 1)) walk(track, 1);
  });
  tracks.forEach((_, track) => {
    if (!visited[track]) walk(track, 0);
  });
  return joined;
}

/** The layout's tracks as smooth curves: continuing tracks joined, and
 * every corner rounded into an arc. */
export function smoothTracks(tracks: readonly ScenePoint[][]): ScenePoint[][] {
  return joinContinuingTracks(tracks, TRACK_FILLET.maxTurnRad).map((points) => filletCorners(points, TRACK_FILLET).points);
}

/** tracks.bin, with its tracks smoothed for drawing. */
export async function loadRailLayout(signal: AbortSignal): Promise<RailLayout> {
  const response = await fetch("/city/tracks.bin", { signal });
  if (!response.ok) throw new RailLayoutError(`tracks.bin: HTTP ${response.status}`);
  const layout = decodeRailLayout(await response.arrayBuffer());
  return { tracks: smoothTracks(layout.tracks), platforms: layout.platforms };
}
