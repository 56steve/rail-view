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
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal, get_args

Corridor = Literal["slow", "fast", "any"]
Direction = Literal["UP", "DN"]
StopRole = Literal["originating", "through", "terminating"]
DoorSide = Literal["left", "right", "both"]

_CORRIDORS = frozenset(get_args(Corridor))
_DIRECTIONS = frozenset(get_args(Direction))
_ROLES = frozenset(get_args(StopRole))
_DOORS = frozenset(get_args(DoorSide))

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
    cover this direction.

    Search order: the stop's own role on its own corridor; "through" on
    its own corridor; the stop's own role on the other corridor;
    "through" on the other corridor. The first step with any entries
    wins - a fast train's originating platform must never fall back to
    the slow platform just because the slow side happens to have a
    role-specific entry and the fast side doesn't. Only a match for the
    stop's own role on its own corridor can be certain: a train starting
    or ending at a station may use a bay rather than the through
    platform, and once it's off its usual corridor nothing is certain.
    """
    facing = [e for e in entries if e.direction == direction]

    def own_corridor(entry: PlatformEntry) -> bool:
        return corridor == "any" or entry.corridor in (corridor, "any")

    role_entries = [e for e in facing if e.role == role]
    through_entries = [e for e in facing if e.role == "through"]
    steps: tuple[tuple[bool, list[PlatformEntry]], ...] = (
        (True, [e for e in role_entries if own_corridor(e)]),
        (role == "through", [e for e in through_entries if own_corridor(e)]),
        (False, [e for e in role_entries if not own_corridor(e)]),
        (False, [e for e in through_entries if not own_corridor(e)]),
    )
    matches: list[PlatformEntry] = []
    certain_eligible = False
    for eligible, candidates in steps:
        if candidates:
            matches, certain_eligible = candidates, eligible
            break
    if not matches:
        return None
    numbers = tuple(sorted({n for e in matches for n in e.numbers}, key=_platform_order))
    doors = {e.door for e in matches}
    return PlatformAssignment(
        numbers=numbers,
        door=doors.pop() if len(doors) == 1 else None,
        certain=certain_eligible and len(matches) == 1 and matches[0].certain,
    )


@dataclass(frozen=True, slots=True)
class PlatformTable:
    # A read-only view: the table is shared across callers via lru_cache.
    stations: Mapping[tuple[str, str], tuple[PlatformEntry, ...]]
    attribution: str
    # (line_code, station_name) pairs where the line has only one pair of
    # through tracks: every stop there is corridor "any".
    single_pair: frozenset[tuple[str, str]]

    def entries(self, line_code: str, station_name: str) -> tuple[PlatformEntry, ...]:
        return self.stations.get((line_code, station_name), ())


def _require(value: object, valid: frozenset[str], field: str, station_key: tuple[str, str]) -> None:
    if value not in valid:
        raise PlatformDataError(f"{station_key}: invalid {field} {value!r}")


def _parse_entry(entry: object, station_key: tuple[str, str]) -> PlatformEntry:
    if not isinstance(entry, dict):
        raise PlatformDataError(f"{station_key}: platform entry must be an object, got {entry!r}")
    try:
        raw_numbers = entry["numbers"]
        corridor = entry["corridor"]
        direction = entry["direction"]
        role = entry["role"]
        door = entry["door"]
        certain = entry["certain"]
    except (KeyError, TypeError) as exc:
        raise PlatformDataError(f"{station_key}: malformed platform entry ({exc})") from exc
    # A bare string (e.g. "10") is iterable character-by-character, which
    # would silently turn one platform number into several: reject it.
    if (
        not isinstance(raw_numbers, list)
        or not raw_numbers
        or not all(isinstance(n, str) for n in raw_numbers)
    ):
        raise PlatformDataError(
            f"{station_key}: numbers must be a non-empty list of strings, got {raw_numbers!r}"
        )
    numbers = tuple(raw_numbers)
    _require(corridor, _CORRIDORS, "corridor", station_key)
    _require(direction, _DIRECTIONS, "direction", station_key)
    _require(role, _ROLES, "role", station_key)
    if door is not None:
        _require(door, _DOORS, "door", station_key)
    if not isinstance(certain, bool):
        raise PlatformDataError(f"{station_key}: certain must be a bool, got {certain!r}")
    return PlatformEntry(
        numbers=numbers,
        corridor=corridor,
        direction=direction,
        role=role,
        door=door,
        certain=certain,
    )


@lru_cache
def load_platform_table(path: Path = PLATFORMS_JSON) -> PlatformTable:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise PlatformDataError(f"{path} is missing - run `uv run python scripts/build_platforms.py`") from exc
    except json.JSONDecodeError as exc:
        raise PlatformDataError(f"{path} is not valid JSON: {exc}") from exc

    try:
        station_list = raw["stations"]
        attribution = raw["attribution"]
        single_pair_raw = raw["single_pair"]
    except (KeyError, TypeError) as exc:
        raise PlatformDataError(f"{path}: malformed platform table ({exc})") from exc

    stations: dict[tuple[str, str], tuple[PlatformEntry, ...]] = {}
    for station in station_list:
        try:
            key = (station["line_code"], station["station"])
            platforms = station["platforms"]
            stations[key] = tuple(_parse_entry(entry, key) for entry in platforms)
        except (KeyError, TypeError) as exc:
            raise PlatformDataError(f"{path}: malformed station entry ({exc})") from exc

    try:
        single_pair = frozenset((line, name) for line, name in single_pair_raw)
    except (TypeError, ValueError) as exc:
        raise PlatformDataError(f"{path}: malformed single_pair ({exc})") from exc

    return PlatformTable(
        stations=MappingProxyType(stations), attribution=attribution, single_pair=single_pair
    )
