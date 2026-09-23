from app.data.mumbai_network import load_routes
from app.services.geometry import (
    ORIGIN_LAT,
    ORIGIN_LON,
    LocalPoint,
    haversine_m,
    to_latlon,
    to_local,
)


def test_origin_maps_to_zero_zero() -> None:
    point = to_local(ORIGIN_LAT, ORIGIN_LON)
    assert abs(point.x) < 1e-6
    assert abs(point.y) < 1e-6


def test_round_trip_is_accurate_to_within_a_metre_for_every_station() -> None:
    for route in load_routes().values():
        for station in route.stations:
            lat, lon = to_latlon(to_local(station.lat, station.lon))
            assert haversine_m(station.lat, station.lon, lat, lon) < 1.0


def test_planar_distance_matches_haversine_across_the_network() -> None:
    # Churchgate to Kasara is the widest span in the network; the
    # equirectangular approximation should stay within ~0.5% there.
    routes = load_routes()
    churchgate = routes["WR-VR"].stations[0]
    kasara = routes["CR-KSRA"].stations[-1]
    a, b = to_local(churchgate.lat, churchgate.lon), to_local(kasara.lat, kasara.lon)
    planar_m = ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5
    geodesic_m = haversine_m(churchgate.lat, churchgate.lon, kasara.lat, kasara.lon)
    assert abs(planar_m - geodesic_m) / geodesic_m < 0.005


def test_local_point_is_frozen_and_comparable() -> None:
    assert LocalPoint(x=1.0, y=2.0) == LocalPoint(x=1.0, y=2.0)
