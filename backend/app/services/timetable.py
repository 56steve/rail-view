"""The official suburban timetable, fitted onto RailView's routes.

`timetable.json` is imported from the Pocket Time Tables Central and
Western Railway publish (see scripts/import_timetables.py). Each train
there is a list of stations and times; here every train is placed on the
route it runs along, in the direction it runs, so the rest of the system
can simulate it on real track and plan journeys with it.

Times in the timetable are minutes after midnight of the service day, in
Mumbai time; a train that runs past midnight has times of 1440 and more.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args
from zoneinfo import ZoneInfo

from app.data.mumbai_network import RouteSeed, load_routes
from app.services.corridors import stop_corridors, stop_directions
from app.services.holidays import runs_sunday_schedule
from app.services.platforms import (
    Corridor,
    Direction,
    PlatformAssignment,
    StopRole,
    load_platform_table,
    resolve_platform,
)
from app.services.station_index import station_id_for_name

TIMETABLE_JSON = Path(__file__).resolve().parents[1] / "data" / "generated" / "timetable.json"
MUMBAI = ZoneInfo("Asia/Kolkata")

# The timetable's own line names, to RailView line codes.
LINE_CODES = {"main": "CR", "harbour": "HR", "transharbour": "THR", "western": "WR"}

Days = Literal["all", "not_sunday", "weekdays", "sunday_only"]


class TimetableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TimetableStop:
    station_name: str
    station_id: str
    arrival_min: int
    departure_min: int
    # Where it calls, if the station's platforms are known.
    platform: PlatformAssignment | None = None


@dataclass(frozen=True, slots=True)
class TimetabledTrain:
    number: str
    code: str | None
    line_code: str
    route_code: str
    # Along the route's station order (towards its last station).
    direction_forward: bool
    # "UP" towards CSMT/Churchgate, "DN" away; reverses after
    # direction_changes_at (Panvel - Wadala Road - Goregaon workings).
    direction: Direction
    # Passes at least one station of its route between its first and last
    # stop without calling there.
    fast: bool
    ac: bool
    non_ac_at_weekends: bool
    cars: int
    days: Days
    ladies_special: bool
    stops: tuple[TimetableStop, ...]
    direction_changes_at: str | None = None

    @property
    def first_departure_min(self) -> int:
        return self.stops[0].departure_min

    @property
    def last_arrival_min(self) -> int:
        return self.stops[-1].arrival_min

    def runs_on(self, service_date: date) -> bool:
        """Whether this train runs on `service_date`. Sundays and the
        listed holidays (app.services.holidays) run the Sunday schedule."""
        if self.days == "all":
            return True
        sunday_schedule = runs_sunday_schedule(service_date)
        if self.days == "not_sunday":
            return not sunday_schedule
        if self.days == "weekdays":
            return service_date.weekday() < 5 and not sunday_schedule
        return sunday_schedule

    def ac_on(self, service_date: date) -> bool:
        return self.ac and not (self.non_ac_at_weekends and service_date.weekday() >= 5)


@dataclass(frozen=True, slots=True)
class Timetable:
    trains: tuple[TimetabledTrain, ...]
    # Train numbers in the source that run beyond RailView's routes.
    unplaced: tuple[str, ...]

    def by_number(self) -> dict[str, TimetabledTrain]:
        return {train.number: train for train in self.trains}


def _fit(stop_names: list[str], line_code: str, routes: Iterable[RouteSeed]) -> tuple[RouteSeed, bool] | None:
    """The first route of the train's line that calls at every stop in
    order, and whether the train runs along or against it."""
    for route in routes:
        if route.line.code != line_code:
            continue
        index = {station.name: i for i, station in enumerate(route.stations)}
        if not all(name in index for name in stop_names):
            continue
        positions = [index[name] for name in stop_names]
        if positions == sorted(positions) and len(set(positions)) == len(positions):
            return route, True
        if positions == sorted(positions, reverse=True) and len(set(positions)) == len(positions):
            return route, False
    return None


def _skips_a_station(route: RouteSeed, stop_names: list[str]) -> bool:
    index = {station.name: i for i, station in enumerate(route.stations)}
    positions = [index[name] for name in stop_names]
    return abs(positions[-1] - positions[0]) + 1 > len(positions)


def _single_pair_by_line(single_pair: frozenset[tuple[str, str]]) -> dict[str, frozenset[str]]:
    """`single_pair` grouped by line, computed once for the whole
    timetable rather than once per train."""
    grouped: dict[str, set[str]] = defaultdict(set)
    for line, name in single_pair:
        grouped[line].add(name)
    return {line: frozenset(names) for line, names in grouped.items()}


_VALID_DIRECTIONS = frozenset(get_args(Direction))


@lru_cache
def load_timetable(path: Path = TIMETABLE_JSON) -> Timetable:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise TimetableError(f"{path} is missing - run `uv run python scripts/import_timetables.py`") from exc

    routes = list(load_routes().values())
    platforms = load_platform_table()
    single_pair_by_line = _single_pair_by_line(platforms.single_pair)
    # (line, station, corridor, direction, role) -> resolved platform.
    # ~51,000 stops in the real timetable resolve to a much smaller set of
    # distinct keys, so caching here turns load_timetable from O(stops)
    # platform resolutions into roughly O(distinct keys).
    platform_cache: dict[tuple[str, str, Corridor, Direction, StopRole], PlatformAssignment | None] = {}

    def resolve_cached(
        line_code: str, station: str, corridor: Corridor, direction: Direction, role: StopRole
    ) -> PlatformAssignment | None:
        key = (line_code, station, corridor, direction, role)
        if key not in platform_cache:
            platform_cache[key] = resolve_platform(
                platforms.entries(line_code, station), corridor=corridor, direction=direction, role=role
            )
        return platform_cache[key]

    trains: list[TimetabledTrain] = []
    unplaced: list[str] = []
    for entry in raw["trains"]:
        line_code = LINE_CODES.get(entry["line"])
        if line_code is None:
            raise TimetableError(f"train {entry['number']}: unknown line {entry['line']!r}")
        direction = entry.get("direction")
        if direction not in _VALID_DIRECTIONS:
            raise TimetableError(f"train {entry['number']}: invalid direction {direction!r}")
        names = [stop[0] for stop in entry["stops"]]
        fitted = _fit(names, line_code, routes)
        if fitted is None:
            unplaced.append(entry["number"])
            continue
        route, forward = fitted

        route_names = [station.name for station in route.stations]
        fast_halts = {station.name for station in route.stations if station.fast_halt}
        single_pair = single_pair_by_line.get(line_code, frozenset())
        try:
            corridors = stop_corridors(route_names, fast_halts, names, single_pair)
            directions = stop_directions(direction, entry["direction_changes_at"], names)
        except ValueError as exc:
            raise TimetableError(f"train {entry['number']}: {exc}") from exc
        last = len(names) - 1
        stop_platforms = [
            resolve_cached(
                line_code,
                name,
                corridors[i],
                directions[i],
                "originating" if i == 0 else "terminating" if i == last else "through",
            )
            for i, name in enumerate(names)
        ]

        trains.append(
            TimetabledTrain(
                number=entry["number"],
                code=entry["code"],
                line_code=line_code,
                route_code=route.code,
                direction_forward=forward,
                direction=direction,
                fast=_skips_a_station(route, names),
                ac=entry["ac"],
                non_ac_at_weekends=entry["non_ac_at_weekends"],
                cars=entry["cars"],
                days=entry["days"],
                ladies_special=entry["ladies_special"],
                direction_changes_at=entry["direction_changes_at"],
                stops=tuple(
                    TimetableStop(
                        station_name=name,
                        station_id=station_id_for_name(name),
                        arrival_min=arrival,
                        departure_min=departure,
                        platform=stop_platforms[i],
                    )
                    for i, (name, arrival, departure) in enumerate(entry["stops"])
                ),
            )
        )
    return Timetable(trains=tuple(trains), unplaced=tuple(unplaced))


def service_midnight_epoch(service_date: date) -> float:
    """Unix time of midnight, Mumbai time, starting `service_date`."""
    return datetime.combine(service_date, time(0), tzinfo=MUMBAI).timestamp()


def service_dates_near(epoch: float) -> tuple[date, date, date]:
    """Yesterday, today and tomorrow in Mumbai at `epoch`: a train from
    yesterday's service may still be running after midnight, and a
    journey planned late at night may take tomorrow's first trains."""
    today = datetime.fromtimestamp(epoch, tz=MUMBAI).date()
    return today - timedelta(days=1), today, today + timedelta(days=1)
