// Cuts the network's tracks into square tiles so close-up track can be
// built for just the ground around the camera.

import type { ScenePoint } from "../geo";
import { pathTangents, type ChainedPath } from "./sweep";

/** The part of one track that lies in one tile. */
export interface TrackPiece extends ChainedPath {
  /** Index of the track in the layout, stable across tiles. */
  readonly track: number;
  readonly points: ScenePoint[];
  readonly along: number[];
  readonly tangents: number[];
  /** Whether the bed should be closed off at this piece's start / end:
   * the track itself starts or ends there, or breaks at a corner too sharp
   * to join, rather than running on into the next tile. */
  readonly capStart: boolean;
  capEnd: boolean;
}

export interface TrackTile {
  readonly key: string;
  readonly ix: number;
  readonly iz: number;
  readonly pieces: TrackPiece[];
}

export function tileKey(ix: number, iz: number): string {
  return `${ix}:${iz}`;
}

// Cuts closer than this (as a fraction of the segment) to a segment's end
// or to each other are dropped, so no piece is a sliver.
const CUT_EPSILON = 1e-9;

// Real track never turns this sharply at a single point. Where OSM data does
// (a way digitised doubling back on itself), joining the segments would
// fold the bed flat along them, so the track is broken there instead.
const MAX_JOIN_TURN_COS = Math.cos(Math.PI / 4);

function segmentCuts(p0: number, p1: number, tileSize: number, into: number[]): void {
  if (p0 === p1) return;
  const lo = Math.min(p0, p1);
  const hi = Math.max(p0, p1);
  for (let k = Math.ceil(lo / tileSize); k * tileSize < hi; k++) {
    const t = (k * tileSize - p0) / (p1 - p0);
    if (t > CUT_EPSILON && t < 1 - CUT_EPSILON) into.push(t);
  }
}

/** A track as runs that can each be swept smoothly: repeated points are
 * dropped and the track is broken (sharing the corner point) wherever it
 * turns too sharply to join. */
export function smoothRuns(points: readonly ScenePoint[]): ScenePoint[][] {
  const clean = points.filter((p, i) => i === 0 || p.x !== points[i - 1]!.x || p.z !== points[i - 1]!.z);
  if (clean.length < 2) return [];
  const runs: ScenePoint[][] = [];
  let run: ScenePoint[] = [clean[0]!];
  for (let i = 1; i < clean.length; i++) {
    const p = clean[i]!;
    run.push(p);
    const next = clean[i + 1];
    if (!next) break;
    const prev = clean[i - 1]!;
    const ax = p.x - prev.x;
    const az = p.z - prev.z;
    const bx = next.x - p.x;
    const bz = next.z - p.z;
    if ((ax * bx + az * bz) / (Math.hypot(ax, az) * Math.hypot(bx, bz)) < MAX_JOIN_TURN_COS) {
      runs.push(run);
      run = [p];
    }
  }
  runs.push(run);
  return runs;
}

/**
 * Split every track at the tile edges it crosses. The cut point is shared
 * by the piece either side (same coordinates, chainage and tangent), so
 * geometry built per tile meets exactly at the edge. Tangents come from
 * the whole run of track, so the geometry doesn't depend on where the cuts
 * fall.
 */
export function splitIntoTiles(tracks: readonly (readonly ScenePoint[])[], tileSize: number): Map<string, TrackTile> {
  if (!(tileSize > 0)) throw new RangeError(`tile size must be positive, got ${tileSize}`);
  const tiles = new Map<string, TrackTile>();
  const cuts: number[] = [];

  const openPiece = (track: number, key: string, ix: number, iz: number, capStart: boolean): TrackPiece => {
    let tile = tiles.get(key);
    if (!tile) {
      tile = { key, ix, iz, pieces: [] };
      tiles.set(key, tile);
    }
    const piece: TrackPiece = { track, points: [], along: [], tangents: [], capStart, capEnd: false };
    tile.pieces.push(piece);
    return piece;
  };

  tracks.forEach((trackPoints, track) => {
    // Chainage runs on through breaks, so the sleeper spacing does too.
    let along = 0;
    for (const points of smoothRuns(trackPoints)) {
      const tangents = pathTangents(points);
      let piece: TrackPiece | null = null;
      let pieceKey = "";
      for (let i = 0; i < points.length - 1; i++) {
        const p = points[i]!;
        const q = points[i + 1]!;
        const length = Math.hypot(q.x - p.x, q.z - p.z);
        const startAlong = along;

        cuts.length = 0;
        segmentCuts(p.x, q.x, tileSize, cuts);
        segmentCuts(p.z, q.z, tileSize, cuts);
        cuts.sort((a, b) => a - b);
        cuts.push(1);

        // A point a fraction t of the way along this segment.
        const tx0 = tangents[i * 2]!;
        const tz0 = tangents[i * 2 + 1]!;
        const tx1 = tangents[i * 2 + 2]!;
        const tz1 = tangents[i * 2 + 3]!;
        const push = (target: TrackPiece, t: number): void => {
          if (t === 0 || t === 1) {
            target.points.push(t === 0 ? p : q);
            target.along.push(t === 0 ? startAlong : startAlong + length);
            target.tangents.push(t === 0 ? tx0 : tx1, t === 0 ? tz0 : tz1);
            return;
          }
          const tx = tx0 + (tx1 - tx0) * t;
          const tz = tz0 + (tz1 - tz0) * t;
          const norm = Math.hypot(tx, tz) || 1;
          target.points.push({ x: p.x + (q.x - p.x) * t, z: p.z + (q.z - p.z) * t });
          target.along.push(startAlong + length * t);
          target.tangents.push(tx / norm, tz / norm);
        };

        let t0 = 0;
        for (const t1 of cuts) {
          // Where a track crosses a tile corner its x and z cuts coincide.
          if (t1 - t0 <= CUT_EPSILON) continue;
          // Each sub-segment lies wholly in one tile; its midpoint says which.
          const mid = (t0 + t1) / 2;
          const ix = Math.floor((p.x + (q.x - p.x) * mid) / tileSize);
          const iz = Math.floor((p.z + (q.z - p.z) * mid) / tileSize);
          const key = tileKey(ix, iz);
          if (!piece || key !== pieceKey) {
            const previous: TrackPiece | null = piece;
            piece = openPiece(track, key, ix, iz, previous === null);
            pieceKey = key;
            if (previous) {
              // Carry the shared cut point over exactly.
              const last = previous.points.length - 1;
              piece.points.push(previous.points[last]!);
              piece.along.push(previous.along[last]!);
              piece.tangents.push(previous.tangents[last * 2]!, previous.tangents[last * 2 + 1]!);
            } else {
              push(piece, t0);
            }
          }
          push(piece, t1);
          t0 = t1;
        }
        along = startAlong + length;
      }
      if (piece) piece.capEnd = true;
    }
  });
  return tiles;
}

/** Horizontal distance from (x, z) to the nearest point of a tile. */
export function distanceToTile(tile: TrackTile, x: number, z: number, tileSize: number): number {
  const minX = tile.ix * tileSize;
  const minZ = tile.iz * tileSize;
  const dx = Math.max(minX - x, 0, x - (minX + tileSize));
  const dz = Math.max(minZ - z, 0, z - (minZ + tileSize));
  return Math.hypot(dx, dz);
}

/** The tiles with any part within `radius` of (x, z), nearest first. */
export function tilesNear(
  tiles: ReadonlyMap<string, TrackTile>,
  x: number,
  z: number,
  radius: number,
  tileSize: number,
): TrackTile[] {
  const found: { tile: TrackTile; distance: number }[] = [];
  const ix0 = Math.floor((x - radius) / tileSize);
  const ix1 = Math.floor((x + radius) / tileSize);
  const iz0 = Math.floor((z - radius) / tileSize);
  const iz1 = Math.floor((z + radius) / tileSize);
  for (let ix = ix0; ix <= ix1; ix++) {
    for (let iz = iz0; iz <= iz1; iz++) {
      const tile = tiles.get(tileKey(ix, iz));
      if (!tile) continue;
      const distance = distanceToTile(tile, x, z, tileSize);
      if (distance <= radius) found.push({ tile, distance });
    }
  }
  found.sort((a, b) => a.distance - b.distance);
  return found.map((f) => f.tile);
}
