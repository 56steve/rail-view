"""`load_timetable`'s own behaviour: failing loudly on bad direction data,
and the exact platforms it resolves for a real reversing train."""

import json
from pathlib import Path

import pytest

from app.services.platforms import resolve_platform
from app.services.timetable import Timetable, TimetableError, load_timetable

WESTERN_STOPS = [["Churchgate", 300, 300], ["Marine Lines", 303, 303], ["Charni Road", 306, 306]]


def _entry(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "number": "T1",
        "code": "T 1",
        "line": "western",
        "direction": "DN",
        "direction_changes_at": None,
        "ac": False,
        "non_ac_at_weekends": False,
        "cars": 12,
        "days": "all",
        "ladies_special": False,
        "stops": WESTERN_STOPS,
    }
    fields.update(overrides)
    return fields


def _load(tmp_path: Path, *entries: dict[str, object]) -> Timetable:
    path = tmp_path / "timetable.json"
    path.write_text(json.dumps({"trains": list(entries)}))
    # Each tmp_path is unique, but clear defensively: lru_cache never
    # caches a call that raised, so this only matters if a test reuses
    # `path` after rewriting it.
    load_timetable.cache_clear()
    return load_timetable(path)


def test_missing_direction_fails_loudly(tmp_path: Path) -> None:
    entry = _entry()
    del entry["direction"]
    with pytest.raises(TimetableError, match="train T1.*direction"):
        _load(tmp_path, entry)


def test_invalid_direction_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(TimetableError, match="train T1.*direction"):
        _load(tmp_path, _entry(direction="SIDEWAYS"))


def test_direction_changes_at_not_among_the_stops_fails_loudly(tmp_path: Path) -> None:
    """stop_directions raises ValueError for this; load_timetable must
    turn it into a TimetableError naming the train, not let it escape
    raw."""
    with pytest.raises(TimetableError, match="train T1.*Bandra"):
        _load(tmp_path, _entry(direction_changes_at="Bandra"))


def test_a_valid_direction_still_loads(tmp_path: Path) -> None:
    timetable = _load(tmp_path, _entry())
    assert timetable.trains[0].direction == "DN"


# -- pinned wiring: train 98901, Panvel -> Goregaon, reverses at Wadala Road --


def test_98901_wadala_and_kings_circle_platforms_are_pinned() -> None:
    train = load_timetable().by_number()["98901"]
    by_name = {stop.station_name: stop for stop in train.stops}

    wadala = by_name["Wadala Road"]
    assert wadala.platform is not None
    assert wadala.platform.numbers == ("4",)

    kings_circle = by_name["King's Circle"]
    assert kings_circle.platform is not None
    assert kings_circle.platform.numbers == ("1",)


def test_98901_first_and_last_stops_match_resolve_platform() -> None:
    """The originating and terminating stops are exactly what
    resolve_platform gives for their own corridor, direction and role -
    not a special case in load_timetable."""
    from app.data.mumbai_network import load_routes
    from app.services.corridors import stop_corridors, stop_directions
    from app.services.platforms import load_platform_table

    train = load_timetable().by_number()["98901"]
    route = load_routes()[train.route_code]
    names = [stop.station_name for stop in train.stops]
    route_names = [station.name for station in route.stations]
    fast_halts = {station.name for station in route.stations if station.fast_halt}
    platforms = load_platform_table()
    single_pair = {name for line, name in platforms.single_pair if line == train.line_code}

    corridors = stop_corridors(route_names, fast_halts, names, single_pair)
    directions = stop_directions(train.direction, train.direction_changes_at, names)

    expected_first = resolve_platform(
        platforms.entries(train.line_code, names[0]),
        corridor=corridors[0],
        direction=directions[0],
        role="originating",
    )
    expected_last = resolve_platform(
        platforms.entries(train.line_code, names[-1]),
        corridor=corridors[-1],
        direction=directions[-1],
        role="terminating",
    )
    assert train.stops[0].platform == expected_first
    assert train.stops[-1].platform == expected_last
