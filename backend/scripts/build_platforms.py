"""Build the station platform table: which platform each train calls
at, and which side its doors open.

    uv run python scripts/build_platforms.py [--derive-only] [--refresh]

For every (line, station) in network.json this pairs the station's
numbered platforms in OpenStreetMap with the tracks beside them, works out
which pair of tracks (slow / fast, or "any" where the line has one pair)
and which direction (UP / DN) each track serves, and on which side of the
train the platform lies. Numbers come from `ref`s on stop positions (a
node on one track) and on platform areas; corridors from track names;
directions from left-hand running. That derivation is written to
backend/data/platforms/derived.json (a build intermediate, not committed).

Stations in backend/data/platforms/curated.json, each citing its source,
then replace the derived ones wholesale, and the result is written to
backend/app/data/generated/platforms.json (committed) after checking it
loads. The script prints the coverage per line and station, where OSM and
the curated data disagree, and what the derivation couldn't place.
--derive-only stops after derived.json.

Reads the Overpass cache written by build_osm_data.py; the only query of
its own is the stop positions (cache key `stop_positions`).

Data (c) OpenStreetMap contributors, available under the ODbL.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from build_osm_data import (
    BACKEND_DIR,
    NETWORK_OUT,
    BuildError,
    bbox_clause,
    overpass,
    platform_polygons,
)
from platform_geometry import (
    SAME_TRACK_M,
    Door,
    LineCode,
    Side,
    TrackCorridor,
    adjacent_tracks,
    common_door,
    door_from_sides,
    left_track,
    numbering_increases_left,
    offset_from,
    orient_along,
    pair_by_numbering,
    place_by_numbering,
    platform_numbers,
    platform_sort_key,
    side_of,
    track_corridor,
    track_line,
)
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import substring

from app.services.geometry import to_local
from app.services.platforms import (
    PLATFORMS_JSON,
    Corridor,
    Direction,
    DoorSide,
    PlatformDataError,
    StopRole,
    load_platform_table,
)

PLATFORMS_DIR = BACKEND_DIR / "data" / "platforms"
DERIVED_OUT = PLATFORMS_DIR / "derived.json"
CURATED_IN = PLATFORMS_DIR / "curated.json"
ATTRIBUTION = (
    "© OpenStreetMap contributors (ODbL); curated entries cite their sources in backend/data/platforms/curated.json"
)

Point2 = tuple[float, float]

# A route's stations run DN (away from CSMT / Churchgate / Thane) except
# Panvel -> Goregaon, which runs UP to Wadala Road and DN after it.
ROUTE_FORWARD_DIRECTION: dict[str, Direction] = {"HR-PLGN": "UP"}
ROUTE_DIRECTION_CHANGES_AT: dict[str, str] = {"HR-PLGN": "Wadala Road"}
# Lines with one pair of tracks throughout, and where a line's second pair
# ends: every platform there is corridor "any".
SINGLE_PAIR_LINES = frozenset({"HR", "THR"})
SINGLE_PAIR_BEYOND: dict[str, str] = {"CR": "Kalyan"}
# Trans-Harbour trains share the Harbour tracks from Nerul to Panvel.
SHARED_TRACK_LINES: dict[str, tuple[LineCode, ...]] = {"THR": ("THR", "HR")}

TRACK_RADIUS_M = 250.0
PLATFORM_RADIUS_M = 400.0
PARALLEL_MAX_ANGLE_DEG = 30.0
TANGENT_HALF_SPAN_M = 20.0
# Offsets across the station are measured from the route this far either side.
ROUTE_WINDOW_M = 800.0
# How far along a track to follow its ways for a name giving its corridor.
TRACE_LIMIT_M = 3000.0
TRACE_MAX_TURN_DEG = 25.0
# A stop position's platforms: those along its track this close to it.
STOP_PLATFORM_RADIUS_M = 60.0
EXCLUDED_TRACK_SERVICES = frozenset({"crossover"})
EXCLUDED_PLATFORM_MODES = ("subway", "monorail", "light_rail")


class PlatformJson(TypedDict):
    numbers: list[str]
    corridor: Corridor
    direction: Direction
    role: StopRole
    door: DoorSide | None
    certain: bool


class StationTable(TypedDict):
    line_code: str
    station: str
    source: str
    platforms: list[PlatformJson]


class DerivedStationJson(StationTable):
    single_pair: bool
    unresolved_polygons: list[str]  # numbered platform areas left unpaired
    unresolved: list[str]  # numbers, tracks and corridors left undecided


# --------------------------------------------------------------------------
# OSM input


@dataclass(frozen=True, slots=True)
class OsmWay:
    id: int
    tags: Mapping[str, str]
    nodes: tuple[int, ...]
    line: LineString


@dataclass(frozen=True, slots=True)
class OsmPlatform:
    id: str
    numbers: tuple[str, ...]
    polygon: Polygon


@dataclass(frozen=True, slots=True)
class OsmStop:
    id: int
    numbers: tuple[str, ...]
    point: Point2


@dataclass(frozen=True, slots=True)
class OsmData:
    ways: tuple[OsmWay, ...]
    way_tree: STRtree
    node_coords: Mapping[int, Point2]
    node_ways: Mapping[int, tuple[int, ...]]  # node id -> indices into ways
    platforms: tuple[OsmPlatform, ...]
    stops: tuple[OsmStop, ...]


def _local(lat: float, lon: float) -> Point2:
    p = to_local(lat, lon)
    return (p.x, p.y)


def _platform_ref(tags: Mapping[str, str]) -> str | None:
    """A platform's number tag: `ref`, else `local_ref`, else a name that
    spells it out ("Platform 2-3")."""
    ref = tags.get("ref") or tags.get("local_ref")
    if ref:
        return ref
    name = tags.get("name", "")
    return name if name.lower().startswith("platform") else None


def load_osm(refresh: bool) -> OsmData:
    """Every rail way, platform and stop position in the Overpass cache."""
    rails = overpass(
        f'[out:json][timeout:180];way["railway"="rail"]{bbox_clause()};out body;>;out skel qt;',
        "rails",
        refresh,
    )
    node_coords = {e["id"]: _local(e["lat"], e["lon"]) for e in rails["elements"] if e["type"] == "node"}
    ways: list[OsmWay] = []
    for element in rails["elements"]:
        if element["type"] != "way":
            continue
        nodes = tuple(n for n in element["nodes"] if n in node_coords)
        if len(nodes) < 2:
            continue
        ways.append(OsmWay(element["id"], element.get("tags", {}), nodes, LineString([node_coords[n] for n in nodes])))
    node_ways: dict[int, list[int]] = defaultdict(list)
    for index, way in enumerate(ways):
        for node in dict.fromkeys(way.nodes):
            node_ways[node].append(index)

    platform_data = overpass(
        f'[out:json][timeout:120];(way["railway"="platform"]{bbox_clause()};'
        f'relation["railway"="platform"]{bbox_clause()};);out tags geom;',
        "platforms",
        refresh,
    )
    platforms = [
        OsmPlatform(f"{element['type']}/{element['id']}", platform_numbers(_platform_ref(tags)), polygon)
        for element in platform_data["elements"]
        if not any((tags := element.get("tags", {})).get(mode) == "yes" for mode in EXCLUDED_PLATFORM_MODES)
        for polygon in platform_polygons(element)
        if not polygon.is_empty
    ]

    stop_data = overpass(
        f'[out:json][timeout:90];(node["railway"="stop"]{bbox_clause()};'
        f'node["public_transport"="stop_position"]["train"="yes"]{bbox_clause()};);out body;',
        "stop_positions",
        refresh,
    )
    stops = [
        OsmStop(element["id"], platform_numbers(_platform_ref(element.get("tags", {}))), _local(element["lat"], element["lon"]))
        for element in stop_data["elements"]
        if element["type"] == "node"
    ]
    return OsmData(
        ways=tuple(ways),
        way_tree=STRtree([way.line for way in ways]),
        node_coords=node_coords,
        node_ways={node: tuple(indices) for node, indices in node_ways.items()},
        platforms=tuple(platforms),
        stops=tuple(s for s in stops if s.numbers),
    )


# --------------------------------------------------------------------------
# Stations


@dataclass(frozen=True, slots=True)
class StationSite:
    line_code: str
    station: str
    route_code: str
    point: Point2
    tangent: Point2  # unit vector along the route's station order
    route: LineString  # the route near the station, in station order
    forward_direction: Direction  # the direction of travel along `tangent`
    fast_halt: bool
    single_pair: bool  # the line has one pair of tracks here
    terminus: bool  # a route of the line starts or ends here


def _unit(dx: float, dy: float) -> Point2:
    length = math.hypot(dx, dy)
    if length == 0:
        raise BuildError("zero-length direction")
    return (dx / length, dy / length)


def _tangent(line: LineString, point: Point2, half_span: float) -> Point2:
    at = line.project(Point(point))
    a = line.interpolate(max(at - half_span, 0.0))
    b = line.interpolate(min(at + half_span, line.length))
    return _unit(b.x - a.x, b.y - a.y)


def _route_near(track: LineString, point: Point2) -> LineString:
    at = track.project(Point(point))
    return substring(track, max(at - ROUTE_WINDOW_M, 0.0), min(at + ROUTE_WINDOW_M, track.length))


def _flip(direction: Direction) -> Direction:
    return "DN" if direction == "UP" else "UP"


def forward_direction_at(route_code: str, station_names: Sequence[str], index: int) -> Direction | None:
    """The direction a train running in the route's station order travels
    at its `index`th station; None where it reverses there."""
    base = ROUTE_FORWARD_DIRECTION.get(route_code, "DN")
    change = ROUTE_DIRECTION_CHANGES_AT.get(route_code)
    if change is None:
        return base
    change_index = station_names.index(change)
    if index == change_index:
        return None
    return base if index < change_index else _flip(base)


def single_pair_stations(routes: Sequence[Mapping[str, object]]) -> set[tuple[str, str]]:
    """(line, station) pairs where the line runs on one pair of tracks:
    all of Harbour and Trans-Harbour, and Central beyond Kalyan."""
    found: set[tuple[str, str]] = set()
    for route in routes:
        line_code = str(route["line_code"])
        stations = route["stations"]
        if not isinstance(stations, list):
            raise BuildError(f"network.json: route {route['code']} has no station list")
        names = [str(station["name"]) for station in stations]
        if line_code in SINGLE_PAIR_LINES:
            found.update((line_code, name) for name in names)
        elif (boundary := SINGLE_PAIR_BEYOND.get(line_code)) in names:
            found.update((line_code, name) for name in names[names.index(boundary) + 1 :])
    return found


def station_sites(network: Mapping[str, object]) -> list[StationSite]:
    """One site per (line, station), in line order then route order, taken
    from the first route that passes the station without reversing."""
    routes = network["routes"]
    if not isinstance(routes, list):
        raise BuildError("network.json: routes must be a list")
    lines = network["lines"]
    if not isinstance(lines, list):
        raise BuildError("network.json: lines must be a list")
    fast_halts: dict[tuple[str, str], bool] = defaultdict(bool)
    termini: set[tuple[str, str]] = set()
    for route in routes:
        for station in route["stations"]:
            fast_halts[(route["line_code"], station["name"])] |= bool(station["fast_halt"])
        termini.update((route["line_code"], route["stations"][end]["name"]) for end in (0, -1))

    single_pairs = single_pair_stations(routes)
    sites: dict[tuple[str, str], StationSite] = {}
    for line in lines:
        for route in (r for r in routes if r["line_code"] == line["code"]):
            track = LineString([_local(lat, lon) for lat, lon in route["track"]])
            names = [s["name"] for s in route["stations"]]
            for index, station in enumerate(route["stations"]):
                key = (route["line_code"], station["name"])
                direction = forward_direction_at(route["code"], names, index)
                if key in sites or direction is None:
                    continue
                point = _local(station["lat"], station["lon"])
                sites[key] = StationSite(
                    line_code=key[0],
                    station=key[1],
                    route_code=route["code"],
                    point=point,
                    tangent=_tangent(track, point, TANGENT_HALF_SPAN_M),
                    route=_route_near(track, point),
                    forward_direction=direction,
                    fast_halt=fast_halts[key],
                    single_pair=key in single_pairs,
                    terminus=key in termini,
                )
    return list(sites.values())


# --------------------------------------------------------------------------
# Step 1: tracks


@dataclass(frozen=True, slots=True)
class Track:
    """One physical track at a station (possibly drawn as several ways)."""

    index: int
    offset: float  # across the station, positive to the left of the route's forward direction
    lines: tuple[LineString, ...]  # its ways, oriented along the route
    way_ids: frozenset[int]
    name_key: str | None  # its own name, normalised; None if unnamed
    named_line: LineCode | None  # the line its own name gives
    line_code: LineCode | None  # that, or the line of the ways it runs on to
    named_corridor: TrackCorridor | None  # the corridor its own name gives
    corridor: TrackCorridor | None  # that, or the corridor of the ways it runs on to
    through: bool  # a running line rather than a siding, yard or spur

    def nearest_line(self, point: Point2) -> LineString:
        return min(self.lines, key=lambda line: line.distance(Point(point)))


def _name_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _heading(a: Point2, b: Point2) -> Point2 | None:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return ((b[0] - a[0]) / length, (b[1] - a[1]) / length) if length else None


def _ways_ahead(osm: OsmData, start: OsmWay, from_last: bool) -> Iterator[OsmWay]:
    """The ways a train would run onto leaving `start` by its last (or
    first) node, following the straightest continuation at each join and
    never a crossover, for up to TRACE_LIMIT_M."""
    min_cos = math.cos(math.radians(TRACE_MAX_TURN_DEG))
    nodes = start.nodes if from_last else start.nodes[::-1]
    node = nodes[-1]
    heading = _heading(osm.node_coords[nodes[-2]], osm.node_coords[node])
    visited = {start.id}
    travelled = 0.0
    while heading is not None and travelled < TRACE_LIMIT_M:
        best: tuple[float, OsmWay, tuple[int, ...]] | None = None
        for way_index in osm.node_ways.get(node, ()):
            way = osm.ways[way_index]
            if way.id in visited or way.tags.get("service") in EXCLUDED_TRACK_SERVICES:
                continue
            for i, candidate in enumerate(way.nodes):
                if candidate != node:
                    continue
                for path in (way.nodes[i:], way.nodes[i::-1]):
                    if len(path) < 2:
                        continue
                    out = _heading(osm.node_coords[node], osm.node_coords[path[1]])
                    if out is None:
                        continue
                    cos = heading[0] * out[0] + heading[1] * out[1]
                    if cos >= min_cos and (best is None or cos > best[0]):
                        best = (cos, way, path)
        if best is None:
            return
        _, way, path = best
        yield way
        visited.add(way.id)
        coords = [osm.node_coords[n] for n in path]
        travelled += LineString(coords).length
        node = path[-1]
        heading = _heading(coords[-2], coords[-1])


def _traced_identity(osm: OsmData, way: OsmWay) -> tuple[LineCode | None, TrackCorridor | None]:
    """A track's line and corridor from the nearest named ways along it in
    either direction; a corridor only where both directions agree (or
    only one finds one)."""
    lines: list[LineCode] = []
    corridors: list[TrackCorridor] = []
    for from_last in (True, False):
        line_found: LineCode | None = None
        for ahead in _ways_ahead(osm, way, from_last):
            name = ahead.tags.get("name")
            line_found = line_found or track_line(name)
            corridor = track_corridor(name)
            if corridor is not None:
                corridors.append(corridor)
                break
        if line_found is not None:
            lines.append(line_found)
    traced_line = lines[0] if len(set(lines)) == 1 else None
    traced_corridor = corridors[0] if len(set(corridors)) == 1 else None
    return traced_line, traced_corridor


def _end_headings(osm: OsmData, way: OsmWay) -> dict[int, Point2]:
    """For each end node of a way, the heading leaving the way there."""
    coords = osm.node_coords
    headings: dict[int, Point2] = {}
    for end, inner in ((way.nodes[0], way.nodes[1]), (way.nodes[-1], way.nodes[-2])):
        heading = _heading(coords[inner], coords[end])
        if heading is not None:
            headings[end] = heading
    return headings


def _joined_ways(ways: Sequence[OsmWay], osm: OsmData) -> list[list[OsmWay]]:
    """Ways that continue one another end to end, straight on, grouped as
    one track. At a set of points only the straightest continuation joins,
    and only if each is the other's straightest (the diverging leg stays a
    track of its own)."""
    min_cos = math.cos(math.radians(TRACE_MAX_TURN_DEG))
    headings = [_end_headings(osm, way) for way in ways]
    ends: dict[int, list[int]] = defaultdict(list)
    for index, way_headings in enumerate(headings):
        for node in way_headings:
            ends[node].append(index)

    def straightest(index: int, node: int) -> int | None:
        out = headings[index][node]
        best: tuple[float, int] | None = None
        for other in ends[node]:
            if other == index:
                continue
            into = headings[other][node]
            cos = -(out[0] * into[0] + out[1] * into[1])  # `into` points out of the other way
            if cos >= min_cos and (best is None or cos > best[0]):
                best = (cos, other)
        return best[1] if best else None

    parent = list(range(len(ways)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for index, way_headings in enumerate(headings):
        for node in way_headings:
            other = straightest(index, node)
            if other is not None and straightest(other, node) == index:
                parent[root(index)] = root(other)
    groups: dict[int, list[OsmWay]] = defaultdict(list)
    for index, way in enumerate(ways):
        groups[root(index)].append(way)
    return list(groups.values())


def station_tracks(site: StationSite, osm: OsmData) -> list[Track]:
    """Every track within TRACK_RADIUS_M of the station running within
    PARALLEL_MAX_ANGLE_DEG of the route - sidings and bays included, as
    trains start and end on them - as physical tracks: ways joined end to
    end, and ways drawn over one another, are one track. A track's offset
    is taken where it passes nearest the station."""
    station = Point(site.point)
    min_cos = math.cos(math.radians(PARALLEL_MAX_ANGLE_DEG))
    candidates: list[OsmWay] = []
    for way_index in osm.way_tree.query(station.buffer(TRACK_RADIUS_M), predicate="intersects"):
        way = osm.ways[int(way_index)]
        if way.tags.get("service") in EXCLUDED_TRACK_SERVICES:
            continue
        direction = _tangent(way.line, site.point, 5.0)
        if abs(direction[0] * site.tangent[0] + direction[1] * site.tangent[1]) >= min_cos:
            candidates.append(way)

    found: list[tuple[float, list[OsmWay]]] = []
    for joined in _joined_ways(candidates, osm):
        nearest_way = min(joined, key=lambda way: way.line.distance(station))
        nearest = nearest_way.line.interpolate(nearest_way.line.project(station))
        found.append((offset_from(site.route, (nearest.x, nearest.y)), joined))

    groups: list[list[tuple[float, OsmWay]]] = []
    for offset, joined in sorted(found, key=lambda pair: pair[0]):
        members = [(offset, way) for way in joined]
        if groups and offset - groups[-1][-1][0] <= SAME_TRACK_M:
            groups[-1].extend(members)
        else:
            groups.append(members)

    tracks: list[Track] = []
    for index, group in enumerate(groups):
        ways = [way for _, way in group]
        names = [name for way in ways if (name := way.tags.get("name"))]
        named_line = next((line for name in names if (line := track_line(name))), None)
        line_code = named_line
        named_corridor = next((c for name in names if (c := track_corridor(name))), None)
        corridor = named_corridor
        if line_code is None or corridor is None:
            nearest_way = min(ways, key=lambda way: way.line.distance(station))
            traced_line, traced_corridor = _traced_identity(osm, nearest_way)
            line_code = line_code or traced_line
            corridor = corridor or traced_corridor
        tracks.append(
            Track(
                index=index,
                offset=sum(offset for offset, _ in group) / len(group),
                lines=tuple(orient_along(way.line, site.tangent) for way in ways),
                way_ids=frozenset(way.id for way in ways),
                name_key=_name_key(names[0]) if names else None,
                named_line=named_line,
                line_code=line_code,
                named_corridor=named_corridor,
                corridor=corridor,
                through=any("service" not in way.tags for way in ways),
            )
        )
    return tracks


# --------------------------------------------------------------------------
# Steps 2-3: platform numbers on tracks


@dataclass(slots=True)
class Pairing:
    """Which track each platform number is on, and the platform areas
    that go with it."""

    tracks: dict[str, int] = field(default_factory=dict)
    polygons: dict[str, list[Polygon]] = field(default_factory=lambda: defaultdict(list))
    stop_points: dict[str, Point2] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)

    def known(self, tracks: Sequence[Track]) -> list[tuple[float, str]]:
        return [(tracks[index].offset, number) for number, index in self.tracks.items()]


def _nearest_site_is(site: StationSite, point: Point2, same_line_sites: Sequence[StationSite]) -> bool:
    """Whether `site` is the nearest station of its line to `point`, so a
    neighbouring station's platforms (Parel / Prabhadevi) stay its own."""
    own = math.dist(site.point, point)
    return all(math.dist(other.point, point) >= own for other in same_line_sites if other is not site)


def stop_position_pairs(
    site: StationSite, tracks: Sequence[Track], osm: OsmData, same_line_sites: Sequence[StationSite]
) -> Pairing:
    """Numbers from stop positions: a node on one track whose ref is a
    single platform number (station codes like CCG give none)."""
    track_of_way = {way_id: track.index for track in tracks for way_id in track.way_ids}
    pairing = Pairing()
    seen: dict[str, set[int]] = defaultdict(set)
    for stop in osm.stops:
        if len(stop.numbers) != 1 or math.dist(stop.point, site.point) > PLATFORM_RADIUS_M:
            continue
        if not _nearest_site_is(site, stop.point, same_line_sites):
            continue
        on = {track_of_way[osm.ways[i].id] for i in osm.node_ways.get(stop.id, ()) if osm.ways[i].id in track_of_way}
        if len(on) != 1:
            continue
        number = stop.numbers[0]
        seen[number].add(on.pop())
        pairing.stop_points[number] = stop.point
    for number, on_tracks in seen.items():
        if len(on_tracks) == 1:
            pairing.tracks[number] = next(iter(on_tracks))
        else:
            pairing.unresolved.append(f"stop positions put PF {number} on {len(on_tracks)} different tracks")
            pairing.stop_points.pop(number, None)
    return pairing


def _adjacent(polygon: Polygon, tracks: Sequence[Track]) -> list[Track]:
    return [track for track in tracks if adjacent_tracks(polygon, track.lines)]


def _describe(platform: OsmPlatform) -> str:
    return f"{platform.id} (ref {'/'.join(platform.numbers)})"


def _island_pairs(
    platform: OsmPlatform, adjacent: Sequence[Track], tracks: Sequence[Track], pairing: Pairing
) -> dict[str, Track] | None:
    """Numbers for a platform beside two tracks (or two numbers beside
    one), from the station's numbering order and the pairs already known;
    None if they don't settle it yet."""
    numbers = platform.numbers
    known = pairing.known(tracks)
    if len(numbers) == 2 and len(adjacent) == 2:
        increases_left = numbering_increases_left(known, (adjacent[0].offset + adjacent[1].offset) / 2)
        if increases_left is None:
            return None
        assignment = pair_by_numbering((numbers[0], numbers[1]), (adjacent[0].offset, adjacent[1].offset), increases_left)
        return {number: adjacent[index] for number, index in assignment.items()}
    if len(numbers) == 1 and len(adjacent) == 2:
        number = numbers[0]
        already = [track for track in adjacent if pairing.tracks.get(number) == track.index]
        if already:
            return {number: already[0]}
        taken = {index for other, index in pairing.tracks.items() if other != number}
        free = [track for track in adjacent if track.index not in taken]
        if len(free) == 1:
            return {number: free[0]}
        index = place_by_numbering(number, (adjacent[0].offset, adjacent[1].offset), known)
        return {number: adjacent[index]} if index is not None else None
    if len(numbers) == 2 and len(adjacent) == 1:
        elsewhere = [n for n in numbers if n in pairing.tracks and pairing.tracks[n] != adjacent[0].index]
        if len(elsewhere) == 1:
            return {next(n for n in numbers if n != elsewhere[0]): adjacent[0]}
    return None


def polygon_pairs(
    site: StationSite,
    tracks: Sequence[Track],
    osm: OsmData,
    pairing: Pairing,
    same_line_sites: Sequence[StationSite],
) -> list[str]:
    """Numbers from platform areas, added to `pairing`: a single number
    beside one track pairs directly; islands pair by the station's
    numbering order, fitted from the pairs already known (repeating while
    each pass settles more). Returns the platforms of this line left
    unresolved."""
    station = Point(site.point)
    nearby = [
        platform
        for platform in osm.platforms
        if platform.numbers
        and platform.polygon.distance(station) <= PLATFORM_RADIUS_M
        and _nearest_site_is(site, (platform.polygon.centroid.x, platform.polygon.centroid.y), same_line_sites)
    ]
    beside = {platform.id: _adjacent(platform.polygon, tracks) for platform in nearby}
    notes: dict[str, str] = {}

    def record(settled: Mapping[str, Track], platform: OsmPlatform) -> None:
        """Adds a platform's numbers, all or none: none if one contradicts
        a number already placed, or lands on a track a stop position has
        already numbered differently (stop positions are the more precise,
        and the more often renumbered)."""
        for number, track in settled.items():
            known = pairing.tracks.get(number)
            if known is not None and known != track.index:
                notes[platform.id] = f"{_describe(platform)}: puts PF {number} on another track than already known"
                return
            stop_numbers = {n for n in pairing.stop_points if pairing.tracks.get(n) == track.index and n != number}
            if stop_numbers:
                notes[platform.id] = (
                    f"{_describe(platform)}: puts PF {number} where a stop position has PF {'/'.join(sorted(stop_numbers))}"
                )
                return
        for number, track in settled.items():
            pairing.tracks[number] = track.index
            pairing.polygons[number].append(platform.polygon)

    pending: list[OsmPlatform] = []
    for platform in nearby:
        adjacent = beside[platform.id]
        if len(platform.numbers) == 1 and len(adjacent) == 1:
            record({platform.numbers[0]: adjacent[0]}, platform)
        elif not adjacent:
            notes[platform.id] = f"{_describe(platform)}: no track beside it"
        elif len(platform.numbers) > 2 or len(adjacent) > 2:
            notes[platform.id] = f"{_describe(platform)}: {len(platform.numbers)} numbers beside {len(adjacent)} tracks"
        else:
            pending.append(platform)

    progress = True
    while pending and progress:
        progress = False
        for platform in list(pending):
            settled = _island_pairs(platform, beside[platform.id], tracks, pairing)
            if settled is not None:
                record(settled, platform)
                pending.remove(platform)
                progress = True
    for platform in pending:
        notes[platform.id] = f"{_describe(platform)}: {len(platform.numbers)} number(s) beside {len(beside[platform.id])} tracks, numbering order unknown"

    return [note for platform_id, note in notes.items() if not _other_lines_only(site, beside[platform_id])]


def _other_lines_only(site: StationSite, adjacent: Sequence[Track]) -> bool:
    """Whether every track beside a platform is named for another line."""
    accepted = SHARED_TRACK_LINES.get(site.line_code, (site.line_code,))
    return bool(adjacent) and all(t.named_line is not None and t.named_line not in accepted for t in adjacent)


# --------------------------------------------------------------------------
# Steps 4-5: corridor and direction of each track


@dataclass(frozen=True, slots=True)
class Classification:
    # track index -> (corridor, direction of travel on it)
    tracks: Mapping[int, tuple[Corridor, Direction]]
    unresolved: tuple[str, ...]


def _line_tracks(site: StationSite, tracks: Sequence[Track]) -> list[Track]:
    """The station's running lines that belong to the site's line."""
    accepted = SHARED_TRACK_LINES.get(site.line_code, (site.line_code,))
    own = [t for t in tracks if t.through and t.line_code in accepted]
    if site.line_code in SHARED_TRACK_LINES:
        preferred = [t for t in own if t.line_code == site.line_code]
        if len(preferred) >= 2:
            return preferred
    if own:
        return own
    # Nothing named for any line: a plain double-track station is the line's pair.
    unnamed = [t for t in tracks if t.through]
    return unnamed if len(unnamed) == 2 and all(t.line_code is None for t in unnamed) else []


def _running_pair(candidates: Sequence[Track]) -> tuple[Track, Track] | None:
    """The pair of tracks trains run through on: the only two, or of
    more, the two sharing one name (an extra, unnamed or differently named
    platform line is not part of the pair)."""
    if len(candidates) == 2:
        return (candidates[0], candidates[1])
    by_name: dict[str, list[Track]] = defaultdict(list)
    for track in candidates:
        if track.name_key is not None:
            by_name[track.name_key].append(track)
    pairs = [group for group in by_name.values() if len(group) == 2]
    return (pairs[0][0], pairs[0][1]) if len(pairs) == 1 else None


def _paired_by_use(line_tracks: Sequence[Track]) -> dict[Corridor, tuple[Track, Track]] | None:
    """For four or six running lines: neighbours in pairs across the
    station (Mumbai pairs its tracks by use), one pair slow and one fast.
    A pair takes the corridor its tracks' own names give; with four lines
    and one pair named, the other is the other corridor; if no pair is
    named, the names of the ways they run on to decide. None if that
    leaves it open or contradicts itself."""
    if len(line_tracks) not in (4, 6):
        return None
    ordered = sorted(line_tracks, key=lambda track: track.offset)
    pairs = [(ordered[i], ordered[i + 1]) for i in range(0, len(ordered), 2)]

    for traced in (False, True):
        corridors: list[TrackCorridor | None] = []
        for pair in pairs:
            named = {c for t in pair if (c := (t.corridor if traced else t.named_corridor)) is not None}
            if len(named) > 1:
                return None
            corridors.append(next(iter(named)) if named else None)
        decided = [c for c in corridors if c is not None]
        if not decided:
            continue
        if len(decided) != len(set(decided)):
            return None
        if len(pairs) == 2 and len(decided) == 1:
            other: TrackCorridor = "fast" if decided[0] == "slow" else "slow"
            corridors = [c if c is not None else other for c in corridors]
        return {c: pair for c, pair in zip(corridors, pairs, strict=True) if c is not None}
    return None


def _side_by_side(pair: tuple[Track, Track], line_tracks: Sequence[Track]) -> bool:
    """Whether no other running line of the line lies between the pair."""
    low, high = sorted((pair[0].offset, pair[1].offset))
    return not any(low < track.offset < high for track in line_tracks)


def classify(site: StationSite, tracks: Sequence[Track]) -> Classification:
    """Corridor and direction for each of the line's tracks. Corridor from
    the track's name (or its neighbour's, where four or six lines pair up,
    or the ways it runs on to); "any" on single-pair lines and stations. Within a pair,
    the track on the left going forward carries forward trains
    (left-hand running)."""
    line_tracks = _line_tracks(site, tracks)
    unresolved: list[str] = []
    pairs: dict[Corridor, tuple[Track, Track]] = {}
    if site.single_pair:
        pair = _running_pair(line_tracks)
        if pair is not None and _side_by_side(pair, line_tracks):
            pairs["any"] = pair
        else:
            unresolved.append(f"{len(line_tracks)} running lines and no single named pair side by side")
    elif (by_use := _paired_by_use(line_tracks)) is not None:
        pairs.update(by_use)
    else:
        groups: dict[Corridor, list[Track]] = defaultdict(list)
        for track in line_tracks:
            if track.corridor is not None:
                groups[track.corridor].append(track)
            else:
                unresolved.append(f"running line at {track.offset:+.0f} m: no slow/fast name")
        for corridor, candidates in groups.items():
            pair = _running_pair(candidates)
            if pair is not None and _side_by_side(pair, line_tracks):
                pairs[corridor] = pair
            else:
                unresolved.append(f"{corridor}: {len(candidates)} running lines and no single named pair side by side")

    assignments: dict[int, tuple[Corridor, Direction]] = {}
    for corridor, pair in pairs.items():
        forward_line = left_track(
            (pair[0].nearest_line(site.point), pair[1].nearest_line(site.point)), forward=True, station_point=site.point
        )
        for track in pair:
            is_forward = any(line is forward_line for line in track.lines)
            assignments[track.index] = (corridor, site.forward_direction if is_forward else _flip(site.forward_direction))
    return Classification(tracks=assignments, unresolved=tuple(unresolved))


# --------------------------------------------------------------------------
# Steps 6-7: door side and entries


def _door(site: StationSite, track: Track, direction: Direction, polygons: Sequence[Polygon]) -> Door | None:
    """Which side of a train travelling `direction` the platforms are on."""
    forward = direction == site.forward_direction
    sides: set[Side] = set()
    for polygon in polygons:
        centroid = (polygon.centroid.x, polygon.centroid.y)
        sides.add(side_of(track.nearest_line(centroid), centroid, forward=forward))
    return door_from_sides(sides)


def _stop_platforms(track: Track, stop_point: Point2, osm: OsmData) -> list[Polygon]:
    """Platform areas for a number known only from its stop position:
    those beside its track near the stop, whatever number they carry (it
    is their side of the track that matters, and their refs may predate a
    renumbering)."""
    stop = Point(stop_point)
    return [
        platform.polygon
        for platform in osm.platforms
        if platform.polygon.distance(stop) <= STOP_PLATFORM_RADIUS_M and adjacent_tracks(platform.polygon, track.lines)
    ]


def entries_for_station(
    site: StationSite, tracks: Sequence[Track], pairing: Pairing, classification: Classification, osm: OsmData
) -> tuple[list[PlatformJson], list[str]]:
    """One through entry per (corridor, direction). Numbers sharing it
    merge, and then vary from train to train, as does the platform at a
    terminus (trains reverse on whichever track they came in on): only a
    lone number away from the termini is certain."""
    grouped: dict[tuple[Corridor, Direction], list[tuple[str, Door | None]]] = defaultdict(list)
    unresolved: list[str] = []
    accepted = SHARED_TRACK_LINES.get(site.line_code, (site.line_code,))
    for number, index in sorted(pairing.tracks.items(), key=lambda item: platform_sort_key(item[0])):
        track = tracks[index]
        assignment = classification.tracks.get(index)
        if assignment is None:
            if track.named_line is None or track.named_line in accepted:
                kind = "running line" if track.through else "siding or bay"
                unresolved.append(f"PF {number}: on a {kind} outside the line's pairs")
            continue
        corridor, direction = assignment
        polygons = pairing.polygons.get(number) or (
            _stop_platforms(track, pairing.stop_points[number], osm) if number in pairing.stop_points else []
        )
        grouped[(corridor, direction)].append((number, _door(site, track, direction, polygons)))

    entries: list[PlatformJson] = []
    for (corridor, direction), numbered in sorted(grouped.items()):
        numbers = [number for number, _ in numbered]
        entries.append(
            PlatformJson(
                numbers=numbers,
                corridor=corridor,
                direction=direction,
                role="through",
                door=common_door(door for _, door in numbered),
                certain=len(numbers) == 1 and not site.terminus,
            )
        )
    return entries, unresolved


def derive_station(site: StationSite, osm: OsmData, same_line_sites: Sequence[StationSite]) -> DerivedStationJson:
    """The station's platform table as OSM gives it."""
    tracks = station_tracks(site, osm)
    pairing = stop_position_pairs(site, tracks, osm, same_line_sites)
    polygon_notes = polygon_pairs(site, tracks, osm, pairing, same_line_sites)
    classification = classify(site, tracks)
    entries, entry_notes = entries_for_station(site, tracks, pairing, classification, osm)
    return DerivedStationJson(
        line_code=site.line_code,
        station=site.station,
        source="osm",
        single_pair=site.single_pair,
        platforms=entries,
        unresolved_polygons=polygon_notes,
        unresolved=[*pairing.unresolved, *classification.unresolved, *entry_notes],
    )


# --------------------------------------------------------------------------
# Step 8: report


def required_corridors(site: StationSite) -> tuple[Corridor, ...]:
    """The corridors a station's trains call on."""
    if site.single_pair:
        return ("any",)
    return ("slow", "fast") if site.fast_halt else ("slow",)


def missing_coverage(site: StationSite, platforms: Sequence[PlatformJson]) -> list[str]:
    """(corridor, direction) combinations the station needs but has no
    entry for; an "any" entry covers both corridors."""
    missing: list[str] = []
    for corridor in required_corridors(site):
        for direction in ("UP", "DN"):
            if not any(
                p["direction"] == direction and (p["corridor"] == corridor or "any" in (p["corridor"], corridor))
                for p in platforms
            ):
                missing.append(f"{corridor} {direction}")
    return missing


def coverage_status(site: StationSite, platforms: Sequence[PlatformJson]) -> tuple[str, str]:
    """("full" | "partial" | "none", the line to print)."""
    if not platforms:
        return "none", "none"
    missing = missing_coverage(site, platforms)
    if missing:
        return "partial", f"partial (missing {', '.join(missing)})"
    return "full", "full"


def print_coverage(sites: Sequence[StationSite], stations: Mapping[tuple[str, str], StationTable]) -> None:
    """Per line and station: full, partial (what's missing) or none."""
    print("\ncoverage (full: every corridor and direction the station's trains need)")
    totals: dict[str, int] = defaultdict(int)
    current_line = ""
    for site in sites:
        if site.line_code != current_line:
            current_line = site.line_code
            print(f"\n  {current_line}")
        station = stations.get((site.line_code, site.station))
        platforms = station["platforms"] if station else []
        category, status = coverage_status(site, platforms)
        withheld = station is not None and not platforms and station["source"] == "curated"
        if withheld:
            status = "none (withheld)"
        totals[category] += 1
        source = f" [{station['source']}]" if station and (platforms or withheld) else ""
        print(f"    {site.station:<24} {status}{source}")
    print(f"\n  totals: {totals['full']} full, {totals['partial']} partial, {totals['none']} none")


def print_unresolved(stations: Mapping[tuple[str, str], DerivedStationJson]) -> None:
    """Everything the derivation couldn't place, per station."""
    print("\nunresolved platform polygons")
    for (line_code, name), station in stations.items():
        for note in station["unresolved_polygons"]:
            print(f"  {line_code} {name}: {note}")
    print("\nother unresolved items in the OSM derivation")
    for (line_code, name), station in stations.items():
        for note in station["unresolved"]:
            print(f"  {line_code} {name}: {note}")


# --------------------------------------------------------------------------
# Curated stations and the merge


def load_curated(path: Path, sites: Sequence[StationSite]) -> dict[tuple[str, str], StationTable]:
    """The curated stations, keyed (line, station). Each must be a station
    of its line in network.json and cite a source; the entries themselves
    are checked by the app's loader once merged. An empty platform list
    withholds the station: known, but deliberately without platforms
    (its source says why)."""
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise BuildError(f"{path}: {exc}") from exc
    stations = raw.get("stations") if isinstance(raw, dict) else None
    if not isinstance(stations, list):
        raise BuildError(f"{path}: expected an object with a list of stations")
    known = {(site.line_code, site.station) for site in sites}
    curated: dict[tuple[str, str], StationTable] = {}
    for station in stations:
        try:
            key = (station["line_code"], station["station"])
            source = station["source"]
            platforms = station["platforms"]
        except (KeyError, TypeError) as exc:
            raise BuildError(f"{path}: malformed station {station!r} ({exc})") from exc
        if key not in known:
            raise BuildError(f"{path}: {key} is not a station of that line in network.json")
        if key in curated:
            raise BuildError(f"{path}: {key} is listed twice")
        if not isinstance(source, str) or not source.strip():
            raise BuildError(f"{path}: {key} has no source")
        if not isinstance(platforms, list):
            raise BuildError(f"{path}: {key} platforms must be a list")
        curated[key] = StationTable(line_code=key[0], station=key[1], source=source, platforms=platforms)
    return curated


def merge_tables(
    sites: Sequence[StationSite],
    derived: Mapping[tuple[str, str], DerivedStationJson],
    curated: Mapping[tuple[str, str], StationTable],
) -> dict[tuple[str, str], StationTable]:
    """Derived stations, each replaced wholesale by its curated one, in
    line then route order. Derived stations with no entries are left out;
    a curated one with none stays in, so a withheld station shows no
    platform rather than OSM's."""
    merged: dict[tuple[str, str], StationTable] = {}
    for site in sites:
        key = (site.line_code, site.station)
        if key in curated:
            merged[key] = StationTable(
                line_code=key[0], station=key[1], source="curated", platforms=curated[key]["platforms"]
            )
        elif derived[key]["platforms"]:
            merged[key] = StationTable(line_code=key[0], station=key[1], source="osm", platforms=derived[key]["platforms"])
    return merged


def _same_corridor(a: Corridor, b: Corridor) -> bool:
    return a == b or "any" in (a, b)


def disagreements(
    derived: Mapping[tuple[str, str], DerivedStationJson], curated: Mapping[tuple[str, str], StationTable]
) -> list[str]:
    """Where a curated station contradicts what OSM gives: an OSM platform
    number the curated entries for that corridor and direction don't list
    (through entries first, else any role, as at termini), or door sides
    that can't both hold."""
    notes: list[str] = []
    for key, station in curated.items():
        if not station["platforms"]:
            if derived[key]["platforms"]:
                withheld = ", ".join(
                    f"{e['corridor']} {e['direction']} PF {'/'.join(e['numbers'])}" for e in derived[key]["platforms"]
                )
                notes.append(f"{key[0]} {key[1]}: withheld by curation; OSM has {withheld}")
            continue
        for osm_entry in derived[key]["platforms"]:
            facing = [
                entry
                for entry in station["platforms"]
                if entry["direction"] == osm_entry["direction"] and _same_corridor(entry["corridor"], osm_entry["corridor"])
            ]
            matching = [entry for entry in facing if entry["role"] == "through"] or facing
            label = f"{key[0]} {key[1]}: {osm_entry['corridor']} {osm_entry['direction']}"
            osm_numbers = "/".join(osm_entry["numbers"])
            if not matching:
                notes.append(f"{label}: OSM has PF {osm_numbers}, curated has nothing")
                continue
            curated_numbers = {number for entry in matching for number in entry["numbers"]}
            if not set(osm_entry["numbers"]) <= curated_numbers:
                listed = "/".join(sorted(curated_numbers, key=platform_sort_key))
                notes.append(f"{label}: OSM has PF {osm_numbers}, curated has PF {listed}")
            for entry in matching:
                door = entry["door"]
                if (
                    set(entry["numbers"]) & set(osm_entry["numbers"])
                    and door is not None
                    and osm_entry["door"] is not None
                    and common_door((door, osm_entry["door"])) is None
                ):
                    notes.append(f"{label}: PF {osm_numbers} doors {osm_entry['door']} in OSM, {door} curated")
    return notes


def write_platform_table(path: Path, sites: Sequence[StationSite], stations: Sequence[StationTable]) -> None:
    """Writes the table, having checked it loads through the app's own
    loader (a failing table never replaces a good one)."""
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "attribution": ATTRIBUTION,
        "single_pair": [[site.line_code, site.station] for site in sites if site.single_pair],
        "stations": list(stations),
    }
    staged = path.with_name(f"{path.stem}.staged.json")
    write_json(staged, payload)
    try:
        load_platform_table(staged)
    except PlatformDataError as exc:
        staged.unlink()
        raise BuildError(f"the merged platform table doesn't load: {exc}") from exc
    staged.replace(path)


# --------------------------------------------------------------------------


def derive_all(sites: Sequence[StationSite], osm: OsmData) -> dict[tuple[str, str], DerivedStationJson]:
    """The OSM derivation for every station."""
    by_line: dict[str, list[StationSite]] = defaultdict(list)
    for site in sites:
        by_line[site.line_code].append(site)
    return {(site.line_code, site.station): derive_station(site, osm, by_line[site.line_code]) for site in sites}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--derive-only", action="store_true", help="stop after writing data/platforms/derived.json")
    parser.add_argument("--refresh", action="store_true", help="ignore the local Overpass cache")
    args = parser.parse_args()

    network = json.loads(NETWORK_OUT.read_text())
    sites = station_sites(network)
    osm = load_osm(args.refresh)
    derived = derive_all(sites, osm)
    write_json(DERIVED_OUT, {f"{line}|{name}": station for (line, name), station in derived.items()})
    print(f"wrote {DERIVED_OUT.relative_to(BACKEND_DIR)} ({len(derived)} stations)")
    if args.derive_only:
        print_coverage(sites, derived)
        print_unresolved(derived)
        return

    curated = load_curated(CURATED_IN, sites)
    merged = merge_tables(sites, derived, curated)
    write_platform_table(PLATFORMS_JSON, sites, list(merged.values()))
    print(
        f"wrote {PLATFORMS_JSON.relative_to(BACKEND_DIR)} ({len(merged)} stations: "
        f"{sum(s['source'] == 'curated' for s in merged.values())} curated, "
        f"{sum(s['source'] == 'osm' for s in merged.values())} from OSM)"
    )
    print_coverage(sites, merged)
    print("\nwhere OSM and the curated stations disagree")
    for note in disagreements(derived, curated) or ["(none)"]:
        print(f"  {note}")
    print_unresolved(derived)


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        sys.exit(1)
