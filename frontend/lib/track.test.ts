import { describe, expect, it } from "vitest";
import { TRACK_FILLET } from "./curves";
import { ORIGIN_LAT, ORIGIN_LON, latLonToScene, type ScenePoint } from "./geo";
import { LaneProfile, laneSample, type RouteLanes } from "./lanes";
import { TrackPath } from "./track";

const EARTH_RADIUS_M = 6_371_000;
const COS_ORIGIN_LAT = Math.cos((ORIGIN_LAT * Math.PI) / 180);

/** The inverse of `latLonToScene`. */
function toLatLon(p: ScenePoint): [number, number] {
  return [
    ORIGIN_LAT + (-p.z / EARTH_RADIUS_M) * (180 / Math.PI),
    ORIGIN_LON + (p.x / (EARTH_RADIUS_M * COS_ORIGIN_LAT)) * (180 / Math.PI),
  ];
}

// East 600 m, then a 12 degree bend at a single node, then on 600 m.
const BEND = 12 * (Math.PI / 180);
const NODES: ScenePoint[] = [
  { x: 0, z: 0 },
  { x: 600, z: 0 },
  { x: 600 + 600 * Math.cos(BEND), z: -600 * Math.sin(BEND) },
];
const POLYLINE = NODES.map(toLatLon);

function yawStep(a: number, b: number): number {
  const d = Math.abs(a - b) % (2 * Math.PI);
  return d > Math.PI ? 2 * Math.PI - d : d;
}

describe("TrackPath", () => {
  const track = new TrackPath(POLYLINE);

  it("keeps the polyline's chainage and ends", () => {
    expect(track.length).toBeCloseTo(1200, 3);
    const start = track.sample(0);
    const end = track.sample(track.length);
    const first = latLonToScene(...POLYLINE[0]!);
    const last = latLonToScene(...POLYLINE[2]!);
    expect(start.x).toBeCloseTo(first.x, 9);
    expect(start.z).toBeCloseTo(first.z, 9);
    expect(end.x).toBeCloseTo(last.x, 9);
    expect(end.z).toBeCloseTo(last.z, 9);
    // Straights away from the bend are where they always were.
    const onStraight = track.sample(200);
    expect(onStraight.x).toBeCloseTo(200, 6);
    expect(onStraight.z).toBeCloseTo(0, 6);
  });

  it("puts the node's chainage at the middle of its arc, just inside the node", () => {
    const p = track.sample(600);
    const inset = TRACK_FILLET.minRadiusM * (1 / Math.cos(BEND / 2) - 1);
    // Between arc samples the line is a chord, at most the sagitta inside the arc.
    expect(Math.abs(Math.hypot(p.x - 600, p.z) - inset)).toBeLessThanOrEqual(TRACK_FILLET.maxSagittaM);
    expect(inset).toBeLessThan(2);
  });

  it("turns through the bend without a jump in heading, always moving on", () => {
    let previous = track.sample(0);
    for (let c = 1; c <= track.length; c += 1) {
      const s = track.sample(c);
      expect(yawStep(s.yaw, previous.yaw)).toBeLessThan(1.5 * (Math.PI / 180));
      // Forward along the previous heading: yaw points local -z along travel.
      const forward = -(s.x - previous.x) * Math.sin(previous.yaw) - (s.z - previous.z) * Math.cos(previous.yaw);
      expect(forward).toBeGreaterThan(0);
      previous = s;
    }
  });

  it("slices along the rounded line", () => {
    const points = track.slice(500, 700);
    expect(points.length).toBeGreaterThan(3);
    expect(points[0]!.x).toBeCloseTo(500, 6);
    for (const p of points) expect(Math.abs(p.z)).toBeLessThan(700 * Math.sin(BEND));
  });

  it("gives trains on an offset lane a smooth heading through the bend", () => {
    const lanes: RouteLanes = { forward: new LaneProfile([[0, 2.5]]), backward: new LaneProfile([[0, -2.5]]) };
    let previous = laneSample(track, lanes, true, 400);
    for (let c = 401; c <= 800; c += 1) {
      const s = laneSample(track, lanes, true, c);
      expect(yawStep(s.yaw, previous.yaw)).toBeLessThan(1.5 * (Math.PI / 180));
      previous = s;
    }
  });
});
