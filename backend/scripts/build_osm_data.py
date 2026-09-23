"""Build RailView's static network and city data from OpenStreetMap.

    uv run python scripts/build_osm_data.py [--refresh]

Outputs (committed; regenerated only when this script runs):
  backend/app/data/generated/network.json  lines, routes, stations, real track geometry
  frontend/public/city/manifest.json       building tile index + attribution
  frontend/public/city/tile-NNN.bin        packed building footprints
  frontend/public/city/tracks.bin          every running track + platform along the routes
  frontend/public/city/land.json           land + inland water polygons
  frontend/public/city/landcover.bin       parks, forest, mangrove, farmland, beaches, urban areas
  frontend/public/city/roads.bin           road centrelines by class

Station membership/order comes from `network_definitions.py`; positions,
track geometry, the individual tracks and platforms at each station,
buildings and coastline come from OSM via the Overpass
API. Raw responses are cached in backend/.osm-cache/ so re-runs don't
hit the public servers again; pass --refresh to refetch.

Data (c) OpenStreetMap contributors, available under the ODbL.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy
from shapely import STRtree, constrained_delaunay_triangles, make_valid
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import linemerge, polygonize, unary_union

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from network_definitions import LINES, LineDef, RouteDef, StationDef  # noqa: E402

from app.services.geometry import LocalPoint, to_latlon, to_local  # noqa: E402

REPO_DIR = BACKEND_DIR.parent
CACHE_DIR = BACKEND_DIR / ".osm-cache"
NETWORK_OUT = BACKEND_DIR / "app" / "data" / "generated" / "network.json"
CITY_OUT_DIR = REPO_DIR / "frontend" / "public" / "city"

# south, west, north, east
BBOX = (18.72, 72.76, 19.68, 73.52)
# Land, sea and inland water extend well past the network so the edge of
# the data is never on screen: past it everything reads as open sea.
LAND_BBOX = (18.2, 72.2, 20.3, 74.2)

MIRRORS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "RailView-data-build/0.2 (+https://github.com/56steve/railpulse)"
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"

EXCLUDED_SERVICES = {"yard", "siding", "spur"}
EXCLUDED_USAGE = {"industrial", "military", "tourism"}
EXCLUDED_NAME_FRAGMENTS = ("freight corridor", "port trust", "jnpt", "fci", "carshed", "siding", "uran")

SNAP_RADIUS_M = 300.0
SNAP_MAX_CANDIDATES = 40
SNAP_WEIGHT = 2.0
# Added to the snap cost of track farther from a station than
# MAX_STATION_OFFSET_M, so the path goes through the station whenever it
# can - even if that means running into a platform and reversing out
# (Panvel - Goregaon trains reverse at Wadala Road) rather than cutting
# the corner through the junction.
FAR_SNAP_PENALTY = 5000.0
# Kept well under the rail gauge so a train drawn on the route centreline
# sits on the same rails as the individually drawn OSM track it follows.
TRACK_SIMPLIFY_M = 0.25
MAX_STATION_OFFSET_M = 150.0

# Individual tracks: every OSM running line, loop and crossover within
# this distance of a route is drawn, which is what makes a four-track
# stretch or a seven-track terminus read as such.
RENDER_CORRIDOR_M = 60.0
RENDER_EXCLUDED_SERVICES = {"yard", "spur"}
MIN_RENDER_PIECE_M = 20.0
RENDER_SIMPLIFY_M = 0.25
PLATFORM_CORRIDOR_M = 80.0
PLATFORM_STATION_RADIUS_M = 600.0
OPEN_PLATFORM_HALF_WIDTH_M = 3.0
PLATFORM_SIMPLIFY_M = 0.2
STATION_PROBE_HALF_WIDTH_M = 70.0
PARALLEL_MAX_ANGLE_DEG = 30.0

# Running lanes: Indian Railways runs on the left, so on a double track a
# train keeps to the track on its left - Up trains (towards CSMT or
# Churchgate) on one, Down trains on the other. For each route and
# direction the build derives the sideways offset from the route
# centreline to that track.
LANE_SAMPLE_M = 10.0
LANE_PROBE_HALF_WIDTH_M = 16.0
LANE_MIN_GAP_M = 3.5
LANE_SIDE_WINDOW = 15  # samples either side when deciding which neighbour pairs with the centreline
LANE_MEDIAN_WINDOW = 5
LANE_MAX_SLEW_M = 1.0  # per sample - about a crossover's divergence
LANE_SIMPLIFY_M = 0.15
# At a terminus both directions use the same platform track (a train
# arrives and departs from it), then cross over to their own running line.
TERMINUS_HOLD_M = 150.0
TERMINUS_RAMP_M = 250.0

BUILDING_CORRIDOR_M = 450.0
TRACK_CLEARANCE_M = 4.0
PLATFORM_CLEARANCE_M = 1.5
MIN_BUILDING_AREA_M2 = 15.0
BUILDING_SIMPLIFY_M = 0.7
MAX_BUILDING_VERTICES = 64
TILE_SIZE_M = 1500.0
COORD_QUANTUM_M = 0.5

LAND_SIMPLIFY_M = 8.0
MIN_WATER_AREA_M2 = 150_000.0

# Land cover and roads: the network plus a margin the client fades them
# out across, so they blend into plain land rather than stopping at a line.
# Fetched as a grid of tiles anchored at a fixed origin, so extending the
# area only adds tiles and every cached tile stays valid. Tile (r, c)
# spans latitudes origin + r*cell .. +(r+1)*cell, and so on.
ENVIRONMENT_GRID_ORIGIN = (18.78, 72.68)
ENVIRONMENT_CELL_DEG = (0.245, 0.23)
ENVIRONMENT_ROWS = range(-1, 4)  # row -1 covers the Khopoli branch
ENVIRONMENT_COLS = range(0, 4)
ENVIRONMENT_BBOX = (
    ENVIRONMENT_GRID_ORIGIN[0] + ENVIRONMENT_ROWS.start * ENVIRONMENT_CELL_DEG[0],
    ENVIRONMENT_GRID_ORIGIN[1] + ENVIRONMENT_COLS.start * ENVIRONMENT_CELL_DEG[1],
    ENVIRONMENT_GRID_ORIGIN[0] + ENVIRONMENT_ROWS.stop * ENVIRONMENT_CELL_DEG[0],
    ENVIRONMENT_GRID_ORIGIN[1] + ENVIRONMENT_COLS.stop * ENVIRONMENT_CELL_DEG[1],
)
LANDCOVER_SIMPLIFY_M = 4.0
MIN_LANDCOVER_AREA_M2 = 300.0
# Built-up tints matter at neighbourhood scale, not per compound.
MIN_URBAN_LANDCOVER_AREA_M2 = 1000.0
URBAN_LANDCOVER_CLASSES = {"residential", "commercial", "industrial"}
# landcover.bin stores vertices as 16-bit offsets from the area's centre
# at this resolution - finer than the simplification tolerance above.
LANDCOVER_QUANTUM_M = 2.5
# Order matters: the client draws classes in this order (urban first,
# greens and sand over them) and landcover.bin stores them in it.
LANDCOVER_CLASSES = (
    "residential",
    "commercial",
    "industrial",
    "grass",
    "farmland",
    "scrub",
    "forest",
    "wetland",
    "mangrove",
    "sand",
)
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "minor")
# Minor streets only matter close up, and close up is along the railway.
MINOR_ROAD_CORRIDOR_M = 2500.0
ROAD_SIMPLIFY_M = 1.0
# roads.bin stores each polyline's first point as i32 and the rest as i16
# steps, all at this resolution.
ROAD_QUANTUM_M = 0.5


class BuildError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Overpass


def overpass(query: str, cache_key: str, refresh: bool) -> dict:
    cache_path = CACHE_DIR / f"{cache_key}.json"
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())

    body = urllib.parse.urlencode({"data": query}).encode()
    failures: list[str] = []
    for attempt in range(3):
        for mirror in MIRRORS:
            request = urllib.request.Request(mirror, data=body, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    payload = response.read()
                data = json.loads(payload)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                failures.append(f"{mirror}: {type(exc).__name__}: {exc}")
                continue
            remark = str(data.get("remark", ""))
            if "error" in remark.lower():
                failures.append(f"{mirror}: {remark}")
                continue
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(payload)
            print(f"  fetched {cache_key} via {mirror} ({len(payload) / 1e6:.1f} MB)")
            return data
        time.sleep(15 * (attempt + 1))
    raise BuildError(f"Overpass query '{cache_key}' failed on every mirror:\n" + "\n".join(failures))


def bbox_clause(bbox: tuple[float, float, float, float] = BBOX) -> str:
    s, w, n, e = bbox
    return f"({s},{w},{n},{e})"


# --------------------------------------------------------------------------
# Stations


@dataclass(frozen=True, slots=True)
class ResolvedStation:
    definition: StationDef
    lat: float
    lon: float
    source: str


def element_latlon(element: dict) -> tuple[float, float]:
    if element["type"] == "node":
        return element["lat"], element["lon"]
    center = element.get("center")
    if center is None:
        raise BuildError(f"{element['type']}/{element['id']} has no center")
    return center["lat"], center["lon"]


def resolve_station(definition: StationDef, elements: list[dict]) -> ResolvedStation:
    if definition.override_latlon is not None:
        lat, lon = definition.override_latlon
        return ResolvedStation(definition, lat, lon, f"override: {definition.override_reason}")

    if definition.osm_id is not None:
        for element in elements:
            if f"{element['type']}/{element['id']}" == definition.osm_id:
                lat, lon = element_latlon(element)
                return ResolvedStation(definition, lat, lon, definition.osm_id)
        raise BuildError(f"{definition.ref}: pinned element {definition.osm_id} not in station query")

    matches = [
        element
        for element in elements
        if definition.ref in (element.get("tags", {}).get("ref"), element.get("tags", {}).get("railway:ref"))
        and element.get("tags", {}).get("station") not in {"subway", "monorail", "light_rail"}
    ]
    if not matches:
        raise BuildError(f"{definition.ref} ({definition.name}): no OSM station with that ref")

    positions = [to_local(*element_latlon(m)) for m in matches]
    spread = max(math.dist((a.x, a.y), (b.x, b.y)) for a in positions for b in positions)
    if spread > 150:
        ids = ", ".join(f"{m['type']}/{m['id']}" for m in matches)
        raise BuildError(f"{definition.ref}: ambiguous ref across {ids}; pin one with osm_id")
    chosen = next((m for m in matches if m["type"] == "node"), matches[0])
    lat, lon = element_latlon(chosen)
    return ResolvedStation(definition, lat, lon, f"{chosen['type']}/{chosen['id']}")


# --------------------------------------------------------------------------
# Rail graph


@dataclass
class RailGraph:
    coords: dict[int, tuple[float, float]]  # node id -> local (x, y)
    latlon: dict[int, tuple[float, float]]
    adjacency: dict[int, list[tuple[int, float]]]
    grid: dict[tuple[int, int], list[int]]
    cell: float = 150.0

    def candidates(self, x: float, y: float, radius: float) -> dict[int, float]:
        cx, cy = int(math.floor(x / self.cell)), int(math.floor(y / self.cell))
        reach = int(math.ceil(radius / self.cell))
        found: list[tuple[float, int]] = []
        for gx in range(cx - reach, cx + reach + 1):
            for gy in range(cy - reach, cy + reach + 1):
                for node in self.grid.get((gx, gy), ()):
                    nx, ny = self.coords[node]
                    d = math.hypot(nx - x, ny - y)
                    if d <= radius:
                        found.append((d, node))
        found.sort()
        return {node: d for d, node in found[:SNAP_MAX_CANDIDATES]}


def keep_rail_way(tags: dict) -> bool:
    if tags.get("service") in EXCLUDED_SERVICES or tags.get("usage") in EXCLUDED_USAGE:
        return False
    name = (tags.get("name") or "").lower()
    return not any(fragment in name for fragment in EXCLUDED_NAME_FRAGMENTS)


def build_rail_graph(data: dict) -> RailGraph:
    node_latlon = {e["id"]: (e["lat"], e["lon"]) for e in data["elements"] if e["type"] == "node"}
    coords: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, list[tuple[int, float]]] = {}

    def local(node: int) -> tuple[float, float]:
        if node not in coords:
            p = to_local(*node_latlon[node])
            coords[node] = (p.x, p.y)
        return coords[node]

    kept = 0
    for way in (e for e in data["elements"] if e["type"] == "way"):
        if not keep_rail_way(way.get("tags", {})):
            continue
        kept += 1
        refs = [n for n in way["nodes"] if n in node_latlon]
        for a, b in zip(refs, refs[1:], strict=False):
            ax, ay = local(a)
            bx, by = local(b)
            w = math.hypot(bx - ax, by - ay)
            adjacency.setdefault(a, []).append((b, w))
            adjacency.setdefault(b, []).append((a, w))

    graph = RailGraph(coords=coords, latlon={n: node_latlon[n] for n in coords}, adjacency=adjacency, grid={})
    for node, (x, y) in coords.items():
        graph.grid.setdefault((int(math.floor(x / graph.cell)), int(math.floor(y / graph.cell))), []).append(node)
    print(f"  rail graph: {kept} ways, {len(coords)} nodes")
    return graph


def dijkstra_to_targets(
    graph: RailGraph, sources: dict[int, float], targets: Iterable[int]
) -> tuple[dict[int, float], dict[int, int]]:
    """Multi-source Dijkstra where each source starts at its own initial
    cost. Returns settled distances for the targets and the predecessor
    map for path reconstruction. Stops once every target is settled.
    """
    remaining = set(targets)
    dist = dict(sources)
    prev: dict[int, int] = {}
    settled: dict[int, float] = {}
    heap = [(cost, node) for node, cost in sources.items()]
    heapq.heapify(heap)
    while heap and remaining:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, math.inf):
            continue
        if node in remaining:
            settled[node] = d
            remaining.discard(node)
        for neighbour, weight in graph.adjacency.get(node, ()):
            nd = d + weight
            if nd < dist.get(neighbour, math.inf):
                dist[neighbour] = nd
                prev[neighbour] = node
                heapq.heappush(heap, (nd, neighbour))
    return settled, prev


def trace_back(prev: dict[int, int], end: int) -> list[int]:
    path = [end]
    while path[-1] in prev:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def path_length(graph: RailGraph, path: list[int]) -> float:
    return sum(math.dist(graph.coords[a], graph.coords[b]) for a, b in zip(path, path[1:], strict=False))


# --------------------------------------------------------------------------
# Lines


@dataclass
class BuiltRoute:
    line: LineDef
    definition: RouteDef
    track_local: list[tuple[float, float]]
    stations: list[dict]
    lanes: dict[str, list[list[float]]] | None = None


def match_route_to_graph(route: RouteDef, stations: list[ResolvedStation], graph: RailGraph) -> list[int]:
    """Map-match the ordered station list onto the rail graph.

    Picks exactly one track node per station so that the sum of
    (snap distance x SNAP_WEIGHT) plus track distance between consecutive
    stations is minimal over the whole line - a Viterbi-style dynamic
    program where each stage is one multi-source Dijkstra (every candidate
    of the previous station starts at its accumulated cost). One node per
    station means the path in and out of a station is continuous, and a
    dead-end platform track is never chosen because leaving it would cost
    a detour in the next stage.
    """
    candidate_sets = []
    for station in stations:
        p = to_local(station.lat, station.lon)
        radius = station.definition.reversal_snap_m or SNAP_RADIUS_M
        candidates = graph.candidates(p.x, p.y, radius)
        if not candidates:
            raise BuildError(f"{route.code}: no track within {radius:.0f}m of {station.definition.ref}")
        candidate_sets.append(
            {node: d + (FAR_SNAP_PENALTY if d > MAX_STATION_OFFSET_M else 0.0) for node, d in candidates.items()}
        )

    cost = {node: d * SNAP_WEIGHT for node, d in candidate_sets[0].items()}
    stage_prev: list[dict[int, int]] = []
    for index in range(1, len(stations)):
        settled, prev = dijkstra_to_targets(graph, cost, candidate_sets[index].keys())
        if not settled:
            a, b = stations[index - 1].definition.ref, stations[index].definition.ref
            raise BuildError(f"{route.code}: no track path {a}->{b} (graph disconnected)")
        cost = {node: d + candidate_sets[index][node] * SNAP_WEIGHT for node, d in settled.items()}
        stage_prev.append(prev)

    node = min(cost, key=cost.__getitem__)
    segments: list[list[int]] = []
    for prev in reversed(stage_prev):
        segment = trace_back(prev, node)
        segments.append(segment)
        node = segment[0]
    segments.reverse()

    for index, segment in enumerate(segments):
        a, b = stations[index], stations[index + 1]
        pa, pb = to_local(a.lat, a.lon), to_local(b.lat, b.lon)
        straight = math.dist((pa.x, pa.y), (pb.x, pb.y))
        length = path_length(graph, segment)
        if length > straight * 2.0 and length - straight > 800:
            raise BuildError(
                f"{route.code}: {a.definition.ref}->{b.definition.ref} matched {length:.0f}m of track "
                f"for {straight:.0f}m straight-line - looks like a detour"
            )

    path = segments[0]
    for segment in segments[1:]:
        path.extend(segment[1:])
    return path


def build_route(line: LineDef, route: RouteDef, stations: list[ResolvedStation], graph: RailGraph) -> BuiltRoute:
    polyline = [graph.coords[n] for n in match_route_to_graph(route, stations, graph)]
    simplified = LineString(polyline).simplify(TRACK_SIMPLIFY_M, preserve_topology=False)
    track = [(x, y) for x, y in simplified.coords]
    track_line = LineString(track)

    built_stations = []
    last_chainage = -1.0
    for sequence, station in enumerate(stations):
        p = to_local(station.lat, station.lon)
        chainage = track_line.project(Point(p.x, p.y))
        snapped = track_line.interpolate(chainage)
        offset = math.dist((p.x, p.y), (snapped.x, snapped.y))
        if offset > MAX_STATION_OFFSET_M:
            raise BuildError(f"{route.code}: {station.definition.ref} is {offset:.0f}m from the built track")
        if chainage <= last_chainage:
            raise BuildError(f"{route.code}: {station.definition.ref} is out of order along the track")
        last_chainage = chainage
        lat, lon = to_latlon(LocalPoint(snapped.x, snapped.y))
        built_stations.append(
            {
                "code": station.definition.ref,
                "name": station.definition.name,
                "sequence": sequence,
                "fast_halt": station.definition.fast_halt,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "position_source": station.source,
                "offset_from_osm_m": round(offset, 1),
            }
        )
    print(
        f"  {route.code}: {len(stations)} stations, track {track_line.length / 1000:.1f} km, "
        f"{len(track)} pts, max station offset {max(s['offset_from_osm_m'] for s in built_stations):.0f} m"
    )
    return BuiltRoute(line, route, track, built_stations)


def write_network(routes: list[BuiltRoute]) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "attribution": ATTRIBUTION,
        "lines": [{"code": line.code, "name": line.name, "color_hex": line.color_hex} for line in LINES],
        "routes": [
            {
                "code": built.definition.code,
                "line_code": built.line.code,
                "stations": built.stations,
                "running_lanes": built.lanes,
                "track": [
                    [round(lat, 6), round(lon, 6)]
                    for lat, lon in (to_latlon(LocalPoint(x, y)) for x, y in built.track_local)
                ],
            }
            for built in routes
        ],
    }
    NETWORK_OUT.parent.mkdir(parents=True, exist_ok=True)
    NETWORK_OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"  wrote {NETWORK_OUT.relative_to(REPO_DIR)}")


def overpass_tiled(query_body: str, cache_prefix: str, refresh: bool) -> list[dict]:
    """Run `query_body` (with a `{bbox}` placeholder) over the environment
    tile grid and merge the results, dropping elements several tiles
    return."""
    (lat0, lon0), (dlat, dlon) = ENVIRONMENT_GRID_ORIGIN, ENVIRONMENT_CELL_DEG
    seen: set[tuple[str, int]] = set()
    elements: list[dict] = []
    for r in ENVIRONMENT_ROWS:
        for c in ENVIRONMENT_COLS:
            tile = (lat0 + r * dlat, lon0 + c * dlon, lat0 + (r + 1) * dlat, lon0 + (c + 1) * dlon)
            clause = "({:.5f},{:.5f},{:.5f},{:.5f})".format(*tile)
            data = overpass(query_body.replace("{bbox}", clause), f"{cache_prefix}-r{r}c{c}", refresh)
            for element in data["elements"]:
                key = (element["type"], element["id"])
                if key not in seen:
                    seen.add(key)
                    elements.append(element)
    return elements


# --------------------------------------------------------------------------
# Individual tracks and platforms


def keep_render_way(tags: dict) -> bool:
    if tags.get("service") in RENDER_EXCLUDED_SERVICES or tags.get("usage") in EXCLUDED_USAGE:
        return False
    name = (tags.get("name") or "").lower()
    return not any(fragment in name for fragment in EXCLUDED_NAME_FRAGMENTS)


def line_parts(geometry) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, LineString)]


def polygon_parts(geometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, Polygon)]


def platform_polygons(element: dict) -> list[Polygon]:
    """OSM platforms come as closed ways (areas), open ways (a centreline
    along the platform edge) or multipolygon relations."""
    if element["type"] == "way":
        points = [(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in element.get("geometry", []))]
        if len(points) < 2:
            return []
        if len(points) >= 4 and points[0] == points[-1]:
            return polygon_parts(make_valid(Polygon(points)))
        return polygon_parts(LineString(points).buffer(OPEN_PLATFORM_HALF_WIDTH_M, cap_style="flat"))
    outers = [
        LineString([(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in member["geometry"])])
        for member in element.get("members", [])
        if member.get("role") == "outer" and len(member.get("geometry", [])) >= 2
    ]
    if not outers:
        return []
    merged = linemerge(MultiLineString(outers))
    return [poly for part in polygonize(merged) for poly in polygon_parts(make_valid(part))]


class TrackIndex:
    """Spatial index over the individually drawn tracks."""

    def __init__(self, tracks: list[LineString]) -> None:
        self.tracks = tracks
        self.tree = STRtree(tracks)

    def parallel_offsets(self, center: Point, tangent: tuple[float, float], half_width: float) -> list[float]:
        """Signed sideways offsets (positive = left of `tangent`) of every
        track a line drawn square across the route at `center` crosses,
        ignoring crossovers and lines crossing at an angle."""
        tx, ty = tangent
        nx, ny = -ty, tx
        probe = LineString(
            [(center.x - nx * half_width, center.y - ny * half_width), (center.x + nx * half_width, center.y + ny * half_width)]
        )
        max_cos = math.cos(math.radians(PARALLEL_MAX_ANGLE_DEG))
        offsets: list[float] = []
        for index in self.tree.query(probe, predicate="intersects"):
            track = self.tracks[int(index)]
            crossing = track.intersection(probe)
            for hit in getattr(crossing, "geoms", [crossing]):
                if not isinstance(hit, Point):
                    continue
                at = track.project(hit)
                a = track.interpolate(max(0.0, at - 3))
                b = track.interpolate(min(track.length, at + 3))
                dx, dy = b.x - a.x, b.y - a.y
                length = math.hypot(dx, dy)
                if length == 0 or abs(dx * tx + dy * ty) / length < max_cos:
                    continue
                offsets.append((hit.x - center.x) * nx + (hit.y - center.y) * ny)
        offsets.sort()
        # Collapse hits on the same track (ways split exactly at the probe).
        return [o for i, o in enumerate(offsets) if i == 0 or o - offsets[i - 1] > 1.5]


def tangent_at(line: LineString, chainage: float, half_span: float = 5.0) -> tuple[float, float]:
    a = line.interpolate(max(0.0, chainage - half_span))
    b = line.interpolate(min(line.length, chainage + half_span))
    length = math.hypot(b.x - a.x, b.y - a.y) or 1.0
    return (b.x - a.x) / length, (b.y - a.y) / length


def collect_render_tracks(routes: list[BuiltRoute], rail_data: dict) -> list[LineString]:
    """Every OSM running line, loop and crossover near a route, clipped to
    the route corridor."""
    corridor = unary_union([LineString(b.track_local).buffer(RENDER_CORRIDOR_M) for b in routes])
    node_local = {
        e["id"]: to_local(e["lat"], e["lon"]) for e in rail_data["elements"] if e["type"] == "node"
    }
    tracks: list[LineString] = []
    for way in (e for e in rail_data["elements"] if e["type"] == "way"):
        if not keep_render_way(way.get("tags", {})):
            continue
        points = [(node_local[n].x, node_local[n].y) for n in way["nodes"] if n in node_local]
        if len(points) < 2:
            continue
        line = LineString(points)
        if not line.intersects(corridor):
            continue
        for piece in line_parts(line.intersection(corridor)):
            if piece.length >= MIN_RENDER_PIECE_M:
                tracks.append(piece.simplify(RENDER_SIMPLIFY_M))
    return tracks


def _fill_gaps(values: list[float | None]) -> list[float]:
    """Linearly interpolate missing samples (held flat past either end)."""
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        return [0.0] * len(values)
    known_values = [v for v in values if v is not None]
    return [float(v) for v in numpy.interp(range(len(values)), known, known_values)]


def _smooth_lane(raw: list[float]) -> list[float]:
    w = LANE_MEDIAN_WINDOW
    median = [sorted(raw[max(0, i - w) : i + w + 1])[len(raw[max(0, i - w) : i + w + 1]) // 2] for i in range(len(raw))]
    # Limit how fast a train can drift sideways, both ways, so a lane
    # change reads as a crossover rather than a jump.
    for i in range(1, len(median)):
        median[i] = min(max(median[i], median[i - 1] - LANE_MAX_SLEW_M), median[i - 1] + LANE_MAX_SLEW_M)
    for i in range(len(median) - 2, -1, -1):
        median[i] = min(max(median[i], median[i + 1] - LANE_MAX_SLEW_M), median[i + 1] + LANE_MAX_SLEW_M)
    return median


def _station_local(station: dict) -> tuple[float, float]:
    p = to_local(station["lat"], station["lon"])
    return p.x, p.y


def compute_running_lanes(built: BuiltRoute, index: TrackIndex) -> dict[str, list[list[float]]]:
    """Sideways offset profile, per direction of travel, from the route
    centreline (itself one real track) to the track a train keeps to.

    Where the centreline has a parallel neighbour, the two form a pair:
    the train travelling towards increasing chainage takes whichever of
    the pair is on its left, the opposite direction the other. Which
    neighbour pairs with the centreline is decided by a majority over a
    few hundred metres so turnouts and platform loops don't flip it.
    """
    line = LineString(built.track_local)
    count = int(line.length // LANE_SAMPLE_M) + 1
    chainages = [min(i * LANE_SAMPLE_M, line.length) for i in range(count)] + [line.length]
    nearest_left: list[float | None] = []
    nearest_right: list[float | None] = []
    for chainage in chainages:
        offsets = index.parallel_offsets(line.interpolate(chainage), tangent_at(line, chainage), LANE_PROBE_HALF_WIDTH_M)
        left = [o for o in offsets if o >= LANE_MIN_GAP_M]
        right = [o for o in offsets if o <= -LANE_MIN_GAP_M]
        nearest_left.append(min(left) if left else None)
        nearest_right.append(max(right) if right else None)

    def side(i: int) -> int:
        l_gap, r_gap = nearest_left[i], nearest_right[i]
        if l_gap is None and r_gap is None:
            return 0
        if r_gap is None or (l_gap is not None and l_gap <= -r_gap):
            return 1
        return -1

    sides = [side(i) for i in range(len(chainages))]
    forward_raw: list[float | None] = []
    backward_raw: list[float | None] = []
    for i in range(len(chainages)):
        vote = sum(sides[max(0, i - LANE_SIDE_WINDOW) : i + LANE_SIDE_WINDOW + 1])
        if vote > 0:
            forward_raw.append(nearest_left[i])
            backward_raw.append(0.0)
        elif vote < 0:
            forward_raw.append(0.0)
            backward_raw.append(nearest_right[i])
        else:
            forward_raw.append(0.0)
            backward_raw.append(0.0)

    first = line.project(Point(*_station_local(built.stations[0])))
    last = line.project(Point(*_station_local(built.stations[-1])))

    def terminus_factor(chainage: float) -> float:
        from_end = min(abs(chainage - first), abs(last - chainage))
        return min(max((from_end - TERMINUS_HOLD_M) / TERMINUS_RAMP_M, 0.0), 1.0)

    def encode(raw: list[float | None]) -> list[list[float]]:
        smoothed = _smooth_lane(_fill_gaps(raw))
        profile = [d * terminus_factor(c) for c, d in zip(chainages, smoothed, strict=True)]
        simplified = LineString(list(zip(chainages, profile, strict=True))).simplify(LANE_SIMPLIFY_M)
        return [[round(c, 1), round(d, 2)] for c, d in simplified.coords]

    return {"forward": encode(forward_raw), "backward": encode(backward_raw)}


def build_tracks(routes: list[BuiltRoute], index: TrackIndex, refresh: bool):
    """Writes tracks.bin and returns the ground the tracks and platforms
    occupy, so buildings can be kept clear of it."""
    route_lines = [LineString(b.track_local) for b in routes]
    tracks = index.tracks

    platform_query = (
        f'[out:json][timeout:120];(way["railway"="platform"]{bbox_clause()};'
        f'relation["railway"="platform"]{bbox_clause()};);out tags geom;'
    )
    platform_data = overpass(platform_query, "platforms", refresh)
    station_points = [
        Point(p.x, p.y)
        for p in (to_local(s["lat"], s["lon"]) for built in routes for s in built.stations)
    ]
    station_zone = unary_union([p.buffer(PLATFORM_STATION_RADIUS_M) for p in station_points])
    platform_zone = unary_union([line.buffer(PLATFORM_CORRIDOR_M) for line in route_lines]).intersection(
        station_zone
    )
    platforms: list[Polygon] = []
    for element in platform_data["elements"]:
        for poly in platform_polygons(element):
            if poly.is_empty or not poly.intersects(platform_zone):
                continue
            for part in polygon_parts(make_valid(poly.simplify(PLATFORM_SIMPLIFY_M))):
                if part.area >= 20 and len(part.exterior.coords) >= 4:
                    platforms.append(orient(part, sign=1.0))

    chunks = [b"RVT1", struct.pack("<I", len(tracks))]
    for track in tracks:
        coords = list(track.coords)
        chunks.append(struct.pack("<I", len(coords)))
        chunks.extend(struct.pack("<ff", x, y) for x, y in coords)
    chunks.append(struct.pack("<I", len(platforms)))
    for poly in platforms:
        ring = list(poly.exterior.coords)[:-1]
        chunks.append(struct.pack("<I", len(ring)))
        chunks.extend(struct.pack("<ff", x, y) for x, y in ring)
    blob = b"".join(chunks)
    CITY_OUT_DIR.mkdir(parents=True, exist_ok=True)
    (CITY_OUT_DIR / "tracks.bin").write_bytes(blob)

    track_km = sum(t.length for t in tracks) / 1000
    print(
        f"  tracks: {len(tracks)} pieces, {track_km:.0f} km of individual track; "
        f"{len(platforms)} platforms; {len(blob) / 1e6:.2f} MB"
    )
    counts: dict[str, int] = {}
    for built, line in zip(routes, route_lines, strict=True):
        for station in built.stations:
            if station["name"] in counts:
                continue
            p = to_local(station["lat"], station["lon"])
            at = line.project(Point(p.x, p.y))
            counts[station["name"]] = len(
                index.parallel_offsets(line.interpolate(at), tangent_at(line, at, 10.0), STATION_PROBE_HALF_WIDTH_M)
            )
    print("  tracks through each station: " + ", ".join(f"{name} {n}" for name, n in counts.items()))

    return unary_union(
        [t.buffer(TRACK_CLEARANCE_M) for t in tracks] + [p.buffer(PLATFORM_CLEARANCE_M) for p in platforms]
    )


# --------------------------------------------------------------------------
# Buildings


def parse_height(tags: dict) -> float | None:
    raw = tags.get("height")
    if raw:
        try:
            return float(raw.lower().replace("m", "").strip())
        except ValueError:
            pass
    levels = tags.get("building:levels")
    if levels:
        try:
            return float(levels) * 3.2 + 1.0
        except ValueError:
            pass
    return None


def estimated_height(way_id: int, area: float) -> float:
    # Deterministic per building so re-runs produce identical output.
    rng = random.Random(way_id)
    if area > 1500:
        return rng.uniform(18, 60)
    if area > 400:
        return rng.uniform(10, 32)
    return rng.uniform(6, 16)


def polygon_to_overpass(poly: Polygon) -> str:
    points = []
    for x, y in poly.exterior.coords:
        lat, lon = to_latlon(LocalPoint(x, y))
        points.append(f"{lat:.5f} {lon:.5f}")
    return " ".join(points)


def largest_polygon(geometry) -> Polygon | None:
    if isinstance(geometry, Polygon):
        return geometry
    polys = [g for g in getattr(geometry, "geoms", []) if isinstance(g, Polygon)]
    return max(polys, key=lambda p: p.area) if polys else None


def build_city(routes: list[BuiltRoute], rail_ground, refresh: bool) -> None:
    tracks = [LineString(b.track_local) for b in routes]
    corridor = unary_union([t.buffer(BUILDING_CORRIDOR_M) for t in tracks]).simplify(40)
    parts = list(corridor.geoms) if isinstance(corridor, MultiPolygon) else [corridor]

    query = "[out:json][timeout:280];(" + "".join(
        f'way["building"](poly:"{polygon_to_overpass(part)}");' for part in parts
    ) + ");out tags geom;"
    data = overpass(query, "buildings", refresh)

    tiles: dict[tuple[int, int], list[tuple[float, list[tuple[float, float]]]]] = {}
    tagged = estimated = skipped = 0
    for way in data["elements"]:
        geometry = way.get("geometry")
        if way["type"] != "way" or not geometry or len(geometry) < 4:
            skipped += 1
            continue
        ring = [(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in geometry)]
        poly = largest_polygon(make_valid(Polygon(ring)))
        if poly is None or poly.area < MIN_BUILDING_AREA_M2 or poly.intersects(rail_ground):
            skipped += 1
            continue
        poly = poly.simplify(BUILDING_SIMPLIFY_M)
        tolerance = BUILDING_SIMPLIFY_M
        while len(poly.exterior.coords) - 1 > MAX_BUILDING_VERTICES:
            tolerance *= 2
            poly = poly.simplify(tolerance)
        poly = largest_polygon(poly)
        if poly is None or poly.is_empty or len(poly.exterior.coords) < 4:
            skipped += 1
            continue
        poly = orient(poly, sign=1.0)  # counter-clockwise in (east, north)

        height = parse_height(way.get("tags", {}))
        if height is None:
            height = estimated_height(way["id"], poly.area)
            estimated += 1
        else:
            tagged += 1
        height = min(max(height, 3.0), 400.0)

        centroid = poly.centroid
        key = (int(math.floor(centroid.x / TILE_SIZE_M)), int(math.floor(centroid.y / TILE_SIZE_M)))
        tiles.setdefault(key, []).append((height, list(poly.exterior.coords)[:-1]))

    CITY_OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in CITY_OUT_DIR.glob("tile-*.bin"):
        stale.unlink()

    manifest_tiles = []
    total_bytes = 0
    for index, (key, buildings) in enumerate(sorted(tiles.items())):
        ox, oy = key[0] * TILE_SIZE_M, key[1] * TILE_SIZE_M
        chunks = [b"RVB1", struct.pack("<I", len(buildings))]
        for height, ring in buildings:
            chunks.append(struct.pack("<HB", round(height * 10), len(ring)))
            for x, y in ring:
                qx = round((x - ox) / COORD_QUANTUM_M)
                qy = round((y - oy) / COORD_QUANTUM_M)
                if not (-32768 <= qx <= 32767 and -32768 <= qy <= 32767):
                    raise BuildError("building coordinate overflows tile quantization")
                chunks.append(struct.pack("<hh", qx, qy))
        blob = b"".join(chunks)
        name = f"tile-{index:03d}.bin"
        (CITY_OUT_DIR / name).write_bytes(blob)
        total_bytes += len(blob)
        origin_lat, origin_lon = to_latlon(LocalPoint(ox, oy))
        manifest_tiles.append(
            {
                "file": name,
                "origin": {"lat": round(origin_lat, 7), "lon": round(origin_lon, 7)},
                "size_m": TILE_SIZE_M,
                "count": len(buildings),
            }
        )

    manifest = {
        "version": 1,
        "attribution": ATTRIBUTION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "format": {
            "magic": "RVB1",
            "endianness": "little",
            "layout": "u32 count; per building: u16 height_dm, u8 n, n x (i16 east, i16 north)",
            "coord_quantum_m": COORD_QUANTUM_M,
            "winding": "counter-clockwise in (east, north)",
        },
        "stats": {
            "buildings": tagged + estimated,
            "height_tagged": tagged,
            "height_estimated": estimated,
            "skipped": skipped,
            "bytes": total_bytes,
        },
        "tiles": manifest_tiles,
    }
    (CITY_OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(
        f"  buildings: {tagged + estimated} kept ({tagged} height-tagged, {estimated} estimated), "
        f"{skipped} skipped, {len(tiles)} tiles, {total_bytes / 1e6:.2f} MB"
    )


# --------------------------------------------------------------------------
# Land / water


def left_side(line: LineString, point: Point) -> bool:
    distance = line.project(point)
    a = line.interpolate(max(distance - 1.0, 0.0))
    b = line.interpolate(min(distance + 1.0, line.length))
    return (b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x) > 0


def ring_latlon(coords: Iterable[tuple[float, float]]) -> list[list[float]]:
    out = []
    for x, y in coords:
        lat, lon = to_latlon(LocalPoint(x, y))
        out.append([round(lat, 5), round(lon, 5)])
    return out


def area_polygons(element: dict) -> list[Polygon]:
    """Polygons for an OSM area: a closed way, or a multipolygon relation
    (outer rings minus inner rings)."""
    def ring_lines(role: str) -> list[LineString]:
        return [
            LineString([(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in member["geometry"])])
            for member in element.get("members", [])
            if member.get("role", "outer") == role and len(member.get("geometry") or []) >= 2
        ]

    if element["type"] == "way":
        geometry = element.get("geometry") or []
        points = [(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in geometry)]
        if len(points) < 4 or points[0] != points[-1]:
            return []
        return polygon_parts(make_valid(Polygon(points)))

    outers = ring_lines("outer")
    if not outers:
        return []
    shell = unary_union(list(polygonize(linemerge(MultiLineString(outers)))))
    inners = ring_lines("inner")
    if inners:
        shell = shell.difference(unary_union(list(polygonize(linemerge(MultiLineString(inners))))))
    return polygon_parts(make_valid(shell))


def landcover_class(tags: dict) -> str | None:
    landuse, natural, leisure = tags.get("landuse"), tags.get("natural"), tags.get("leisure")
    if natural == "wetland":
        return "mangrove" if tags.get("wetland") == "mangrove" else "wetland"
    if natural in {"beach", "sand"}:
        return "sand"
    if landuse == "forest" or natural == "wood" or leisure == "nature_reserve":
        return "forest"
    if natural in {"scrub", "grassland", "heath", "bare_rock"}:
        return "scrub"
    if landuse in {"farmland", "orchard", "plant_nursery", "allotments"}:
        return "farmland"
    if landuse in {"grass", "meadow", "recreation_ground", "cemetery", "village_green"} or leisure in {
        "park",
        "garden",
        "golf_course",
        "pitch",
        "stadium",
    }:
        return "grass"
    if landuse == "residential":
        return "residential"
    if landuse in {"commercial", "retail"}:
        return "commercial"
    if landuse in {"industrial", "railway", "quarry", "military"}:
        return "industrial"
    return None


def triangulate(poly: Polygon) -> tuple[list[tuple[float, float]], list[int]]:
    vertices: list[tuple[float, float]] = []
    lookup: dict[tuple[float, float], int] = {}
    indices: list[int] = []
    for triangle in constrained_delaunay_triangles(poly).geoms:
        coords = list(triangle.exterior.coords)[:3]
        for x, y in coords:
            key = (round(x, 2), round(y, 2))
            if key not in lookup:
                lookup[key] = len(vertices)
                vertices.append(key)
            indices.append(lookup[key])
    return vertices, indices


def build_landcover(refresh: bool) -> None:
    query = (
        "[out:json][timeout:240];("
        'wr["landuse"~"^(forest|grass|meadow|farmland|orchard|recreation_ground|cemetery|village_green|'
        'residential|commercial|retail|industrial|plant_nursery|allotments|military|railway|quarry)$"]{bbox};'
        'wr["natural"~"^(wood|scrub|grassland|heath|wetland|beach|sand|bare_rock)$"]{bbox};'
        'wr["leisure"~"^(park|garden|golf_course|pitch|nature_reserve|stadium)$"]{bbox};'
        ");out tags geom;"
    )
    elements = overpass_tiled(query, "landcover", refresh)
    s, w, n, e = ENVIRONMENT_BBOX
    sw, ne = to_local(s, w), to_local(n, e)
    frame = box(sw.x, sw.y, ne.x, ne.y)

    meshes: dict[str, tuple[list[tuple[float, float]], list[int]]] = {c: ([], []) for c in LANDCOVER_CLASSES}
    counts = dict.fromkeys(LANDCOVER_CLASSES, 0)
    for element in elements:
        cls = landcover_class(element.get("tags", {}))
        if cls is None:
            continue
        for poly in area_polygons(element):
            if not poly.intersects(frame):
                continue
            clipped = poly.intersection(frame).simplify(LANDCOVER_SIMPLIFY_M)
            min_area = MIN_URBAN_LANDCOVER_AREA_M2 if cls in URBAN_LANDCOVER_CLASSES else MIN_LANDCOVER_AREA_M2
            for part in polygon_parts(make_valid(clipped)):
                if part.area < min_area:
                    continue
                vertices, indices = triangulate(part)
                mesh_vertices, mesh_indices = meshes[cls]
                base = len(mesh_vertices)
                mesh_vertices.extend(vertices)
                mesh_indices.extend(base + i for i in indices)
                counts[cls] += 1

    # Header: the covered bbox (south, west, north, east) so the client can
    # fade the layer out towards its edges, then the quantisation origin
    # (local east, north) and step. Per class: vertices as i16 offsets,
    # then indices as u16 where they fit (u32 otherwise).
    centre = frame.centroid
    chunks = [
        b"RVC2",
        struct.pack("<4d", *ENVIRONMENT_BBOX),
        struct.pack("<3d", centre.x, centre.y, LANDCOVER_QUANTUM_M),
        struct.pack("<I", len(LANDCOVER_CLASSES)),
    ]
    for cls in LANDCOVER_CLASSES:
        vertices, indices = meshes[cls]
        quantised = [
            (round((x - centre.x) / LANDCOVER_QUANTUM_M), round((y - centre.y) / LANDCOVER_QUANTUM_M))
            for x, y in vertices
        ]
        if any(not (-32768 <= qx <= 32767 and -32768 <= qy <= 32767) for qx, qy in quantised):
            raise BuildError(f"land cover {cls}: a vertex overflows 16-bit quantisation")
        chunks.append(struct.pack("<I", len(quantised)))
        chunks.append(struct.pack(f"<{2 * len(quantised)}h", *(v for pair in quantised for v in pair)))
        wide = len(vertices) > 65535
        chunks.append(struct.pack("<BI", 4 if wide else 2, len(indices)))
        chunks.append(struct.pack(f"<{len(indices)}{'I' if wide else 'H'}", *indices))
    blob = b"".join(chunks)
    (CITY_OUT_DIR / "landcover.bin").write_bytes(blob)
    summary = ", ".join(f"{cls} {counts[cls]}" for cls in LANDCOVER_CLASSES)
    print(f"  land cover: {summary}; {len(blob) / 1e6:.2f} MB")


def road_class(tags: dict) -> str | None:
    highway = (tags.get("highway") or "").removesuffix("_link")
    if tags.get("tunnel") in {"yes", "building_passage"} or tags.get("area") == "yes":
        return None
    if highway in {"motorway", "trunk", "primary", "secondary", "tertiary"}:
        return highway
    if highway in {"residential", "unclassified", "living_street"}:
        return "minor"
    return None


def build_roads(routes: list[BuiltRoute], refresh: bool) -> None:
    query = (
        "[out:json][timeout:240];("
        'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|'
        'secondary_link|tertiary_link|residential|unclassified|living_street)$"]{bbox};'
        ");out tags geom;"
    )
    elements = overpass_tiled(query, "roads", refresh)
    s, w, n, e = ENVIRONMENT_BBOX
    sw, ne = to_local(s, w), to_local(n, e)
    frame = box(sw.x, sw.y, ne.x, ne.y)
    near_rail = unary_union(
        [LineString(b.track_local).buffer(MINOR_ROAD_CORRIDOR_M) for b in routes]
    ).simplify(50)

    lines: dict[str, list[LineString]] = {c: [] for c in ROAD_CLASSES}
    for element in elements:
        cls = road_class(element.get("tags", {}))
        geometry = element.get("geometry") or []
        if cls is None or len(geometry) < 2:
            continue
        line = LineString([(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in geometry)])
        region = frame if cls != "minor" else near_rail
        if not line.intersects(region):
            continue
        for piece in line_parts(line.intersection(region)):
            if piece.length > 5:
                lines[cls].append(piece.simplify(ROAD_SIMPLIFY_M))

    # Header: covered bbox, then the quantum. Per class: u32 polyline count;
    # per polyline u32 n, i32 first (east, north), (n-1) x i16 steps.
    chunks = [
        b"RVR2",
        struct.pack("<4d", *ENVIRONMENT_BBOX),
        struct.pack("<d", ROAD_QUANTUM_M),
        struct.pack("<I", len(ROAD_CLASSES)),
    ]
    for cls in ROAD_CLASSES:
        chunks.append(struct.pack("<I", len(lines[cls])))
        for line in lines[cls]:
            points = [(round(x / ROAD_QUANTUM_M), round(y / ROAD_QUANTUM_M)) for x, y in line.coords]
            steps = [(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(points, points[1:], strict=False)]
            if any(not (-32768 <= dx <= 32767 and -32768 <= dy <= 32767) for dx, dy in steps):
                raise BuildError(f"road {cls}: a segment is too long for 16-bit steps")
            chunks.append(struct.pack("<Iii", len(points), *points[0]))
            chunks.append(struct.pack(f"<{2 * len(steps)}h", *(v for step in steps for v in step)))
    blob = b"".join(chunks)
    (CITY_OUT_DIR / "roads.bin").write_bytes(blob)
    km = {cls: sum(line.length for line in lines[cls]) / 1000 for cls in ROAD_CLASSES}
    print("  roads: " + ", ".join(f"{cls} {km[cls]:.0f} km" for cls in ROAD_CLASSES) + f"; {len(blob) / 1e6:.2f} MB")


def build_land(refresh: bool) -> None:
    wide = bbox_clause(LAND_BBOX)
    coast = overpass(f'[out:json][timeout:180];way["natural"="coastline"]{wide};out geom;', "coastline-wide", refresh)
    water = overpass(f'[out:json][timeout:240];way["natural"="water"]{wide};out geom;', "water-wide", refresh)

    s, w, n, e = LAND_BBOX
    sw, ne = to_local(s, w), to_local(n, e)
    frame = box(sw.x, sw.y, ne.x, ne.y)

    coast_lines = []
    for way in coast["elements"]:
        geometry = way.get("geometry") or []
        if len(geometry) >= 2:
            coast_lines.append(LineString([(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in geometry)]))
    if not coast_lines:
        raise BuildError("no coastline returned")

    clipped = [line.intersection(frame) for line in coast_lines]
    faces = list(polygonize(unary_union([*clipped, frame.exterior])))
    land = []
    for face in faces:
        probe = face.representative_point()
        nearest = min(coast_lines, key=lambda line: line.distance(probe))
        if left_side(nearest, probe):
            land.append(face)
    land_geometry = unary_union(land).simplify(LAND_SIMPLIFY_M)

    water_polys = []
    for way in water["elements"]:
        geometry = way.get("geometry") or []
        if len(geometry) < 4:
            continue
        poly = largest_polygon(make_valid(Polygon([(p.x, p.y) for p in (to_local(g["lat"], g["lon"]) for g in geometry)])))
        if poly is not None and poly.area >= MIN_WATER_AREA_M2:
            water_polys.append(poly.simplify(LAND_SIMPLIFY_M))

    def serialize(polys: Iterable[Polygon]) -> list[dict]:
        return [
            {"exterior": ring_latlon(p.exterior.coords), "holes": [ring_latlon(h.coords) for h in p.interiors]}
            for p in polys
            if not p.is_empty
        ]

    land_polys = list(land_geometry.geoms) if isinstance(land_geometry, MultiPolygon) else [land_geometry]
    payload = {
        "attribution": ATTRIBUTION,
        "bbox": {"south": s, "west": w, "north": n, "east": e},
        "land": serialize(land_polys),
        "water": serialize(water_polys),
    }
    (CITY_OUT_DIR / "land.json").write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(f"  land: {len(land_polys)} polygons, inland water: {len(water_polys)} polygons")


# --------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="ignore the local Overpass cache")
    args = parser.parse_args()

    print("stations")
    station_data = overpass(
        "[out:json][timeout:90];("
        f'nwr["railway"~"^(station|halt)$"]{bbox_clause()};'
        f'nwr["public_transport"="station"]["train"="yes"]{bbox_clause()};'
        ");out center tags;",
        "stations",
        args.refresh,
    )
    station_elements = station_data["elements"]

    print("rail network")
    rail_data = overpass(
        f'[out:json][timeout:180];way["railway"="rail"]{bbox_clause()};out body;>;out skel qt;',
        "rails",
        args.refresh,
    )
    graph = build_rail_graph(rail_data)

    print("routes")
    built = [
        build_route(line, route, [resolve_station(s, station_elements) for s in route.stations], graph)
        for line in LINES
        for route in line.routes
    ]
    track_index = TrackIndex(collect_render_tracks(built, rail_data))
    for route in built:
        route.lanes = compute_running_lanes(route, track_index)
        paired = sum(
            b[0] - a[0]
            for lane in route.lanes.values()
            for a, b in zip(lane, lane[1:], strict=False)
            if abs(a[1]) > 1 or abs(b[1]) > 1
        )
        print(f"  {route.definition.code}: running lanes separated over {paired / 1000:.1f} km (both directions)")
    write_network(built)

    print("tracks and platforms")
    rail_ground = build_tracks(built, track_index, args.refresh)

    print("buildings")
    build_city(built, rail_ground, args.refresh)

    print("land")
    build_land(args.refresh)

    print("land cover and roads")
    build_landcover(args.refresh)
    build_roads(built, args.refresh)


if __name__ == "__main__":
    try:
        main()
    except BuildError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        sys.exit(1)
