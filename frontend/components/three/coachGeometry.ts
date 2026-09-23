import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

// A Mumbai suburban EMU coach at true scale, in metres, built low-poly so
// a dozen rakes can be on screen on a phone. Local frame: x across the
// coach, y up from rail level, z along it with the front at -z (so
// `TrackPath` yaw points the front along the direction of travel).
//
// Dimensions from Indian Railways' EMU references (IRIMEE "Basics of EMU",
// Central Railway's AC EMU book): coaches 20.726 m long and 3.658 m wide
// over a 1,676 mm broad-gauge track. Look from photos of the current
// Siemens/Bombardier/Medha rakes: flat stainless sides curving into the
// roof, three wide doorways a side (left open on non-AC rakes), a yellow
// driving cab, and on AC rakes a silver body with a blue band and
// red/yellow stripes, closed sliding doors and roof-mounted AC units.
//
// A detailed GLB can replace this module; only `coachGeometry`,
// `coachGlyphGeometry` and the constants below are used elsewhere.
export const COACH = {
  length: 20.73,
  width: 3.66,
  gap: 0.9,
} as const;
export const COACH_PITCH = COACH.length + COACH.gap;

export type CoachKind = "cab" | "motor" | "trailer";

const GAUGE_M = 1.676;
const FLOOR_Y = 1.15;
const SIDE_TOP_Y = 3.15; // sides are vertical up to here, then curve into the roof
const ROOF_Y = 4.0;
const DOOR_CENTRES = [-6.3, 0, 6.3];
const DOOR_WIDTH = 1.35;
const WINDOW_BOTTOM_Y = 2.08;
const WINDOW_HEIGHT = 0.95;
const CAB_LENGTH = 2.3; // driver's cab at the front of a cab coach
const DOOR_BOTTOM_Y = FLOOR_Y + 0.05;
const DOOR_HEIGHT = SIDE_TOP_Y - DOOR_BOTTOM_Y; // up to where the side starts curving
const CAB_SPLIT_Y = 1.85; // yellow nose above, dark lower panel below

const PALETTE = {
  stainless: "#C9CED6",
  stainlessDark: "#AEB4BD",
  roofKit: "#7C838E",
  glass: "#18202B",
  doorway: "#0F1318",
  pole: "#C3C8CF",
  underframe: "#262B32",
  bogie: "#16191E",
  wheel: "#3A3F46",
  cabYellow: "#F2C21B",
  cabLower: "#3A3F47",
  headlight: "#FFF6D8",
  tailLight: "#D8352A",
  destination: "#FFB547",
  acBlue: "#1F5DB8",
  acRed: "#D23A2E",
  acYellow: "#F2C21B",
} as const;

/** What distinguishes one rake's look from another's. */
export interface Livery {
  /** Band colour on non-AC rakes: the line's colour, like the real bands. */
  band: string;
  ac: boolean;
}

// -- building blocks ---------------------------------------------------------

function paint(geometry: THREE.BufferGeometry, color: string): THREE.BufferGeometry {
  const flat = geometry.index ? geometry.toNonIndexed() : geometry;
  if (flat !== geometry) geometry.dispose();
  flat.deleteAttribute("uv");
  const c = new THREE.Color(color);
  const count = flat.getAttribute("position").count;
  const colors = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    colors[i * 3] = c.r;
    colors[i * 3 + 1] = c.g;
    colors[i * 3 + 2] = c.b;
  }
  flat.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return flat;
}

function box(size: [number, number, number], centre: [number, number, number], color: string): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(...size);
  geometry.translate(...centre);
  return paint(geometry, color);
}

/** A thin panel on both sides of the body (windows, doors, bands). */
function sidePanels(
  zCentre: number,
  zLength: number,
  yBottom: number,
  height: number,
  color: string,
  proud = 0.015,
): THREE.BufferGeometry[] {
  const x = COACH.width / 2 + proud / 2;
  return [-x, x].map((px) => box([proud, height, zLength], [px, yBottom + height / 2, zCentre], color));
}

/** The body shell: the real cross-section - flat sides, a curved roof -
 * extruded along the coach. */
function shell(length: number, zCentre: number, color: string): THREE.BufferGeometry {
  const hw = COACH.width / 2;
  const roofEdge = hw - 0.12;
  const shape = new THREE.Shape();
  shape.moveTo(-hw, FLOOR_Y);
  shape.lineTo(hw, FLOOR_Y);
  shape.lineTo(hw, SIDE_TOP_Y);
  shape.quadraticCurveTo(hw, SIDE_TOP_Y + 0.4, roofEdge, SIDE_TOP_Y + 0.5);
  shape.quadraticCurveTo(0, ROOF_Y + 0.12, -roofEdge, SIDE_TOP_Y + 0.5);
  shape.quadraticCurveTo(-hw, SIDE_TOP_Y + 0.4, -hw, SIDE_TOP_Y);
  shape.closePath();
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false, curveSegments: 5 });
  geometry.translate(0, 0, zCentre - length / 2);
  return paint(geometry, color);
}

function wheelset(z: number): THREE.BufferGeometry[] {
  return [-GAUGE_M / 2, GAUGE_M / 2].map((x) => {
    const wheel = new THREE.CylinderGeometry(0.46, 0.46, 0.14, 10);
    wheel.rotateZ(Math.PI / 2);
    wheel.translate(x, 0.46, z);
    return paint(wheel, PALETTE.wheel);
  });
}

function bogie(z: number): THREE.BufferGeometry[] {
  return [
    box([2.3, 0.55, 3.1], [0, 0.72, z], PALETTE.bogie),
    ...wheelset(z - 1.25),
    ...wheelset(z + 1.25),
  ];
}

/** Evenly spaced windows between `zFrom` and `zTo` on both sides. */
function windowRun(zFrom: number, zTo: number, count: number): THREE.BufferGeometry[] {
  const span = zTo - zFrom;
  const width = Math.min(0.95, (span / count) * 0.72);
  const parts: THREE.BufferGeometry[] = [];
  for (let i = 0; i < count; i++) {
    const z = zFrom + (span * (i + 0.5)) / count;
    parts.push(...sidePanels(z, width, WINDOW_BOTTOM_Y, WINDOW_HEIGHT, PALETTE.glass));
  }
  return parts;
}

function doorway(z: number, livery: Livery): THREE.BufferGeometry[] {
  if (livery.ac) {
    // Closed sliding doors with a window in each leaf.
    return [
      ...sidePanels(z, DOOR_WIDTH, DOOR_BOTTOM_Y, DOOR_HEIGHT, PALETTE.stainlessDark),
      ...sidePanels(z - DOOR_WIDTH / 4, DOOR_WIDTH * 0.36, WINDOW_BOTTOM_Y + 0.05, 0.85, PALETTE.glass, 0.03),
      ...sidePanels(z + DOOR_WIDTH / 4, DOOR_WIDTH * 0.36, WINDOW_BOTTOM_Y + 0.05, 0.85, PALETTE.glass, 0.03),
    ];
  }
  // Mumbai's non-AC locals run with their doorways open: a dark opening
  // with the grab pole standing in the middle.
  return [
    ...sidePanels(z, DOOR_WIDTH, DOOR_BOTTOM_Y, DOOR_HEIGHT, PALETTE.doorway),
    ...sidePanels(z, 0.05, DOOR_BOTTOM_Y + 0.1, DOOR_HEIGHT - 0.2, PALETTE.pole, 0.06),
  ];
}

function bands(zFrom: number, zTo: number, livery: Livery): THREE.BufferGeometry[] {
  const length = zTo - zFrom;
  const z = (zFrom + zTo) / 2;
  if (livery.ac) {
    return [
      ...sidePanels(z, length, 1.3, 0.55, PALETTE.acBlue, 0.012),
      ...sidePanels(z, length, 1.88, 0.07, PALETTE.acRed, 0.012),
      ...sidePanels(z, length, 1.97, 0.06, PALETTE.acYellow, 0.012),
    ];
  }
  return [
    ...sidePanels(z, length, 1.72, 0.26, livery.band, 0.012),
    ...sidePanels(z, length, WINDOW_BOTTOM_Y + WINDOW_HEIGHT + 0.03, 0.07, livery.band, 0.012),
  ];
}

function roofEquipment(kind: CoachKind, livery: Livery): THREE.BufferGeometry[] {
  const parts: THREE.BufferGeometry[] = [];
  if (livery.ac) {
    parts.push(
      box([2.0, 0.42, 3.2], [0, ROOF_Y + 0.25, -5.4], PALETTE.roofKit),
      box([2.0, 0.42, 3.2], [0, ROOF_Y + 0.25, 5.4], PALETTE.roofKit),
    );
  } else {
    // A row of roof ventilators.
    for (let i = 0; i < 7; i++) {
      parts.push(box([0.55, 0.16, 0.8], [0, ROOF_Y + 0.12, -7.8 + i * 2.6], PALETTE.roofKit));
    }
  }
  if (kind !== "trailer") {
    // Pantograph on the motor coaches, folded down.
    const z = kind === "cab" ? -COACH.length / 2 + 5.2 : -3.2;
    parts.push(
      box([1.3, 0.12, 1.5], [0, ROOF_Y + 0.3, z], PALETTE.bogie),
      box([0.1, 0.55, 0.1], [0, ROOF_Y + 0.6, z - 0.45], PALETTE.bogie),
      box([1.9, 0.08, 0.45], [0, ROOF_Y + 0.9, z - 0.2], PALETTE.bogie),
    );
  }
  return parts;
}

function cabFront(front: number): THREE.BufferGeometry[] {
  const W = COACH.width;
  const face = front - 0.06;
  return [
    // Yellow driving-cab nose over a dark lower panel and coupler.
    box([W + 0.03, ROOF_Y - 0.05 - CAB_SPLIT_Y, 0.5], [0, (ROOF_Y - 0.05 + CAB_SPLIT_Y) / 2, front + 0.2], PALETTE.cabYellow),
    box([W + 0.03, CAB_SPLIT_Y - 0.95, 0.5], [0, (CAB_SPLIT_Y + 0.95) / 2, front + 0.2], PALETTE.cabLower),
    box([0.5, 0.35, 0.5], [0, 0.95, front - 0.2], PALETTE.underframe),
    // Two-pane windscreen and the route display above it.
    box([1.45, 1.0, 0.06], [-0.8, 3.0, face], PALETTE.glass),
    box([1.45, 1.0, 0.06], [0.8, 3.0, face], PALETTE.glass),
    box([1.3, 0.24, 0.06], [0, 3.72, face], PALETTE.destination),
    // Headlights, a roof headlight, and red tail lamps.
    box([0.38, 0.22, 0.06], [-1.25, 2.12, face], PALETTE.headlight),
    box([0.38, 0.22, 0.06], [1.25, 2.12, face], PALETTE.headlight),
    box([0.34, 0.2, 0.08], [0, 3.95, face], PALETTE.headlight),
    box([0.18, 0.18, 0.06], [-1.62, 1.72, face], PALETTE.tailLight),
    box([0.18, 0.18, 0.06], [1.62, 1.72, face], PALETTE.tailLight),
    // Side windows of the driver's cab.
    ...sidePanels(front + 1.2, 0.8, 2.35, 0.75, PALETTE.glass),
  ];
}

// -- coaches -----------------------------------------------------------------

function buildCoach(kind: CoachKind, livery: Livery): THREE.BufferGeometry {
  const L = COACH.length;
  const front = -L / 2;
  const back = L / 2;
  const cabEnd = kind === "cab" ? front + CAB_LENGTH : front;
  const [door0, door1, door2] = DOOR_CENTRES as [number, number, number];
  const halfDoor = DOOR_WIDTH / 2;

  const parts: THREE.BufferGeometry[] = [
    shell(L, 0, PALETTE.stainless),
    // Underframe equipment boxes between the bogies, and the bogies.
    box([COACH.width - 0.7, 0.55, L - 8.5], [0, 1.0, 0], PALETTE.underframe),
    ...bogie(front + 3.4),
    ...bogie(back - 3.4),
    ...bands(front + 0.05, back - 0.05, livery),
    ...DOOR_CENTRES.flatMap((z) => doorway(z, livery)),
    // Windows between the doorways and towards each end.
    ...windowRun(cabEnd + 0.4, door0 - halfDoor - 0.2, kind === "cab" ? 1 : 2),
    ...windowRun(door0 + halfDoor + 0.2, door1 - halfDoor - 0.2, 4),
    ...windowRun(door1 + halfDoor + 0.2, door2 - halfDoor - 0.2, 4),
    ...windowRun(door2 + halfDoor + 0.2, back - 0.4, 2),
    ...roofEquipment(kind, livery),
  ];
  if (kind === "cab") parts.push(...cabFront(front));

  const merged = mergeGeometries(parts);
  for (const geometry of parts) geometry.dispose();
  if (!merged) throw new Error(`coach geometry merge failed for ${kind}`);
  merged.computeVertexNormals();
  merged.computeBoundingSphere();
  return merged;
}

/** The far-distance stand-in: a plain body with a band and yellow cab
 * ends - about a hundred triangles, since hundreds are drawn at once. */
function buildGlyph(livery: Livery): THREE.BufferGeometry {
  const L = COACH.length;
  const W = COACH.width;
  const parts = [
    box([W, ROOF_Y - FLOOR_Y, L], [0, (ROOF_Y + FLOOR_Y) / 2, 0], PALETTE.stainless),
    box([W + 0.04, 0.9, L - 0.3], [0, 2.1, 0], livery.ac ? PALETTE.acBlue : livery.band),
    box([W + 0.06, ROOF_Y - FLOOR_Y - 0.2, 0.6], [0, (ROOF_Y + FLOOR_Y) / 2, -L / 2 + 0.2], PALETTE.cabYellow),
  ];
  const merged = mergeGeometries(parts);
  for (const geometry of parts) geometry.dispose();
  if (!merged) throw new Error("coach glyph merge failed");
  merged.computeVertexNormals();
  merged.computeBoundingSphere();
  return merged;
}

const coachCache = new Map<string, THREE.BufferGeometry>();
const glyphCache = new Map<string, THREE.BufferGeometry>();

function liveryKey(livery: Livery): string {
  return livery.ac ? "ac" : `band:${livery.band}`;
}

/** Shared, cached geometry for a coach kind in a livery. */
export function coachGeometry(kind: CoachKind, livery: Livery): THREE.BufferGeometry {
  const key = `${kind}:${liveryKey(livery)}`;
  let geometry = coachCache.get(key);
  if (!geometry) {
    geometry = buildCoach(kind, livery);
    coachCache.set(key, geometry);
  }
  return geometry;
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

export function coachMaterial(): THREE.MeshStandardMaterial {
  sharedMaterial ??= new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.42, metalness: 0.3 });
  return sharedMaterial;
}
