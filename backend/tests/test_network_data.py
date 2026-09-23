"""Integrity checks on the OSM-derived network data the whole app runs on."""

import pytest

from app.data.mumbai_network import load_lines, load_network, load_routes
from app.services.track_matching import get_all_routes, get_route

# Published route lengths, rounded; the OSM-derived track should land
# within a few percent of each.
EXPECTED_LENGTH_KM = {
    "WR-BVI": 34.0,
    "CR-KSRA": 120.5,
    "CR-KJT": 100.0,
    "HR-VSH": 29.0,
    "THR-VSH": 18.5,
}


def test_all_four_lines_are_present() -> None:
    assert set(load_lines()) == {"WR", "CR", "HR", "THR"}


def test_every_route_belongs_to_a_known_line() -> None:
    routes = load_routes()
    assert set(routes) == set(EXPECTED_LENGTH_KM)
    assert {route.line.code for route in routes.values()} == set(load_lines())


@pytest.mark.parametrize(("code", "expected_km"), EXPECTED_LENGTH_KM.items())
def test_track_length_matches_the_real_route(code: str, expected_km: float) -> None:
    length_km = get_route(code).length_m / 1000
    assert abs(length_km - expected_km) / expected_km < 0.06


def test_stations_lie_on_their_track_in_order() -> None:
    for route in get_all_routes().values():
        chainages = [sc.chainage_m for sc in route.stations]
        assert chainages == sorted(chainages)
        for sc in route.stations:
            assert route.match(sc.station.lat, sc.station.lon).offset_m < 1.0


def test_central_branches_share_the_trunk_up_to_kalyan() -> None:
    kasara, karjat = get_route("CR-KSRA"), get_route("CR-KJT")
    trunk = [sc.station.code for sc in kasara.stations]
    trunk = trunk[: trunk.index("KYN") + 1]
    assert [sc.station.code for sc in karjat.stations][: len(trunk)] == trunk
    kalyan_a = next(sc for sc in kasara.stations if sc.station.code == "KYN")
    kalyan_b = next(sc for sc in karjat.stations if sc.station.code == "KYN")
    # Same trunk geometry, so Kalyan sits at the same chainage on both.
    assert kalyan_a.chainage_m == pytest.approx(kalyan_b.chainage_m, abs=50)
    assert kasara.stations[-1].station.name == "Kasara"
    assert karjat.stations[-1].station.name == "Karjat"


def test_trains_keep_left_on_their_own_track() -> None:
    # Mumbai runs on the left: facing increasing chainage (away from CSMT
    # or Churchgate), that direction's track is on the left (positive
    # offset) of the other direction's.
    for route in load_routes().values():
        forward, backward = route.running_lanes.forward, route.running_lanes.backward
        assert forward[0][0] == 0 and backward[0][0] == 0
        assert all(d >= -0.01 for _, d in forward), route.code
        assert all(d <= 0.01 for _, d in backward), route.code
        # Real track centres, not a nominal nudge: most of each route has
        # the two directions a track-spacing apart.
        track = get_route(route.code)
        separated = sum(
            b[0] - a[0]
            for a, b in zip(forward, forward[1:], strict=False)
            if a[1] > 3.5 and b[1] > 3.5
        ) + sum(
            b[0] - a[0]
            for a, b in zip(backward, backward[1:], strict=False)
            if a[1] < -3.5 and b[1] < -3.5
        )
        assert separated > 0.8 * track.length_m, route.code


def test_interchanges_are_shared_by_name() -> None:
    names: dict[str, set[str]] = {}
    for route in load_routes().values():
        names.setdefault(route.line.code, set()).update(s.name for s in route.stations)
    assert "Dadar" in names["WR"] & names["CR"]
    assert "Kurla" in names["CR"] & names["HR"]
    assert "Thane" in names["CR"] & names["THR"]
    assert "Vashi" in names["HR"] & names["THR"]


def test_fast_service_only_where_defined() -> None:
    routes = load_routes()
    assert routes["WR-BVI"].has_fast_service
    assert routes["CR-KSRA"].has_fast_service
    assert routes["CR-KJT"].has_fast_service
    assert not routes["HR-VSH"].has_fast_service
    assert not routes["THR-VSH"].has_fast_service


def test_attribution_is_carried_through() -> None:
    assert "OpenStreetMap" in load_network().attribution
