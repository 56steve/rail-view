"""Integrity checks on the imported official timetable (timetable.json)."""

import json
from collections import Counter
from pathlib import Path

import pytest

TIMETABLE = Path(__file__).resolve().parents[1] / "app" / "data" / "generated" / "timetable.json"


@pytest.fixture(scope="module")
def timetable() -> dict:
    return json.loads(TIMETABLE.read_text())


@pytest.fixture(scope="module")
def trains(timetable: dict) -> dict[str, dict]:
    return {t["number"]: t for t in timetable["trains"]}


def test_every_train_number_is_unique(timetable: dict) -> None:
    numbers = Counter(t["number"] for t in timetable["trains"])
    assert [n for n, c in numbers.items() if c > 1] == []


def test_every_train_runs_forward_in_time(timetable: dict) -> None:
    for t in timetable["trains"]:
        assert len(t["stops"]) >= 2, t["number"]
        for (_, arr, dep) in t["stops"]:
            assert arr <= dep, t["number"]
        for (_, _, dep), (_, arr, _) in zip(t["stops"], t["stops"][1:], strict=False):
            assert arr >= dep, t["number"]
        assert t["stops"][-1][1] - t["stops"][0][2] < 5 * 60, t["number"]


def test_no_train_calls_at_a_station_twice(timetable: dict) -> None:
    for t in timetable["trains"]:
        names = [s[0] for s in t["stops"]]
        assert len(names) == len(set(names)), t["number"]


@pytest.mark.parametrize(
    ("line", "low", "high"),
    [("main", 850, 950), ("harbour", 550, 700), ("transharbour", 240, 280), ("western", 1200, 1400)],
)
def test_service_counts_match_the_published_scale(timetable: dict, line: str, low: int, high: int) -> None:
    count = sum(1 for t in timetable["trains"] if t["line"] == line)
    assert low <= count <= high


def test_known_trains_read_as_published(trains: dict[str, dict]) -> None:
    kasara = trains["96401"]  # first page of the CR main line DN timetable
    assert kasara["code"] == "N 1"
    assert kasara["stops"][0] == ["CSMT", 8, 8]
    assert kasara["stops"][-1][0] == "Kasara"

    trans_harbour = trains["99003"]  # Thane - Panvel
    assert [s[0] for s in trans_harbour["stops"]][:2] == ["Thane", "Digha Gaon"]
    assert trans_harbour["stops"][0][2] == 5 * 60 + 12


def test_split_listings_are_joined(trains: dict[str, dict]) -> None:
    panvel_goregaon = trains["98901"]
    names = [s[0] for s in panvel_goregaon["stops"]]
    assert names[0] == "Panvel" and names[-1] == "Goregaon"
    assert panvel_goregaon["direction_changes_at"] == "Wadala Road"


def test_source_typos_are_corrected_and_recorded(timetable: dict, trains: dict[str, dict]) -> None:
    prabhadevi = next(s for s in trains["91039"]["stops"] if s[0] == "Prabhadevi")
    assert prabhadevi[1] == 28  # printed 12:28, between 00:25 and 00:30
    assert any("91039" in c and "Prabhadevi" in c for c in timetable["corrections"])


def test_central_marks_are_interpreted(timetable: dict) -> None:
    days = Counter(t["days"] for t in timetable["trains"] if t["railway"] == "CR")
    # X (not on Sunday/holiday) is common on Central; XX is rarer.
    assert days["not_sunday"] > 200
    assert all("flags" not in t for t in timetable["trains"])


def test_sources_are_pinned(timetable: dict) -> None:
    assert len(timetable["sources"]) == 7
    for source in timetable["sources"]:
        assert len(source["sha256"]) == 64
        assert source["url"].startswith("https://")
