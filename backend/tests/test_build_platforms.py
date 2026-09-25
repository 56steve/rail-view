import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_osm_data import NETWORK_OUT, BuildError  # noqa: E402
from build_platforms import (  # noqa: E402
    CURATED_IN,
    DerivedStationJson,
    PlatformJson,
    StationSite,
    StationTable,
    disagreements,
    forward_direction_at,
    load_curated,
    merge_tables,
    missing_coverage,
    single_pair_stations,
    station_sites,
)

from app.services.platforms import Corridor, Direction, DoorSide, StopRole  # noqa: E402

PLGN = ["Panvel", "Vashi", "Kurla", "Wadala Road", "King's Circle", "Goregaon"]


def entry(
    numbers: list[str],
    corridor: Corridor,
    direction: Direction,
    role: StopRole = "through",
    door: DoorSide | None = None,
) -> PlatformJson:
    return PlatformJson(
        numbers=numbers, corridor=corridor, direction=direction, role=role, door=door, certain=len(numbers) == 1
    )


def derived(line: str, station: str, platforms: list[PlatformJson]) -> DerivedStationJson:
    return DerivedStationJson(
        line_code=line,
        station=station,
        source="osm",
        platforms=platforms,
        single_pair=False,
        unresolved_polygons=[],
        unresolved=[],
    )


def curated(line: str, station: str, platforms: list[PlatformJson]) -> StationTable:
    return StationTable(line_code=line, station=station, source="Wikipedia", platforms=platforms)


def site(line: str, station: str, fast_halt: bool = True, single_pair: bool = False) -> StationSite:
    return StationSite(
        line_code=line,
        station=station,
        route_code=f"{line}-X",
        point=(0.0, 0.0),
        tangent=(0.0, 1.0),
        route=LineString([(0, -100), (0, 100)]),
        forward_direction="DN",
        fast_halt=fast_halt,
        single_pair=single_pair,
        terminus=False,
    )


def test_routes_run_down_in_station_order() -> None:
    assert forward_direction_at("WR-VR", ["Churchgate", "Virar"], 1) == "DN"


def test_panvel_goregaon_runs_up_to_wadala_road_and_down_after_it() -> None:
    assert forward_direction_at("HR-PLGN", PLGN, PLGN.index("Vashi")) == "UP"
    assert forward_direction_at("HR-PLGN", PLGN, PLGN.index("Wadala Road")) is None
    assert forward_direction_at("HR-PLGN", PLGN, PLGN.index("Goregaon")) == "DN"


def test_single_pair_stations_are_harbour_trans_harbour_and_central_beyond_kalyan() -> None:
    routes = [
        {"code": "CR-KSRA", "line_code": "CR", "stations": [{"name": n} for n in ("CSMT", "Thane", "Kalyan", "Titwala")]},
        {"code": "WR-VR", "line_code": "WR", "stations": [{"name": n} for n in ("Churchgate", "Virar")]},
        {"code": "HR-PNVL", "line_code": "HR", "stations": [{"name": n} for n in ("CSMT", "Panvel")]},
    ]
    assert single_pair_stations(routes) == {("CR", "Titwala"), ("HR", "CSMT"), ("HR", "Panvel")}


def test_coverage_needs_both_directions_of_each_corridor_the_station_serves() -> None:
    slow_only = site("WR", "Marine Lines", fast_halt=False)
    assert missing_coverage(slow_only, [entry(["1"], "slow", "DN")]) == ["slow UP"]
    fast_halt = site("WR", "Dadar")
    assert missing_coverage(fast_halt, [entry(["1"], "slow", "DN"), entry(["2"], "slow", "UP")]) == ["fast UP", "fast DN"]
    one_pair = site("HR", "Chembur", single_pair=True)
    assert missing_coverage(one_pair, [entry(["1"], "any", "DN"), entry(["2"], "any", "UP")]) == []


def test_curated_stations_replace_derived_ones_wholesale() -> None:
    sites = [site("WR", "Andheri"), site("WR", "Dadar"), site("WR", "Malad")]
    osm = {
        ("WR", "Andheri"): derived("WR", "Andheri", [entry(["3"], "slow", "DN", door="left")]),
        ("WR", "Dadar"): derived("WR", "Dadar", [entry(["1"], "slow", "DN")]),
        ("WR", "Malad"): derived("WR", "Malad", []),
    }
    hand = {("WR", "Andheri"): curated("WR", "Andheri", [entry(["4"], "slow", "UP", "originating")])}
    merged = merge_tables(sites, osm, hand)
    assert list(merged) == [("WR", "Andheri"), ("WR", "Dadar")]
    assert merged[("WR", "Andheri")]["source"] == "curated"
    assert merged[("WR", "Andheri")]["platforms"] == hand[("WR", "Andheri")]["platforms"]
    assert merged[("WR", "Dadar")]["source"] == "osm"


def test_disagreements_flag_swapped_directions() -> None:
    # Were Sanpada (Harbour) curated from Wikipedia, which reverses OSM's
    # 3 = Panvel-bound, 4 = CSMT-bound, both directions would be flagged.
    osm = {("HR", "Sanpada"): derived("HR", "Sanpada", [entry(["3"], "any", "DN"), entry(["4"], "any", "UP")])}
    hand = {("HR", "Sanpada"): curated("HR", "Sanpada", [entry(["4"], "any", "DN"), entry(["3"], "any", "UP")])}
    assert disagreements(osm, hand) == [
        "HR Sanpada: any DN: OSM has PF 3, curated has PF 4",
        "HR Sanpada: any UP: OSM has PF 4, curated has PF 3",
    ]


def test_a_withheld_station_is_reported_with_what_osm_would_have_shown() -> None:
    osm = {("HR", "Sanpada"): derived("HR", "Sanpada", [entry(["3"], "any", "DN"), entry(["4"], "any", "UP")])}
    hand = {("HR", "Sanpada"): curated("HR", "Sanpada", [])}
    assert disagreements(osm, hand) == ["HR Sanpada: withheld by curation; OSM has any DN PF 3, any UP PF 4"]


def test_a_withheld_station_stays_in_the_merge_with_no_platforms() -> None:
    sites = [site("HR", "Sanpada", single_pair=True)]
    osm = {("HR", "Sanpada"): derived("HR", "Sanpada", [entry(["3"], "any", "DN")])}
    hand = {("HR", "Sanpada"): curated("HR", "Sanpada", [])}
    merged = merge_tables(sites, osm, hand)
    assert merged[("HR", "Sanpada")]["source"] == "curated"
    assert merged[("HR", "Sanpada")]["platforms"] == []


def test_curated_station_may_be_withheld_with_an_empty_platform_list(tmp_path: Path) -> None:
    path = _write_curated(
        tmp_path, [{"line_code": "HR", "station": "Sanpada", "source": "OSM and Wikipedia disagree", "platforms": []}]
    )
    stations = load_curated(path, [site("HR", "Sanpada", single_pair=True)])
    assert stations[("HR", "Sanpada")]["platforms"] == []


def test_the_curated_file_withholds_harbour_sanpada() -> None:
    sites = station_sites(json.loads(NETWORK_OUT.read_text()), frozenset())
    assert load_curated(CURATED_IN, sites)[("HR", "Sanpada")]["platforms"] == []


def test_disagreements_accept_a_curated_entry_listing_more_numbers() -> None:
    osm = {("WR", "Dadar"): derived("WR", "Dadar", [entry(["3"], "fast", "DN", door="left")])}
    hand = {("WR", "Dadar"): curated("WR", "Dadar", [entry(["3", "5"], "fast", "DN", door="left")])}
    assert disagreements(osm, hand) == []


def test_disagreements_match_termini_by_any_role() -> None:
    osm = {("WR", "Churchgate"): derived("WR", "Churchgate", [entry(["1"], "slow", "DN", door="both")])}
    hand = {
        ("WR", "Churchgate"): curated("WR", "Churchgate", [entry(["1", "2"], "slow", "DN", "originating", "both")])
    }
    assert disagreements(osm, hand) == []


def test_disagreements_flag_doors_that_cannot_both_hold() -> None:
    osm = {("WR", "Dadar"): derived("WR", "Dadar", [entry(["1"], "slow", "DN", door="right")])}
    compatible = {("WR", "Dadar"): curated("WR", "Dadar", [entry(["1"], "slow", "DN", door="both")])}
    conflicting = {("WR", "Dadar"): curated("WR", "Dadar", [entry(["1"], "slow", "DN", door="left")])}
    assert disagreements(osm, compatible) == []
    assert disagreements(osm, conflicting) == ["WR Dadar: slow DN: PF 1 doors right in OSM, left curated"]


def test_disagreements_flag_a_direction_the_curated_station_leaves_out() -> None:
    osm = {("CR", "Kalyan"): derived("CR", "Kalyan", [entry(["2"], "slow", "DN")])}
    hand = {("CR", "Kalyan"): curated("CR", "Kalyan", [entry(["4", "6"], "fast", "DN")])}
    assert disagreements(osm, hand) == ["CR Kalyan: slow DN: OSM has PF 2, curated has nothing"]


def test_the_curated_file_names_real_stations_and_cites_sources() -> None:
    sites = station_sites(json.loads(NETWORK_OUT.read_text()), frozenset())
    stations = load_curated(CURATED_IN, sites)
    assert ("WR", "Dadar") in stations
    assert all(station["source"].strip() for station in stations.values())


def _write_curated(tmp_path: Path, stations: list[dict[str, object]]) -> Path:
    path = tmp_path / "curated.json"
    path.write_text(json.dumps({"stations": stations}))
    return path


def test_curated_station_must_exist_on_its_line(tmp_path: Path) -> None:
    path = _write_curated(
        tmp_path, [{"line_code": "WR", "station": "Thane", "source": "x", "platforms": [entry(["1"], "slow", "DN")]}]
    )
    with pytest.raises(BuildError, match="not a station of that line"):
        load_curated(path, [site("CR", "Thane")])


def test_curated_station_must_cite_a_source(tmp_path: Path) -> None:
    path = _write_curated(
        tmp_path, [{"line_code": "CR", "station": "Thane", "source": " ", "platforms": [entry(["1"], "slow", "DN")]}]
    )
    with pytest.raises(BuildError, match="no source"):
        load_curated(path, [site("CR", "Thane")])


def test_curated_station_is_listed_once(tmp_path: Path) -> None:
    station = {"line_code": "CR", "station": "Thane", "source": "x", "platforms": [entry(["1"], "slow", "DN")]}
    path = _write_curated(tmp_path, [station, station])
    with pytest.raises(BuildError, match="listed twice"):
        load_curated(path, [site("CR", "Thane")])
