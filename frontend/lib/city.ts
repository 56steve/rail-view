import * as THREE from "three";
import { latLonToScene } from "./geo";

// Decoder for the packed building tiles written by
// backend/scripts/build_osm_data.py (format documented in manifest.json):
//   "RVB1", u32 count, then per building:
//   u16 height (decimetres), u8 n, n x (i16 east, i16 north) quantised
//   offsets from the tile origin; rings are counter-clockwise in
//   (east, north) and not closed.

export interface CityTile {
  file: string;
  origin: { lat: number; lon: number };
  size_m: number;
  count: number;
}

export interface CityManifest {
  version: number;
  attribution: string;
  format: { coord_quantum_m: number };
  stats: { buildings: number; height_tagged: number; height_estimated: number };
  tiles: CityTile[];
}

export class CityTileError extends Error {}

export interface BuildingColors {
  base: THREE.Color;
  top: THREE.Color;
  roof: THREE.Color;
}

const TALL_BUILDING_M = 60;

export function buildTileGeometry(
  buffer: ArrayBuffer,
  tile: CityTile,
  quantum: number,
  colors: BuildingColors,
): THREE.BufferGeometry {
  const view = new DataView(buffer);
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== "RVB1") throw new CityTileError(`${tile.file}: bad magic "${magic}"`);
  const count = view.getUint32(4, true);

  // Pass 1: size the buffers exactly.
  let vertexTotal = 0;
  let indexTotal = 0;
  let offset = 8;
  for (let b = 0; b < count; b++) {
    const n = view.getUint8(offset + 2);
    vertexTotal += n * 4 + n; // wall quads + roof ring
    indexTotal += n * 6 + (n - 2) * 3;
    offset += 3 + n * 4;
  }

  const positions = new Float32Array(vertexTotal * 3);
  const normals = new Float32Array(vertexTotal * 3);
  const vertexColors = new Float32Array(vertexTotal * 3);
  const indices = new Uint32Array(indexTotal);
  const origin = latLonToScene(tile.origin.lat, tile.origin.lon);
  const topColor = new THREE.Color();
  const ring: THREE.Vector2[] = [];

  let v = 0;
  let ix = 0;
  offset = 8;
  const put = (x: number, y: number, z: number, nx: number, ny: number, nz: number, c: THREE.Color) => {
    const k = v * 3;
    positions[k] = x;
    positions[k + 1] = y;
    positions[k + 2] = z;
    normals[k] = nx;
    normals[k + 1] = ny;
    normals[k + 2] = nz;
    vertexColors[k] = c.r;
    vertexColors[k + 1] = c.g;
    vertexColors[k + 2] = c.b;
    return v++;
  };

  for (let b = 0; b < count; b++) {
    const height = view.getUint16(offset, true) / 10;
    const n = view.getUint8(offset + 2);
    offset += 3;
    ring.length = 0;
    for (let i = 0; i < n; i++) {
      const x = origin.x + view.getInt16(offset, true) * quantum;
      const z = origin.z - view.getInt16(offset + 2, true) * quantum;
      ring.push(new THREE.Vector2(x, z));
      offset += 4;
    }

    topColor.copy(colors.base).lerp(colors.top, Math.min(height / TALL_BUILDING_M, 1) * 0.6 + 0.4);

    // Walls: one quad per edge, with an outward normal. For a ring that is
    // counter-clockwise in (east, north), (a, b, b') faces outward.
    for (let i = 0; i < n; i++) {
      const a = ring[i]!;
      const c = ring[(i + 1) % n]!;
      const dx = c.x - a.x;
      const dz = c.y - a.y;
      const len = Math.hypot(dx, dz) || 1;
      const nx = -dz / len;
      const nz = dx / len;
      const a0 = put(a.x, 0, a.y, nx, 0, nz, colors.base);
      const b0 = put(c.x, 0, c.y, nx, 0, nz, colors.base);
      const b1 = put(c.x, height, c.y, nx, 0, nz, topColor);
      const a1 = put(a.x, height, a.y, nx, 0, nz, topColor);
      indices.set([a0, b0, b1, a0, b1, a1], ix);
      ix += 6;
    }

    // Roof: triangulate the footprint, flipping any triangle that would
    // face down.
    const first = v;
    for (const p of ring) put(p.x, height, p.y, 0, 1, 0, colors.roof);
    for (const [i0, i1, i2] of THREE.ShapeUtils.triangulateShape(ring, [])) {
      const p0 = ring[i0!]!;
      const p1 = ring[i1!]!;
      const p2 = ring[i2!]!;
      const up = (p1.y - p0.y) * (p2.x - p0.x) - (p1.x - p0.x) * (p2.y - p0.y) > 0;
      indices.set(up ? [first + i0!, first + i1!, first + i2!] : [first + i0!, first + i2!, first + i1!], ix);
      ix += 3;
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(vertexColors, 3));
  // Degenerate footprints can triangulate to fewer faces than n-2.
  geometry.setIndex(new THREE.BufferAttribute(indices.subarray(0, ix), 1));
  geometry.computeBoundingSphere();
  return geometry;
}
