import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.services.platforms import (
    PlatformDataError,
    PlatformEntry,
    _platform_order,
    load_platform_table,
    resolve_platform,
)


@pytest.fixture(autouse=True)
def _reset_platform_table_cache() -> Iterator[None]:
    """`load_platform_table` is `lru_cache`d on its path argument; clear it
    around every test in this module so `tmp_path` fixtures never leak
    into another test's cache entry."""
    load_platform_table.cache_clear()
    yield
    load_platform_table.cache_clear()

ANDHERI_WR = (
    PlatformEntry(numbers=("3",), corridor="slow", direction="DN", role="through", door="left", certain=True),
    PlatformEntry(numbers=("5",), corridor="slow", direction="UP", role="through", door="left", certain=True),
    PlatformEntry(numbers=("6",), corridor="fast", direction="DN", role="through", door="right", certain=True),
    PlatformEntry(numbers=("7",), corridor="fast", direction="UP", role="through", door="right", certain=True),
    PlatformEntry(numbers=("4",), corridor="slow", direction="UP", role="originating", door="right", certain=False),
    PlatformEntry(numbers=("8", "9"), corridor="fast", direction="UP", role="originating", door=None, certain=False),
)

# Shaped after the plan's curated Kalyan data: through platforms on the
# fast pair, but only the slow pair has an originating entry.
KALYAN_CR = (
    PlatformEntry(numbers=("4",), corridor="fast", direction="DN", role="through", door="left", certain=True),
    PlatformEntry(numbers=("6",), corridor="fast", direction="DN", role="through", door="left", certain=True),
    PlatformEntry(numbers=("5",), corridor="fast", direction="UP", role="through", door="right", certain=True),
    PlatformEntry(numbers=("7",), corridor="fast", direction="UP", role="through", door="right", certain=True),
    PlatformEntry(
        numbers=("1", "1A"), corridor="slow", direction="UP", role="originating", door=None, certain=False
    ),
)


def test_through_stop_on_its_corridor_is_certain() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="slow", direction="DN", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("3",), "left", True)


def test_role_specific_entries_win() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="UP", role="originating")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("8", "9"), None, False)


def test_missing_role_falls_back_to_through() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="DN", role="terminating")
    assert p is not None and p.numbers == ("6",) and p.certain


def test_other_corridor_is_a_fallback_and_never_certain() -> None:
    only_slow = tuple(e for e in ANDHERI_WR if e.corridor == "slow" and e.role == "through")
    p = resolve_platform(only_slow, corridor="fast", direction="UP", role="through")
    assert p is not None and p.numbers == ("5",) and not p.certain


def test_any_corridor_matches_every_train() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door="right", certain=True),)
    p = resolve_platform(entries, corridor="slow", direction="DN", role="through")
    assert p is not None and p.numbers == ("1",) and p.certain


def test_several_matches_union_and_lose_certainty() -> None:
    entries = (
        PlatformEntry(numbers=("2",), corridor="any", direction="UP", role="through", door="left", certain=True),
        PlatformEntry(numbers=("1",), corridor="any", direction="UP", role="through", door="left", certain=True),
    )
    p = resolve_platform(entries, corridor="any", direction="UP", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("1", "2"), "left", False)


def test_no_entry_for_the_direction_is_none() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door=None, certain=True),)
    assert resolve_platform(entries, corridor="any", direction="UP", role="through") is None


def test_own_corridor_beats_role_match_on_the_other_corridor() -> None:
    # A fast train originating at Kalyan must go to its own fast
    # platforms (5, 7), not the slow platforms just because those have a
    # role-specific "originating" entry and the fast side doesn't.
    p = resolve_platform(KALYAN_CR, corridor="fast", direction="UP", role="originating")
    assert p is not None
    assert p.numbers == ("5", "7")
    assert not p.certain


def test_platform_order_sorts_numeric_then_letter_suffix() -> None:
    assert sorted(("10", "1A", "2"), key=_platform_order) == ["1A", "2", "10"]


GOOD_TABLE = {
    "attribution": "test fixture",
    "single_pair": [["CR", "Titwala"]],
    "stations": [
        {
            "line_code": "WR",
            "station": "Andheri",
            "platforms": [
                {
                    "numbers": ["3"],
                    "corridor": "slow",
                    "direction": "DN",
                    "role": "through",
                    "door": "left",
                    "certain": True,
                }
            ],
        }
    ],
}


def test_load_platform_table_parses_a_good_file(tmp_path: Path) -> None:
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(GOOD_TABLE))
    table = load_platform_table(path)
    assert table.attribution == "test fixture"
    assert table.single_pair == frozenset({("CR", "Titwala")})
    entries = table.entries("WR", "Andheri")
    assert len(entries) == 1 and entries[0].numbers == ("3",)


def test_load_platform_table_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PlatformDataError):
        load_platform_table(tmp_path / "does-not-exist.json")


def test_load_platform_table_bad_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "platforms.json"
    path.write_text("{not valid json")
    with pytest.raises(PlatformDataError):
        load_platform_table(path)


def test_load_platform_table_bad_corridor_value_raises(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(GOOD_TABLE))
    bad["stations"][0]["platforms"][0]["corridor"] = "Fast"
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(PlatformDataError):
        load_platform_table(path)


def test_load_platform_table_string_numbers_raises(tmp_path: Path) -> None:
    # "numbers": "10" is iterable character-by-character in Python, which
    # would silently produce platforms ("1", "0") instead of ("10",).
    bad = json.loads(json.dumps(GOOD_TABLE))
    bad["stations"][0]["platforms"][0]["numbers"] = "10"
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(bad))
    with pytest.raises(PlatformDataError):
        load_platform_table(path)


def test_load_platform_table_keeps_a_withheld_station_with_no_platforms(tmp_path: Path) -> None:
    table_json = json.loads(json.dumps(GOOD_TABLE))
    table_json["stations"].append({"line_code": "HR", "station": "Sanpada", "platforms": []})
    path = tmp_path / "platforms.json"
    path.write_text(json.dumps(table_json))
    table = load_platform_table(path)
    assert ("HR", "Sanpada") in table.stations
    assert table.entries("HR", "Sanpada") == ()
