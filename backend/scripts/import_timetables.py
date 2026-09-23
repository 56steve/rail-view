"""Import the official Mumbai suburban timetables into RailView.

    uv run python scripts/import_timetables.py

Reads the Pocket Time Table (PTT) PDFs that Central and Western Railway
publish (listed in SOURCES, downloaded to backend/data/timetables/) and
writes backend/app/data/generated/timetable.json: every train with its
number, service code, direction, rake (AC, 12/15 car), running days and
the time it calls at each station.

The PDFs are laid out as one column per train and one row per station.
pdfplumber's table extraction merges neighbouring columns on some pages,
so this reads the page word by word instead: the header row of 5-digit
train numbers fixes the columns, the station names in the left margin fix
the rows, and every time on the page is placed by its position. Anything
that doesn't fit - an unknown station name, times running backwards, a
train listed twice - fails the import rather than being skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pdfplumber

BACKEND_DIR = Path(__file__).resolve().parents[1]
PDF_DIR = BACKEND_DIR / "data" / "timetables"
OUTPUT = BACKEND_DIR / "app" / "data" / "generated" / "timetable.json"

Railway = Literal["CR", "WR"]
Direction = Literal["UP", "DN"]
# Holidays follow the Sunday schedule (Central's list of such holidays is
# on the same page as the timetables).
Days = Literal["all", "not_sunday", "weekdays", "sunday_only"]


@dataclass(frozen=True, slots=True)
class Source:
    file: str
    url: str
    railway: Railway
    line: str  # main | harbour | transharbour | western
    valid_from: str  # ISO date the timetable takes effect
    # UP/DN when the whole PDF runs one way; None when it mixes both
    # (Trans-Harbour), in which case each page's station order decides.
    direction: Direction | None


SOURCES = (
    Source(
        "cr-main-dn.pdf",
        "https://cr.indianrailways.gov.in/cris//uploads/files/1728294831372-SUB%20PTT%20DN%20ML'24.pdf",
        "CR",
        "main",
        "2024-10-05",
        "DN",
    ),
    Source(
        "cr-main-up.pdf",
        "https://cr.indianrailways.gov.in/cris//uploads/files/1728294891897-SUB%20PTT%20UP%20ML'24.pdf",
        "CR",
        "main",
        "2024-10-05",
        "UP",
    ),
    Source(
        "cr-harbour-dn.pdf",
        "https://cr.indianrailways.gov.in/cris//uploads/files/1777550323377-DN%20HB%20REVISED%20PTT%20WEF%2001.05.2026.pdf",
        "CR",
        "harbour",
        "2026-05-01",
        "DN",
    ),
    Source(
        "cr-harbour-up.pdf",
        "https://cr.indianrailways.gov.in/cris//uploads/files/1777550366723-UP%20HB%20REVISED%20PTT%20WEF%2001.05.2026.pdf",
        "CR",
        "harbour",
        "2026-05-01",
        "UP",
    ),
    Source(
        "cr-transharbour.pdf",
        "https://cr.indianrailways.gov.in/cris//uploads/files/1781174782507-THB%20PTT%20wef%20%20%2013.01.2024.pdf",
        "CR",
        "transharbour",
        "2024-01-13",
        None,
    ),
    Source(
        "wr-dn.pdf",
        "https://wr.indianrailways.gov.in/cris//uploads/files/1788159627721-DN%20TRAINS%20PTT%2079%20W.E.F.%2001.09.2026.pdf",
        "WR",
        "western",
        "2026-09-01",
        "DN",
    ),
    Source(
        "wr-up.pdf",
        "https://wr.indianrailways.gov.in/cris//uploads/files/1788159720525-UP%20TRAINS%20PTT%2079%20W.E.F.%2001.09.2026.pdf",
        "WR",
        "western",
        "2026-09-01",
        "UP",
    ),
)

# Where each end of a line is, to tell UP (towards the city terminus)
# from DN when a PDF mixes both directions.
CITY_TERMINI = {"CSMT", "Churchgate", "Thane"}

# --------------------------------------------------------------------------
# Station names

# Canonical names. The first block matches scripts/network_definitions.py
# exactly (that is how timetable stops find their place on a route); the
# rest are stations beyond RailView's current network, named so trains
# running there keep every stop.
CANONICAL_STATIONS = (
    # Western
    "Churchgate", "Marine Lines", "Charni Road", "Grant Road", "Mumbai Central", "Mahalaxmi",
    "Lower Parel", "Prabhadevi", "Dadar", "Matunga Road", "Mahim", "Bandra", "Khar Road",
    "Santacruz", "Vile Parle", "Andheri", "Jogeshwari", "Ram Mandir", "Goregaon", "Malad",
    "Kandivali", "Borivali",
    # Central main line
    "CSMT", "Masjid", "Sandhurst Road", "Byculla", "Chinchpokli", "Currey Road", "Parel",
    "Matunga", "Sion", "Kurla", "Vidyavihar", "Ghatkopar", "Vikhroli", "Kanjurmarg", "Bhandup",
    "Nahur", "Mulund", "Thane", "Kalva", "Mumbra", "Diva", "Kopar", "Dombivli", "Thakurli",
    "Kalyan", "Shahad", "Ambivli", "Titwala", "Khadavli", "Vasind", "Asangaon", "Atgaon",
    "Thansit", "Khardi", "Umbermali", "Kasara", "Vithalwadi", "Ulhasnagar", "Ambarnath",
    "Badlapur", "Vangani", "Shelu", "Neral", "Bhivpuri Road", "Karjat",
    # Harbour and Trans-Harbour
    "Dockyard Road", "Reay Road", "Cotton Green", "Sewri", "Wadala Road", "GTB Nagar",
    "Chunabhatti", "Tilak Nagar", "Chembur", "Govandi", "Mankhurd", "Vashi", "Airoli", "Rabale",
    "Ghansoli", "Kopar Khairane", "Turbhe", "Sanpada",
    # Beyond the current network
    "Palasdhari", "Kelavli", "Dolavli", "Lowjee", "Khopoli", "King's Circle", "Juinagar",
    "Nerul", "Seawoods Darave Karave", "Belapur CBD", "Kharghar", "Mansarovar", "Khandeshwar",
    "Panvel", "Digha Gaon", "Dahisar", "Mira Road", "Bhayandar", "Naigaon", "Vasai Road",
    "Nallasopara", "Virar",
)  # fmt: skip

# PDF spellings that differ from the canonical name beyond case, spacing
# and punctuation (keys are normalised with _key).
ALIASES = {
    "mumbaicsmt": "CSMT",
    "mbaicentrall": "Mumbai Central",
    "mahalakshmi": "Mahalaxmi",
    "mahimjn": "Mahim",
    "kandivli": "Kandivali",
    "ambernath": "Ambarnath",
    "umbermalli": "Umbermali",
    "diwa": "Diva",
    "vadalaroad": "Wadala Road",
    "ramnagar": "Ram Mandir",
    "seawooddaravekarave": "Seawoods Darave Karave",
}

# Trans-Harbour pages label rows with station codes.
STATION_CODES = {
    "TNA": "Thane", "DIGH": "Digha Gaon", "AIRL": "Airoli", "RABE": "Rabale",
    "GNSL": "Ghansoli", "KPHN": "Kopar Khairane", "TUH": "Turbhe", "SNPD": "Sanpada",
    "VSH": "Vashi", "JNJ": "Juinagar", "NEU": "Nerul", "SWDV": "Seawoods Darave Karave",
    "BEPR": "Belapur CBD", "KHAG": "Kharghar", "MANR": "Mansarovar", "KNDS": "Khandeshwar",
    "PNVL": "Panvel",
}  # fmt: skip

# Left-margin text that is layout, not a station.
MARGIN_LABELS = {"station", "stations", "dntrains", "uptrains", "stationsdntrains", "stationsuptrains"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower())


_CANONICAL_BY_KEY = {_key(name): name for name in CANONICAL_STATIONS}


def canonical_station(label: str) -> str | None:
    """The canonical name for a left-margin label, or None if it isn't a
    station label at all (a heading such as 'STATIONS')."""
    stripped = label.strip()
    if stripped in STATION_CODES:
        return STATION_CODES[stripped]
    key = _key(stripped)
    if not key or key in MARGIN_LABELS:
        return None
    if key in ALIASES:
        return ALIASES[key]
    return _CANONICAL_BY_KEY.get(key)


class TimetableImportError(RuntimeError):
    """The timetable doesn't parse cleanly; the message says where."""


# --------------------------------------------------------------------------
# Page parsing

TRAIN_NUMBER = re.compile(r"^(\*?)(\d{5})(\*?)$")
# One source prints 20;02 for 20:02.
TIME = re.compile(r"^(\d{1,2})[:;](\d{2})$")
PASS_MARKERS = {"…", "...", "..", "|", "-", "--", "`", "``"}
# Words that label a time printed inside a column as where the train
# comes from or goes to beyond this table ("EX CSMT", "CSTM Arr", "TNA"),
# rather than a call at the station row it happens to sit on.
ANNOTATION_WORDS = {"EX", "ARR", "ARR.", "CSMT", "CSTM", "PNVL", "TNA", "BVI"}
# The labelled time is printed on the label's line or a line or two away.
ANNOTATION_REACH_PT = 30.0
ROW_TOLERANCE_PT = 6.0
MARGIN_GAP_PT = 4.0


@dataclass
class Column:
    number: str
    x: float
    starred: bool
    header: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # station row index -> times (minutes past midnight, unrolled later)
    times: dict[int, list[int]] = field(default_factory=lambda: defaultdict(list))


@dataclass(frozen=True, slots=True)
class StationRow:
    name: str
    y: float


@dataclass(frozen=True, slots=True)
class OutsideStations:
    """A train listed on a page but calling at only one of its stations."""

    number: str
    source: str
    page: int
    station: str


@dataclass
class ParsedTrain:
    number: str
    code: str | None
    railway: Railway
    line: str
    direction: Direction
    ac: bool
    non_ac_at_weekends: bool
    cars: int
    days: Days
    ladies_special: bool
    # Three coaches reserved for ladies on an otherwise general train.
    ladies_coaches_reserved: bool
    stops: list[tuple[str, int, int]]  # station, arrival min, departure min
    source: str
    page: int
    valid_from: str
    corrections: list[str]
    # Set on trains whose Up/Down designation flips part-way, e.g. Panvel -
    # Goregaon services: Up to Wadala Road, then Down along the Goregaon
    # branch. The PDFs print the two halves in different tables.
    direction_changes_at: str | None = None


def _words(page) -> list[dict]:
    # A tight x tolerance keeps neighbouring columns apart; times whose
    # characters come out split are rejoined by _join_split_times.
    return _join_split_times(page.extract_words(x_tolerance=2.5, y_tolerance=3, keep_blank_chars=False))


def _join_split_times(words: list[dict]) -> list[dict]:
    """Some PDFs space a time's characters widely enough that they come
    out as separate words ('0' '4' ':' '5' '1'). Rejoin runs of single
    characters on one line that form a time."""
    by_line: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        by_line[round(w["top"])].append(w)
    out: list[dict] = []
    for line in by_line.values():
        line.sort(key=lambda w: w["x0"])
        i = 0
        while i < len(line):
            run = [line[i]]
            while (
                len(run) < 5
                and i + len(run) < len(line)
                and len(line[i + len(run)]["text"]) == 1
                and len(run[-1]["text"]) == 1
                and line[i + len(run)]["x0"] - run[-1]["x1"] < 4
            ):
                run.append(line[i + len(run)])
            text = "".join(w["text"] for w in run)
            if len(run) > 1 and TIME.match(text):
                out.append({**run[0], "text": text, "x1": run[-1]["x1"]})
                i += len(run)
            else:
                out.append(line[i])
                i += 1
    return out


def _minutes(token: str) -> int:
    match = TIME.match(token)
    if not match:
        raise ValueError(token)
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        raise TimetableImportError(f"impossible time {token!r}")
    return hours * 60 + minutes


def parse_page(page, source: Source, page_index: int) -> list[ParsedTrain | OutsideStations]:
    words = _words(page)
    numbers = [w for w in words if TRAIN_NUMBER.match(w["text"])]
    if len(numbers) < 2:
        return []
    header_y = sorted(w["top"] for w in numbers)[len(numbers) // 2]
    numbers = [w for w in numbers if abs(w["top"] - header_y) < 12]
    columns = [
        Column(
            number=TRAIN_NUMBER.match(w["text"]).group(2),  # type: ignore[union-attr]
            x=(w["x0"] + w["x1"]) / 2,
            starred="*" in w["text"],
        )
        for w in sorted(numbers, key=lambda w: w["x0"])
    ]
    first_column_x0 = min(w["x0"] for w in numbers)
    spacing = min((b.x - a.x for a, b in zip(columns, columns[1:], strict=False)), default=60.0)

    # Station rows: left-margin text below the header, grouped by line.
    margin_lines: dict[int, list[dict]] = defaultdict(list)
    for w in words:
        if w["x1"] < first_column_x0 - MARGIN_GAP_PT and w["top"] > header_y + 4:
            margin_lines[round(w["top"] / 2)].append(w)
    rows: list[StationRow] = []
    for line_words in sorted(margin_lines.values(), key=lambda ws: ws[0]["top"]):
        label = " ".join(w["text"] for w in sorted(line_words, key=lambda w: w["x0"]))
        name = canonical_station(label)
        if name is None:
            if _key(label) and rows:
                raise TimetableImportError(f"{source.file} page {page_index + 1}: unknown station label {label!r}")
            continue
        y = sum(w["top"] for w in line_words) / len(line_words)
        if rows and abs(rows[-1].y - y) < ROW_TOLERANCE_PT and rows[-1].name == name:
            continue
        rows.append(StationRow(name, y))
    if len(rows) < 2:
        raise TimetableImportError(f"{source.file} page {page_index + 1}: found {len(rows)} station rows")

    def column_for(x: float) -> Column | None:
        best = min(columns, key=lambda c: abs(c.x - x))
        return best if abs(best.x - x) < spacing * 0.55 else None

    def row_for(y: float) -> int | None:
        index = min(range(len(rows)), key=lambda i: abs(rows[i].y - y))
        return index if abs(rows[index].y - y) < ROW_TOLERANCE_PT else None

    number_ids = {id(w) for w in numbers}
    body = [
        (w, column)
        for w in words
        if id(w) not in number_ids
        and w["x1"] >= first_column_x0 - MARGIN_GAP_PT
        and (column := column_for((w["x0"] + w["x1"]) / 2)) is not None
    ]
    # Each annotation label claims the nearest time in its column.
    annotated_times: set[int] = set()
    for label, column in body:
        within_table = rows[0].y - ROW_TOLERANCE_PT <= label["top"] <= rows[-1].y + ROW_TOLERANCE_PT
        if label["text"].upper() not in ANNOTATION_WORDS or not within_table:
            # Footers mention stations too ("TNA end 3 coaches reserved...").
            continue
        candidates = [
            (abs(w["top"] - label["top"]), w)
            for w, c in body
            if c is column and TIME.match(w["text"]) and abs(w["top"] - label["top"]) <= ANNOTATION_REACH_PT
        ]
        if candidates:
            annotated_times.add(id(min(candidates, key=lambda pair: pair[0])[1]))

    def is_annotation_time(w: dict, column: Column) -> bool:
        return id(w) in annotated_times

    for w, column in body:
        text = w["text"]
        if w["top"] < rows[0].y - ROW_TOLERANCE_PT:
            column.header.append(text)
        elif TIME.match(text) and is_annotation_time(w, column):
            column.notes.append(f"annotated {text}")
        elif TIME.match(text):
            row = row_for(w["top"])
            if row is None:
                raise TimetableImportError(
                    f"{source.file} page {page_index + 1}: time {text} for train {column.number} "
                    f"sits between station rows (y={w['top']:.0f})"
                )
            column.times[row].append(_minutes(text))
        elif text not in PASS_MARKERS:
            column.notes.append(text)

    direction = source.direction or _direction_from_order(rows)
    return [
        train
        for column in columns
        if (train := _build_train(column, rows, source, page_index, direction)) is not None
    ]


# How close a time must sit to both neighbours, once shifted by 12 hours,
# to be treated as a 12-hour slip in the source (e.g. 12:28 printed for
# 00:28 between 00:25 and 00:30).
SLIP_MATCH_MIN = 20


def _circular_gap(a: int, b: int) -> int:
    gap = abs(a - b) % 1440
    return min(gap, 1440 - gap)


def _fix_twelve_hour_slips(column: Column, rows: list[StationRow], source: Source, page_index: int) -> list[str]:
    """Correct a lone time printed 12 hours out, and say so."""
    order = sorted(column.times)
    corrections: list[str] = []
    for i, index in enumerate(order):
        neighbours = [column.times[order[j]][0] for j in (i - 1, i + 1) if 0 <= j < len(order)]
        if len(neighbours) < 2:
            continue
        times = column.times[index]
        for k, minute in enumerate(times):
            if all(_circular_gap(minute, n) <= SLIP_MATCH_MIN for n in neighbours):
                continue
            shifted = (minute + 720) % 1440
            if all(_circular_gap(shifted, n) <= SLIP_MATCH_MIN for n in neighbours):
                times[k] = shifted
                corrections.append(
                    f"{source.file} p{page_index + 1} train {column.number} at {rows[index].name}: "
                    f"{minute // 60:02d}:{minute % 60:02d} read as {shifted // 60:02d}:{shifted % 60:02d}"
                )
    return corrections


def running_days(notes: str, starred: bool) -> Days:
    """Which schedule a train runs on, from the notes printed in its
    column. Holidays follow the Sunday schedule, so "not on Sunday &
    holiday" and "not on Sunday" are the same thing here.

    Deliberately narrow: "Ladies special, on Sunday general" is about who
    may board, not about when the train runs.
    """
    if starred or re.search(r"\bNO[TS]\s+(ON\s+)?(SUN|ONLY)", notes, re.I):
        return "not_sunday"
    if re.search(r"\bSUN(DAY)?\.?\s+(ONLY|&\s*HOLIDAY)", notes, re.I) or re.fullmatch(
        r"\s*ON\s+SUNDAY\s*", notes, re.I
    ):
        return "sunday_only"
    return "all"


def _direction_from_order(rows: list[StationRow]) -> Direction:
    first, last = rows[0].name, rows[-1].name
    if first in CITY_TERMINI and last not in CITY_TERMINI:
        return "DN"
    if last in CITY_TERMINI and first not in CITY_TERMINI:
        return "UP"
    raise TimetableImportError(f"can't tell direction of a page running {first} -> {last}")


def _build_train(
    column: Column, rows: list[StationRow], source: Source, page_index: int, direction: Direction
) -> ParsedTrain | OutsideStations | None:
    if not column.times:
        # A train number with no times on this page (e.g. a footnote).
        return None
    header = " ".join(column.header + column.notes)
    # Central's service codes ("N 1", "PLGN 3"); not Western's car counts
    # ("12 CAR"), which Western prints where Central prints the code.
    code_match = re.search(r"\b([A-Z]{1,5})\s+(\d{1,3})\b(?!\s*CAR)", " ".join(column.header))
    code = f"{code_match.group(1)} {code_match.group(2)}" if code_match else None

    # Central's marks, from its ABBREVIATIONS sheet (data/timetables/
    # cr-abbreviations.pdf): X - not on Sunday/holiday; XX - not on
    # Saturday/Sunday/holiday; $ - 3 coaches reserved for ladies;
    # # - ladies special, general on Sundays and holidays.
    marks = set(re.findall(r"(?:^|\s)(XX|X|\$|#)(?=\s|$)", header))
    days = running_days(header, column.starred)
    if "XX" in marks:
        days = "weekdays"
    elif "X" in marks and days == "all":
        days = "not_sunday"
    cars = 15 if re.search(r"\b15\s*C(AR)?\b", header) else 12
    ac = bool(re.search(r"\bAC\b(?<!NON AC)|Air\s*Condition", header, re.I))
    # "Air Condition - ON SAT & SUN NON AC": an AC rake that runs as a
    # regular train at weekends.
    non_ac_at_weekends = ac and bool(re.search(r"SAT\s*&\s*SUN|SA\s*&\s*SU", header, re.I))
    ladies = bool(re.search(r"Ladies|L\s+SPL", header, re.I)) or "#" in marks
    ladies_coaches = "$" in marks

    corrections = _fix_twelve_hour_slips(column, rows, source, page_index)

    stops: list[tuple[str, int, int]] = []
    previous = None
    day_offset = 0
    for index in sorted(column.times):
        raw = column.times[index]
        unrolled: list[int] = []
        for minute in raw:
            value = minute + day_offset
            if previous is not None and value < previous - 600:
                day_offset += 1440
                value += 1440
            unrolled.append(value)
            previous = value
        arrival, departure = min(unrolled), max(unrolled)
        stops.append((rows[index].name, arrival, departure))

    where = f"{source.file} page {page_index + 1} train {column.number}"
    if len(stops) < 2:
        # Its other stops are outside this PDF (e.g. Virar - Dahanu Road
        # services, which have their own timetable).
        return OutsideStations(column.number, source.file, page_index + 1, stops[0][0])
    for (a_name, _, a_dep), (b_name, b_arr, _) in zip(stops, stops[1:], strict=False):
        if b_arr < a_dep:
            raise TimetableImportError(f"{where}: {b_name} ({b_arr}) before {a_name} ({a_dep})")
    if stops[-1][1] - stops[0][2] > 5 * 60:
        raise TimetableImportError(f"{where}: runs {stops[-1][1] - stops[0][2]} minutes - misread times?")

    return ParsedTrain(
        corrections=corrections,
        number=column.number,
        code=code,
        railway=source.railway,
        line=source.line,
        direction=direction,
        ac=ac,
        non_ac_at_weekends=non_ac_at_weekends,
        cars=cars,
        days=days,
        ladies_special=ladies,
        ladies_coaches_reserved=ladies_coaches,
        stops=stops,
        source=source.file,
        page=page_index + 1,
        valid_from=source.valid_from,
    )


# --------------------------------------------------------------------------
# Whole import


def import_source(source: Source) -> tuple[list[ParsedTrain], list[OutsideStations]]:
    path = PDF_DIR / source.file
    if not path.exists():
        raise TimetableImportError(f"{path} is missing - download it from {source.url}")
    trains: list[ParsedTrain] = []
    outside: list[OutsideStations] = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            for parsed in parse_page(page, source, index):
                (trains if isinstance(parsed, ParsedTrain) else outside).append(parsed)
    return trains, outside


# Longest a train stands where its two published halves meet.
MAX_STITCH_WAIT_MIN = 20


def _is_excerpt(part: ParsedTrain, whole: ParsedTrain) -> bool:
    """Whether `part` lists a stretch of `whole` with the same times -
    e.g. a Thane - Panvel train also printed in the Harbour table for the
    Nerul - Panvel section the two lines share."""
    times = {name: (arr, dep) for name, arr, dep in whole.stops}
    # Modulo a day: an excerpt after midnight may be printed as 00:01
    # where the full listing, counting from the train's start, has 24:01.
    return len(part.stops) < len(whole.stops) and all(
        name in times and _circular_gap(times[name][0], arr) <= 1 and _circular_gap(times[name][1], dep) <= 1
        for name, arr, dep in part.stops
    )


def _reconcile(a: ParsedTrain, b: ParsedTrain, number: str, railway: str) -> ParsedTrain:
    """Two official listings of one train that overlap but disagree - e.g.
    a Harbour train that Western's newer timetable extends to Borivali with
    retimed stops. The newer timetable wins for the stations both list;
    stations only the older one lists are kept."""
    shared = {name for name, _, _ in a.stops} & {name for name, _, _ in b.stops}
    where = f"{railway} train {number} ({a.source} p{a.page}, {b.source} p{b.page})"
    if len(shared) < 2:
        raise TimetableImportError(f"{where}: two listings that neither join up nor overlap")
    newer, older = (a, b) if a.valid_from >= b.valid_from else (b, a)
    newer_names = {name for name, _, _ in newer.stops}
    merged = sorted(
        [*newer.stops, *(stop for stop in older.stops if stop[0] not in newer_names)],
        key=lambda stop: (stop[1], stop[2]),
    )
    for listing in (a, b):
        order = [name for name, _, _ in merged if name in {n for n, _, _ in listing.stops}]
        if order != [name for name, _, _ in listing.stops]:
            raise TimetableImportError(f"{where}: listings visit stations in different orders")
    for (a_name, _, a_dep), (b_name, b_arr, _) in zip(merged, merged[1:], strict=False):
        if b_arr < a_dep:
            raise TimetableImportError(f"{where}: merged times run backwards at {a_name} -> {b_name}")
    newer.stops = merged
    # The railway the train starts on runs it: a Harbour train extended
    # in Western's table is still a Harbour train.
    starter = a if a.stops[0][0] == merged[0][0] else b
    newer.railway, newer.line, newer.code = starter.railway, starter.line, starter.code or newer.code
    newer.ac = newer.ac or older.ac
    newer.cars = max(newer.cars, older.cars)
    newer.ladies_coaches_reserved = newer.ladies_coaches_reserved or older.ladies_coaches_reserved
    newer.corrections = [
        *newer.corrections,
        *older.corrections,
        f"{where}: listings disagree; used {newer.source} (valid from {newer.valid_from}) where both list a station",
    ]
    return newer


def stitch_split_trains(trains: list[ParsedTrain]) -> list[ParsedTrain]:
    """Resolve trains printed in two tables: drop an excerpt of a train
    listed in full elsewhere, and join the halves of trains whose Up/Down
    designation flips part-way (see ParsedTrain.direction_changes_at).
    Two different trains sharing a number is an error."""
    # Train numbers are unique across both railways: a Harbour train
    # printed in Western's table for the stretch it runs on WR tracks is
    # the same train as in Central's table.
    by_number: dict[str, list[ParsedTrain]] = defaultdict(list)
    for train in trains:
        by_number[train.number].append(train)

    stitched: list[ParsedTrain] = []
    for number, listings in by_number.items():
        railway = "/".join(sorted({p.railway for p in listings}))
        parts = [p for p in listings if not any(_is_excerpt(p, other) for other in listings if other is not p)]
        parts.sort(key=lambda t: t.stops[0][2])
        train = parts[0]
        for part in parts[1:]:
            (junction, arrival, _), (start, _, departure) = train.stops[-1], part.stops[0]
            if junction != start or not 0 <= departure - arrival <= MAX_STITCH_WAIT_MIN:
                train = _reconcile(train, part, number, railway)
                continue
            train.stops = [*train.stops[:-1], (junction, arrival, departure), *part.stops[1:]]
            if part.direction != train.direction:
                train.direction_changes_at = junction
            train.ac = train.ac or part.ac
            train.cars = max(train.cars, part.cars)
            train.ladies_coaches_reserved = train.ladies_coaches_reserved or part.ladies_coaches_reserved
            train.corrections = train.corrections + part.corrections
        stitched.append(train)
    return stitched


def to_json(trains: list[ParsedTrain], outside: list[OutsideStations]) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": [
            {
                "file": s.file,
                "url": s.url,
                "railway": s.railway,
                "line": s.line,
                "valid_from": s.valid_from,
                "sha256": hashlib.sha256((PDF_DIR / s.file).read_bytes()).hexdigest(),
            }
            for s in SOURCES
        ],
        "notes": (
            "Times are minutes after midnight of the service day; values of 1440 or more "
            "are after midnight. arrival == departure where the timetable gives one time."
        ),
        "trains": [
            {
                "number": t.number,
                "code": t.code,
                "railway": t.railway,
                "line": t.line,
                "direction": t.direction,
                "direction_changes_at": t.direction_changes_at,
                "ac": t.ac,
                "non_ac_at_weekends": t.non_ac_at_weekends,
                "cars": t.cars,
                "days": t.days,
                "ladies_special": t.ladies_special,
                "ladies_coaches_reserved": t.ladies_coaches_reserved,
                "stops": [[name, arr, dep] for name, arr, dep in t.stops],
            }
            for t in sorted(trains, key=lambda t: (t.railway, t.line, t.direction, t.stops[0][2], t.number))
        ],
        "corrections": [c for t in trains for c in t.corrections],
        "outside_stations": [
            {"number": o.number, "source": o.source, "page": o.page, "only_station": o.station} for o in outside
        ],
    }


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    trains: list[ParsedTrain] = []
    outside: list[OutsideStations] = []
    for source in SOURCES:
        parsed, beyond = import_source(source)
        stops = sum(len(t.stops) for t in parsed)
        extra = f"; {len(beyond)} calling at only one station here" if beyond else ""
        print(f"  {source.file}: {len(parsed)} trains, {stops} stops{extra}")
        trains.extend(parsed)
        outside.extend(beyond)
    listed = len(trains)
    trains = stitch_split_trains(trains)
    stitched = sum(1 for t in trains if t.direction_changes_at)
    print(
        f"  resolved {listed - len(trains)} trains printed in two tables "
        f"({stitched} joined across an Up/Down change, the rest duplicates of a fuller listing)"
    )
    for correction in (c for t in trains for c in t.corrections):
        print(f"  corrected {correction}")
    OUTPUT.write_text(json.dumps(to_json(trains, outside), separators=(",", ":")) + "\n")
    print(f"  wrote {OUTPUT.relative_to(BACKEND_DIR)} ({len(trains)} trains)")


if __name__ == "__main__":
    try:
        main()
    except TimetableImportError as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        sys.exit(1)
