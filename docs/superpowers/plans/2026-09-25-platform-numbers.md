# Platform Numbers and Door Side Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For every timetabled train at every stop, show the platform it calls at and which side its doors open, like m-Indicator's route view:
- "PF 3 · Doors left" when the station's layout makes it certain;
- "Usually PF 5–7" where it varies from train to train.

**Architecture:**
1. **Station platform table.** An offline script derives, per (line, station), which platform serves which corridor (slow / fast / single-corridor lines) in which direction (UP / DN), and on which side of the train it lies. The inputs are OpenStreetMap stop positions, platform polygons and named tracks, all read from the existing Overpass cache.
2. **Hand curation.** A hand-curated file overrides whole stations: the gaps, conflicts and termini.
3. **Merge.** The two are merged into `backend/app/data/generated/platforms.json`.
4. **Resolution.** At timetable load, each train's stops are resolved against that table from the train's line, its direction at the stop, its corridor on the approach (derived from which stations it skips) and the stop's role (originating / through / terminating).
5. **Delivery.**
   - The result rides on `TimetableStop` into the run plan.
   - It goes out in the REST stop timeline and journey options, and as three scalar columns on the live WebSocket table.
   - The frontend formats it in one helper and shows it on the timeline, the follow screen, the 3D next-station pin, the journey options and arrival alerts.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, shapely, pytest (backend, `uv`); Next.js 16, React 19, TypeScript strict, Tailwind v4, vitest (frontend).

**Data licence:** the platform table is derived from OSM (ODbL). Keep `attribution` in the generated file and the existing "© OpenStreetMap contributors" credit in the app. Curated entries cite their source (a Wikipedia article or an official renumbering notice) as plain facts.

---

## Background the engineer needs

- **UP / DN.** UP is towards CSMT or Churchgate; DN is away from them. The timetable JSON has `direction` (`"UP"`/`"DN"`) and `direction_changes_at` (only `"Wadala Road"`, for Panvel → Goregaon workings), but `load_timetable` currently drops both.
- **Corridors.** On WR (Churchgate–Virar) and CR (CSMT–Kalyan) there are separate slow and fast track pairs. Each track has its own platforms at each station. Harbour, Trans-Harbour, and CR beyond Kalyan have one pair, which we call corridor `"any"`.
- **Left-hand running.** Within a pair, a train's own track is the left one in its direction of travel.
- **Line codes.** `WR`, `CR`, `HR`, `THR`, from `LINE_CODES` in `app/services/timetable.py`. A station on two lines has separate platform sets: Dadar WR vs Dadar CR, Andheri WR vs Andheri HR. The table is keyed by `(line_code, station_name)`, and station names are the canonical names used in `timetable.json` stops.
- **Current fast flag.** `TimetabledTrain.fast` is one flag per train. Platforms need the corridor per stop: a semi-fast train is fast to Thane and slow after it.
- **Cache.** The OSM cache lives in `backend/.osm-cache/` (`rails.json`, `platforms.json`, `stations.json`). `scripts/build_osm_data.py:188` `overpass(query, cache_key, refresh)` returns the cached file for a fixed key. A new query needs a new key.
- **Frontend ordering.** `frontend/lib/liveWire.ts` `decodeSnapshot` throws if a column in `TRAIN_FIELDS` is missing. Task 10 makes the new columns optional, so it doesn't matter whether Vercel or Render deploys first.

## File structure

**Backend: new**

| File | Responsibility |
|---|---|
| `backend/app/services/platforms.py` | Domain types (`PlatformEntry`, `PlatformAssignment`), loading the generated table, and resolving one stop. Pure, no I/O besides the loader. |
| `backend/app/services/corridors.py` | Per-stop corridor (`slow`/`fast`/`any`) and direction (`UP`/`DN`) for a timetabled train. |
| `backend/scripts/platform_geometry.py` | Pure geometry: classify tracks, pair stop positions and platforms with tracks, decide the UP/DN track and the door side. Unit-tested with synthetic shapes. |
| `backend/scripts/build_platforms.py` | CLI: reads the OSM cache and `network.json`, derives entries, merges the curated file, writes the generated table and a coverage report. |
| `backend/data/platforms/curated.json` | Hand entries per station, each with its source. |
| `backend/app/data/generated/platforms.json` | Build output, committed like `network.json`. |

**Backend tests: new**

`backend/tests/test_platforms.py`, `test_corridors.py`, `test_platform_geometry.py`, `test_platform_data.py`.

**Backend: modified**

| File | Change |
|---|---|
| `app/services/timetable.py` | Keep `direction` / `direction_changes_at`; attach a `platform` to each `TimetableStop`. |
| `app/services/simulator/schedule.py` | `ScheduledStop.platform`, filled by `timetable_run_plan`. |
| `app/schemas/train.py` | `PlatformOut`; `StopTime.platform`; three `next_platform*` fields on `TrainPositionUpdate`. |
| `app/schemas/journey.py` | `JourneyOption.board_platform` / `alight_platform`. |
| `app/services/timeline.py`, `position_processor.py`, `journey_planner.py` | Fill the new fields. |

**Frontend: new**

`frontend/lib/platform.ts` (formatting) and `frontend/lib/platform.test.ts`.

**Frontend: modified**

- `lib/types.ts`, `lib/liveWire.ts`
- `components/screens/TrainDetailsScreen.tsx`, `components/screens/FollowScreen.tsx`, `components/ui/NextStationPin.tsx`, `components/screens/JourneyScreen.tsx`
- `hooks/useArrivalAlerts.ts`

---

## Phase 1: the platform table

### Task 1: Domain types and the stop resolver

**Files:**
- Create: `backend/app/services/platforms.py`
- Test: `backend/tests/test_platforms.py`

The resolver answers one question: given a station's entries and a stop's (corridor, direction, role), which platforms and which door side?

Rules:
1. **Role.** Prefer entries with the stop's role. If there are none, fall back to `"through"` entries.
2. **Corridor.** Match the corridor exactly or `"any"`. If none match, use the other corridor's entries, marked not certain. This covers a slow train diverted onto the fast line.
3. **Direction.** It must match.
4. **Several matches.** Union their numbers. The result is certain only if exactly one entry matched and it is certain.
5. **Door side.** The common value if all matches agree, otherwise `None`.
6. **No match:** return `None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_platforms.py
from app.services.platforms import PlatformEntry, resolve_platform

ANDHERI_WR = (
    PlatformEntry(numbers=("3",), corridor="slow", direction="DN", role="through", door="left", certain=True),
    PlatformEntry(numbers=("5",), corridor="slow", direction="UP", role="through", door="left", certain=True),
    PlatformEntry(numbers=("6",), corridor="fast", direction="DN", role="through", door="right", certain=True),
    PlatformEntry(numbers=("7",), corridor="fast", direction="UP", role="through", door="right", certain=True),
    PlatformEntry(numbers=("4",), corridor="slow", direction="UP", role="originating", door="right", certain=False),
    PlatformEntry(numbers=("8", "9"), corridor="fast", direction="UP", role="originating", door=None, certain=False),
)


def test_through_stop_on_its_corridor_is_certain() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="slow", direction="DN", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("3",), "left", True)


def test_role_specific_entries_win() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="UP", role="originating")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("8", "9"), None, False)


def test_missing_role_falls_back_to_through() -> None:
    p = resolve_platform(ANDHERI_WR, corridor="fast", direction="DN", role="terminating")
    assert p is not None and p.numbers == ("6",) and p.certain


def test_other_corridor_is_a_fallback_and_never_certain() -> None:
    only_slow = tuple(e for e in ANDHERI_WR if e.corridor == "slow" and e.role == "through")
    p = resolve_platform(only_slow, corridor="fast", direction="UP", role="through")
    assert p is not None and p.numbers == ("5",) and not p.certain


def test_any_corridor_matches_every_train() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door="right", certain=True),)
    p = resolve_platform(entries, corridor="slow", direction="DN", role="through")
    assert p is not None and p.numbers == ("1",) and p.certain


def test_several_matches_union_and_lose_certainty() -> None:
    entries = (
        PlatformEntry(numbers=("2",), corridor="any", direction="UP", role="through", door="left", certain=True),
        PlatformEntry(numbers=("1",), corridor="any", direction="UP", role="through", door="left", certain=True),
    )
    p = resolve_platform(entries, corridor="any", direction="UP", role="through")
    assert p is not None
    assert (p.numbers, p.door, p.certain) == (("1", "2"), "left", False)


def test_no_entry_for_the_direction_is_none() -> None:
    entries = (PlatformEntry(numbers=("1",), corridor="any", direction="DN", role="through", door=None, certain=True),)
    assert resolve_platform(entries, corridor="any", direction="UP", role="through") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_platforms.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.platforms'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/platforms.py
"""Which platform a train calls at, and on which side its doors open.

A station's platforms are listed per line as entries: the platform
numbers that serve one corridor (the slow or fast pair, or "any" where a
line has only one pair) in one direction, for trains passing through or
starting or ending there. They are derived from OpenStreetMap and
curated by hand (scripts/build_platforms.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

Corridor = Literal["slow", "fast", "any"]
Direction = Literal["UP", "DN"]
StopRole = Literal["originating", "through", "terminating"]
DoorSide = Literal["left", "right", "both"]

PLATFORMS_JSON = Path(__file__).resolve().parents[1] / "data" / "generated" / "platforms.json"


class PlatformDataError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlatformEntry:
    numbers: tuple[str, ...]
    corridor: Corridor
    direction: Direction
    role: StopRole
    # Side of the train the platform is on, facing the way it travels.
    door: DoorSide | None
    certain: bool


@dataclass(frozen=True, slots=True)
class PlatformAssignment:
    numbers: tuple[str, ...]
    door: DoorSide | None
    # False where the platform varies from train to train (termini) or the
    # train is off its usual corridor: show "usually".
    certain: bool


def _platform_order(number: str) -> tuple[int, str]:
    match = re.match(r"(\d+)(.*)", number)
    return (int(match.group(1)), match.group(2)) if match else (10**6, number)


def resolve_platform(
    entries: tuple[PlatformEntry, ...], corridor: Corridor, direction: Direction, role: StopRole
) -> PlatformAssignment | None:
    """The platform for a stop, or None if the station's table doesn't
    cover this direction."""
    facing = [e for e in entries if e.direction == direction]
    by_role = [e for e in facing if e.role == role] or [e for e in facing if e.role == "through"]
    own = [e for e in by_role if e.corridor in (corridor, "any") or corridor == "any"]
    matches, off_corridor = (own, False) if own else (by_role, True)
    if not matches:
        return None
    numbers = tuple(sorted({n for e in matches for n in e.numbers}, key=_platform_order))
    doors = {e.door for e in matches}
    return PlatformAssignment(
        numbers=numbers,
        door=doors.pop() if len(doors) == 1 else None,
        certain=len(matches) == 1 and matches[0].certain and not off_corridor,
    )


@dataclass(frozen=True, slots=True)
class PlatformTable:
    stations: dict[tuple[str, str], tuple[PlatformEntry, ...]]
    attribution: str

    def entries(self, line_code: str, station_name: str) -> tuple[PlatformEntry, ...]:
        return self.stations.get((line_code, station_name), ())


@lru_cache
def load_platform_table(path: Path = PLATFORMS_JSON) -> PlatformTable:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise PlatformDataError(f"{path} is missing - run `uv run python scripts/build_platforms.py`") from exc
    stations: dict[tuple[str, str], tuple[PlatformEntry, ...]] = {}
    for station in raw["stations"]:
        stations[(station["line_code"], station["station"])] = tuple(
            PlatformEntry(
                numbers=tuple(entry["numbers"]),
                corridor=entry["corridor"],
                direction=entry["direction"],
                role=entry["role"],
                door=entry["door"],
                certain=entry["certain"],
            )
            for entry in station["platforms"]
        )
    return PlatformTable(stations=stations, attribution=raw["attribution"])
```

The `own` filter treats a stop with corridor `"any"` (a single-pair section) as matching every entry, and an entry with `"any"` as matching every stop.

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_platforms.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/platforms.py backend/tests/test_platforms.py
git commit -m "Resolve a stop's platform and door side from a station's platform table"
```

### Task 2: Corridor and direction per stop

**Files:**
- Create: `backend/app/services/corridors.py`
- Test: `backend/tests/test_corridors.py`

Rules:

**Direction at stop `i`.** The train's `direction`, flipped for stops after `direction_changes_at`. At the change station itself the train arrives in its original direction.

**Corridor at stop `i`: the section the train arrives on.** The departure section is used for the first stop. Each section between consecutive stops is:
- `"fast"` if the train passes, without calling, a station of its route that is not a fast halt (`StationSeed.fast_halt` is False). Slow-only stations only have slow platforms, so a train that skips one is on the fast pair.
- **inherited** from the section before it if it runs between two adjacent fast halts with nothing passed. A fast train calling at consecutive fast halts stays on its pair.
- `"slow"` otherwise.

A stop at a station where the line has only one pair of tracks is `"any"`. That set (`single_pair`) comes from the platform table built in Task 5; the function takes it as a parameter so it stays pure.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_corridors.py
from app.services.corridors import stop_corridors, stop_directions

# Route order (DN): A B C D E F. Fast halts: A, C, E, F.
ROUTE = ("A", "B", "C", "D", "E", "F")
FAST_HALTS = frozenset({"A", "C", "E", "F"})


def test_all_stations_called_is_slow_throughout() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "B", "C", "D", "E", "F"), single_pair=frozenset()) == (
        "slow", "slow", "slow", "slow", "slow", "slow",
    )


def test_skipping_slow_only_stations_is_fast() -> None:
    # E -> F passes nothing but runs between fast halts: stays fast.
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "E", "F"), single_pair=frozenset()) == (
        "fast", "fast", "fast", "fast",
    )


def test_semi_fast_switches_where_it_starts_calling_everywhere() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "D", "E", "F"), single_pair=frozenset()) == (
        "fast", "fast", "slow", "slow", "slow",
    )


def test_single_pair_stations_are_any() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("A", "C", "E", "F"), single_pair=frozenset({"E", "F"})) == (
        "fast", "fast", "any", "any",
    )


def test_backward_trains_read_the_route_backwards() -> None:
    assert stop_corridors(ROUTE, FAST_HALTS, ("F", "E", "C", "A"), single_pair=frozenset()) == (
        "fast", "fast", "fast", "fast",
    )


def test_direction_flips_after_the_change_station() -> None:
    assert stop_directions("UP", "C", ("A", "B", "C", "D")) == ("UP", "UP", "UP", "DN")
    assert stop_directions("DN", None, ("A", "B")) == ("DN", "DN")
```

In the semi-fast test, D is not a fast halt, so the section C→D is genuinely slow, and E and F inherit slow.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_corridors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.corridors'`

- [ ] **Step 3: Implement**

```python
# backend/app/services/corridors.py
"""Which pair of tracks a train uses at each of its stops, and which way
it is going there. Slow-only stations have platforms on the slow pair
alone, so a train that passes one without calling is on the fast pair."""

from __future__ import annotations

from collections.abc import Collection, Sequence

from app.services.platforms import Corridor, Direction


def stop_corridors(
    route_stations: Sequence[str],
    fast_halts: Collection[str],
    stops: Sequence[str],
    single_pair: Collection[str],
) -> tuple[Corridor, ...]:
    """The corridor each stop is reached on (the first stop: left on)."""
    index = {name: i for i, name in enumerate(route_stations)}
    sections: list[Corridor] = []
    previous: Corridor = "slow"
    for a, b in zip(stops, stops[1:], strict=False):
        lo, hi = sorted((index[a], index[b]))
        passed = route_stations[lo + 1 : hi]
        if any(name not in fast_halts for name in passed):
            corridor: Corridor = "fast"
        elif not passed and a in fast_halts and b in fast_halts:
            corridor = previous  # consecutive fast halts: stays on its pair
        else:
            corridor = "slow"
        sections.append(corridor)
        previous = corridor
    if not sections:
        return ("any",) * len(stops)
    per_stop = [sections[0], *sections]
    return tuple("any" if name in single_pair else c for name, c in zip(stops, per_stop, strict=True))


def stop_directions(direction: Direction, changes_at: str | None, stops: Sequence[str]) -> tuple[Direction, ...]:
    """The direction at each stop; it reverses after `changes_at`."""
    flipped: Direction = "DN" if direction == "UP" else "UP"
    result: list[Direction] = []
    passed_change = False
    for name in stops:
        result.append(flipped if passed_change else direction)
        if name == changes_at:
            passed_change = True
    return tuple(result)
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_corridors.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/corridors.py backend/tests/test_corridors.py
git commit -m "Work out each stop's track pair and direction from the timetable"
```

### Task 3: Geometry for pairing platforms with tracks

**Files:**
- Create: `backend/scripts/platform_geometry.py`
- Test: `backend/tests/test_platform_geometry.py`

All coordinates are local metres (east, north), the same projection as `build_osm_data.py`. Functions:

| Function | What it does |
|---|---|
| `track_corridor(name)` | `"fast"` if the name contains "fast", `"slow"` if it contains "slow", else `None` (case-insensitive). |
| `side_of(line, point, forward)` | `"left"` / `"right"` of `point` relative to `line` when travelling along it in the forward (`True`) or reverse direction. Uses the cross product with the nearest segment. |
| `platform_numbers(ref)` | Splits an OSM `ref` (`"4;5"`, `"4 - 5"`, `"2A;3"`, `"Platform 5,6"`) into numbers, and rejects station codes like `"CCG"`. |
| `left_track(tracks, forward, station_point)` | Of two parallel tracks, the one on the left when travelling forward: the track a forward train runs on, by left-hand running. |
| `adjacent_tracks(platform, tracks, max_gap_m=4.0)` | Tracks running within `max_gap_m` of the platform polygon's boundary. |

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_platform_geometry.py
import sys
from pathlib import Path

from shapely.geometry import LineString, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from platform_geometry import adjacent_tracks, left_track, platform_numbers, side_of, track_corridor  # noqa: E402

# Two tracks running north (increasing y), 5 m apart; x grows to the east.
WEST = LineString([(0, 0), (0, 300)])
EAST = LineString([(5, 0), (5, 300)])


def test_track_corridor_from_osm_names() -> None:
    assert track_corridor("Western Railway (Fast)") == "fast"
    assert track_corridor("Central Line (Slow)") == "slow"
    assert track_corridor("Mumbai-Pune Railway") is None
    assert track_corridor(None) is None


def test_side_of_depends_on_direction_of_travel() -> None:
    assert side_of(WEST, (-3, 150), forward=True) == "left"
    assert side_of(WEST, (-3, 150), forward=False) == "right"
    assert side_of(WEST, (3, 150), forward=True) == "right"


def test_platform_numbers_parse_osm_refs() -> None:
    assert platform_numbers("4;5") == ("4", "5")
    assert platform_numbers("4 - 5") == ("4", "5")
    assert platform_numbers("2A;3") == ("2A", "3")
    assert platform_numbers("Platform 5,6") == ("5", "6")
    assert platform_numbers("CCG") == ()
    assert platform_numbers(None) == ()


def test_left_hand_running_picks_the_west_track_going_north() -> None:
    assert left_track((WEST, EAST), forward=True, station_point=(2.5, 150)) is WEST
    assert left_track((WEST, EAST), forward=False, station_point=(2.5, 150)) is EAST


def test_adjacent_tracks_are_those_along_the_platform_edges() -> None:
    island = Polygon([(1.5, 100), (3.5, 100), (3.5, 200), (1.5, 200)])
    far = LineString([(30, 0), (30, 300)])
    assert set(map(id, adjacent_tracks(island, (WEST, EAST, far)))) == {id(WEST), id(EAST)}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_platform_geometry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'platform_geometry'`

- [ ] **Step 3: Implement**

```python
# backend/scripts/platform_geometry.py
"""Geometry for pairing OpenStreetMap platforms with the tracks beside
them. Coordinates are local metres (east, north)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from shapely.geometry import LineString, Point, Polygon

Side = Literal["left", "right"]

_NUMBER = re.compile(r"\b(\d{1,2}[A-Z]?)\b")


def track_corridor(name: str | None) -> Literal["slow", "fast"] | None:
    lowered = (name or "").lower()
    if "fast" in lowered:
        return "fast"
    if "slow" in lowered:
        return "slow"
    return None


def platform_numbers(ref: str | None) -> tuple[str, ...]:
    """Platform numbers in an OSM ref; station codes and prose give none."""
    return tuple(_NUMBER.findall((ref or "").upper()))


def side_of(line: LineString, point: tuple[float, float], forward: bool) -> Side:
    """Which side of `line` the point lies on, travelling along it
    (forward: in the order of its coordinates)."""
    p = Point(point)
    along = line.project(p)
    a = line.interpolate(max(along - 1.0, 0.0))
    b = line.interpolate(min(along + 1.0, line.length))
    cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
    left = cross > 0
    return "left" if left == forward else "right"


def left_track(tracks: Sequence[LineString], forward: bool, station_point: tuple[float, float]) -> LineString:
    """Of a pair of parallel tracks, the one a train travelling `forward`
    (in the first track's coordinate order) runs on: the left one."""
    reference = tracks[0]
    for track in tracks[1:]:
        if side_of(reference, _nearest_point(track, station_point), forward) == "left":
            return track
    return reference  # nothing lies to its left: it is the left one


def _nearest_point(track: LineString, point: tuple[float, float]) -> tuple[float, float]:
    nearest = track.interpolate(track.project(Point(point)))
    return (nearest.x, nearest.y)


def adjacent_tracks(platform: Polygon, tracks: Sequence[LineString], max_gap_m: float = 4.0) -> list[LineString]:
    edge = platform.exterior
    return [t for t in tracks if t.distance(edge) <= max_gap_m and t.intersection(platform.buffer(max_gap_m)).length > 10.0]
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && uv run pytest tests/test_platform_geometry.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/platform_geometry.py backend/tests/test_platform_geometry.py
git commit -m "Geometry for pairing OSM platforms with their tracks and door side"
```

### Task 4: Derive station tables from OSM

**Files:**
- Create: `backend/scripts/build_platforms.py`

The script reuses `build_osm_data.py`'s projection, cache and Overpass helper. Import them rather than copying:
- `overpass`
- the local projection helper (whatever `build_osm_data.py` uses to turn lat/lon into metres: find it with `grep -n "def .*project\|def to_local\|def local" backend/scripts/build_osm_data.py`)
- `keep_rail_way`
- `platform_polygons`

For each route in `network.json` and each station on it:

1. **Tracks.** Take every kept rail way within 250 m of the station whose direction is within 30° of the route's direction there. Classify each with `track_corridor(way name)`.
2. **Stop positions.** Fetch once with a new cache key, `stop_positions`:
   ```
   node["railway"="stop"](bbox); node["public_transport"="stop_position"]["train"="yes"](bbox); out tags;
   ```
   For each node within 400 m whose `ref` parses to exactly one number (`platform_numbers`), the track is the kept way containing that node id. That gives the pair (track, number).
3. **Platform polygons** (`platforms.json`) within 400 m, with a ref, handled by how many tracks are adjacent (`adjacent_tracks`):
   - **One adjacent track and one number:** pair them.
   - **Two adjacent tracks and two numbers:** pair each number with a track using the station's numbering order. Take the pairs already known from step 2, or from single-number platforms, and fit which lateral direction the numbers increase in. The lower number goes on that side. If no known pair exists, record the polygon as unresolved.
4. **Corridor of each paired track:**
   - the track's own `track_corridor`;
   - otherwise, if the station has only two through tracks, `"any"`;
   - otherwise unresolved.
5. **Direction of each paired track.** Group the tracks by corridor. Within a pair, `left_track(pair, forward=True, station)` is the track of forward trains. Forward means DN for every route except HR-PLGN (UP until Wadala Road). Use the route's `direction` mapping: add `ROUTE_FORWARD_DIRECTION = {"HR-PLGN": "UP"}`, defaulting to `"DN"`.
6. **Door side.** `side_of(track, platform centroid, forward=direction-is-forward)`. For stop positions without a polygon, use the nearest platform polygon to that stop node.
7. **Emit.** One `PlatformEntry`-shaped dict per (number, corridor, direction), with `role: "through"`, `certain: true`, `source: "osm"`. Numbers that share (corridor, direction) are merged into one entry.
8. **Report.** Record unresolved items per station for the report.

Output: `backend/data/platforms/derived.json`, keyed `"{line_code}|{station}"`. It is not committed; it's a build intermediate, so add it to `.gitignore`.

- [ ] **Step 1: Write the script** following the steps above.
  - Keep each step in its own function: `station_tracks`, `stop_position_pairs`, `polygon_pairs`, `classify`, `entries_for_station`.
  - Every function carries a docstring and type hints.
  - `main()` prints a coverage table: stations with both directions of every corridor resolved / partly / none.
- [ ] **Step 2: Run it offline.** It must not hit the network except once for `stop_positions`.

Run: `cd backend && uv run python scripts/build_platforms.py --derive-only`
Expected: coverage printed and `data/platforms/derived.json` written. The first run fetches `stop_positions.json` into `.osm-cache/`.

- [ ] **Step 3: Spot-check against known layouts.** Andheri WR must come out as:
  - slow DN 3, slow UP 5, fast DN 6, fast UP 7.

  Dadar WR must come out as:
  - slow DN 1, slow UP 2, fast DN 3 and 5, fast UP 4.

Run: `cd backend && uv run python -c "import json; d=json.load(open('data/platforms/derived.json')); print(d['WR|Andheri']); print(d['WR|Dadar'])"`
Expected: exactly the platforms above, with door sides. If not, fix the derivation, not the expectation. These layouts are confirmed by two independent sources.

- [ ] **Step 4: Commit**

```bash
echo "backend/data/platforms/derived.json" >> .gitignore
git add .gitignore backend/scripts/build_platforms.py
git commit -m "Derive each station's platforms and door sides from OpenStreetMap"
```

### Task 5: Curated overrides, merge, and the generated table

**Files:**
- Create: `backend/data/platforms/curated.json`
- Modify: `backend/scripts/build_platforms.py` (add the merge and write step)
- Create (generated): `backend/app/data/generated/platforms.json`

`curated.json` entries replace a derived station **wholesale**. There's no per-entry merging, so a curated station reads as exactly what the source says:

```json
{
  "stations": [
    {
      "line_code": "WR",
      "station": "Churchgate",
      "source": "https://en.wikipedia.org/wiki/Churchgate_railway_station (infobox, retrieved 2026-09-25)",
      "platforms": [
        {"numbers": ["1", "2"], "corridor": "slow", "direction": "DN", "role": "originating", "door": null, "certain": false},
        {"numbers": ["3", "4"], "corridor": "fast", "direction": "DN", "role": "originating", "door": null, "certain": false},
        {"numbers": ["1", "2"], "corridor": "slow", "direction": "UP", "role": "terminating", "door": null, "certain": false},
        {"numbers": ["3", "4"], "corridor": "fast", "direction": "UP", "role": "terminating", "door": null, "certain": false}
      ]
    }
  ]
}
```

Curate these, from the sources the research found:

| Station | Source | Entries |
|---|---|---|
| WR Churchgate | Wikipedia infobox | as above |
| WR Dadar | Wikipedia table | P1 slow DN, P2 slow UP, P3 and P5 fast DN, P4 fast UP; all through, certain |
| CR Dadar | Mumbai Live 2023 and FPJ 2024 renumbering, where they override Wikipedia | P8 slow DN, P9 slow UP, P9A and P11 fast DN, P12 fast UP |
| WR Andheri | Wikipedia table | through: P3 slow DN, P5 slow UP, P6 fast DN, P7 fast UP; originating: P4 slow UP, P8–9 fast UP (certain false) |
| HR Andheri | Wikipedia table | P1 terminating (from CSMT/Panvel, DN), P2 UP |
| CR Kalyan | Wikipedia | P4 and P6 fast DN, P5 and P7 fast UP; originating slow UP 1, 1A (certain false) |
| CR Kanjurmarg | Wikipedia | 1 and 1A DN, 2 UP (slow) |
| HR Wadala Road | Wikipedia | 1 DN (both branches), 4 UP, 2–3 originating or terminating (certain false) |
| THR / HR Vashi, Sanpada, Juinagar, Nerul, CBD Belapur, Kharghar, Mansarovar, Khandeshwar | Wikipedia text | as quoted in the research report; direction per the text |
| HR CSMT | FPJ 2022, Deccan Herald | 1–2, originating DN and terminating UP, certain false |
| CR CSMT | No open source for the slow/fast split of 3–7 | 3–7 for both corridors, originating DN and terminating UP, certain false. Refine when a source appears. |
| THR Thane | Trans-Harbour line article | 9–10, originating DN (towards Vashi/Panvel) and terminating UP, certain false |

Stations with no data anywhere (Virar, Govandi, Malad, Kandivali, Nallasopara, Mumbra) are listed in the report and left without entries. Their stops show no platform rather than a guess.

**Generated file shape** (`backend/app/data/generated/platforms.json`):

```json
{
  "generated_at": "2026-09-25T00:00:00+00:00",
  "attribution": "© OpenStreetMap contributors (ODbL); curated entries cite their sources in backend/data/platforms/curated.json",
  "single_pair": [["CR", "Titwala"], ["HR", "Vadala Road"]],
  "stations": [
    {"line_code": "WR", "station": "Andheri", "source": "osm", "platforms": [{"numbers": ["3"], "corridor": "slow", "direction": "DN", "role": "through", "door": "left", "certain": true}]}
  ]
}
```

`single_pair` lists the (line, station) pairs where the build found one pair of through tracks. Task 6's corridor derivation reads it. Add it to `PlatformTable` in `app/services/platforms.py`:

```python
    single_pair: frozenset[tuple[str, str]]
```

Load it with `frozenset((line, name) for line, name in raw["single_pair"])`, and update Task 1's loader and the `PlatformTable` construction accordingly.

- [ ] **Step 1:** Write `curated.json` with the entries in the table. Every station gets its `source`.
- [ ] **Step 2:** Add the merge in `build_platforms.py`:
  1. derived dict;
  2. replaced by curated stations;
  3. sorted by line then route order;
  4. written with `generated_at`, `attribution`, `single_pair` and `stations`.
- [ ] **Step 3: Run it.**

Run: `cd backend && uv run python scripts/build_platforms.py`
Expected: `app/data/generated/platforms.json` written, and the coverage table printed again, now including curated stations.

- [ ] **Step 4: Commit**

```bash
git add backend/data/platforms/curated.json backend/scripts/build_platforms.py backend/app/data/generated/platforms.json backend/app/services/platforms.py
git commit -m "Curate platforms where OpenStreetMap has none, and write the platform table"
```

### Task 6: Data checks over the real timetable

**Files:**
- Create: `backend/tests/test_platform_data.py`

These tests guard the generated data the way `test_network_data.py` guards `network.json`.

- [ ] **Step 1: Write the tests**

```python
# backend/tests/test_platform_data.py
from app.services.platforms import load_platform_table
from app.services.timetable import load_timetable

KNOWN = {
    ("WR", "Andheri", "slow", "DN"): ("3",),
    ("WR", "Andheri", "slow", "UP"): ("5",),
    ("WR", "Andheri", "fast", "DN"): ("6",),
    ("WR", "Andheri", "fast", "UP"): ("7",),
    ("WR", "Dadar", "slow", "DN"): ("1",),
    ("WR", "Dadar", "slow", "UP"): ("2",),
    ("WR", "Dadar", "fast", "UP"): ("4",),
}


def test_known_layouts_are_exact() -> None:
    table = load_platform_table()
    for (line, station, corridor, direction), numbers in KNOWN.items():
        through = [
            e
            for e in table.entries(line, station)
            if e.role == "through" and e.corridor == corridor and e.direction == direction
        ]
        assert [e.numbers for e in through] == [numbers], (line, station, corridor, direction)


def test_most_stops_have_a_platform() -> None:
    stops = [stop for train in load_timetable().trains for stop in train.stops]
    with_platform = sum(1 for stop in stops if stop.platform is not None)
    assert with_platform / len(stops) >= 0.85


def test_through_stops_are_mostly_certain() -> None:
    timetable = load_timetable()
    through = [s for t in timetable.trains for s in t.stops[1:-1] if s.platform is not None]
    certain = sum(1 for s in through if s.platform.certain)
    assert certain / len(through) >= 0.8


def test_every_platform_has_numbers() -> None:
    for entries in load_platform_table().stations.values():
        assert all(entry.numbers for entry in entries)
```

- [ ] **Step 2: Run them.** They'll fail on `stop.platform` until Task 7 lands, so commit them together with Task 7.

Run: `cd backend && uv run pytest tests/test_platform_data.py -q`
Expected: FAIL with `AttributeError: 'TimetableStop' object has no attribute 'platform'`

## Phase 2: backend

### Task 7: Attach platforms to timetabled stops

**Files:**
- Modify: `backend/app/services/timetable.py:41-65` (dataclasses) and `:124-167` (`load_timetable`)
- Test: `backend/tests/test_platform_data.py` (from Task 6)

- [ ] **Step 1: Extend the dataclasses**

```python
@dataclass(frozen=True, slots=True)
class TimetableStop:
    station_name: str
    station_id: str
    arrival_min: int
    departure_min: int
    # Where it calls, if the station's platforms are known.
    platform: PlatformAssignment | None = None
```

Add these to `TimetabledTrain`, after `direction_forward`:

```python
    # "UP" towards CSMT/Churchgate, "DN" away; reverses after
    # direction_changes_at (Panvel - Wadala Road - Goregaon workings).
    direction: Direction = "DN"
    direction_changes_at: str | None = None
```

Import `PlatformAssignment`, `Direction`, `resolve_platform` and `load_platform_table` from `app.services.platforms`, and `stop_corridors` and `stop_directions` from `app.services.corridors`.

- [ ] **Step 2: Resolve per stop in `load_timetable`.** After fitting the route, before building the `TimetabledTrain`:

```python
        platforms = load_platform_table()
        route_names = [station.name for station in route.stations]
        fast_halts = {station.name for station in route.stations if station.fast_halt}
        single_pair = {name for line, name in platforms.single_pair if line == line_code}
        corridors = stop_corridors(route_names, fast_halts, names, single_pair)
        directions = stop_directions(entry["direction"], entry["direction_changes_at"], names)
        last = len(names) - 1
        stop_platforms = [
            resolve_platform(
                platforms.entries(line_code, name),
                corridor=corridors[i],
                direction=directions[i],
                role="originating" if i == 0 else "terminating" if i == last else "through",
            )
            for i, name in enumerate(names)
        ]
```

Pass `direction=entry["direction"]` and `direction_changes_at=entry["direction_changes_at"]` into `TimetabledTrain`, and `platform=stop_platforms[i]` into each `TimetableStop`. Build the stops with `enumerate(entry["stops"])`.

- [ ] **Step 3: Run the data checks and the full suite**

Run: `cd backend && uv run pytest -q`
Expected: all pass, including `test_platform_data.py`.
- If `test_most_stops_have_a_platform` fails, the coverage report from Task 4 says which stations to curate. Add them to `curated.json` and rebuild; don't lower the threshold.
- If `test_through_stops_are_mostly_certain` fails, check how often stops fall back to the other corridor, and review `stop_corridors` against a few real fast trains before touching data.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/timetable.py backend/tests/test_platform_data.py
git commit -m "Give every timetabled stop its platform and door side"
```

### Task 8: Carry platforms into run plans and the API

**Files:**
- Modify: `backend/app/services/simulator/schedule.py` (`ScheduledStop`, `timetable_run_plan`)
- Modify: `backend/app/schemas/train.py`, `backend/app/schemas/journey.py`
- Modify: `backend/app/services/timeline.py`, `backend/app/services/position_processor.py:170-195`, `backend/app/services/journey_planner.py:92-108`
- Test: `backend/tests/test_timeline.py`, `test_journey_planner.py`, `test_live_wire.py`, `test_position_processor.py`

- [ ] **Step 1: Schemas**

```python
# backend/app/schemas/train.py
DoorSide = Literal["left", "right", "both"]


class PlatformOut(BaseModel):
    numbers: list[str]
    # Side of the train the platform is on, facing the way it travels.
    door: DoorSide | None
    # False: it varies from train to train here, so show "usually".
    certain: bool
```

On `StopTime`, add:

```python
    platform: PlatformOut | None = None
```

On `TrainPositionUpdate`, after `next_station`, add scalar fields (the live table only carries scalars):

```python
    # The next stop's platform numbers, comma-separated ("3", "5,6,7").
    next_platform: str | None = None
    next_platform_certain: bool = False
    next_platform_door: DoorSide | None = None
```

On `JourneyOption` in `backend/app/schemas/journey.py`:

```python
    board_platform: PlatformOut | None = None
    alight_platform: PlatformOut | None = None
```

Add a converter to `app/services/platforms.py`:

```python
def platform_out(assignment: PlatformAssignment | None) -> PlatformOut | None:
    if assignment is None:
        return None
    return PlatformOut(numbers=list(assignment.numbers), door=assignment.door, certain=assignment.certain)
```

Import `PlatformOut` inside the module with `from app.schemas.train import PlatformOut`. `app.schemas.train` must not import `app.services`, which keeps the dependency one-way.

- [ ] **Step 2: Failing tests**

```python
# append to backend/tests/test_timeline.py
from app.services.platforms import PlatformAssignment


def test_timeline_carries_each_stops_platform(network) -> None:
    context = network.place("T1", "WR-VR", "SLOW", forward=True, at_fraction=0.3, delay_s=0.0)
    stop = context.run.plan.stops[2]
    object.__setattr__(stop, "platform", PlatformAssignment(numbers=("3",), door="left", certain=True))
    timeline = build_timeline(context)
    assert timeline[2].platform is not None
    assert timeline[2].platform.numbers == ["3"]
    assert timeline[2].platform.door == "left"
```

Check `tests/conftest.py`'s `Network.place` for its exact signature and return value, and adapt the call. The point of the test is that `build_timeline` copies `ScheduledStop.platform` through `platform_out`.

```python
# append to backend/tests/test_live_wire.py
def test_snapshot_table_has_next_platform_columns(evening_trains) -> None:
    from app.services.live_wire import SNAPSHOT_FIELDS

    assert {"next_platform", "next_platform_certain", "next_platform_door"} <= set(SNAPSHOT_FIELDS)
```

```python
# append to backend/tests/test_journey_planner.py: find the existing test that plans a WR trip
# between two stations with known platforms (e.g. Dadar -> Andheri) and assert:
#     assert option.board_platform is not None and option.board_platform.numbers
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd backend && uv run pytest tests/test_timeline.py tests/test_live_wire.py tests/test_journey_planner.py -q`
Expected: FAIL on the new assertions.

- [ ] **Step 4: Implement**
  - **`ScheduledStop`:** add `platform: PlatformAssignment | None = None`. In `timetable_run_plan`, pass `platform=train.stops[0].platform` for the first stop and `platform=stop.platform` in the loop.
  - **`build_timeline`:** `platform=platform_out(stop.platform)`.
  - **`position_processor`:** when building `TrainPositionUpdate`:

    ```python
            next_platform = next_stop.platform if next_stop is not None else None
    ```

    and pass:

    ```python
            next_platform=",".join(next_platform.numbers) if next_platform is not None else None,
            next_platform_certain=next_platform.certain if next_platform is not None else False,
            next_platform_door=next_platform.door if next_platform is not None else None,
    ```
  - **`journey_planner`:** `board_platform=platform_out(train.stops[board].platform)`, `alight_platform=platform_out(train.stops[alight].platform)`.

- [ ] **Step 5: Run the whole suite and lint**

Run: `cd backend && uv run ruff check . && uv run pytest -q`
Expected: `All checks passed!` and all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests
git commit -m "Send platforms and door sides with stops, journeys and live trains"
```

## Phase 3: frontend

### Task 9: Types and the formatting helper

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/platform.ts`, `frontend/lib/platform.test.ts`

The formatting rules:
- **Numbers.** Runs of consecutive plain numbers compress with an en dash ("5–7"). Otherwise they are joined with ", " ("1, 1A").
- **Certain:** "PF 3".
- **Not certain:** "Usually PF 5–7".
- **Door:** "Doors left", "Doors right", or "Doors both sides". Nothing when unknown.

- [ ] **Step 1: Types.** In `frontend/lib/types.ts`:

```ts
export type DoorSide = "left" | "right" | "both";

export interface Platform {
  numbers: string[];
  door: DoorSide | null;
  certain: boolean;
}
```

- Add `platform?: Platform | null;` to `StopTime`.
- Add `board_platform?: Platform | null; alight_platform?: Platform | null;` to `JourneyOption`.
- Add these to `TrainPositionUpdate`:

  ```ts
  next_platform: string | null;
  next_platform_certain: boolean;
  next_platform_door: DoorSide | null;
  ```

- [ ] **Step 2: Failing tests**

```ts
// frontend/lib/platform.test.ts
import { describe, expect, it } from "vitest";
import { doorLabel, livePlatform, platformLabel } from "./platform";

describe("platformLabel", () => {
  it("names a single certain platform", () => {
    expect(platformLabel({ numbers: ["3"], door: "left", certain: true })).toBe("PF 3");
  });
  it("compresses consecutive platforms and says usually when uncertain", () => {
    expect(platformLabel({ numbers: ["5", "6", "7"], door: null, certain: false })).toBe("Usually PF 5–7");
  });
  it("lists platforms that don't run on", () => {
    expect(platformLabel({ numbers: ["1", "1A", "4"], door: null, certain: false })).toBe("Usually PF 1, 1A, 4");
  });
});

describe("doorLabel", () => {
  it("says which side the doors open", () => {
    expect(doorLabel("left")).toBe("Doors left");
    expect(doorLabel("both")).toBe("Doors both sides");
    expect(doorLabel(null)).toBeNull();
  });
});

describe("livePlatform", () => {
  it("rebuilds a platform from the live table's columns", () => {
    expect(livePlatform("5,6", false, "right")).toEqual({ numbers: ["5", "6"], door: "right", certain: false });
    expect(livePlatform(null, false, null)).toBeNull();
  });
});
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd frontend && npm run test -- lib/platform.test.ts`
Expected: FAIL, "Failed to resolve import ./platform"

- [ ] **Step 4: Implement**

```ts
// frontend/lib/platform.ts
// How a train's platform reads: "PF 3", or "Usually PF 5–7" where it
// varies from train to train, and which side its doors open.

import type { DoorSide, Platform } from "./types";

function numberRuns(numbers: readonly string[]): string {
  const parts: string[] = [];
  let i = 0;
  while (i < numbers.length) {
    let j = i;
    while (
      j + 1 < numbers.length &&
      /^\d+$/.test(numbers[j]!) &&
      /^\d+$/.test(numbers[j + 1]!) &&
      Number(numbers[j + 1]) === Number(numbers[j]) + 1
    ) {
      j++;
    }
    parts.push(j - i >= 2 ? `${numbers[i]}–${numbers[j]}` : numbers.slice(i, j + 1).join(", "));
    i = j + 1;
  }
  return parts.join(", ");
}

export function platformLabel(platform: Platform): string {
  const label = `PF ${numberRuns(platform.numbers)}`;
  return platform.certain ? label : `Usually ${label}`;
}

export function doorLabel(door: DoorSide | null): string | null {
  if (door === null) return null;
  return door === "both" ? "Doors both sides" : `Doors ${door}`;
}

/** The next stop's platform from the live table's scalar columns. */
export function livePlatform(numbers: string | null, certain: boolean, door: DoorSide | null): Platform | null {
  if (numbers === null || numbers === "") return null;
  return { numbers: numbers.split(","), door, certain };
}
```

Two numbers in a run ("5, 6") stay listed; three or more compress ("5–7").

- [ ] **Step 5: Run the tests**

Run: `cd frontend && npm run test -- lib/platform.test.ts`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/platform.ts frontend/lib/platform.test.ts
git commit -m "Format platforms and door sides for the app"
```

### Task 10: Decode the new live columns, tolerating an older backend

**Files:**
- Modify: `frontend/lib/liveWire.ts`

The backend (Render) and frontend (Vercel) deploy separately. Until Render has the new columns, the decoder must not throw.

- [ ] **Step 1:** Add `"next_platform", "next_platform_certain", "next_platform_door"` to `TRAIN_FIELDS`, so the compile-time completeness check passes.
- [ ] **Step 2:** Add an optional-field default map, and use it in `decodeSnapshot` so a missing optional column decodes to its default instead of throwing:

```ts
// Columns added after the first release: an older server doesn't send
// them yet, so they decode to these instead of failing the snapshot.
const OPTIONAL_DEFAULTS: Partial<Record<TrainField, SnapshotCell>> = {
  next_platform: null,
  next_platform_certain: false,
  next_platform_door: null,
};
```

  In the missing-column check at line 73, skip fields in `OPTIONAL_DEFAULTS`. When building each train, fill a missing optional field from `OPTIONAL_DEFAULTS`. Read the current `decodeSnapshot` and follow its structure: it builds an index per field, so a missing optional field has index `-1`, which should read as the default.
- [ ] **Step 3: Check.** Run `npx tsc --noEmit`, `npm run lint` and `npm run test`. All must pass.
- [ ] **Step 4: Commit**

```bash
git add frontend/lib/liveWire.ts
git commit -m "Decode the next stop's platform from the live feed, tolerating older servers"
```

### Task 11: Show platforms in the app

**Files:**
- Modify: `frontend/components/screens/TrainDetailsScreen.tsx` (`Timeline` 182–232, `StatusBadge` 142–149)
- Modify: `frontend/components/screens/FollowScreen.tsx` (Next card 88–101)
- Modify: `frontend/components/ui/NextStationPin.tsx` (57–60)
- Modify: `frontend/components/screens/JourneyScreen.tsx` (`JourneyOptionRow` 208–221)
- Modify: `frontend/hooks/useArrivalAlerts.ts` (46–49)

Design:
- A platform shows as a small chip matching the existing status badge: `rounded-full border px-2 py-0.5 text-[11.5px] font-medium tabular-nums`.
  - **Certain:** `border-primary/40 text-primary`.
  - **"Usually":** `border-ink-600 text-fg-muted`.
- The door side is secondary text in `text-fg-subtle`.
- No icons. Keep rows single-line; truncate the station name, not the chip.

- [ ] **Step 1: Timeline row.**
  - After the `{detail}` span, add, when `stop.platform` exists:

    ```tsx
    <span className={`ml-auto shrink-0 rounded-full border px-2 py-0.5 text-[11.5px] font-medium tabular-nums ${stop.platform.certain ? "border-primary/40 text-primary" : "border-ink-600 text-fg-muted"}`}>
      {platformLabel(stop.platform)}
    </span>
    ```

  - For the current and next stop only, append the door side under the name: `text-[11.5px] text-fg-subtle`, `doorLabel(stop.platform.door)`.
  - The `"at_platform"` detail becomes `At ${platformLabel(stop.platform)}` when known ("At PF 3").
- [ ] **Step 2: Status badge.**
  - "At platform" becomes "At PF 3" when the current stop's platform is certain.
  - It stays "At platform" otherwise, since "At usually PF…" reads badly.
- [ ] **Step 3: Follow screen Next card.**
  - Build `const platform = livePlatform(train.next_platform, train.next_platform_certain, train.next_platform_door)`.
  - Under the ETA line, add `{platform && <span className="block text-[12px] text-fg-muted">{[platformLabel(platform), doorLabel(platform.door)].filter(Boolean).join(" · ")}</span>}`.
- [ ] **Step 4: Next-station pin.** Append `· PF 3` to the distance line when the platform is certain. Uncertain platforms stay off the 3D pin to keep it short.
- [ ] **Step 5: Journey option row.**
  - Append `{" · "}{platformLabel(option.board_platform)}` to the second line when present.
  - Under the right-hand times, add the alighting side: `doorLabel(option.alight_platform?.door ?? null)` in `text-[11.5px] text-fg-subtle`. This is m-Indicator's "which door to get out of".
- [ ] **Step 6: Arrival alert.** "Arriving at Andheri in 2 min" becomes "Arriving at Andheri in 2 min · PF 3 · Doors left" when certain.
- [ ] **Step 7: Checks**

Run: `cd frontend && npm run lint && npx tsc --noEmit && npm run test && npm run build`
Expected: all pass.

- [ ] **Step 8: Browser verification** (built-in browser, dev servers on 3010 and 8000; start them with `preview_start` if they aren't running):
  - follow a WR slow train through Andheri and check "PF 3 · Doors left" or "PF 5 · …" against the table;
  - open a train starting at Churchgate and check "Usually PF 1–2" or "Usually PF 3–4" at the first stop;
  - plan Dadar → Andheri and check the boarding platform and door side;
  - no console errors;
  - screenshot each.
- [ ] **Step 9: Commit**

```bash
git add frontend/components frontend/hooks
git commit -m "Show each stop's platform and door side, like the station boards"
```

## Final verification

- [ ] Backend: `uv run ruff check . && uv run pytest -q`: clean.
- [ ] Frontend: `npm run lint && npx tsc --noEmit && npm run test && npm run build`: clean.
- [ ] Coverage report from `scripts/build_platforms.py` saved in the PR description: stations fully, partly and not covered, and the list still needing sources.
- [ ] Push to `development`; open the PR to `main` only when the user asks.

## Known limits (tell the user)

- **Scheduled platforms only.** Day-of platform changes need live data we don't have.
- **Termini.** Platforms at CSMT, Churchgate, Virar, Kalyan (originating) and similar read "Usually …". CSMT's main-line split across 3–7 has no open source yet.
- **Stations with no data** (Virar, Govandi, Malad, Kandivali, Nallasopara, Mumbra) show no platform until a source is found.
- **Door side** is geometric (which side of the track the platform lies). At island platforms that's exact; where OSM platform polygons are missing it is omitted rather than guessed.
