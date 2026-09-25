"""Which pair of tracks a train uses at each of its stops, and which way
it is going there. Slow-only stations have platforms on the slow pair
alone, so a train that passes one without calling is on the fast pair."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from app.services.platforms import Corridor, Direction


def stop_corridors(
    route_stations: Sequence[str],
    fast_halts: Collection[str],
    stops: Sequence[str],
    single_pair: Collection[str],
) -> tuple[Corridor, ...]:
    """The corridor each stop is reached on (the first stop: left on).

    A section that neither skips a station nor lies between two fast
    halts inherits the corridor of the section before it. That chain has
    to be built in route order (lowest station index first) rather than
    in travel order, or a train running DN-to-UP would inherit from the
    wrong end and default to "slow" for a leading fast section.
    """
    index = {name: i for i, name in enumerate(route_stations)}
    forward = len(stops) < 2 or index[stops[0]] < index[stops[-1]]
    ordered = stops if forward else tuple(reversed(stops))
    sections: list[Corridor] = []
    previous: Corridor = "slow"
    for a, b in zip(ordered, ordered[1:], strict=False):
        lo, hi = index[a], index[b]
        passed = route_stations[lo + 1 : hi]
        if any(name not in fast_halts for name in passed):
            corridor: Corridor = "fast"
        elif not passed and a in fast_halts and b in fast_halts:
            corridor = previous  # consecutive fast halts: stays on its pair
        else:
            corridor = "slow"
        sections.append(corridor)
        previous = corridor
    if not sections:
        return ("any",) * len(stops)
    per_ordered = [sections[0], *sections] if forward else [*sections, sections[-1]]
    by_name = dict(zip(ordered, per_ordered, strict=True))
    return tuple("any" if name in single_pair else by_name[name] for name in stops)


def stop_directions(direction: Direction, changes_at: str | None, stops: Sequence[str]) -> tuple[Direction, ...]:
    """The direction at each stop; it reverses after `changes_at`."""
    flipped: Direction = "DN" if direction == "UP" else "UP"
    result: list[Direction] = []
    passed_change = False
    for name in stops:
        result.append(flipped if passed_change else direction)
        if name == changes_at:
            passed_change = True
    return tuple(result)
