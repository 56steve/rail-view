"""GPS-to-railway-track matching.

This is the core of the "don't just place trains at raw GPS coordinates"
requirement. Given a raw (possibly noisy) GPS fix, `RailwayRoute.match`
finds the nearest point on the line's real track centerline and returns:

  - chainage_m:  distance along the track from the line's first station
                 to the projected point - the train's true rail-relative
                 position, independent of GPS noise.
  - snapped lat/lon: the fix pulled onto the rail.
  - offset_m:    how far the raw fix was from the rail, so a wildly
                 inaccurate fix (multipath, bridge/tunnel glitch) can be
                 rejected by the position processor instead of trusted.

Each route's geometry is built once (in local planar metres - see
`app.services.geometry`) from the OSM-derived track and cached.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise

from shapely.geometry import LineString, Point

from app.data.mumbai_network import NetworkDataError, RouteSeed, StationSeed, load_routes
from app.services.geometry import LocalPoint, to_latlon, to_local


@dataclass(frozen=True, slots=True)
class TrackMatch:
    chainage_m: float
    snapped_lat: float
    snapped_lon: float
    offset_m: float


@dataclass(frozen=True, slots=True)
class StationChainage:
    station: StationSeed
    chainage_m: float


class RailwayRoute:
    """One route's track as a matchable, chainage-addressable centerline."""

    def __init__(self, route: RouteSeed) -> None:
        self.seed = route
        local = [to_local(lat, lon) for lat, lon in route.track]
        self._geometry = LineString([(p.x, p.y) for p in local])

        self._station_chainages = []
        for station in route.stations:
            p = to_local(station.lat, station.lon)
            chainage = self._geometry.project(Point(p.x, p.y))
            self._station_chainages.append(StationChainage(station=station, chainage_m=chainage))
        for a, b in pairwise(self._station_chainages):
            if b.chainage_m <= a.chainage_m:
                raise NetworkDataError(
                    f"{route.code}: {b.station.code} does not lie after {a.station.code} along the track"
                )

    @property
    def length_m(self) -> float:
        return self._geometry.length

    @property
    def stations(self) -> list[StationChainage]:
        return self._station_chainages

    def match(self, lat: float, lon: float) -> TrackMatch:
        """Project a raw GPS fix onto the track and return its rail-relative position."""
        local = to_local(lat, lon)
        raw_point = Point(local.x, local.y)
        chainage = self._geometry.project(raw_point)
        snapped = self._geometry.interpolate(chainage)
        snapped_lat, snapped_lon = to_latlon(LocalPoint(x=snapped.x, y=snapped.y))
        return TrackMatch(
            chainage_m=chainage,
            snapped_lat=snapped_lat,
            snapped_lon=snapped_lon,
            offset_m=raw_point.distance(snapped),
        )

    def position_at_chainage(self, chainage_m: float) -> tuple[float, float]:
        """Inverse of matching: chainage -> (lat, lon) exactly on the rail."""
        clamped = max(0.0, min(chainage_m, self.length_m))
        point = self._geometry.interpolate(clamped)
        return to_latlon(LocalPoint(x=point.x, y=point.y))

    def heading_deg_at_chainage(self, chainage_m: float) -> float:
        """Compass bearing (0=N, 90=E) of the track in the direction of increasing chainage."""
        probe_m = 5.0
        a = max(0.0, chainage_m - probe_m)
        b = min(self.length_m, chainage_m + probe_m)
        if a >= b:
            b = min(self.length_m, a + probe_m)
        pa = self._geometry.interpolate(a)
        pb = self._geometry.interpolate(b)
        return math.degrees(math.atan2(pb.x - pa.x, pb.y - pa.y)) % 360

    def current_station(self, chainage_m: float, tolerance_m: float = 60.0) -> StationChainage | None:
        for sc in self._station_chainages:
            if abs(sc.chainage_m - chainage_m) <= tolerance_m:
                return sc
        return None

    def next_station(self, chainage_m: float, direction_forward: bool) -> StationChainage | None:
        ordered = self._station_chainages if direction_forward else list(reversed(self._station_chainages))
        for sc in ordered:
            if direction_forward and sc.chainage_m > chainage_m + 1e-6:
                return sc
            if not direction_forward and sc.chainage_m < chainage_m - 1e-6:
                return sc
        return None


@lru_cache
def get_route(route_code: str) -> RailwayRoute:
    routes = load_routes()
    if route_code not in routes:
        raise KeyError(f"unknown route code '{route_code}'")
    return RailwayRoute(routes[route_code])


def get_all_routes() -> dict[str, RailwayRoute]:
    return {code: get_route(code) for code in load_routes()}
