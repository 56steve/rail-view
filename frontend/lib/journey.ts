import type { TrackPath } from "./track";
import type { RouteOut, StationIndexEntry } from "./types";

export interface JourneySegment {
  lineCode: string;
  routeCode: string;
  fromChainage: number;
  toChainage: number;
  points: { x: number; z: number }[];
}

/** The stretch of track a direct train covers between two stations, on
 * the first route that serves both (null if none does). */
export function directSegment(
  from: StationIndexEntry,
  to: StationIndexEntry,
  routes: Record<string, RouteOut>,
  tracks: Record<string, TrackPath>,
): JourneySegment | null {
  for (const route of Object.values(routes)) {
    const a = route.stations.find((s) => s.name === from.name);
    const b = route.stations.find((s) => s.name === to.name);
    const track = tracks[route.route_id];
    if (a && b && track) {
      return {
        lineCode: route.line_code,
        routeCode: route.route_id,
        fromChainage: a.chainage_m,
        toChainage: b.chainage_m,
        points: track.slice(a.chainage_m, b.chainage_m),
      };
    }
  }
  return null;
}
