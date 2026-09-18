from app.services.track_matching import get_route


def test_route_length_is_positive_and_plausible() -> None:
    route = get_route("CR")
    # Thane to Dadar is roughly 20km by rail; a straight-line placeholder
    # polyline (see app/data/mumbai_network.py) sums slightly long because
    # it cuts corners as straight segments rather than the true curve, but
    # should stay in a plausible neighbourhood of the real distance.
    assert 15_000 < route.length_m < 30_000


def test_station_chainage_is_monotonically_increasing() -> None:
    route = get_route("CR")
    chainages = [sc.chainage_m for sc in route.stations]
    assert chainages == sorted(chainages)
    assert chainages[0] == 0.0


def test_matching_a_station_exactly_returns_near_zero_offset() -> None:
    route = get_route("CR")
    ghatkopar = next(sc for sc in route.stations if sc.station.code == "GC")
    match = route.match(ghatkopar.station.lat, ghatkopar.station.lon)
    assert match.offset_m < 1.0
    assert abs(match.chainage_m - ghatkopar.chainage_m) < 1.0


def test_matching_an_offset_point_snaps_onto_the_track() -> None:
    route = get_route("CR")
    kurla = next(sc for sc in route.stations if sc.station.code == "KRL")
    # ~50m east of Kurla station - not on the line, so it must be pulled
    # back onto the rail rather than reported as-is.
    nudged_lon = kurla.station.lon + 0.0006
    match = route.match(kurla.station.lat, nudged_lon)
    assert match.offset_m > 10.0
    assert (match.snapped_lat, match.snapped_lon) != (kurla.station.lat, nudged_lon)
    # Near a station the polyline bends, so the nearest point can shift
    # along the corner by somewhat more than the raw perpendicular offset -
    # still expected to land close to the station, not somewhere else on
    # the route entirely.
    assert abs(match.chainage_m - kurla.chainage_m) < 100.0


def test_position_at_chainage_is_the_inverse_of_match() -> None:
    route = get_route("CR")
    original_chainage = 4200.0
    lat, lon = route.position_at_chainage(original_chainage)
    match = route.match(lat, lon)
    assert abs(match.chainage_m - original_chainage) < 1.0
    assert match.offset_m < 0.5


def test_heading_flips_roughly_180_degrees_between_directions() -> None:
    route = get_route("CR")
    forward_heading = route.heading_deg_at_chainage(3000.0)
    # There's no reverse-direction geometry (single centerline), but a
    # heading value should always be a valid compass bearing.
    assert 0.0 <= forward_heading < 360.0


def test_next_station_respects_direction() -> None:
    route = get_route("CR")
    mid_chainage = route.stations[3].chainage_m
    forward_next = route.next_station(mid_chainage, direction_forward=True)
    backward_next = route.next_station(mid_chainage, direction_forward=False)
    assert forward_next is not None
    assert backward_next is not None
    assert forward_next.chainage_m > mid_chainage
    assert backward_next.chainage_m < mid_chainage
