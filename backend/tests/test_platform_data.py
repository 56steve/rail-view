"""Data checks over the generated platform table and the real timetable,
the way test_network_data.py guards network.json.

Coverage is deliberately incomplete (94 curated/derived stations, not
every line-station), so the thresholds below are regression guards set a
few points under what the real data actually measures, not the higher
bars a fully-curated table might reach. See the measurements printed by
`test_measured_coverage_is_reported` (run with `-s`) for the exact
figures this was tuned against.
"""

from app.services.platforms import load_platform_table
from app.services.timetable import load_timetable

# Exact through-platform layouts, confirmed against the generated table.
# Dadar WR fast DN is deliberately excluded: it is curated as ("3", "5")
# because OSM and the renumbering notice disagree on which single number
# is current, so it is checked separately for "contains 3" instead of
# equality.
KNOWN = {
    ("WR", "Andheri", "slow", "DN"): ("3",),
    ("WR", "Andheri", "slow", "UP"): ("5",),
    ("WR", "Andheri", "fast", "DN"): ("6",),
    ("WR", "Andheri", "fast", "UP"): ("7",),
    ("WR", "Dadar", "slow", "DN"): ("1",),
    ("WR", "Dadar", "slow", "UP"): ("2",),
    ("WR", "Dadar", "fast", "UP"): ("4",),
}

# Measured on the real timetable: ~0.70 of stops have a platform and
# ~0.63 of through stops with a platform are certain. Thresholds are set
# a few points below each measurement as a regression guard.
MIN_STOPS_WITH_PLATFORM = 0.65
MIN_THROUGH_STOPS_CERTAIN = 0.58


def test_known_layouts_are_exact() -> None:
    table = load_platform_table()
    for (line, station, corridor, direction), numbers in KNOWN.items():
        through = [
            e
            for e in table.entries(line, station)
            if e.role == "through" and e.corridor == corridor and e.direction == direction
        ]
        assert [e.numbers for e in through] == [numbers], (line, station, corridor, direction)


def test_dadar_fast_dn_includes_platform_3() -> None:
    """Curated because OSM and the renumbering notice disagree; only the
    presence of platform 3 is asserted, not an exact single number."""
    table = load_platform_table()
    through = [
        e
        for e in table.entries("WR", "Dadar")
        if e.role == "through" and e.corridor == "fast" and e.direction == "DN"
    ]
    assert len(through) == 1
    assert "3" in through[0].numbers


def test_most_stops_have_a_platform() -> None:
    stops = [stop for train in load_timetable().trains for stop in train.stops]
    with_platform = sum(1 for stop in stops if stop.platform is not None)
    assert with_platform / len(stops) >= MIN_STOPS_WITH_PLATFORM


def test_through_stops_are_mostly_certain() -> None:
    timetable = load_timetable()
    through = [s for t in timetable.trains for s in t.stops[1:-1] if s.platform is not None]
    certain = sum(1 for s in through if s.platform.certain)
    assert certain / len(through) >= MIN_THROUGH_STOPS_CERTAIN


def test_every_platform_has_numbers() -> None:
    for entries in load_platform_table().stations.values():
        assert all(entry.numbers for entry in entries)
