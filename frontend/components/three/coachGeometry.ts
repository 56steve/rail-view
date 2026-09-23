import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// A Mumbai suburban EMU coach at true scale (metres). Local frame: x
// across the coach, y up from rail level, z along it with the front at -z
// (so `TrackPath` yaw points the front along the direction of travel).
//
// Procedural stand-in for a detailed GLB model: if one is dropped in,
// only this module (and the coach count/pitch it exports) needs to change.
export const COACH = {
  length: 20.7,
  width: 3.66,
  gap: 0.9,
} as const;
export const COACH_PITCH = COACH.length + COACH.gap;

const LIVERY = {
  body: "#C8CDD5",
  bodyUpper: "#DCE0E6",
  glass: "#1A222D",
  door: "#39424F",
  roof: "#8E959F",
  roofKit: "#6F7681",
  bogie: "#15181D",
  cabFront: "#F2C21B",
  cabStripe: "#D2372A",
  headlight: "#FFF7D6",
  destination: "#FFB547",
} as const;

type CoachKind = "cab" | "trailer";

function part(
  size: [number, number, number],
  center: [number, number, number],
  color: string,
): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(...size);
  geometry.translate(...center);
  geometry.deleteAttribute("uv");
  const c = new THREE.Color(color);
  const colors = new Float32Array(geometry.getAttribute("position").count * 3);
  for (let i = 0; i < colors.length; i += 3) {
    colors[i] = c.r;
    colors[i + 1] = c.g;
    colors[i + 2] = c.b;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

function buildCoach(kind: CoachKind, bandColor: string): THREE.BufferGeometry {
  const L = COACH.length;
  const W = COACH.width;
  const parts: THREE.BufferGeometry[] = [
    // bogies
    part([2.5, 0.9, 3.4], [0, 0.55, -L / 2 + 3.3], LIVERY.bogie),
    part([2.5, 0.9, 3.4], [0, 0.55, L / 2 - 3.3], LIVERY.bogie),
    part([W - 0.5, 0.35, L - 1.0], [0, 1.05, 0], LIVERY.bogie),
    // body
    part([W, 1.0, L], [0, 1.72, 0], LIVERY.body),
    part([W + 0.02, 0.3, L - 0.2], [0, 2.35, 0], bandColor),
    part([W + 0.02, 0.95, L - 1.6], [0, 2.98, 0], LIVERY.glass),
    part([W, 0.5, L], [0, 3.7, 0], LIVERY.bodyUpper),
    // doors (three per side; the box spans both sides)
    ...[-6.3, 0, 6.3].map((z) => part([W + 0.05, 2.35, 1.35], [0, 2.47, z], LIVERY.door)),
    // roof and roof-mounted AC units
    part([W - 0.35, 0.28, L - 0.5], [0, 4.09, 0], LIVERY.roof),
    part([1.7, 0.36, 3.0], [0, 4.41, -5.2], LIVERY.roofKit),
    part([1.7, 0.36, 3.0], [0, 4.41, 5.2], LIVERY.roofKit),
  ];

  if (kind === "cab") {
    const front = -L / 2;
    parts.push(
      part([W + 0.04, 2.95, 0.7], [0, 2.55, front - 0.15], LIVERY.cabFront),
      part([2.9, 1.05, 0.12], [0, 3.2, front - 0.55], LIVERY.glass),
      part([W + 0.06, 0.2, 0.74], [0, 1.95, front - 0.15], LIVERY.cabStripe),
      part([0.42, 0.24, 0.1], [-1.15, 1.55, front - 0.55], LIVERY.headlight),
      part([0.42, 0.24, 0.1], [1.15, 1.55, front - 0.55], LIVERY.headlight),
      part([1.5, 0.3, 0.1], [0, 3.92, front - 0.55], LIVERY.destination),
      // pantograph on the cab/motor coach
      part([0.12, 0.8, 0.12], [0, 4.65, -3.2], LIVERY.bogie),
      part([1.9, 0.08, 0.5], [0, 5.08, -3.2], LIVERY.bogie),
    );
  }

  const merged = mergeGeometries(parts);
  for (const geometry of parts) geometry.dispose();
  if (!merged) throw new Error("coach geometry merge failed");
  merged.computeBoundingSphere();
  return merged;
}

const cache = new Map<string, THREE.BufferGeometry>();

/** Shared, cached coach geometry for a kind + line band colour. */
export function coachGeometry(kind: CoachKind, bandColor: string): THREE.BufferGeometry {
  const key = `${kind}:${bandColor}`;
  let geometry = cache.get(key);
  if (!geometry) {
    geometry = buildCoach(kind, bandColor);
    cache.set(key, geometry);
  }
  return geometry;
}

let sharedMaterial: THREE.MeshStandardMaterial | null = null;

export function coachMaterial(): THREE.MeshStandardMaterial {
  sharedMaterial ??= new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, metalness: 0.25 });
  return sharedMaterial;
}
