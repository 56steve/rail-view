import type { ScenePoint } from "./geo";
import type { TrackPath } from "./track";
import type { RouteOut } from "./types";

export interface RouteSpan {
  /** Unique per span; a route can contribute several. */
  key: string;
  routeId: string;
  lineCode: string;
  color: string;
  points: ScenePoint[];
}

/**
 * The stretches of each route to draw so that track shared by several
 * routes of one line is drawn once - otherwise the shared stretch's glow
 * doubles up. Central's Kasara and Khopoli routes share everything up to
 * Kalyan; Harbour's Panvel - Goregaon route shares both its halves with
 * the CSMT routes, travelling the other way on one of them. Stretches are
 * compared station pair by station pair, in either direction.
 */
export function routeSpans(routes: Record<string, RouteOut>, tracks: Record<string, TrackPath>): RouteSpan[] {
  const drawnPairs = new Map<string, Set<string>>(); // line code -> "A|B" station pairs
  const spans: RouteSpan[] = [];
  for (const route of Object.values(routes)) {
    const track = tracks[route.route_id];
    if (!track) continue;
    const drawn = drawnPairs.get(route.line_code) ?? new Set<string>();
    drawnPairs.set(route.line_code, drawn);

    let runStart: number | null = null;
    const flush = (endIndex: number) => {
      if (runStart === null) return;
      const from = route.stations[runStart]!.chainage_m;
      const to = route.stations[endIndex]!.chainage_m;
      spans.push({
        key: `${route.route_id}:${runStart}`,
        routeId: route.route_id,
        lineCode: route.line_code,
        color: route.color_hex,
        points: track.slice(from, to),
      });
      runStart = null;
    };

    for (let i = 0; i + 1 < route.stations.length; i++) {
      const a = route.stations[i]!.name;
      const b = route.stations[i + 1]!.name;
      const shared = drawn.has(`${a}|${b}`) || drawn.has(`${b}|${a}`);
      if (shared) {
        flush(i);
      } else if (runStart === null) {
        runStart = i;
      }
    }
    flush(route.stations.length - 1);
    for (let i = 0; i + 1 < route.stations.length; i++) {
      drawn.add(`${route.stations[i]!.name}|${route.stations[i + 1]!.name}`);
    }
  }
  return spans;
}
