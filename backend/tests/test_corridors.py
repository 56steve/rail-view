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
