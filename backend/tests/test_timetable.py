"""`load_timetable`'s own behaviour: failing loudly on bad direction data,
and the exact platforms it resolves for a real reversing train."""

import json
from pathlib import Path

import pytest

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
    # Bypass the cache: these files are one-offs, and clearing it would
    # make every later test reload the real timetable.
    return load_timetable.__wrapped__(path)


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


def test_a_train_starting_at_a_terminus_gets_its_departure_platforms() -> None:
    # CSMT's Harbour platforms (1-2) are listed for trains starting there;
    # resolved as a through stop it would have none.
    first = load_timetable().by_number()["98301"].stops[0]
    assert first.station_name == "CSMT"
    assert first.platform is not None
    assert (first.platform.numbers, first.platform.door, first.platform.certain) == (("1", "2"), "both", False)


def test_a_train_ending_at_a_terminus_gets_its_arrival_platform() -> None:
    # Vashi has a platform for trains ending there; as a through stop it
    # would be the through pair, 3-4.
    last = load_timetable().by_number()["98573"].stops[-1]
    assert last.station_name == "Vashi"
    assert last.platform is not None
    assert (last.platform.numbers, last.platform.certain) == (("2",), True)
