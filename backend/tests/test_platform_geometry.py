import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from platform_geometry import (  # noqa: E402
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
    probe_offset,
    side_of,
    track_corridor,
    track_line,
)

# Two tracks running north (increasing y), 5 m apart; x grows to the east.
WEST = LineString([(0, 0), (0, 300)])
EAST = LineString([(5, 0), (5, 300)])


def test_track_corridor_from_osm_names() -> None:
    assert track_corridor("Western Railway (Fast)") == "fast"
    assert track_corridor("Central Line (Slow)") == "slow"
    assert track_corridor("Mumbai-Pune Railway") is None
    assert track_corridor(None) is None


def test_track_corridor_ignores_spacing_and_case() -> None:
    assert track_corridor("WesternRailway(Fast)") == "fast"
    assert track_corridor("CENTRAL RAILWAY (SLOW)") == "slow"


def test_track_line_from_osm_names() -> None:
    assert track_line("Western Railway (Slow)") == "WR"
    assert track_line("Mumbai - Delhi Railway") == "WR"
    assert track_line("Central Railway (Fast)") == "CR"
    assert track_line("Central Line (Slow)") == "CR"
    assert track_line("Mumbai-Pune Railway") == "CR"
    assert track_line("Central Railway (Harbour Line)") == "HR"
    assert track_line("Harbour Line (Belapur, Panvel)") == "HR"
    assert track_line("Trans-Harbour Line") == "THR"
    assert track_line("Konkan Railway") is None
    assert track_line(None) is None


def test_side_of_depends_on_direction_of_travel() -> None:
    assert side_of(WEST, (-3, 150), forward=True) == "left"
    assert side_of(WEST, (-3, 150), forward=False) == "right"
    assert side_of(WEST, (3, 150), forward=True) == "right"


def test_side_of_is_undecided_within_half_a_metre_of_the_line() -> None:
    assert side_of(WEST, (0.3, 150), forward=True) is None
    assert side_of(WEST, (0.0, 150), forward=False) is None
    assert side_of(WEST, (0.8, 150), forward=True) == "right"


def test_side_of_uses_the_nearest_segment_of_a_bending_track() -> None:
    bend = LineString([(0, 0), (0, 100), (100, 100)])  # north, then east
    assert side_of(bend, (50, 105), forward=True) == "left"
    assert side_of(bend, (-3, 50), forward=True) == "left"


def test_platform_numbers_parse_osm_refs() -> None:
    assert platform_numbers("4;5") == ("4", "5")
    assert platform_numbers("4 - 5") == ("4", "5")
    assert platform_numbers("2A;3") == ("2A", "3")
    assert platform_numbers("Platform 5,6") == ("5", "6")
    assert platform_numbers("CCG") == ()
    assert platform_numbers(None) == ()


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("MMCT", ()),
        ("1/12", ("1", "12")),
        ("2&1", ("2", "1")),
        ("9/10A", ("9", "10A")),
        ("platform no.2", ("2",)),
        ("P;atform 5", ("5",)),
        ("1;1", ("1",)),
        ("1a", ("1A",)),
        ("10A1", ()),
        ("123", ()),
        ("", ()),
    ],
)
def test_platform_numbers_edge_cases(ref: str, expected: tuple[str, ...]) -> None:
    assert platform_numbers(ref) == expected


def test_platform_sort_key_orders_suffixed_numbers_between_neighbours() -> None:
    assert sorted(["10", "9A", "2", "9", "1A"], key=platform_sort_key) == ["1A", "2", "9", "9A", "10"]


def test_left_hand_running_picks_the_west_track_going_north() -> None:
    assert left_track((WEST, EAST), forward=True, station_point=(2.5, 150)) is WEST
    assert left_track((WEST, EAST), forward=False, station_point=(2.5, 150)) is EAST


def test_left_track_is_undecided_for_tracks_drawn_on_top_of_each_other() -> None:
    assert left_track((WEST, LineString([(0.2, 0), (0.2, 300)])), forward=True, station_point=(0, 150)) is None


def test_adjacent_tracks_are_those_along_the_platform_edges() -> None:
    island = Polygon([(1.5, 100), (3.5, 100), (3.5, 200), (1.5, 200)])
    far = LineString([(30, 0), (30, 300)])
    assert set(map(id, adjacent_tracks(island, (WEST, EAST, far)))) == {id(WEST), id(EAST)}


def test_adjacent_tracks_skip_a_track_that_only_touches_a_platform_end() -> None:
    platform = Polygon([(1.5, 100), (3.5, 100), (3.5, 200), (1.5, 200)])
    crossing = LineString([(-50, 98), (50, 98)])
    assert adjacent_tracks(platform, (crossing,)) == []


def test_orient_along_reverses_a_track_drawn_against_the_route() -> None:
    southbound = LineString([(0, 300), (0, 0)])
    assert list(orient_along(southbound, (0.0, 1.0)).coords) == [(0, 0), (0, 300)]
    assert orient_along(WEST, (0.0, 1.0)) is WEST


def test_offset_from_is_positive_to_the_left_of_travel() -> None:
    assert offset_from(WEST, (-3, 10)) == pytest.approx(3.0)
    assert offset_from(WEST, (4, 10)) == pytest.approx(-4.0)


def test_offset_from_is_a_plain_float_and_zero_on_the_line() -> None:
    assert type(offset_from(WEST, (-3, 10))) is float
    assert offset_from(WEST, (0.2, 10)) == 0.0


def test_probe_offset_is_where_a_line_square_across_the_route_meets_the_track() -> None:
    # A track bending away east: measured where it crosses y = 150, not at
    # its nearest point to the station.
    bending = LineString([(10, 0), (10, 100), (14, 300)])
    assert probe_offset((bending,), origin=(0, 150), tangent=(0.0, 1.0), half_width=50) == pytest.approx(-11.0)


def test_probe_offset_is_none_for_a_track_that_ends_before_the_station() -> None:
    leg = LineString([(5, 0), (5, 100)])
    assert probe_offset((leg,), origin=(0, 150), tangent=(0.0, 1.0), half_width=50) is None


def test_probe_offset_ignores_a_track_crossing_at_an_angle() -> None:
    crossing = LineString([(-40, 140), (40, 160)])
    assert probe_offset((crossing,), origin=(0, 150), tangent=(0.0, 1.0), half_width=50) is None


def test_offset_from_follows_a_curving_line() -> None:
    curve = LineString([(0, 0), (0, 100), (100, 200)])
    # 5 m left of the diagonal leg, which a straight tangent at the start
    # would put ~65 m to the right.
    assert offset_from(curve, (50 - 5 / 2**0.5, 150 + 5 / 2**0.5)) == pytest.approx(5.0)


def test_numbering_direction_from_the_nearest_known_platforms() -> None:
    # Numbers grow eastwards (to the right, going north): 1 at x=10, 4 at x=-5.
    known = [(10.0, "1"), (-5.0, "4")]
    assert numbering_increases_left(known, near=2.0) is False
    assert numbering_increases_left([(10.0, "4"), (-5.0, "1")], near=2.0) is True


def test_numbering_direction_needs_two_known_platforms_that_agree() -> None:
    assert numbering_increases_left([], near=0.0) is None
    assert numbering_increases_left([(0.0, "1")], near=0.0) is None
    assert numbering_increases_left([(0.0, "1"), (0.5, "2")], near=0.0) is None  # same track
    contradicting = [(0.0, "1"), (10.0, "2"), (20.0, "1A")]
    assert numbering_increases_left(contradicting, near=10.0) is None


def test_numbering_direction_ignores_far_platforms_of_another_series() -> None:
    # A second series further east, numbered the other way, doesn't
    # contradict the local pair.
    known = [(0.0, "1"), (-5.0, "2"), (-120.0, "8"), (-100.0, "9")]
    assert numbering_increases_left(known, near=-3.0) is False


def test_pair_by_numbering_follows_the_numbering_direction() -> None:
    assert pair_by_numbering(("4", "5"), (-6.0, -21.0), increases_left=False, known=[]) == {"4": 0, "5": 1}
    assert pair_by_numbering(("5", "4"), (-6.0, -21.0), increases_left=True, known=[]) == {"4": 1, "5": 0}
    assert pair_by_numbering(("2A", "3"), (0.0, 5.0), increases_left=True, known=[]) == {"2A": 0, "3": 1}


def test_pair_by_numbering_rejects_numbers_that_do_not_fit_their_neighbours() -> None:
    # 1 and 2 known to the west, growing eastwards: an island east of them
    # tagged "1;2" again can't be right.
    known = [(10.0, "1"), (5.0, "2")]
    assert pair_by_numbering(("3", "4"), (0.0, -5.0), increases_left=False, known=known) == {"3": 0, "4": 1}
    assert pair_by_numbering(("1", "2"), (0.0, -5.0), increases_left=False, known=known) is None


def test_door_from_sides() -> None:
    assert door_from_sides({"left"}) == "left"
    assert door_from_sides({"right"}) == "right"
    assert door_from_sides({"left", "right"}) == "both"
    assert door_from_sides(set()) is None


def test_common_door_is_the_side_open_in_every_case() -> None:
    assert common_door(["left", "left"]) == "left"
    assert common_door(["left", "both"]) == "left"
    assert common_door(["both", "right"]) == "right"
    assert common_door(["both", "both"]) == "both"
    assert common_door(["left", "right"]) is None
    assert common_door(["left", None]) is None
    assert common_door([]) is None


def test_place_by_numbering_puts_a_lone_island_number_on_the_side_numbers_come_from() -> None:
    # Dadar (Western): 1, 2, 3 run east (rightwards going north); the island
    # east of 3 is tagged only "4", which is its western face.
    known = [(0.1, "1"), (-4.3, "2"), (-20.5, "3")]
    assert place_by_numbering("4", (-32.6, -24.0), known) == 1
    assert place_by_numbering("4", (-24.0, -32.6), known) == 0


def test_place_by_numbering_needs_a_known_numbering_order() -> None:
    assert place_by_numbering("4", (-32.6, -24.0), [(0.1, "1")]) is None


def test_place_by_numbering_rejects_a_number_out_of_sequence() -> None:
    # "2" can't sit east of 3 when numbers grow eastwards.
    known = [(0.1, "1"), (-20.5, "3")]
    assert place_by_numbering("2", (-32.6, -24.0), known) is None
