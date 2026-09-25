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
    # (line_code, station_name) pairs where the line has only one pair of
    # through tracks: every stop there is corridor "any".
    single_pair: frozenset[tuple[str, str]]

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
    single_pair = frozenset((line, name) for line, name in raw["single_pair"])
    return PlatformTable(stations=stations, attribution=raw["attribution"], single_pair=single_pair)
