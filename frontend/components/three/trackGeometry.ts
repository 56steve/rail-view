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

/**
 * Untextured flat ribbons of `width` along every polyline, written straight
 * into one pre-sized buffer - for thousands of kilometres of road, where
 * building a geometry per road and merging them stalls the main thread.
 * Positions and indices only: the unlit ground material needs nothing else.
 */
export function flatRibbonsGeometry(lines: Point2[][], width: number, y: number): THREE.BufferGeometry {
  let vertexCount = 0;
  let indexCount = 0;
  for (const line of lines) {
    if (line.length < 2) continue;
    vertexCount += line.length * 2;
    indexCount += (line.length - 1) * 6;
  }
  const positions = new Float32Array(vertexCount * 3);
  const indices = new Uint32Array(indexCount);
  const half = width / 2;
  let v = 0;
  let ix = 0;
  for (const line of lines) {
    if (line.length < 2) continue;
    const first = v;
    for (let i = 0; i < line.length; i++) {
      const p = line[i]!;
      const prev = line[Math.max(i - 1, 0)]!;
      const next = line[Math.min(i + 1, line.length - 1)]!;
      const tx = next.x - prev.x;
      const tz = next.z - prev.z;
      const len = Math.hypot(tx, tz) || 1;
      const nx = (-tz / len) * half;
      const nz = (tx / len) * half;
      const k = v * 3;
      positions[k] = p.x + nx;
      positions[k + 1] = y;
      positions[k + 2] = p.z + nz;
      positions[k + 3] = p.x - nx;
      positions[k + 4] = y;
      positions[k + 5] = p.z - nz;
      v += 2;
    }
    for (let i = 0; i < line.length - 1; i++) {
      const a = first + i * 2;
      indices[ix] = a;
      indices[ix + 1] = a + 2;
      indices[ix + 2] = a + 1;
      indices[ix + 3] = a + 1;
      indices[ix + 4] = a + 2;
      indices[ix + 5] = a + 3;
      ix += 6;
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  geometry.computeBoundingSphere();
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
 * ribbon; one texture repeat = TEXTURE_REPEAT_M metres along it. Drawn in
 * light neutral greys and tinted by the material colour, so the far ribbon
 * matches the close-up ballast it takes over from. */
export function trackBedTexture(): THREE.CanvasTexture {
  const width = 64;
  const height = 128;
  const pxPerM = width / SINGLE_TRACK_BED_WIDTH_M;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable for track texture");

  ctx.fillStyle = "#AAA9A6";
  ctx.fillRect(0, 0, width, height);
  // Deterministic speckle so the ballast doesn't look flat.
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  for (let i = 0; i < 700; i++) {
    const shade = 130 + Math.floor(random() * 80);
    ctx.fillStyle = `rgb(${shade},${shade},${shade - 3})`;
    ctx.fillRect(random() * width, random() * height, 1.2, 1.2);
  }

  const gauge = 1.676;
  const pxPerMAlong = height / TEXTURE_REPEAT_M;
  const cx = width / 2;
  ctx.fillStyle = "#D6D4D0";
  for (let s = 0; s < TEXTURE_REPEAT_M; s += 0.66) {
    ctx.fillRect(cx - 1.4 * pxPerM, s * pxPerMAlong, 2.8 * pxPerM, 0.25 * pxPerMAlong);
  }
  ctx.fillStyle = "#F4F5F7";
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

/** Metres of ballast per repeat of `ballastTexture`, across and along. */
export const BALLAST_TEXTURE_M = 1.5;

/**
 * Loose ballast stone for the close-up track bed: a seamlessly tiling
 * 512px canvas, one repeat per BALLAST_TEXTURE_M. Drawn in neutral light
 * greys with a faint warm/cool spread, so the material colour sets the
 * day or night tone. Deterministic, so every load looks the same.
 */
export function ballastTexture(): THREE.CanvasTexture {
  const size = 512;
  const pxPerM = size / BALLAST_TEXTURE_M;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2D canvas unavailable for ballast texture");

  // The dark gaps between stones.
  ctx.fillStyle = "#5C5956";
  ctx.fillRect(0, 0, size, size);

  let seed = 20_231;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const outline: number[] = [];
  const fillStone = (x: number, y: number, scale: number): void => {
    ctx.beginPath();
    ctx.moveTo(x + outline[0]! * scale, y + outline[1]! * scale);
    for (let k = 2; k < outline.length; k += 2) ctx.lineTo(x + outline[k]! * scale, y + outline[k + 1]! * scale);
    ctx.closePath();
    ctx.fill();
  };
  for (let i = 0; i < 2400; i++) {
    // Crushed stone of roughly 30-65 mm, as irregular polygons.
    const cx = random() * size;
    const cy = random() * size;
    const radius = (0.015 + random() * 0.018) * pxPerM;
    const turn = random() * Math.PI * 2;
    const corners = 5 + Math.floor(random() * 3);
    outline.length = 0;
    for (let k = 0; k < corners; k++) {
      const a = turn + (k / corners) * Math.PI * 2;
      const r = radius * (0.7 + random() * 0.45);
      outline.push(Math.cos(a) * r, Math.sin(a) * r);
    }
    const shade = 150 + Math.floor(random() * 85);
    const warmth = Math.floor(random() * 14) - 5;
    const body = `rgb(${shade + warmth},${shade},${shade - warmth})`;
    const lit = `rgb(${Math.min(shade + 34, 255)},${Math.min(shade + 32, 255)},${Math.min(shade + 30, 255)})`;

    // Draw the stone again across any edge it overlaps, so the tile wraps.
    for (const ox of [-size, 0, size]) {
      if (cx + ox + radius * 1.3 < 0 || cx + ox - radius * 1.3 > size) continue;
      for (const oy of [-size, 0, size]) {
        if (cy + oy + radius * 1.3 < 0 || cy + oy - radius * 1.3 > size) continue;
        const x = cx + ox;
        const y = cy + oy;
        // Shadow falling down-right, the stone, then a lit face up-left.
        ctx.fillStyle = "rgba(20,18,16,0.45)";
        fillStone(x + radius * 0.18, y + radius * 0.22, 1);
        ctx.fillStyle = body;
        fillStone(x, y, 1);
        ctx.fillStyle = lit;
        fillStone(x - radius * 0.2, y - radius * 0.22, 0.5);
      }
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}
