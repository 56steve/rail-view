import pytest

from app.services.corridors import stop_corridors, stop_directions

# Route order (DN): A B C D E F. Fast halts: A, C, E, F.
ROUTE = ("A", "B", "C", "D", "E", "F")
FAST_HALTS = frozenset({"A", "C", "E", "F"})


def test_all_stations_called_is_slow_throughout() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "B", "C", "D", "E", "F"), single_pair=frozenset()) == (
        "slow", "slow", "slow", "slow", "slow", "slow",
    )


def test_skipping_slow_only_stations_is_fast() -> None:
    # E -> F passes nothing but runs between fast halts: stays fast.
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "E", "F"), single_pair=frozenset()) == (
        "fast", "fast", "fast", "fast",
    )


def test_semi_fast_switches_where_it_starts_calling_everywhere() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "D", "E", "F"), single_pair=frozenset()) == (
        "fast", "fast", "slow", "slow", "slow",
    )


def test_single_pair_stations_are_any() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "E", "F"), single_pair=frozenset({"E", "F"})) == (
        "fast", "fast", "any", "any",
    )


def test_backward_trains_read_the_route_backwards() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("F", "E", "C", "A"), single_pair=frozenset()) == (
        "fast", "fast", "fast", "fast",
    )


def test_direction_flips_after_the_change_station() -> None:
    assert stop_directions("UP", "C", ("A", "B", "C", "D")) == ("UP", "UP", "UP", "DN")
    assert stop_directions("DN", None, ("A", "B")) == ("DN", "DN")


def test_corridor_inheritance_is_route_order_not_travel_order() -> None:
    # Route X Y Z W; X, Y and W are fast halts, Z is slow-only. The X-Y
    # section is undecided on its own (adjacent fast halts, nothing
    # skipped); it inherits from the decided Y-W section (Z is skipped),
    # regardless of which way the train runs it.
    route = ("X", "Y", "Z", "W")
    fast_halts = frozenset({"X", "Y", "W"})
    forward = stop_corridors(route, fast_halts, ("X", "Y", "W"), single_pair=frozenset())
    backward = stop_corridors(route, fast_halts, ("W", "Y", "X"), single_pair=frozenset())
    assert forward == ("fast", "fast", "fast")
    assert backward == tuple(reversed(forward))


def test_section_passing_only_fast_halts_is_undecided_not_slow() -> None:
    # A, B, C are fast halts; D is not. A->C passes B (a fast halt), so
    # it's undecided on its own - not "slow" just because nothing
    # non-fast-halt was skipped. C->D is genuinely slow (D isn't a fast
    # halt), so A and C inherit slow from it.
    route = ("A", "B", "C", "D")
    fast_halts = frozenset({"A", "B", "C"})
    assert stop_corridors(route, fast_halts, ("A", "C", "D"), single_pair=frozenset()) == (
        "slow", "slow", "slow",
    )


def test_section_passing_only_fast_halts_inherits_a_preceding_fast_section() -> None:
    # A, B, C are fast halts; X is slow-only. A->B skips X: decided fast.
    # B->C passes nothing but both ends are fast halts: undecided, and
    # inherits "fast" from the section before it.
    route = ("A", "X", "B", "C")
    fast_halts = frozenset({"A", "B", "C"})
    assert stop_corridors(route, fast_halts, ("A", "B", "C"), single_pair=frozenset()) == (
        "fast", "fast", "fast",
    )


def test_section_skipping_a_fast_halt_keeps_the_track_pair_it_came_on() -> None:
    # Like Vasai Road -> Virar past Nallasopara: A->B skips slow-only X
    # (fast), then B->D passes C, a fast halt the train doesn't call at.
    # That says nothing about the pair, so it stays on the fast one.
    route = ("A", "X", "B", "C", "D")
    fast_halts = frozenset({"A", "B", "C", "D"})
    assert stop_corridors(route, fast_halts, ("A", "B", "D"), single_pair=frozenset()) == (
        "fast", "fast", "fast",
    )


def test_single_stop_is_any() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("C",), single_pair=frozenset()) == ("any",)


def test_no_stops_is_empty() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, (), single_pair=frozenset()) == ()


def test_unknown_station_raises_value_error_naming_it() -> None:
    with pytest.raises(ValueError, match="Q"):
        stop_corridors(ROUTE, FAST_HALTS, ("A", "Q"), single_pair=frozenset())


def test_non_monotonic_stops_raise() -> None:
    with pytest.raises(ValueError):
        stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "B"), single_pair=frozenset())


def test_changes_at_not_among_stops_raises() -> None:
    with pytest.raises(ValueError):
        stop_directions("UP", "Q", ("A", "B"))
