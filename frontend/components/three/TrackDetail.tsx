"use client";

import { useEffect, useMemo, useRef, type JSX } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { ScenePoint } from "@/lib/geo";
import {
  BALLAST_PROFILE,
  BALLAST_PROFILE_Y,
  RAIL_HEAD_PROFILE,
  RAIL_OFFSETS_M,
  RAIL_PROFILE_Y,
  RAIL_SIDE_PROFILE,
  SLEEPER_BOTTOM_Y,
  SLEEPER_BOX,
  SLEEPER_LENGTH_M,
  SLEEPER_SPACING_M,
  fasteningParts,
  type SleeperPart,
} from "@/lib/trackDetail/profiles";
import { SLEEPER_STRIDE, sleepersAlong } from "@/lib/trackDetail/sleepers";
import { MeshBuffers, sweepProfile, sweepSize, type SweepCaps } from "@/lib/trackDetail/sweep";
import { distanceToTile, splitIntoTiles, tilesNear, type TrackPiece, type TrackTile } from "@/lib/trackDetail/tiles";
import { usePalette, type TrackPalette } from "./palette";
import { BALLAST_TEXTURE_M, ballastTexture } from "./trackGeometry";

// Real track - ballast bed, sleepers, fastenings and rails - for the ground
// around the camera when it is close to the railway. The network is cut
// into square tiles once; tiles near the camera are built one per frame and
// freed again once the camera has moved away, so the cost stays bounded
// however much of Mumbai's railway there is. Farther out, the flat textured
// ribbon in RailLines stands in for it.

const TILE_SIZE_M = 500;
/** Track is built for tiles within this distance of the camera's ground point. */
const DETAIL_RADIUS_M = 700;
// Built tiles are kept until they're this far away, so panning back and
// forth across the edge of the radius doesn't rebuild the same tile.
const RELEASE_RADIUS_M = DETAIL_RADIUS_M + 200;
/** Camera height above which close-up track is neither built nor drawn. */
export const TRACK_DETAIL_MAX_HEIGHT_M = 400;
// Between the two heights built tiles are only hidden, so zooming out a
// little and back in again doesn't rebuild everything; above this they're
// freed.
const RELEASE_HEIGHT_M = 1200;
// Which tiles are wanted is worked out again once the camera has moved this far.
const RESCAN_STEP_M = 20;
// Pads and clips are a few centimetres across: past this they're well under
// a pixel, so tiles farther away skip drawing them.
const FASTENING_MAX_DISTANCE_M = 260;
// Beds of converging tracks overlap at turnouts; lifting each track's whole
// stack by a few millimetres more than its neighbour's stops their
// coplanar faces from z-fighting.
const LIFT_STEP_M = 0.004;
const LIFT_LEVELS = 4;

interface TrackResources {
  readonly ballastTexture: THREE.CanvasTexture;
  readonly ballast: THREE.MeshStandardMaterial;
  readonly rail: THREE.MeshStandardMaterial;
  readonly railHead: THREE.MeshStandardMaterial;
  readonly sleeper: THREE.MeshStandardMaterial;
  readonly fastening: THREE.MeshStandardMaterial;
  readonly sleeperGeometry: THREE.BufferGeometry;
  readonly fasteningGeometry: THREE.BufferGeometry;
}

interface BuiltTile {
  readonly tile: TrackTile;
  readonly root: THREE.Group;
  readonly fastenings: THREE.InstancedMesh | null;
  dispose(): void;
}

interface TileManager {
  readonly built: Map<string, BuiltTile>;
  /** Wanted tiles not built yet, nearest first. */
  queue: TrackTile[];
  /** Camera position at the last rescan; NaN until the first. */
  scanX: number;
  scanY: number;
  scanZ: number;
  shown: boolean;
}

type Vec3 = readonly [number, number, number];

// The faces of a box bar its underside: outward normal and two in-plane
// axes with u x v = normal, so corners taken (-,-) (+,-) (+,+) (-,+) wind
// counter-clockwise seen from outside.
const BOX_FACES: readonly (readonly [Vec3, Vec3, Vec3])[] = [
  [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
  [[0, 1, 0], [0, 0, 1], [1, 0, 0]],
  [[0, 0, 1], [1, 0, 0], [0, 1, 0]],
  [[0, 0, -1], [0, 1, 0], [1, 0, 0]],
];
const FACE_CORNERS: readonly (readonly [number, number])[] = [
  [-1, -1],
  [1, -1],
  [1, 1],
  [-1, 1],
];

/** Boxes with their undersides left off (they always sit on something),
 * merged into one geometry in the sleeper's frame. */
function boxesGeometry(parts: readonly SleeperPart[]): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  for (const { centre, size } of parts) {
    const [hx, hy, hz] = [size[0] / 2, size[1] / 2, size[2] / 2];
    for (const [n, u, v] of BOX_FACES) {
      const first = positions.length / 3;
      for (const [su, sv] of FACE_CORNERS) {
        positions.push(
          centre[0] + (n[0] + su * u[0] + sv * v[0]) * hx,
          centre[1] + (n[1] + su * u[1] + sv * v[1]) * hy,
          centre[2] + (n[2] + su * u[2] + sv * v[2]) * hz,
        );
        normals.push(...n);
      }
      indices.push(first, first + 1, first + 2, first, first + 2, first + 3);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  return geometry;
}

function createResources(): TrackResources {
  const texture = ballastTexture();
  return {
    ballastTexture: texture,
    ballast: new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 }),
    rail: new THREE.MeshStandardMaterial({ roughness: 0.75, metalness: 0.15 }),
    railHead: new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.55 }),
    sleeper: new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0 }),
    fastening: new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.35 }),
    sleeperGeometry: boxesGeometry([SLEEPER_BOX]),
    fasteningGeometry: boxesGeometry(fasteningParts()),
  };
}

function applyPalette(resources: TrackResources, palette: TrackPalette): void {
  resources.ballast.color.set(palette.ballast);
  resources.rail.color.set(palette.rail);
  resources.railHead.color.set(palette.railHead);
  resources.sleeper.color.set(palette.sleeper);
  resources.fastening.color.set(palette.fastening);
}

function disposeResources(resources: TrackResources): void {
  resources.ballastTexture.dispose();
  for (const material of [resources.ballast, resources.rail, resources.railHead, resources.sleeper, resources.fastening]) {
    material.dispose();
  }
  resources.sleeperGeometry.dispose();
  resources.fasteningGeometry.dispose();
}

function liftOf(piece: TrackPiece): number {
  return (piece.track % LIFT_LEVELS) * LIFT_STEP_M;
}

function capsOf(piece: TrackPiece): SweepCaps {
  return { start: piece.capStart, end: piece.capEnd };
}

function toGeometry(buffers: MeshBuffers): THREE.BufferGeometry {
  if (!buffers.full) throw new Error("track tile buffers were sized for a different amount of geometry");
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(buffers.positions, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(buffers.normals, 3));
  if (buffers.uvs) geometry.setAttribute("uv", new THREE.BufferAttribute(buffers.uvs, 2));
  geometry.setIndex(new THREE.BufferAttribute(buffers.indices, 1));
  geometry.computeBoundingSphere();
  return geometry;
}

/** Every track's ballast bed in the tile, in one geometry. */
function ballastGeometry(tile: TrackTile, origin: ScenePoint): THREE.BufferGeometry {
  let vertices = 0;
  let indices = 0;
  for (const piece of tile.pieces) {
    const size = sweepSize(piece.points.length, BALLAST_PROFILE, capsOf(piece));
    vertices += size.vertices;
    indices += size.indices;
  }
  const out = new MeshBuffers(vertices, indices, true, origin);
  for (const piece of tile.pieces) {
    sweepProfile(out, piece, BALLAST_PROFILE, {
      lateral: 0,
      y: BALLAST_PROFILE_Y + liftOf(piece),
      uvRepeatM: BALLAST_TEXTURE_M,
      caps: capsOf(piece),
    });
  }
  return toGeometry(out);
}

/** Every rail in the tile, in one geometry: the sides as group 0 and the
 * polished running surfaces as group 1. */
function railGeometry(tile: TrackTile, origin: ScenePoint): THREE.BufferGeometry {
  const layers = [RAIL_SIDE_PROFILE, RAIL_HEAD_PROFILE] as const;
  let vertices = 0;
  let indices = 0;
  for (const profile of layers) {
    for (const piece of tile.pieces) {
      const size = sweepSize(piece.points.length, profile);
      vertices += size.vertices * RAIL_OFFSETS_M.length;
      indices += size.indices * RAIL_OFFSETS_M.length;
    }
  }
  const out = new MeshBuffers(vertices, indices, false, origin);
  const groupStarts: number[] = [];
  for (const profile of layers) {
    groupStarts.push(out.indexCount);
    for (const piece of tile.pieces) {
      for (const lateral of RAIL_OFFSETS_M) {
        sweepProfile(out, piece, profile, { lateral, y: RAIL_PROFILE_Y + liftOf(piece), uvRepeatM: 1 });
      }
    }
  }
  const geometry = toGeometry(out);
  geometry.addGroup(0, groupStarts[1]!, 0);
  geometry.addGroup(groupStarts[1]!, out.indexCount - groupStarts[1]!, 1);
  return geometry;
}

/** One instance matrix per sleeper, relative to `origin`, and a sphere
 * round them all for frustum culling. */
function sleeperInstances(tile: TrackTile, origin: ScenePoint): { matrices: THREE.InstancedBufferAttribute; bounds: THREE.Sphere } | null {
  const placements = tile.pieces.map((piece) => sleepersAlong(piece, SLEEPER_SPACING_M));
  const count = placements.reduce((sum, p) => sum + p.length / SLEEPER_STRIDE, 0);
  if (count === 0) return null;

  const matrices = new Float32Array(count * 16);
  const box = new THREE.Box3();
  const corner = new THREE.Vector3();
  let m = 0;
  tile.pieces.forEach((piece, j) => {
    const sleepers = placements[j]!;
    const y = SLEEPER_BOTTOM_Y + liftOf(piece);
    for (let i = 0; i < sleepers.length; i += SLEEPER_STRIDE) {
      const x = sleepers[i]! - origin.x;
      const z = sleepers[i + 1]! - origin.z;
      const c = Math.cos(sleepers[i + 2]!);
      const s = Math.sin(sleepers[i + 2]!);
      // Column-major: rotation about +y by the heading, then translation.
      const k = m * 16;
      matrices[k] = c;
      matrices[k + 2] = -s;
      matrices[k + 5] = 1;
      matrices[k + 8] = s;
      matrices[k + 10] = c;
      matrices[k + 12] = x;
      matrices[k + 13] = y;
      matrices[k + 14] = z;
      matrices[k + 15] = 1;
      box.expandByPoint(corner.set(x, y, z));
      m += 1;
    }
  });
  const bounds = box.getBoundingSphere(new THREE.Sphere());
  bounds.radius += SLEEPER_LENGTH_M;
  return { matrices: new THREE.InstancedBufferAttribute(matrices, 16), bounds };
}

function instanced(
  geometry: THREE.BufferGeometry,
  material: THREE.Material,
  matrices: THREE.InstancedBufferAttribute,
  bounds: THREE.Sphere,
): THREE.InstancedMesh {
  // Created empty and given the prepared matrices, rather than filling a
  // buffer of identities first.
  const mesh = new THREE.InstancedMesh(geometry, material, 0);
  mesh.instanceMatrix = matrices;
  mesh.count = matrices.count;
  mesh.boundingSphere = bounds;
  return mesh;
}

function buildTile(tile: TrackTile, resources: TrackResources): BuiltTile {
  // Geometry is stored relative to the tile's corner, for float precision.
  const origin: ScenePoint = { x: tile.ix * TILE_SIZE_M, z: tile.iz * TILE_SIZE_M };
  const root = new THREE.Group();
  root.position.set(origin.x, 0, origin.z);

  const ballast = new THREE.Mesh(ballastGeometry(tile, origin), resources.ballast);
  const rails = new THREE.Mesh(railGeometry(tile, origin), [resources.rail, resources.railHead]);
  root.add(ballast, rails);

  let fastenings: THREE.InstancedMesh | null = null;
  const sleepers = sleeperInstances(tile, origin);
  if (sleepers) {
    root.add(instanced(resources.sleeperGeometry, resources.sleeper, sleepers.matrices, sleepers.bounds));
    // The fastenings sit at the same place on every sleeper, so they share
    // the sleepers' matrices.
    fastenings = instanced(resources.fasteningGeometry, resources.fastening, sleepers.matrices, sleepers.bounds);
    root.add(fastenings);
  }

  root.traverse((object) => {
    object.matrixAutoUpdate = false;
    object.updateMatrix();
  });
  root.updateMatrixWorld(true);

  return {
    tile,
    root,
    fastenings,
    dispose() {
      ballast.geometry.dispose();
      rails.geometry.dispose();
      // Releases the instance buffers; the shared geometries and materials
      // stay for other tiles.
      for (const child of root.children) {
        if (child instanceof THREE.InstancedMesh) child.dispose();
      }
    },
  };
}

function showFastenings(built: BuiltTile, x: number, y: number, z: number): void {
  if (!built.fastenings) return;
  const distance = Math.hypot(distanceToTile(built.tile, x, z, TILE_SIZE_M), y);
  built.fastenings.visible = distance < FASTENING_MAX_DISTANCE_M;
}

function release(manager: TileManager, key: string, group: THREE.Group | null): void {
  const built = manager.built.get(key);
  if (!built) return;
  group?.remove(built.root);
  built.dispose();
  manager.built.delete(key);
}

/** Close-up 3D track for every track in `tracks`, near the camera only. */
export function TrackDetail({ tracks }: { tracks: readonly (readonly ScenePoint[])[] }): JSX.Element {
  const palette = usePalette();
  const tiles = useMemo(() => splitIntoTiles(tracks, TILE_SIZE_M), [tracks]);
  const resources = useMemo(() => createResources(), []);
  const group = useRef<THREE.Group>(null);
  const manager = useRef<TileManager>({
    built: new Map(),
    queue: [],
    scanX: Number.NaN,
    scanY: Number.NaN,
    scanZ: Number.NaN,
    shown: false,
  });

  useEffect(() => applyPalette(resources, palette.track), [resources, palette]);
  useEffect(() => () => disposeResources(resources), [resources]);
  // New tiles (or unmounting): free everything built from the old ones and
  // scan afresh on the next frame.
  useEffect(() => {
    const state = manager.current;
    const parent = group.current;
    return () => {
      for (const key of [...state.built.keys()]) release(state, key, parent);
      state.queue = [];
      state.scanX = Number.NaN;
    };
  }, [tiles]);

  useFrame(({ camera }) => {
    const parent = group.current;
    if (!parent) return;
    const state = manager.current;
    const { x, y, z } = camera.position;
    const shown = y < TRACK_DETAIL_MAX_HEIGHT_M;
    parent.visible = shown;

    const moved = Math.hypot(x - state.scanX, y - state.scanY, z - state.scanZ);
    if (shown !== state.shown || !(moved < RESCAN_STEP_M)) {
      state.scanX = x;
      state.scanY = y;
      state.scanZ = z;
      state.shown = shown;
      const keep =
        y < RELEASE_HEIGHT_M ? new Set(tilesNear(tiles, x, z, RELEASE_RADIUS_M, TILE_SIZE_M).map((t) => t.key)) : null;
      for (const key of [...state.built.keys()]) {
        if (!keep?.has(key)) release(state, key, parent);
      }
      state.queue = shown ? tilesNear(tiles, x, z, DETAIL_RADIUS_M, TILE_SIZE_M).filter((t) => !state.built.has(t.key)) : [];
      for (const built of state.built.values()) showFastenings(built, x, y, z);
    }

    // One tile per frame keeps each frame's extra work to a few milliseconds.
    const next = shown ? state.queue.shift() : undefined;
    if (!next) return;
    try {
      const built = buildTile(next, resources);
      showFastenings(built, x, y, z);
      state.built.set(next.key, built);
      parent.add(built.root);
    } catch (error: unknown) {
      console.error(`RailView: close-up track for tile ${next.key} failed to build`, error);
    }
  });

  return <group ref={group} />;
}
