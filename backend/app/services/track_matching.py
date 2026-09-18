"""GPS-to-railway-track matching.

This is the core of the "don't just place trains at raw GPS coordinates"
requirement. Given a raw (possibly noisy) GPS fix, `RailwayRoute.match`
finds the nearest point on the known railway centerline and returns:

  - chainage_m:  distance along the route from its origin terminus to the
                 projected point - this is the train's true rail-relative
                 position, independent of GPS noise.
  - snapped lat/lon: the fix pulled onto the rail.
  - offset_m:    how far the raw fix was from the rail, so a wildly
                 inaccurate fix (multipath, tunnel exit glitch, etc.) can be
                 flagged/rejected by the position processor instead of
                 being trusted.

The route geometry is built once (in local planar metres - see
`app.services.geometry`) from the station seed data and cached, since it
never changes at runtime for a fixed line.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

from shapely.geometry import LineString, Point

from app.data.mumbai_network import RAILWAY_LINES, LineSeed, StationSeed
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
    """A single directional corridor (e.g. Thane -> Dadar) as a matchable line."""

    def __init__(self, line: LineSeed) -> None:
        self.line_seed = line
        ordered = sorted(line.stations, key=lambda s: s.sequence)
        self._stations = ordered

        local_points = [to_local(s.lat, s.lon) for s in ordered]
        self._geometry = LineString([(p.x, p.y) for p in local_points])

        station_chainages: list[StationChainage] = []
        running_m = 0.0
        for i, (point, station) in enumerate(zip(local_points, ordered, strict=True)):
            if i > 0:
                prev = local_points[i - 1]
                running_m += math.hypot(point.x - prev.x, point.y - prev.y)
            station_chainages.append(StationChainage(station=station, chainage_m=running_m))
        self._station_chainages = station_chainages

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
        offset_m = raw_point.distance(snapped)
        snapped_lat, snapped_lon = to_latlon(LocalPoint(x=snapped.x, y=snapped.y))
        return TrackMatch(
            chainage_m=chainage,
            snapped_lat=snapped_lat,
            snapped_lon=snapped_lon,
            offset_m=offset_m,
        )

    def position_at_chainage(self, chainage_m: float) -> tuple[float, float]:
        """Inverse of matching: chainage -> (lat, lon) exactly on the rail."""
        clamped = max(0.0, min(chainage_m, self.length_m))
        point = self._geometry.interpolate(clamped)
        return to_latlon(LocalPoint(x=point.x, y=point.y))

    def heading_deg_at_chainage(self, chainage_m: float) -> float:
        """Compass bearing (0=N, 90=E) of the track direction of increasing chainage."""
        probe_m = 5.0
        a = max(0.0, chainage_m - probe_m)
        b = min(self.length_m, chainage_m + probe_m)
        if a >= b:
            b = min(self.length_m, a + probe_m)
        pa = self._geometry.interpolate(a)
        pb = self._geometry.interpolate(b)
        dx, dy = pb.x - pa.x, pb.y - pa.y
        return math.degrees(math.atan2(dx, dy)) % 360

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

    def terminus_station(self, direction_forward: bool) -> StationChainage:
        return self._station_chainages[-1] if direction_forward else self._station_chainages[0]


@lru_cache
def get_route(line_code: str = "CR") -> RailwayRoute:
    return RailwayRoute(RAILWAY_LINES[line_code])
