// Draw order of the flat ground layers. None of them write depth (they are
// nearly coplanar), so their order alone decides what shows on top: urban
// areas, then greens and sand, then inland water over mangrove and
// wetland edges, then roads (which carry over creeks on bridges).
export const GROUND_ORDER = {
  sea: -40,
  land: -39,
  landcover: -30, // + class index (LANDCOVER_CLASSES order)
  inlandWater: -15,
  roads: -10, // + position, minor roads lowest
} as const;

/** Height of the highest flat ground layer (roads). Anything that has to
 * show over the ground - the track bed, say - stands above it: land cover,
 * water and roads are transparent, so they're drawn after everything
 * opaque and cover whatever is lower. */
export const GROUND_TOP_Y = 0.1;
