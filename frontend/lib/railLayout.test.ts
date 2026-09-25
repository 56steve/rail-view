import { describe, expect, it } from "vitest";
import type { ScenePoint } from "./geo";
import { joinContinuingTracks, smoothTracks } from "./railLayout";

const MAX_TURN = Math.PI / 4;

function pts(...coords: [number, number][]): ScenePoint[] {
  return coords.map(([x, z]) => ({ x, z }));
}

describe("joinContinuingTracks", () => {
  it("joins a track that carries on as another, whichever way each runs", () => {
    const a = pts([0, 0], [100, 0]);
    const b = pts([200, 5], [100, 0]); // runs towards the joint
    const c = pts([200, 5], [300, 5]);
    const joined = joinContinuingTracks([a, b, c], MAX_TURN);
    expect(joined).toHaveLength(1);
    const line = joined[0]!;
    const forwards = line[0]!.x === 0 ? line : line.slice().reverse();
    expect(forwards).toEqual(pts([0, 0], [100, 0], [200, 5], [300, 5]));
  });

  it("leaves junctions and sharp joints alone", () => {
    const through = pts([0, 0], [100, 0]);
    const onward = pts([100, 0], [200, 0]);
    const diverging = pts([100, 0], [200, 20]);
    expect(joinContinuingTracks([through, onward, diverging], MAX_TURN)).toHaveLength(3);

    const back = pts([100, 0], [0, 10]);
    expect(joinContinuingTracks([through, back], MAX_TURN)).toHaveLength(2);
  });

  it("keeps closed loops and lone tracks", () => {
    // A loop drawn as two halves of a 12-sided polygon, turning 30 degrees at each node.
    const ring = (from: number, to: number): ScenePoint[] => {
      const out: ScenePoint[] = [];
      for (let k = from; k <= to; k++) {
        const a = (k % 12) * (Math.PI / 6);
        out.push({ x: Math.round(1000 * Math.cos(a)) / 10, z: Math.round(1000 * Math.sin(a)) / 10 });
      }
      return out;
    };
    const lone = pts([500, 0], [600, 0]);
    const joined = joinContinuingTracks([ring(0, 6), ring(6, 12), lone], MAX_TURN);
    expect(joined).toHaveLength(2);
    expect(joined.map((t) => t.length).sort((x, y) => x - y)).toEqual([2, 13]);
  });
});

describe("smoothTracks", () => {
  it("rounds the corner where two tracks meet", () => {
    const [line] = smoothTracks([pts([0, 0], [300, 0]), pts([300, 0], [600, -40])]);
    expect(line).toBeDefined();
    expect(line!.length).toBeGreaterThan(4);
    expect(line![0]).toEqual({ x: 0, z: 0 });
    expect(line![line!.length - 1]).toEqual({ x: 600, z: -40 });
    expect(line!.some((p) => p.x === 300 && p.z === 0)).toBe(false);
  });
});
