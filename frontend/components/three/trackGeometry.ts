import * as THREE from "three";

// World-space geometry for the railway: a textured ballast ribbon per
// individual track, and extruded platforms.

/** Ballast shoulder of one broad-gauge track. Track centres in Mumbai are
 * ~4.6-5.3m apart, so neighbouring beds just meet. */
export const SINGLE_TRACK_BED_WIDTH_M = 4.6;
const TEXTURE_REPEAT_M = 4;

interface Point2 {
  x: number;
  z: number;
}

/** Per-vertex left-hand normals (in XZ), averaging adjacent segments so
 * strips stay unbroken through corners. */
function vertexNormals(points: Point2[]): Point2[] {
  return points.map((p, i) => {
    const prev = points[Math.max(i - 1, 0)]!;
    const next = points[Math.min(i + 1, points.length - 1)]!;
    const tx = next.x - prev.x;
    const tz = next.z - prev.z;
    const len = Math.hypot(tx, tz) || 1;
    return { x: -tz / len, z: tx / len };
  });
}

/** A flat textured ribbon of `width` along `points`, v in metres/repeat. */
export function ribbonGeometry(points: Point2[], width: number, y: number): THREE.BufferGeometry {
  const normals = vertexNormals(points);
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];
  let along = 0;
  points.forEach((p, i) => {
    if (i > 0) along += Math.hypot(p.x - points[i - 1]!.x, p.z - points[i - 1]!.z);
    const n = normals[i]!;
    positions.push(p.x + (n.x * width) / 2, y, p.z + (n.z * width) / 2);
    positions.push(p.x - (n.x * width) / 2, y, p.z - (n.z * width) / 2);
    uvs.push(0, along / TEXTURE_REPEAT_M, 1, along / TEXTURE_REPEAT_M);
    if (i > 0) {
      const a = (i - 1) * 2;
      indices.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** Flat-topped prisms from counter-clockwise (east, north) footprints,
 * already in scene space (x = east, z = -north): top face plus walls. */
export function extrudedFootprintsGeometry(rings: Point2[][], height: number): THREE.BufferGeometry {
  const positions: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  const put = (x: number, y: number, z: number, nx: number, ny: number, nz: number) => {
    positions.push(x, y, z);
    normals.push(nx, ny, nz);
    return positions.length / 3 - 1;
  };

  for (const ring of rings) {
    const n = ring.length;
    if (n < 3) continue;
    for (let i = 0; i < n; i++) {
      const a = ring[i]!;
      const b = ring[(i + 1) % n]!;
      const dx = b.x - a.x;
      const dz = b.z - a.z;
      const len = Math.hypot(dx, dz) || 1;
      // For a ring counter-clockwise in (east, north), (-dz, dx) points
      // outward in scene space and (a, b, b') faces it.
      const nx = -dz / len;
      const nz = dx / len;
      const a0 = put(a.x, 0, a.z, nx, 0, nz);
      const b0 = put(b.x, 0, b.z, nx, 0, nz);
      const b1 = put(b.x, height, b.z, nx, 0, nz);
      const a1 = put(a.x, height, a.z, nx, 0, nz);
      indices.push(a0, b0, b1, a0, b1, a1);
    }
    const contour = ring.map((p) => new THREE.Vector2(p.x, p.z));
    const first = positions.length / 3;
    for (const p of ring) put(p.x, height, p.z, 0, 1, 0);
    for (const [i0, i1, i2] of THREE.ShapeUtils.triangulateShape(contour, [])) {
      const p0 = contour[i0!]!;
      const p1 = contour[i1!]!;
      const p2 = contour[i2!]!;
      // Wind every roof triangle to face up (+y) regardless of ring order.
      const up = (p1.x - p0.x) * (p2.y - p0.y) - (p1.y - p0.y) * (p2.x - p0.x) < 0;
      indices.push(...(up ? [first + i0!, first + i1!, first + i2!] : [first + i0!, first + i2!, first + i1!]));
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.setIndex(indices);
  geometry.computeBoundingSphere();
  return geometry;
}

/** Ballast, sleepers and one broad-gauge (1676mm) track across the
 * ribbon; one texture repeat = TEXTURE_REPEAT_M metres along it. */
export function trackBedTexture(): THREE.CanvasTexture {
  const width = 64;
  const height = 128;
  const pxPerM = width / SINGLE_TRACK_BED_WIDTH_M;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable for track texture");

  ctx.fillStyle = "#3A3D43";
  ctx.fillRect(0, 0, width, height);
  // Deterministic speckle so the ballast doesn't look flat.
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  for (let i = 0; i < 700; i++) {
    const shade = 44 + Math.floor(random() * 40);
    ctx.fillStyle = `rgb(${shade},${shade},${shade + 4})`;
    ctx.fillRect(random() * width, random() * height, 1.2, 1.2);
  }

  const gauge = 1.676;
  const pxPerMAlong = height / TEXTURE_REPEAT_M;
  const cx = width / 2;
  ctx.fillStyle = "#4B4038";
  for (let s = 0; s < TEXTURE_REPEAT_M; s += 0.66) {
    ctx.fillRect(cx - 1.4 * pxPerM, s * pxPerMAlong, 2.8 * pxPerM, 0.25 * pxPerMAlong);
  }
  ctx.fillStyle = "#C9CED6";
  for (const side of [-gauge / 2, gauge / 2]) {
    ctx.fillRect(cx + side * pxPerM - 0.6, 0, 1.2, height);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}
