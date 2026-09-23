import pytest

from app.services.journey_planner import UnknownStationError, plan_journey


def plan(network, from_id: str, to_id: str, sort: str = "fastest"):
    contexts = network.processor.contexts()
    return plan_journey(from_id, to_id, sort, contexts, set(contexts), network.now)


def test_only_trains_that_will_still_call_at_the_origin_are_offered(network) -> None:
    network.place("WR-01", "WR-VR", "SLOW", forward=True, at_fraction=0.1)  # before Dadar -> valid
    network.place("WR-02", "WR-VR", "SLOW", forward=True, at_fraction=0.8)  # past Dadar -> gone
    network.place("WR-03", "WR-VR", "SLOW", forward=False, at_fraction=0.5)  # wrong direction

    result = plan(network, "dadar", "borivali")

    assert [o.train_id for o in result.options] == ["WR-01"]
    option = result.options[0]
    assert option.board_expected_epoch >= network.now
    assert option.alight_expected_epoch > option.board_expected_epoch
    assert option.duration_seconds == pytest.approx(option.alight_expected_epoch - option.board_expected_epoch)
    assert result.interchange_hint is None


def test_fast_train_skips_intermediate_halts_and_wins_fastest(network) -> None:
    network.place("CR-01", "CR-KSRA", "SLOW", forward=True, at_fraction=0.0)
    network.place("CR-02", "CR-KSRA", "FAST", forward=True, at_fraction=0.0)

    result = plan(network, "csmt", "thane", sort="fastest")

    assert result.options[0].train_id == "CR-02"
    fast, slow = result.options[0], result.options[1]
    assert fast.intermediate_stops < slow.intermediate_stops
    assert fast.duration_seconds < slow.duration_seconds


def test_fast_train_is_not_offered_for_a_station_it_skips(network) -> None:
    network.place("CR-02", "CR-KSRA", "FAST", forward=True, at_fraction=0.0)
    assert plan(network, "csmt", "kurla").options == []


def test_cross_line_journey_gets_an_interchange_hint(network) -> None:
    result = plan(network, "thane", "bandra")
    assert result.options == []
    # Dadar (Central to Western) or Kurla (Central to the Harbour branch
    # through Bandra) both work; the hint names the shorter detour.
    assert result.interchange_hint is not None
    assert result.interchange_hint.startswith("No direct train - change at ")
    assert any(station in result.interchange_hint for station in ("Dadar", "Kurla"))


def test_journey_across_central_branches_changes_at_kalyan(network) -> None:
    result = plan(network, "titwala", "badlapur")
    assert result.options == []
    assert result.interchange_hint == "No direct train - change at Kalyan for the Khopoli branch"


def test_same_branch_journey_needs_no_interchange(network) -> None:
    assert plan(network, "thane", "kasara").interchange_hint is None


def test_same_station_has_no_options(network) -> None:
    network.place("WR-01", "WR-VR", "SLOW", forward=True, at_fraction=0.1)
    assert plan(network, "dadar", "dadar").options == []


def test_unknown_station_raises(network) -> None:
    with pytest.raises(UnknownStationError):
        plan(network, "atlantis", "dadar")
