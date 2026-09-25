import { describe, expect, it } from "vitest";
import type { ScenePoint } from "../geo";
import { distanceToTile, smoothRuns, splitIntoTiles, tileKey, tilesNear, type TrackPiece, type TrackTile } from "./tiles";

const TILE = 500;

function piecesOf(tiles: Map<string, TrackTile>, track: number): TrackPiece[] {
  return [...tiles.values()]
    .flatMap((tile) => tile.pieces)
    .filter((piece) => piece.track === track)
    .sort((a, b) => a.along[0]! - b.along[0]!);
}

function pathLength(points: readonly ScenePoint[]): number {
  let length = 0;
  for (let i = 1; i < points.length; i++) {
    length += Math.hypot(points[i]!.x - points[i - 1]!.x, points[i]!.z - points[i - 1]!.z);
  }
  return length;
}

describe("splitIntoTiles", () => {
  it("cuts a track exactly at each tile edge it crosses", () => {
    const tiles = splitIntoTiles([[{ x: -100, z: 10 }, { x: 1100, z: 10 }]], TILE);
    expect([...tiles.keys()].sort()).toEqual([tileKey(-1, 0), tileKey(0, 0), tileKey(1, 0), tileKey(2, 0)].sort());

    const pieces = piecesOf(tiles, 0);
    expect(pieces.map((p) => p.points.map((q) => q.x))).toEqual([
      [-100, 0],
      [0, 500],
      [500, 1000],
      [1000, 1100],
    ]);
    expect(pieces.map((p) => [p.capStart, p.capEnd])).toEqual([
      [true, false],
      [false, false],
      [false, false],
      [false, true],
    ]);
  });

  it("leaves no gap between neighbouring pieces: they share the cut point and its chainage", () => {
    // A curve that wanders across several tiles in both directions.
    const track: ScenePoint[] = [];
    for (let i = 0; i <= 60; i++) {
      const a = (i / 60) * Math.PI * 1.5;
      track.push({ x: 800 * Math.cos(a) + 37, z: 800 * Math.sin(a) - 12 });
    }
    const pieces = piecesOf(splitIntoTiles([track], TILE), 0);
    expect(pieces.length).toBeGreaterThan(4);

    for (let i = 1; i < pieces.length; i++) {
      const before = pieces[i - 1]!;
      const after = pieces[i]!;
      expect(after.points[0]).toEqual(before.points[before.points.length - 1]);
      expect(after.along[0]).toBe(before.along[before.along.length - 1]);
    }
    expect(pieces[0]!.points[0]).toEqual(track[0]);
    expect(pieces[pieces.length - 1]!.points.at(-1)).toEqual(track.at(-1));
    expect(pieces[pieces.length - 1]!.along.at(-1)).toBeCloseTo(pathLength(track), 6);
  });

  it("keeps every piece inside its own tile", () => {
    const track: ScenePoint[] = [
      { x: -730, z: 260 },
      { x: 20, z: -640 },
      { x: 990, z: 1480 },
    ];
    for (const tile of splitIntoTiles([track], TILE).values()) {
      for (const piece of tile.pieces) {
        for (const p of piece.points) {
          expect(p.x).toBeGreaterThanOrEqual(tile.ix * TILE - 1e-6);
          expect(p.x).toBeLessThanOrEqual((tile.ix + 1) * TILE + 1e-6);
          expect(p.z).toBeGreaterThanOrEqual(tile.iz * TILE - 1e-6);
          expect(p.z).toBeLessThanOrEqual((tile.iz + 1) * TILE + 1e-6);
        }
      }
    }
  });

  it("makes no sliver pieces where a track passes exactly through a tile corner", () => {
    const pieces = piecesOf(splitIntoTiles([[{ x: 100, z: 100 }, { x: 900, z: 900 }]], TILE), 0);
    expect(pieces.map((p) => p.points)).toEqual([
      [
        { x: 100, z: 100 },
        { x: 500, z: 500 },
      ],
      [
        { x: 500, z: 500 },
        { x: 900, z: 900 },
      ],
    ]);
  });

  it("starts a new piece at a vertex lying on a tile edge, and drops repeated points", () => {
    const track: ScenePoint[] = [
      { x: 400, z: 50 },
      { x: 500, z: 50 },
      { x: 500, z: 50 },
      { x: 650, z: 80 },
    ];
    const pieces = piecesOf(splitIntoTiles([track], TILE), 0);
    expect(pieces.map((p) => p.points.length)).toEqual([2, 2]);
    expect(pieces[1]!.points[0]).toEqual({ x: 500, z: 50 });
    expect(pieces[1]!.along[0]).toBe(100);
  });

  it("breaks a track that doubles back on itself, capping the bed at each break", () => {
    // Bad OSM data: forward, back a little, forward again.
    const track: ScenePoint[] = [
      { x: 0, z: 0 },
      { x: 200, z: 0 },
      { x: 140, z: 10 },
      { x: 400, z: 20 },
    ];
    const pieces = piecesOf(splitIntoTiles([track], TILE), 0);
    expect(pieces.map((p) => p.points)).toEqual([
      [track[0], track[1]],
      [track[1], track[2]],
      [track[2], track[3]],
    ]);
    expect(pieces.every((p) => p.capStart && p.capEnd)).toBe(true);
    // Each run follows its own segment rather than a folded-over bisector.
    for (const piece of pieces) {
      const [a, b] = piece.points as [ScenePoint, ScenePoint];
      const length = Math.hypot(b.x - a.x, b.z - a.z);
      for (let i = 0; i < 2; i++) {
        const along = (piece.tangents[i * 2]! * (b.x - a.x) + piece.tangents[i * 2 + 1]! * (b.z - a.z)) / length;
        expect(along).toBeCloseTo(1, 9);
      }
    }
    // Chainage carries on through the breaks.
    expect(pieces[1]!.along[0]).toBe(pieces[0]!.along[1]);
    expect(pieces[2]!.along[0]).toBe(pieces[1]!.along[1]);
  });

  it("returns nothing for a track with no length", () => {
    expect(splitIntoTiles([[{ x: 3, z: 4 }], [{ x: 1, z: 1 }, { x: 1, z: 1 }]], TILE).size).toBe(0);
  });
});

describe("smoothRuns", () => {
  it("keeps a curving track in one run", () => {
    const curve: ScenePoint[] = [];
    for (let d = 0; d <= 90; d += 5) {
      const a = (d * Math.PI) / 180;
      curve.push({ x: 300 * Math.cos(a), z: 300 * Math.sin(a) });
    }
    expect(smoothRuns(curve)).toEqual([curve]);
  });

  it("splits at a sharp corner, sharing the corner point", () => {
    const corner: ScenePoint[] = [
      { x: 0, z: 0 },
      { x: 10, z: 0 },
      { x: 10, z: 10 },
    ];
    expect(smoothRuns(corner)).toEqual([corner.slice(0, 2), corner.slice(1)]);
  });
});

describe("tilesNear", () => {
  const tiles = new Map<string, TrackTile>();
  for (let ix = -3; ix <= 3; ix++) {
    for (let iz = -3; iz <= 3; iz++) tiles.set(tileKey(ix, iz), { key: tileKey(ix, iz), ix, iz, pieces: [] });
  }

  it("finds the tiles within the radius, nearest first", () => {
    const near = tilesNear(tiles, 250, 250, 300, TILE);
    expect(near[0]!.key).toBe(tileKey(0, 0));
    expect(near.map((t) => t.key).sort()).toEqual(
      [tileKey(-1, 0), tileKey(0, -1), tileKey(0, 0), tileKey(0, 1), tileKey(1, 0)].sort(),
    );
    for (let i = 1; i < near.length; i++) {
      expect(distanceToTile(near[i]!, 250, 250, TILE)).toBeGreaterThanOrEqual(distanceToTile(near[i - 1]!, 250, 250, TILE));
    }
  });

  it("measures to the nearest corner for diagonal tiles", () => {
    expect(distanceToTile(tiles.get(tileKey(1, 1))!, 250, 250, TILE)).toBeCloseTo(Math.hypot(250, 250), 9);
    expect(tilesNear(tiles, 250, 250, 360, TILE).map((t) => t.key)).toContain(tileKey(1, 1));
  });

  it("skips tiles with no track", () => {
    expect(tilesNear(tiles, 10_000, 10_000, 700, TILE)).toEqual([]);
  });
});
