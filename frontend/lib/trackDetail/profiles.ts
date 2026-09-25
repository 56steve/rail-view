// Indian Railways broad-gauge plain track at true scale, in metres: a 60 kg
// rail on rubber pads, clipped to PSC sleepers laid every 0.6 m in a
// trapezoidal ballast bed. Cross-sections are in the track's own frame:
// x across the track (positive to the left of travel), y up.
//
// Heights are scene y. The ballast foot stands just above the flat ground
// layers (the highest, roads, are at y = 0.1), leaving room between them
// for the far-away track ribbon, and everything stacks from it:
//   formation 0.14 -> sleeper bottom 0.44 -> sleeper top 0.65
//   -> rail foot 0.66 (on a 10 mm pad) -> rail top 0.832.

import type { Profile, Vec2 } from "./sweep";

export const GAUGE_M = 1.676;

const RAIL_HEIGHT_M = 0.172;
const RAIL_HEAD_WIDTH_M = 0.072;
const RAIL_FOOT_WIDTH_M = 0.15;
const RAIL_WEB_WIDTH_M = 0.016;
const RAIL_PAD_M = 0.01;

export const SLEEPER_LENGTH_M = 2.75;
export const SLEEPER_WIDTH_M = 0.25;
export const SLEEPER_HEIGHT_M = 0.21;
export const SLEEPER_SPACING_M = 0.6;

const CLIP_ACROSS_M = 0.05;
const CLIP_ALONG_M = 0.1;
const CLIP_HEIGHT_M = 0.04;
// Clips bear on the edge of the rail foot, so they overlap it slightly.
const CLIP_OVER_FOOT_M = 0.01;

const BALLAST_SHOULDER_M = 0.35;
const BALLAST_UNDER_SLEEPER_M = 0.3;
// Crib ballast is packed a little way up the sleepers' sides, so they read
// as bedded in rather than resting on top.
const BALLAST_CRIB_M = 0.06;
const BALLAST_SLOPE = 1.5; // horizontal : vertical

export const FORMATION_Y = 0.14;
export const SLEEPER_BOTTOM_Y = FORMATION_Y + BALLAST_UNDER_SLEEPER_M;
const RAIL_FOOT_Y = SLEEPER_BOTTOM_Y + SLEEPER_HEIGHT_M + RAIL_PAD_M;
/** Height of the rail running surface. Trains are drawn with their wheels
 * on it. */
export const RAIL_TOP_Y = RAIL_FOOT_Y + RAIL_HEIGHT_M;

/** Sideways offset of each rail's centreline from the track centreline:
 * the gauge is measured between the inner faces of the heads. */
export const RAIL_OFFSETS_M = [GAUGE_M / 2 + RAIL_HEAD_WIDTH_M / 2, -(GAUGE_M / 2 + RAIL_HEAD_WIDTH_M / 2)] as const;

/** Where the rail profiles below sit relative to the swept path. */
export const RAIL_PROFILE_Y = RAIL_FOOT_Y;
export const BALLAST_PROFILE_Y = FORMATION_Y;

const ballastHeight = SLEEPER_BOTTOM_Y + BALLAST_CRIB_M - FORMATION_Y;
const ballastTopHalf = SLEEPER_LENGTH_M / 2 + BALLAST_SHOULDER_M;
/** Half-width of the ballast bed at its foot. */
export const BALLAST_FOOT_HALF_WIDTH_M = ballastTopHalf + ballastHeight * BALLAST_SLOPE;

/** The ballast bed: two side slopes and the top. Its foot is left open;
 * it stands on the ground. */
export const BALLAST_PROFILE: Profile = [
  [
    { x: -BALLAST_FOOT_HALF_WIDTH_M, y: 0 },
    { x: -ballastTopHalf, y: ballastHeight },
    { x: ballastTopHalf, y: ballastHeight },
    { x: BALLAST_FOOT_HALF_WIDTH_M, y: 0 },
  ],
];

// One side of a simplified 60 kg flat-bottom rail, from the outer edge of
// the foot up to the corner of the head, relative to the rail's centre and
// the underside of its foot.
const halfFoot = RAIL_FOOT_WIDTH_M / 2;
const halfWeb = RAIL_WEB_WIDTH_M / 2;
const halfHead = RAIL_HEAD_WIDTH_M / 2;
const headRunningHalf = halfHead - 0.006;
const LEFT_RAIL_SIDE: readonly Vec2[] = [
  { x: -halfFoot, y: 0 },
  { x: -halfFoot, y: 0.012 },
  { x: -0.02, y: 0.03 },
  { x: -halfWeb, y: 0.045 },
  { x: -halfWeb, y: 0.122 },
  { x: -halfHead, y: 0.135 },
  { x: -halfHead, y: RAIL_HEIGHT_M - 0.01 },
  { x: -headRunningHalf, y: RAIL_HEIGHT_M },
];
const RIGHT_RAIL_SIDE: readonly Vec2[] = [...LEFT_RAIL_SIDE].reverse().map((p) => ({ x: -p.x, y: p.y }));

/** Both sides of the rail. The running surface is left open: it is the
 * separate polished strip below, in its own material. */
export const RAIL_SIDE_PROFILE: Profile = [LEFT_RAIL_SIDE, RIGHT_RAIL_SIDE];

/** The polished running surface along the top of the head. */
export const RAIL_HEAD_PROFILE: Profile = [
  [
    { x: -headRunningHalf, y: RAIL_HEIGHT_M },
    { x: headRunningHalf, y: RAIL_HEIGHT_M },
  ],
];

/** An axis-aligned box in a sleeper's frame: x across the track, y up
 * from the sleeper's underside, z along the track. */
export interface SleeperPart {
  readonly centre: readonly [number, number, number];
  readonly size: readonly [number, number, number];
}

export const SLEEPER_BOX: SleeperPart = {
  centre: [0, SLEEPER_HEIGHT_M / 2, 0],
  size: [SLEEPER_LENGTH_M, SLEEPER_HEIGHT_M, SLEEPER_WIDTH_M],
};

/** The fastenings on one sleeper: a pad under each rail and a clip either
 * side of its foot. */
export function fasteningParts(): SleeperPart[] {
  const parts: SleeperPart[] = [];
  const clipX = halfFoot + CLIP_ACROSS_M / 2 - CLIP_OVER_FOOT_M;
  for (const rail of RAIL_OFFSETS_M) {
    parts.push({
      centre: [rail, SLEEPER_HEIGHT_M + RAIL_PAD_M / 2, 0],
      size: [RAIL_FOOT_WIDTH_M + 0.01, RAIL_PAD_M, SLEEPER_WIDTH_M * 0.8],
    });
    for (const side of [-1, 1]) {
      parts.push({
        centre: [rail + side * clipX, SLEEPER_HEIGHT_M + CLIP_HEIGHT_M / 2, 0],
        size: [CLIP_ACROSS_M, CLIP_HEIGHT_M, CLIP_ALONG_M],
      });
    }
  }
  return parts;
}
