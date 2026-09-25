"""The OSM derivation in scripts/build_platforms.py: real data around
Andheri and Dadar (a small extract of the Overpass cache), and synthetic
stations for the rules that keep a wrong platform from showing as
certain."""

import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_osm_data import NETWORK_OUT, BuildError  # noqa: E402
from build_platforms import (  # noqa: E402
    Assignment,
    Classification,
    CorridorEvidence,
    OsmData,
    Pairing,
    Placement,
    StationSite,
    Track,
    classify,
    derive_station,
    entries_for_station,
    forward_direction_at,
    load_curated,
    parse_osm,
    read_json,
    station_sites,
    timetable_termini,
    write_platform_table,
)
from platform_geometry import LineCode, TrackCorridor  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "osm_andheri_dadar.json"


# --------------------------------------------------------------------------
# Real data


@pytest.fixture(scope="module")
def fixture_osm() -> OsmData:
    data = json.loads(FIXTURE.read_text())
    return parse_osm(data["rails"], data["platforms"], data["stop_positions"])


@pytest.fixture(scope="module")
def western_sites() -> list[StationSite]:
    sites = station_sites(json.loads(NETWORK_OUT.read_text()), frozenset())
    return [site for site in sites if site.line_code == "WR"]


def _layout(station: str, osm: OsmData, sites: list[StationSite]) -> set[tuple[str, str, tuple[str, ...]]]:
    site = next(s for s in sites if s.station == station)
    derived = derive_station(site, osm, sites)
    return {(p["corridor"], p["direction"], tuple(p["numbers"])) for p in derived["platforms"]}


def test_andheri_western_comes_out_as_the_plan_says(fixture_osm: OsmData, western_sites: list[StationSite]) -> None:
    assert _layout("Andheri", fixture_osm, western_sites) == {
        ("slow", "DN", ("3",)),
        ("slow", "UP", ("5",)),
        ("fast", "DN", ("6",)),
        ("fast", "UP", ("7",)),
    }


def test_dadar_western_comes_out_as_the_plan_says_bar_platform_5(
    fixture_osm: OsmData, western_sites: list[StationSite]
) -> None:
    assert _layout("Dadar", fixture_osm, western_sites) == {
        ("slow", "DN", ("1",)),
        ("slow", "UP", ("2",)),
        ("fast", "DN", ("3",)),
        ("fast", "UP", ("4",)),
    }
    site = next(s for s in western_sites if s.station == "Dadar")
    assert any(note.startswith("PF 5:") for note in derive_station(site, fixture_osm, western_sites)["unresolved"])


def test_parse_osm_skips_ways_too_short_to_have_a_direction() -> None:
    rails = {
        "elements": [
            {"type": "node", "id": 1, "lat": 19.0, "lon": 72.8},
            {"type": "node", "id": 2, "lat": 19.0, "lon": 72.8},
            {"type": "node", "id": 3, "lat": 19.001, "lon": 72.8},
            {"type": "way", "id": 10, "nodes": [1, 2], "tags": {}},
            {"type": "way", "id": 11, "nodes": [1, 3], "tags": {}},
        ]
    }
    osm = parse_osm(rails, {"elements": []}, {"elements": []})
    assert [way.id for way in osm.ways] == [11]


# --------------------------------------------------------------------------
# Stations and inputs


def test_timetabled_trains_make_their_first_and_last_stops_termini() -> None:
    timetable = {
        "trains": [
            {"number": "1", "line": "western", "stops": [["Churchgate", 0, 0], ["Dadar", 9, 9], ["Borivali", 40, 40]]},
            {"number": "2", "line": "main", "stops": [["Thane", 0, 0], ["Kalyan", 20, 20]]},
        ]
    }
    assert timetable_termini(timetable) == {("WR", "Churchgate"), ("WR", "Borivali"), ("CR", "Thane"), ("CR", "Kalyan")}


def test_timetable_on_an_unknown_line_fails_the_build() -> None:
    with pytest.raises(BuildError, match="unknown line"):
        timetable_termini({"trains": [{"number": "1", "line": "metro", "stops": []}]})


def test_intermediate_termini_from_the_timetable_mark_their_sites() -> None:
    network = json.loads(NETWORK_OUT.read_text())
    sites = {(s.line_code, s.station): s for s in station_sites(network, {("WR", "Borivali")})}
    assert sites[("WR", "Borivali")].terminus
    assert sites[("WR", "Churchgate")].terminus  # a route end
    assert not sites[("WR", "Dahisar")].terminus


def test_a_reversal_at_a_station_off_the_route_fails_the_build() -> None:
    with pytest.raises(BuildError, match="reverses at Wadala Road"):
        forward_direction_at("HR-PLGN", ["Panvel", "Goregaon"], 0)


def test_a_missing_input_says_how_to_build_it(tmp_path: Path) -> None:
    with pytest.raises(BuildError, match="run `uv run python scripts/build_osm_data.py` first"):
        read_json(tmp_path / "network.json", "scripts/build_osm_data.py")


def test_curated_station_names_must_be_strings(tmp_path: Path) -> None:
    path = tmp_path / "curated.json"
    path.write_text(json.dumps({"stations": [{"line_code": ["WR"], "station": "Dadar", "source": "x", "platforms": []}]}))
    with pytest.raises(BuildError, match="must be strings"):
        load_curated(path, [])


def test_a_table_that_does_not_load_leaves_nothing_behind(tmp_path: Path) -> None:
    path = tmp_path / "platforms.json"
    path.write_text("previous table\n")
    bad_station = {"line_code": "WR", "station": "Dadar", "source": "osm", "platforms": [{"numbers": "1"}]}
    with pytest.raises(BuildError, match="doesn't load"):
        write_platform_table(path, [], [bad_station])  # type: ignore[list-item]
    assert path.read_text() == "previous table\n"
    assert list(tmp_path.iterdir()) == [path]


# --------------------------------------------------------------------------
# Synthetic stations: the route runs north through (0, 0), so a track at
# offset o (positive = left = west) is the line x = -o.


def site(line: str = "WR", single_pair: bool = False, terminus: bool = False) -> StationSite:
    return StationSite(
        line_code=line,
        station="Somewhere",
        route_code=f"{line}-X",
        point=(0.0, 0.0),
        tangent=(0.0, 1.0),
        route=LineString([(0, -800), (0, 800)]),
        forward_direction="DN",
        fast_halt=True,
        single_pair=single_pair,
        terminus=terminus,
    )


def track(
    index: int,
    offset: float,
    *,
    name: str | None = None,
    lines: frozenset[LineCode] = frozenset({"WR"}),
    named_corridor: TrackCorridor | None = None,
    corridor: TrackCorridor | None = None,
    crosses: bool = True,
    drawn_at: float | None = None,
) -> Track:
    x = -(offset if drawn_at is None else drawn_at)
    return Track(
        index=index,
        offset=offset,
        crosses=crosses,
        lines=(LineString([(x, -300), (x, 300)]),),
        way_ids=frozenset({index}),
        name_key=name,
        named_lines=lines,
        traced_line=None,
        named_corridor=named_corridor,
        corridor=corridor if corridor is not None else named_corridor,
        through=True,
    )


def assigned(result: Classification) -> dict[int, tuple[str, str, CorridorEvidence]]:
    return {index: (a.corridor, a.direction, a.evidence) for index, a in result.tracks.items()}


def test_four_lines_with_one_pair_named_make_the_other_pair_the_opposite_corridor_but_weakly() -> None:
    tracks = [
        track(0, 0.0, name="slow", named_corridor="slow"),
        track(1, -5.0),
        track(2, -20.0),
        track(3, -25.0),
    ]
    assert assigned(classify(site(), tracks)) == {
        0: ("slow", "DN", "own_name"),
        1: ("slow", "UP", "partner_name"),
        2: ("fast", "DN", "opposite"),
        3: ("fast", "UP", "opposite"),
    }


def test_a_traced_corridor_contradicting_the_opposite_one_leaves_the_pair_unresolved() -> None:
    # Byculla: the pair taken as "fast" by elimination has a track whose
    # ways lead onto a slow line.
    tracks = [
        track(0, 19.0, name="slow", named_corridor="slow"),
        track(1, 14.5, corridor="slow"),
        track(2, 0.0, corridor="slow"),
        track(3, -3.0),
    ]
    result = assigned(classify(site(), tracks))
    assert 2 not in result and 3 not in result


def test_six_lines_need_each_pair_named_on_the_ground() -> None:
    tracks = [
        track(0, 0.0, name="slow", named_corridor="slow"),
        track(1, -5.0, name="slow", named_corridor="slow"),
        track(2, -20.0),
        track(3, -25.0),
        track(4, -40.0),
        track(5, -45.0),
    ]
    assert set(assigned(classify(site(), tracks))) == {0, 1}


def test_a_turnout_leg_ending_before_the_station_is_not_part_of_the_pair() -> None:
    # Vashi (Trans-Harbour): a leg at -11 m that ends short of the station
    # once paired with the real track at -14 m.
    thr = frozenset({"THR"})
    tracks = [
        track(0, -14.2, name="thr", lines=thr),
        track(1, -11.2, name="thr", lines=thr, crosses=False),
        track(2, 0.0, name="thr", lines=thr),
    ]
    assert assigned(classify(site("THR", single_pair=True), tracks)) == {
        0: ("any", "UP", "own_name"),
        2: ("any", "DN", "own_name"),
    }


def test_left_hand_running_must_agree_with_the_order_across_the_station() -> None:
    # Offsets say track 0 is on the left, but it is drawn on the right.
    hr = frozenset({"HR"})
    tracks = [track(0, 5.0, lines=hr, drawn_at=-5.0), track(1, 0.0, lines=hr, drawn_at=5.0)]
    result = classify(site("HR", single_pair=True), tracks)
    assert result.tracks == {}
    assert any("disagree" in note for note in result.unresolved)


def test_a_pair_drawn_on_top_of_each_other_is_unresolved() -> None:
    hr = frozenset({"HR"})
    tracks = [track(0, 0.2, lines=hr), track(1, 0.0, lines=hr)]
    result = classify(site("HR", single_pair=True), tracks)
    assert result.tracks == {}
    assert any("too close" in note for note in result.unresolved)


# --------------------------------------------------------------------------
# Certainty


EMPTY_OSM = parse_osm({"elements": []}, {"elements": []}, {"elements": []})
PLATFORM_WEST = Polygon([(-3, -100), (-8, -100), (-8, 100), (-3, 100)])


def _entry_certainty(evidence: CorridorEvidence, placement: Placement, terminus: bool = False) -> bool:
    tracks = [track(0, 0.0)]
    pairing = Pairing(tracks={"1": 0}, placements={"1": placement}, polygons={"1": [PLATFORM_WEST]})
    classification = Classification(tracks={0: Assignment("slow", "DN", evidence)}, unresolved=())
    entries, _ = entries_for_station(site(terminus=terminus), tracks, pairing, classification, EMPTY_OSM)
    assert entries[0]["door"] == "left"
    return entries[0]["certain"]


@pytest.mark.parametrize("evidence", ["own_name", "partner_name", "only_pair"])
@pytest.mark.parametrize("placement", ["stop", "single"])
def test_certain_needs_a_name_and_a_direct_placement(evidence: CorridorEvidence, placement: Placement) -> None:
    assert _entry_certainty(evidence, placement)


@pytest.mark.parametrize("evidence", ["traced", "opposite"])
def test_a_corridor_found_indirectly_is_never_certain(evidence: CorridorEvidence) -> None:
    assert not _entry_certainty(evidence, "stop")


@pytest.mark.parametrize("placement", ["numbering", "free"])
def test_a_number_placed_by_inference_is_never_certain(placement: Placement) -> None:
    assert not _entry_certainty("own_name", placement)


def test_nothing_is_certain_where_trains_start_or_end() -> None:
    assert not _entry_certainty("own_name", "stop", terminus=True)
