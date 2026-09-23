import type { ScenePoint } from "./geo";
import type { TrackPath } from "./track";
import type { RouteOut } from "./types";

export interface RouteSpan {
  routeId: string;
  lineCode: string;
  color: string;
  points: ScenePoint[];
}

/**
 * The part of each route to draw so that track shared by several routes
 * of one line is drawn once: Central's Kasara and Karjat routes share
 * everything up to Kalyan, and drawing both in full would double the
 * trunk's glow. A later route starts from the last station it has in
 * common (in order, from its origin) with an earlier route of its line.
 */
export function routeSpans(routes: Record<string, RouteOut>, tracks: Record<string, TrackPath>): RouteSpan[] {
  const drawn: RouteOut[] = [];
  const spans: RouteSpan[] = [];
  for (const route of Object.values(routes)) {
    const track = tracks[route.route_id];
    if (!track) continue;
    let startChainage = 0;
    for (const earlier of drawn) {
      if (earlier.line_code !== route.line_code) continue;
      let shared = 0;
      while (
        shared < route.stations.length &&
        shared < earlier.stations.length &&
        route.stations[shared]!.code === earlier.stations[shared]!.code
      ) {
        shared++;
      }
      if (shared > 0) startChainage = Math.max(startChainage, route.stations[shared - 1]!.chainage_m);
    }
    drawn.push(route);
    spans.push({
      routeId: route.route_id,
      lineCode: route.line_code,
      color: route.color_hex,
      points: startChainage > 0 ? track.slice(startChainage, track.length) : track.points(),
    });
  }
  return spans;
}
