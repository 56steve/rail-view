import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// Coach dimensions and rake formation shared by the scene, and the compact
// glyph drawn for trains seen from afar. Up close, trains are the Blender
// EMU model (emuModel.ts).
//
// Frame: x across the coach, y up from rail level, z along it with the
// front at -z (so `TrackPath` yaw points the front along the direction of
// travel). Dimensions from Indian Railways' EMU references (IRIMEE "Basics
// of EMU", Central Railway's AC EMU book): coaches 20.726 m long and
// 3.658 m wide over a 1,676 mm broad-gauge track.
export const COACH = {
  length: 20.73,
  width: 3.66,
  gap: 0.9,
} as const;
export const COACH_PITCH = COACH.length + COACH.gap;

export type CoachKind = "cab" | "motor" | "trailer";

const FLOOR_Y = 1.15;
const ROOF_Y = 4.0;

const GLYPH_COLOURS = {
  body: "#C9CED6",
  cab: "#F2C21B",
  acBand: "#1F5DB8",
} as const;

/** What distinguishes one rake's glyph from another's. */
export interface Livery {
  /** Band colour on non-AC rakes: the line's colour, so trains read by line
   * at city scale. */
  band: string;
  ac: boolean;
}

function paintedBox(size: [number, number, number], centre: [number, number, number], color: string): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(...size).toNonIndexed();
  geometry.translate(...centre);
  geometry.deleteAttribute("uv");
  const c = new THREE.Color(color);
  const count = geometry.getAttribute("position").count;
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) colors.set([c.r, c.g, c.b], i * 3);
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

/** The far-distance stand-in: a plain body with a band and a yellow cab
 * end - about a hundred triangles, since hundreds are drawn at once. */
function buildGlyph(livery: Livery): THREE.BufferGeometry {
  const L = COACH.length;
  const W = COACH.width;
  const parts = [
    paintedBox([W, ROOF_Y - FLOOR_Y, L], [0, (ROOF_Y + FLOOR_Y) / 2, 0], GLYPH_COLOURS.body),
    paintedBox([W + 0.04, 0.9, L - 0.3], [0, 2.1, 0], livery.ac ? GLYPH_COLOURS.acBand : livery.band),
    paintedBox([W + 0.06, ROOF_Y - FLOOR_Y - 0.2, 0.6], [0, (ROOF_Y + FLOOR_Y) / 2, -L / 2 + 0.2], GLYPH_COLOURS.cab),
  ];
  const merged = mergeGeometries(parts);
  for (const geometry of parts) geometry.dispose();
  if (!merged) throw new Error("coach glyph merge failed");
  merged.computeVertexNormals();
  merged.computeBoundingSphere();
  return merged;
}

const glyphCache = new Map<string, THREE.BufferGeometry>();

function liveryKey(livery: Livery): string {
  return livery.ac ? "ac" : `band:${livery.band}`;
}

/** Shared, cached low-detail geometry for a train seen from afar. */
export function coachGlyphGeometry(livery: Livery): THREE.BufferGeometry {
  const key = liveryKey(livery);
  let geometry = glyphCache.get(key);
  if (!geometry) {
    geometry = buildGlyph(livery);
    glyphCache.set(key, geometry);
  }
  return geometry;
}

/** Which coach of a rake is which: driving cabs at both ends, a motor
 * coach (with pantograph) leading each following three-coach unit. */
export function coachKindAt(index: number, coachCount: number): CoachKind {
  if (index === 0 || index === coachCount - 1) return "cab";
  return index % 3 === 0 ? "motor" : "trailer";
}

let sharedMaterial: THREE.MeshStandardMaterial | null = null;

/** The glyph's material: colours from its vertices. */
export function coachMaterial(): THREE.MeshStandardMaterial {
  sharedMaterial ??= new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.42, metalness: 0.3 });
  return sharedMaterial;
}
