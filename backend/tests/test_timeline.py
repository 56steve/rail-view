import pytest

from app.services.timeline import build_timeline


def test_states_split_around_the_trains_position(network) -> None:
    network.place("CR-01", "CR-KSRA", "SLOW", forward=True, at_fraction=0.43)
    timeline = build_timeline(network.processor.context("CR-01"))

    states = [stop.state for stop in timeline]
    assert states.count("next") == 1
    next_index = states.index("next")
    assert all(s == "departed" for s in states[:next_index])
    assert all(s == "upcoming" for s in states[next_index + 1 :])


def test_upcoming_times_carry_the_current_delay(network) -> None:
    network.place("CR-02", "CR-KSRA", "SLOW", forward=True, at_fraction=0.43, delay_s=180)
    timeline = build_timeline(network.processor.context("CR-02"))
    for stop in timeline:
        if stop.state in ("next", "upcoming"):
            assert stop.expected_epoch - stop.scheduled_epoch == pytest.approx(180, abs=2)


def test_stops_passed_before_tracking_began_have_no_observed_time(network) -> None:
    network.place("WR-01", "WR-BVI", "SLOW", forward=True, at_fraction=0.6)
    timeline = build_timeline(network.processor.context("WR-01"))
    departed = [s for s in timeline if s.state == "departed"]
    assert departed
    assert all(s.observed_arrival_epoch is None for s in departed)
    assert all(s.expected_epoch == s.scheduled_epoch for s in departed)


def test_timeline_follows_travel_order_for_reverse_runs(network) -> None:
    network.place("HR-01", "HR-VSH", "SLOW", forward=False, at_fraction=0.3)
    timeline = build_timeline(network.processor.context("HR-01"))
    assert timeline[0].station.name == "Vashi"
    assert timeline[-1].station.name == "CSMT"
    scheduled = [s.scheduled_epoch for s in timeline]
    assert scheduled == sorted(scheduled)
