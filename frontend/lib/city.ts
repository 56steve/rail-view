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

// Per-vertex "shade": 0-1 is how far a wall vertex sits between the base
// and top colours; ROOF_SHADE marks roof vertices. Colours are applied
// from it by paintBuildings, so a theme change repaints tiles in place.
const ROOF_SHADE = -1;

export function buildTileGeometry(buffer: ArrayBuffer, tile: CityTile, quantum: number): THREE.BufferGeometry {
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
  const shades = new Float32Array(vertexTotal);
  const indices = new Uint32Array(indexTotal);
  const origin = latLonToScene(tile.origin.lat, tile.origin.lon);
  const ring: THREE.Vector2[] = [];

  let v = 0;
  let ix = 0;
  offset = 8;
  const put = (x: number, y: number, z: number, nx: number, ny: number, nz: number, shade: number) => {
    const k = v * 3;
    positions[k] = x;
    positions[k + 1] = y;
    positions[k + 2] = z;
    normals[k] = nx;
    normals[k + 1] = ny;
    normals[k + 2] = nz;
    shades[v] = shade;
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

    const topShade = Math.min(height / TALL_BUILDING_M, 1) * 0.6 + 0.4;

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
      const a0 = put(a.x, 0, a.y, nx, 0, nz, 0);
      const b0 = put(c.x, 0, c.y, nx, 0, nz, 0);
      const b1 = put(c.x, height, c.y, nx, 0, nz, topShade);
      const a1 = put(a.x, height, a.y, nx, 0, nz, topShade);
      indices.set([a0, b0, b1, a0, b1, a1], ix);
      ix += 6;
    }

    // Roof: triangulate the footprint, flipping any triangle that would
    // face down.
    const first = v;
    for (const p of ring) put(p.x, height, p.y, 0, 1, 0, ROOF_SHADE);
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
  geometry.setAttribute("shade", new THREE.BufferAttribute(shades, 1));
  geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(vertexTotal * 3), 3));
  // Degenerate footprints can triangulate to fewer faces than n-2.
  geometry.setIndex(new THREE.BufferAttribute(indices.subarray(0, ix), 1));
  geometry.computeBoundingSphere();
  return geometry;
}

/** Writes vertex colours for a tile from its per-vertex shade. */
export function paintBuildings(geometry: THREE.BufferGeometry, colors: BuildingColors): void {
  const shade = geometry.getAttribute("shade");
  const color = geometry.getAttribute("color");
  if (!(shade instanceof THREE.BufferAttribute) || !(color instanceof THREE.BufferAttribute)) {
    throw new CityTileError("building geometry is missing its shade or colour attribute");
  }
  const out = color.array as Float32Array;
  const scratch = new THREE.Color();
  for (let i = 0; i < shade.count; i++) {
    const t = shade.getX(i);
    const c = t === ROOF_SHADE ? colors.roof : scratch.copy(colors.base).lerp(colors.top, t);
    out[i * 3] = c.r;
    out[i * 3 + 1] = c.g;
    out[i * 3 + 2] = c.b;
  }
  color.needsUpdate = true;
}
