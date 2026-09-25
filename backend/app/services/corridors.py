"""Which pair of tracks a train uses at each of its stops, and which way
it is going there. Slow-only stations have platforms on the slow pair
alone, so a train that passes one without calling is on the fast pair."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from itertools import pairwise

from app.services.platforms import Corridor, Direction


def _route_index(route_stations: Sequence[str]) -> dict[str, int]:
    return {name: i for i, name in enumerate(route_stations)}


def _stop_positions(index: dict[str, int], stops: Sequence[str]) -> list[int]:
    positions: list[int] = []
    for name in stops:
        if name not in index:
            raise ValueError(f"{name!r} is not a station on this route")
        positions.append(index[name])
    if len(positions) > 1:
        increasing = all(a < b for a, b in pairwise(positions))
        decreasing = all(a > b for a, b in pairwise(positions))
        if not (increasing or decreasing):
            raise ValueError("stops must run strictly forward or strictly backward along the route")
    return positions


def _fill_undecided(sections: list[Corridor | None]) -> list[Corridor]:
    """Undecided sections (adjacent fast halts, nothing skipped) take the
    nearest decided corridor: earlier in route order first, then later.
    "slow" only if nothing in the whole run is decided."""
    filled: list[Corridor | None] = list(sections)
    last: Corridor | None = None
    for i, corridor in enumerate(filled):
        if corridor is not None:
            last = corridor
        elif last is not None:
            filled[i] = last
    following: Corridor | None = None
    for i in range(len(filled) - 1, -1, -1):
        corridor = filled[i]
        if corridor is not None:
            following = corridor
        elif following is not None:
            filled[i] = following
    return [corridor if corridor is not None else "slow" for corridor in filled]


def stop_corridors(
    route_stations: Sequence[str],
    fast_halts: Collection[str],
    stops: Sequence[str],
    single_pair: Collection[str],
) -> tuple[Corridor, ...]:
    """The corridor each stop is reached on (the first stop: left on).

    A section passing a slow-only station is fast; a section between two
    fast halts passing only fast halts (or none) takes its track pair
    from the nearest decided section - earlier in route order first,
    then later - which has to happen in route order (lowest station
    index first), not in travel order, or a DN-to-UP train would inherit
    from the wrong end.
    """
    index = _route_index(route_stations)
    positions = _stop_positions(index, stops)
    forward = len(positions) < 2 or positions[0] < positions[-1]
    ordered = stops if forward else tuple(reversed(stops))

    raw: list[Corridor | None] = []
    for a, b in pairwise(ordered):
        lo, hi = index[a], index[b]
        passed = route_stations[lo + 1 : hi]
        if any(name not in fast_halts for name in passed):
            corridor: Corridor | None = "fast"
        elif a in fast_halts and b in fast_halts:
            corridor = None  # undecided: filled in below
        else:
            corridor = "slow"
        raw.append(corridor)

    if not raw:
        return ("any",) * len(stops)
    sections = _fill_undecided(raw)
    per_ordered = [sections[0], *sections] if forward else [*sections, sections[-1]]
    by_name = dict(zip(ordered, per_ordered, strict=True))
    return tuple("any" if name in single_pair else by_name[name] for name in stops)


def stop_directions(direction: Direction, changes_at: str | None, stops: Sequence[str]) -> tuple[Direction, ...]:
    """The direction at each stop; it reverses after `changes_at`."""
    if changes_at is not None and changes_at not in stops:
        raise ValueError(f"{changes_at!r} is not one of the stops")
    flipped: Direction = "DN" if direction == "UP" else "UP"
    result: list[Direction] = []
    passed_change = False
    for name in stops:
        result.append(flipped if passed_change else direction)
        if name == changes_at:
            passed_change = True
    return tuple(result)
