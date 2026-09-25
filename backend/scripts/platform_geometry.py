"""Geometry for pairing OpenStreetMap platforms with the tracks beside
them, and for reading platform numbers and track names. Coordinates are
local metres (east, north)."""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Sequence
from itertools import combinations
from typing import Literal

from shapely.geometry import LineString, MultiPoint, Point, Polygon

Side = Literal["left", "right"]
Door = Literal["left", "right", "both"]
TrackCorridor = Literal["slow", "fast"]
LineCode = Literal["WR", "CR", "HR", "THR"]

# A platform number: one or two digits and an optional letter suffix,
# standing alone (so "10A1", "123" and station codes give nothing).
_NUMBER = re.compile(r"(?<![0-9A-Z])(\d{1,2}[A-Z]?)(?![0-9A-Z])")
_LEADING_DIGITS = re.compile(r"(\d+)(.*)")

# Name fragments naming each line, most specific first: "Central Railway
# (Harbour Line)" is Harbour, not Central.
_LINE_NAMES: tuple[tuple[str, LineCode], ...] = (
    ("trans-harbour", "THR"),
    ("trans harbour", "THR"),
    ("harbour", "HR"),
    ("western", "WR"),
    ("mumbai-delhi", "WR"),
    ("mumbai - delhi", "WR"),
    ("central", "CR"),
    ("mumbai-pune", "CR"),
    ("mumbai - pune", "CR"),
    ("mumbai–nagpur", "CR"),
)

# Known platforms further than this across the station from a platform
# being paired belong to another series (Dadar's Western 1-7 and Central
# 8-14): only use them if nothing nearer is known.
NUMBERING_WINDOW_M = 40.0
# Tracks closer than this across are the same track drawn as two ways.
SAME_TRACK_M = 1.5
# A point this close to a line is on it: neither left nor right.
SIDE_TOLERANCE_M = 0.5
# A track crossing a line square across the route at more than this angle
# to the route is crossing it, not running alongside.
PARALLEL_MAX_ANGLE_DEG = 30.0


def track_corridor(name: str | None) -> TrackCorridor | None:
    """The corridor a track's OSM name gives, if any."""
    lowered = (name or "").lower()
    if "fast" in lowered:
        return "fast"
    if "slow" in lowered:
        return "slow"
    return None


def track_line(name: str | None) -> LineCode | None:
    """The suburban line a track's OSM name belongs to, if any."""
    lowered = (name or "").lower()
    for fragment, line in _LINE_NAMES:
        if fragment in lowered:
            return line
    return None


def platform_numbers(ref: str | None) -> tuple[str, ...]:
    """Platform numbers in an OSM ref; station codes and prose give none."""
    numbers = _NUMBER.findall((ref or "").upper())
    return tuple(dict.fromkeys(numbers))


def platform_sort_key(number: str) -> tuple[int, str]:
    """Orders platform numbers as the station does: 9, 9A, 10."""
    match = _LEADING_DIGITS.match(number)
    return (int(match.group(1)), match.group(2)) if match else (10**6, number)


def side_of(line: LineString, point: tuple[float, float], forward: bool) -> Side | None:
    """Which side of `line` the point lies on, travelling along it
    (forward: in the order of its coordinates); None if it lies within
    SIDE_TOLERANCE_M of the line, where the side is noise."""
    p = Point(point)
    if line.distance(p) <= SIDE_TOLERANCE_M:
        return None
    along = line.project(p)
    a = line.interpolate(max(along - 1.0, 0.0))
    b = line.interpolate(min(along + 1.0, line.length))
    cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
    if cross == 0:
        return None
    left = cross > 0
    return "left" if left == forward else "right"


def left_track(
    tracks: Sequence[LineString], forward: bool, station_point: tuple[float, float]
) -> LineString | None:
    """Of a pair of parallel tracks, the one a train travelling `forward`
    (in the first track's coordinate order) runs on: the left one. None if
    they lie too close together to tell."""
    reference = tracks[0]
    for track in tracks[1:]:
        side = side_of(reference, _nearest_point(track, station_point), forward)
        if side is None:
            return None
        if side == "left":
            return track
    return reference  # nothing lies to its left: it is the left one


def _nearest_point(track: LineString, point: tuple[float, float]) -> tuple[float, float]:
    nearest = track.interpolate(track.project(Point(point)))
    return (nearest.x, nearest.y)


def adjacent_tracks(platform: Polygon, tracks: Sequence[LineString], max_gap_m: float = 4.0) -> list[LineString]:
    """Tracks running along the platform within `max_gap_m` of its edge
    for more than a few metres."""
    edge = platform.exterior
    reach = platform.buffer(max_gap_m)
    return [t for t in tracks if t.distance(edge) <= max_gap_m and t.intersection(reach).length > 10.0]


def orient_along(line: LineString, tangent: tuple[float, float]) -> LineString:
    """`line`, reversed if it was drawn against `tangent`."""
    (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
    if (x1 - x0) * tangent[0] + (y1 - y0) * tangent[1] >= 0:
        return line
    return LineString(list(line.coords)[::-1])


def offset_from(line: LineString, point: tuple[float, float]) -> float:
    """Signed distance of `point` from `line`: positive to the left
    travelling along it, so it follows the line round curves."""
    side = side_of(line, point, forward=True)
    if side is None:
        return 0.0
    distance = float(line.distance(Point(point)))
    return distance if side == "left" else -distance


def probe_offset(
    lines: Sequence[LineString], origin: tuple[float, float], tangent: tuple[float, float], half_width: float
) -> float | None:
    """Where a track (its ways) crosses a line drawn square across the
    route at `origin`: the signed offset along it, positive to the left of
    `tangent` (a unit vector). The crossing nearest `origin` counts; one at
    more than PARALLEL_MAX_ANGLE_DEG to the route doesn't. None if the
    track doesn't cross it (it ends before the station)."""
    nx, ny = -tangent[1], tangent[0]
    ox, oy = origin
    probe = LineString([(ox - nx * half_width, oy - ny * half_width), (ox + nx * half_width, oy + ny * half_width)])
    min_cos = math.cos(math.radians(PARALLEL_MAX_ANGLE_DEG))
    offsets: list[float] = []
    for line in lines:
        crossing = line.intersection(probe)
        hits = crossing.geoms if isinstance(crossing, MultiPoint) else [crossing]
        for hit in hits:
            if not isinstance(hit, Point) or hit.is_empty:
                continue
            at = line.project(hit)
            a = line.interpolate(max(at - 3.0, 0.0))
            b = line.interpolate(min(at + 3.0, line.length))
            length = math.hypot(b.x - a.x, b.y - a.y)
            if length == 0 or abs((b.x - a.x) * tangent[0] + (b.y - a.y) * tangent[1]) / length < min_cos:
                continue
            offsets.append((hit.x - ox) * nx + (hit.y - oy) * ny)
    return min(offsets, key=abs) if offsets else None


def numbering_increases_left(known: Sequence[tuple[float, str]], near: float) -> bool | None:
    """Whether platform numbers grow to the left (positive offset) around
    the lateral offset `near`, from (offset, number) pairs already known.

    Uses the known tracks within NUMBERING_WINDOW_M of `near` (or the two
    nearest, if fewer lie that close). None if fewer than two distinct
    tracks are known or they disagree.
    """
    tracks: list[tuple[float, str]] = []
    for offset, number in sorted(known, key=lambda pair: abs(pair[0] - near)):
        if all(abs(offset - other) > SAME_TRACK_M for other, _ in tracks):
            tracks.append((offset, number))
    window = [pair for pair in tracks if abs(pair[0] - near) <= NUMBERING_WINDOW_M]
    considered = window if len(window) >= 2 else tracks[:2]
    signs = {
        (platform_sort_key(nb) > platform_sort_key(na)) == (ob > oa)
        for (oa, na), (ob, nb) in combinations(considered, 2)
        if platform_sort_key(na) != platform_sort_key(nb)
    }
    return signs.pop() if len(signs) == 1 else None


def _fits_numbering(
    number: str, at: float, known: Sequence[tuple[float, str]], increases_left: bool
) -> bool:
    """Whether `number` on the track at offset `at` fits the known numbers
    nearby: lower ones on the side numbering comes from, higher ones on
    the other."""
    key = platform_sort_key(number)
    for offset, other in known:
        if abs(offset - at) > NUMBERING_WINDOW_M or abs(offset - at) <= SAME_TRACK_M:
            continue
        on_lower_side = (offset > at) != increases_left
        if (platform_sort_key(other) < key) != on_lower_side:
            return False
    return True


def pair_by_numbering(
    numbers: tuple[str, str],
    offsets: tuple[float, float],
    increases_left: bool,
    known: Sequence[tuple[float, str]],
) -> dict[str, int] | None:
    """Which of two tracks (by index into `offsets`) each of an island
    platform's two numbers belongs to, given the numbering direction; None
    if either number doesn't fit the known numbers around it."""
    low, high = sorted(numbers, key=platform_sort_key)
    left_index = 0 if offsets[0] > offsets[1] else 1
    right_index = 1 - left_index
    assignment = {low: right_index, high: left_index} if increases_left else {low: left_index, high: right_index}
    if all(_fits_numbering(number, offsets[index], known, increases_left) for number, index in assignment.items()):
        return assignment
    return None


def place_by_numbering(number: str, offsets: tuple[float, float], known: Sequence[tuple[float, str]]) -> int | None:
    """Which of an island's two tracks (by index into `offsets`) carries
    the one number it is tagged with: the face towards the lower numbers,
    provided the number fits the known numbers on either side of it."""
    near = (offsets[0] + offsets[1]) / 2
    increases_left = numbering_increases_left(known, near)
    if increases_left is None:
        return None
    left_index = 0 if offsets[0] > offsets[1] else 1
    index = 1 - left_index if increases_left else left_index
    return index if _fits_numbering(number, offsets[index], known, increases_left) else None


def door_from_sides(sides: Collection[Side]) -> Door | None:
    """The door side for a track with platforms on the given sides."""
    if not sides:
        return None
    if len(set(sides)) > 1:
        return "both"
    return next(iter(sides))


def common_door(doors: Iterable[Door | None]) -> Door | None:
    """The side the doors open on whichever of several platforms a train
    uses: a platform with both sides open agrees with either."""
    candidates = list(doors)
    if not candidates or any(door is None for door in candidates):
        return None
    sides = {door for door in candidates if door != "both"}
    if not sides:
        return "both"
    return next(iter(sides)) if len(sides) == 1 else None

