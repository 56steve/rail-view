// Geographic -> 3D scene coordinates.
//
// Mirrors backend/app/services/geometry.py exactly (same origin, same
// equirectangular approximation), so chainage and positions computed
// server-side land in the identical spot in the scene. If ORIGIN changes,
// change it in both places.
//
// Scene units are metres: x = east, y = up, z = -north (so north reads
// as "into the screen" from a default camera, like a north-up map).

export const ORIGIN_LAT = 19.08;
export const ORIGIN_LON = 72.91;
const EARTH_RADIUS_M = 6_371_000;
const COS_ORIGIN_LAT = Math.cos((ORIGIN_LAT * Math.PI) / 180);

export interface ScenePoint {
  x: number;
  z: number;
}

/** Local planar metres from ORIGIN: east, north. */
export function latLonToLocal(lat: number, lon: number): { east: number; north: number } {
  return {
    east: (((lon - ORIGIN_LON) * Math.PI) / 180) * COS_ORIGIN_LAT * EARTH_RADIUS_M,
    north: (((lat - ORIGIN_LAT) * Math.PI) / 180) * EARTH_RADIUS_M,
  };
}

export function latLonToScene(lat: number, lon: number): ScenePoint {
  const { east, north } = latLonToLocal(lat, lon);
  return { x: east, z: -north };
}
