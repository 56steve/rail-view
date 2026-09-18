// Geographic -> 3D scene coordinate conversion.
//
// Mirrors backend/app/services/geometry.py EXACTLY (same origin, same
// equirectangular-approximation formula) so a lat/lon computed server-side
// via track matching lands in the identical spot in the Three.js scene
// without either side needing to know about the other's coordinate
// system. If ORIGIN_LAT/ORIGIN_LON ever change, update both files.

export const ORIGIN_LAT = 19.1868;
export const ORIGIN_LON = 72.975;
const EARTH_RADIUS_M = 6_371_000;

// How many real-world metres one Three.js scene unit represents. Chosen
// so the ~26km Thane-Dadar corridor spans a comfortable few thousand
// scene units (good float precision, sane camera near/far planes),
// independent of how large train models are drawn (see
// components/three/TrainMesh.tsx - train visual size is deliberately
// exaggerated for legibility, position accuracy is not).
export const METERS_PER_SCENE_UNIT = 20;

export interface ScenePoint {
  x: number;
  z: number;
}

function originLatRad(): number {
  return (ORIGIN_LAT * Math.PI) / 180;
}

/** Local planar offset in metres from ORIGIN, x=east, y=north. */
export function latLonToLocalMeters(lat: number, lon: number): { x: number; y: number } {
  const x = (((lon - ORIGIN_LON) * Math.PI) / 180) * Math.cos(originLatRad()) * EARTH_RADIUS_M;
  const y = (((lat - ORIGIN_LAT) * Math.PI) / 180) * EARTH_RADIUS_M;
  return { x, y };
}

/**
 * Convert lat/lon to a Three.js ground-plane point. Scene x = east,
 * scene z = -north (so "north" reads as "into the screen" from the
 * default overview camera, a conventional map-like orientation).
 */
export function latLonToScene(lat: number, lon: number): ScenePoint {
  const { x, y } = latLonToLocalMeters(lat, lon);
  return { x: x / METERS_PER_SCENE_UNIT, z: -y / METERS_PER_SCENE_UNIT };
}
