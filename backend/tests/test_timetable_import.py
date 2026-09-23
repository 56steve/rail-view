"""The rules the timetable importer applies to the official PDFs."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import import_timetables as tt  # noqa: E402


def train(number: str, stops: list[tuple[str, int, int]], **overrides) -> tt.ParsedTrain:
    fields = {
        "number": number,
        "code": "X 1",
        "railway": "CR",
        "line": "harbour",
        "direction": "DN",
        "ac": False,
        "non_ac_at_weekends": False,
        "cars": 12,
        "days": "all",
        "ladies_special": False,
        "ladies_coaches_reserved": False,
        "stops": stops,
        "source": "test.pdf",
        "page": 1,
        "valid_from": "2026-01-01",
        "corrections": [],
    }
    fields.update(overrides)
    return tt.ParsedTrain(**fields)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Ulhas Nagar", "Ulhasnagar"),
        ("Mumbai CSMT", "CSMT"),
        ("M'BAI CENTRAL (L)", "Mumbai Central"),
        ("Diwa", "Diva"),
        ("Vadala Road", "Wadala Road"),
        ("Ramnagar", "Ram Mandir"),
        ("DIGH", "Digha Gaon"),
        ("STATIONS", None),
    ],
)
def test_station_labels_map_to_canonical_names(label: str, expected: str | None) -> None:
    assert tt.canonical_station(label) == expected


def test_unknown_station_label_is_not_guessed() -> None:
    assert tt.canonical_station("Atlantis") is None


@pytest.mark.parametrize(
    ("notes", "starred", "expected"),
    [
        ("NOT ON SUN ONLY", False, "not_sunday"),
        ("NOT ON SUN & HOLIDAY", False, "not_sunday"),
        ("NOS ON SUNDAY", False, "not_sunday"),
        ("", True, "not_sunday"),
        ("SUN & HOLIDAY", False, "sunday_only"),
        ("SUN ONLY", False, "sunday_only"),
        ("ON SUNDAY", False, "sunday_only"),
        # About who may board on Sundays, not whether it runs.
        ("Ladies Special ON SUN General", False, "all"),
        ("Air Condition ON SAT & SUN NON AC", False, "all"),
    ],
)
def test_running_days_from_column_notes(notes: str, starred: bool, expected: str) -> None:
    assert tt.running_days(notes, starred) == expected


def test_a_time_printed_twelve_hours_out_is_corrected_and_recorded() -> None:
    column = tt.Column(number="91039", x=0.0, starred=False)
    rows = [tt.StationRow(name, float(i)) for i, name in enumerate(["Lower Parel", "Prabhadevi", "Dadar"])]
    column.times[0].append(25)
    column.times[1].append(12 * 60 + 28)  # printed as 12:28
    column.times[2].append(30)
    source = tt.SOURCES[0]
    corrections = tt._fix_twelve_hour_slips(column, rows, source, 0)
    assert column.times[1] == [28]
    assert len(corrections) == 1 and "Prabhadevi" in corrections[0]


def test_a_genuine_gap_is_not_mistaken_for_a_slip() -> None:
    column = tt.Column(number="1", x=0.0, starred=False)
    rows = [tt.StationRow(name, float(i)) for i, name in enumerate(["A", "B", "C"])]
    for i, minute in enumerate((600, 640, 680)):
        column.times[i].append(minute)
    assert tt._fix_twelve_hour_slips(column, rows, tt.SOURCES[0], 0) == []


def test_halves_printed_in_up_and_down_tables_join_at_the_junction() -> None:
    up = train("98901", [("Panvel", 357, 357), ("Kurla", 406, 406), ("Wadala Road", 418, 418)], direction="UP")
    down = train("98901", [("Wadala Road", 422, 422), ("Bandra", 434, 434), ("Goregaon", 459, 459)])
    [joined] = tt.stitch_split_trains([down, up])
    assert [s[0] for s in joined.stops] == ["Panvel", "Kurla", "Wadala Road", "Bandra", "Goregaon"]
    assert ("Wadala Road", 418, 422) in joined.stops
    assert joined.direction_changes_at == "Wadala Road"


def test_an_excerpt_across_midnight_is_dropped_for_the_full_listing() -> None:
    full = train("99073", [("Thane", 1412, 1412), ("Nerul", 1441, 1441), ("Panvel", 1464, 1464)])
    excerpt = train("99073", [("Nerul", 1, 1), ("Panvel", 24, 24)])
    [kept] = tt.stitch_split_trains([excerpt, full])
    assert kept is full


def test_disagreeing_listings_prefer_the_newer_timetable() -> None:
    older = train(
        "91491",
        [("CSMT", 1246, 1246), ("Andheri", 1287, 1287), ("Goregaon", 1298, 1298)],
        valid_from="2026-05-01",
    )
    newer = train(
        "91491",
        [("Andheri", 1291, 1291), ("Goregaon", 1300, 1300), ("Borivali", 1313, 1313)],
        railway="WR",
        valid_from="2026-09-01",
    )
    [merged] = tt.stitch_split_trains([older, newer])
    assert merged.stops == [
        ("CSMT", 1246, 1246),
        ("Andheri", 1291, 1291),
        ("Goregaon", 1300, 1300),
        ("Borivali", 1313, 1313),
    ]
    assert any("listings disagree" in c for c in merged.corrections)
    # Still the Harbour train it started as.
    assert (merged.railway, merged.line) == ("CR", "harbour")


def test_two_unrelated_trains_sharing_a_number_fail_the_import() -> None:
    a = train("90001", [("Churchgate", 300, 300), ("Dadar", 315, 315)])
    b = train("90001", [("Virar", 900, 900), ("Borivali", 930, 930)])
    with pytest.raises(tt.TimetableImportError):
        tt.stitch_split_trains([a, b])
