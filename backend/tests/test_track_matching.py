import pytest

from app.services.track_matching import get_route


def _station(route_code: str, station_code: str):
    return next(sc for sc in get_route(route_code).stations if sc.station.code == station_code)


def test_matching_a_station_exactly_returns_near_zero_offset() -> None:
    route = get_route("CR-KSRA")
    ghatkopar = _station("CR-KSRA", "GC")
    match = route.match(ghatkopar.station.lat, ghatkopar.station.lon)
    assert match.offset_m < 1.0
    assert abs(match.chainage_m - ghatkopar.chainage_m) < 1.0


def test_matching_an_offset_point_snaps_onto_the_track() -> None:
    route = get_route("CR-KSRA")
    kurla = _station("CR-KSRA", "CLA")
    # ~60m east of the station: must be pulled onto the rail, not reported as-is.
    match = route.match(kurla.station.lat, kurla.station.lon + 0.0006)
    assert match.offset_m > 10.0
    assert abs(match.chainage_m - kurla.chainage_m) < 100.0


def test_position_at_chainage_is_the_inverse_of_match() -> None:
    route = get_route("WR-VR")
    lat, lon = route.position_at_chainage(12_345.0)
    match = route.match(lat, lon)
    assert match.chainage_m == pytest.approx(12_345.0, abs=1.0)
    assert match.offset_m < 0.5


def test_position_at_chainage_clamps_to_the_track_ends() -> None:
    route = get_route("THR-VSH")
    assert route.position_at_chainage(-500) == route.position_at_chainage(0)
    assert route.position_at_chainage(route.length_m + 500) == route.position_at_chainage(route.length_m)


def test_heading_is_a_valid_bearing_and_follows_the_line() -> None:
    # Western line runs broadly north from Churchgate towards Borivali.
    route = get_route("WR-VR")
    heading = route.heading_deg_at_chainage(route.length_m * 0.7)
    assert 0.0 <= heading < 360.0
    assert heading > 300 or heading < 60


def test_next_station_respects_direction() -> None:
    route = get_route("HR-PNVL")
    mid = route.stations[5].chainage_m + 10
    forward_next = route.next_station(mid, direction_forward=True)
    backward_next = route.next_station(mid, direction_forward=False)
    assert forward_next is not None and forward_next.chainage_m > mid
    assert backward_next is not None and backward_next.chainage_m < mid


def test_unknown_route_code_raises() -> None:
    with pytest.raises(KeyError):
        get_route("XX")
