"""Static geometry for the Mumbai suburban network.

Loaded from `generated/network.json`, which `scripts/build_osm_data.py`
produces from OpenStreetMap: real station positions (snapped onto the
track) and real track centerlines map-matched through the OSM rail graph.
Which stations belong to which route, their order, and fast-halt flags
come from the curated `scripts/network_definitions.py`.

A *line* (Central, Western...) is the commuter-facing grouping, with a
name and colour. A *route* is one end-to-end path trains run on within a
line - the Central line forks at Kalyan into a Kasara route and a Karjat
route that share track up to Kalyan. Track matching, simulation and
schedules all work per route.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NETWORK_JSON = Path(__file__).parent / "generated" / "network.json"


class NetworkDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StationSeed:
    code: str
    name: str
    lat: float
    lon: float
    sequence: int  # position along its route, 0 = the route's first station
    fast_halt: bool


@dataclass(frozen=True, slots=True)
class LineSeed:
    code: str
    name: str
    color_hex: str


LaneProfile = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class RunningLanes:
    """Where trains actually run relative to the route centreline.

    Mumbai's railways run on the left, so each direction keeps to its own
    track. Each profile is piecewise-linear (chainage_m, offset_m) pairs;
    offset is sideways from the centreline, positive to the left when
    facing increasing chainage. `forward` is for trains travelling towards
    increasing chainage, `backward` for the opposite direction.
    """

    forward: LaneProfile
    backward: LaneProfile


@dataclass(frozen=True, slots=True)
class RouteSeed:
    code: str
    line: LineSeed
    stations: tuple[StationSeed, ...]
    # Ordered (lat, lon) track centerline from the first station to the last.
    track: tuple[tuple[float, float], ...]
    running_lanes: RunningLanes

    @property
    def name(self) -> str:
        return f"{self.stations[0].name} – {self.stations[-1].name}"

    @property
    def has_fast_service(self) -> bool:
        return any(station.fast_halt for station in self.stations)


@dataclass(frozen=True, slots=True)
class NetworkSeed:
    lines: dict[str, LineSeed]
    routes: dict[str, RouteSeed]
    attribution: str
    generated_at: str


@lru_cache
def load_network() -> NetworkSeed:
    try:
        raw = json.loads(NETWORK_JSON.read_text())
    except FileNotFoundError as exc:
        raise NetworkDataError(
            f"{NETWORK_JSON} is missing - run `uv run python scripts/build_osm_data.py`"
        ) from exc

    lines = {line["code"]: LineSeed(line["code"], line["name"], line["color_hex"]) for line in raw["lines"]}
    routes: dict[str, RouteSeed] = {}
    for route in raw["routes"]:
        if route["line_code"] not in lines:
            raise NetworkDataError(f"route {route['code']} references unknown line {route['line_code']}")
        stations = tuple(
            StationSeed(
                code=s["code"],
                name=s["name"],
                lat=s["lat"],
                lon=s["lon"],
                sequence=s["sequence"],
                fast_halt=s["fast_halt"],
            )
            for s in sorted(route["stations"], key=lambda s: s["sequence"])
        )
        lanes = route.get("running_lanes")
        if not lanes or not lanes.get("forward") or not lanes.get("backward"):
            raise NetworkDataError(f"route {route['code']} has no running lanes - rebuild network.json")
        if len(stations) < 2 or len(route["track"]) < 2:
            raise NetworkDataError(f"route {route['code']} needs at least two stations and track points")
        routes[route["code"]] = RouteSeed(
            code=route["code"],
            line=lines[route["line_code"]],
            stations=stations,
            track=tuple((lat, lon) for lat, lon in route["track"]),
            running_lanes=RunningLanes(
                forward=tuple((c, d) for c, d in lanes["forward"]),
                backward=tuple((c, d) for c, d in lanes["backward"]),
            ),
        )
    return NetworkSeed(lines=lines, routes=routes, attribution=raw["attribution"], generated_at=raw["generated_at"])


def load_routes() -> dict[str, RouteSeed]:
    return load_network().routes


def load_lines() -> dict[str, LineSeed]:
    return load_network().lines
