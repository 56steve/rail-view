from app.data.mumbai_network import CENTRAL_LINE
from app.services.geometry import LocalPoint, haversine_m, to_latlon, to_local


def test_origin_maps_to_zero_zero() -> None:
    point = to_local(19.1868, 72.9750)
    assert abs(point.x) < 1e-6
    assert abs(point.y) < 1e-6


def test_round_trip_is_accurate_to_within_a_metre() -> None:
    for station in CENTRAL_LINE.stations:
        local = to_local(station.lat, station.lon)
        lat, lon = to_latlon(local)
        error_m = haversine_m(station.lat, station.lon, lat, lon)
        assert error_m < 1.0


def test_local_distance_matches_haversine_over_short_range() -> None:
    thane = CENTRAL_LINE.stations[0]
    mulund = CENTRAL_LINE.stations[1]
    a, b = to_local(thane.lat, thane.lon), to_local(mulund.lat, mulund.lon)
    planar_m = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
    geodesic_m = haversine_m(thane.lat, thane.lon, mulund.lat, mulund.lon)
    assert abs(planar_m - geodesic_m) < 5.0


def test_local_point_is_frozen_and_comparable() -> None:
    assert LocalPoint(x=1.0, y=2.0) == LocalPoint(x=1.0, y=2.0)
