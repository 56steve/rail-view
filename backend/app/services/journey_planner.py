"""Journey planning over the official timetable.

For a from/to station pair, finds every timetabled train that calls at
both, in that order, and leaves the boarding station within the next few
hours - including trains that haven't started their run yet. Trains that
are running have their current delay applied to both ends of the trip;
the rest are shown at their timetabled times. Journeys needing a change
get an interchange hint instead of a multi-leg itinerary.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping

from app.data.mumbai_network import load_lines, load_routes
from app.schemas.journey import JourneyOption, JourneyPlan, JourneySort
from app.schemas.station import StationIndexEntry
from app.services.position_processor import TrainContext
from app.services.station_index import route_station_ids, station_index
from app.services.timetable import (
    Timetable,
    TimetabledTrain,
    service_dates_near,
    service_midnight_epoch,
)

MAX_OPTIONS = 8
# Trains leaving the boarding station further ahead than this aren't
# offered: a commuter plans the next train or two, not tomorrow's.
PLANNING_HORIZON_S = 3 * 3600.0
# A train that left the boarding station this recently is still listed
# (the commuter may be on the platform as it pulls out) - no longer.
MISSED_GRACE_S = 30.0
# Upper bound on how late a running train can be; timetabled departures
# further in the past than this can't still be ahead.
MAX_CONSIDERED_DELAY_S = 3600.0


class UnknownStationError(LookupError):
    pass


def plan_journey(
    from_id: str,
    to_id: str,
    sort: JourneySort,
    timetable: Timetable,
    contexts: Mapping[str, TrainContext],
    live_train_ids: Collection[str],
    now_epoch: float,
) -> JourneyPlan:
    index = station_index()
    for station_id in (from_id, to_id):
        if station_id not in index:
            raise UnknownStationError(station_id)
    origin, destination = index[from_id], index[to_id]

    options: list[JourneyOption] = []
    if from_id != to_id:
        lines = load_lines()
        routes = load_routes()
        for service_date in service_dates_near(now_epoch):
            midnight = service_midnight_epoch(service_date)
            for train in timetable.trains:
                if not train.runs_on(service_date):
                    continue
                trip = _trip(train, from_id, to_id)
                if trip is None:
                    continue
                board, alight = trip
                board_scheduled = midnight + train.stops[board].departure_min * 60.0
                if board_scheduled > now_epoch + PLANNING_HORIZON_S:
                    continue
                if board_scheduled < now_epoch - MISSED_GRACE_S - MAX_CONSIDERED_DELAY_S:
                    continue

                context = contexts.get(train.number)
                run_start = midnight + train.first_departure_min * 60.0
                live = (
                    train.number in live_train_ids
                    and context is not None
                    and abs(context.run.started_at_epoch - run_start) < 1.0
                )
                delay_s = context.delay_s if live and context is not None else 0.0
                board_expected = board_scheduled + delay_s
                if board_expected < now_epoch - MISSED_GRACE_S:
                    continue  # already gone
                alight_expected = max(midnight + train.stops[alight].arrival_min * 60.0 + delay_s, board_expected)
                route = routes[train.route_code]
                options.append(
                    JourneyOption(
                        train_id=train.number,
                        train_type="FAST" if train.fast else "SLOW",
                        service_code=train.code,
                        ac=train.ac_on(service_date),
                        line_code=train.line_code,
                        line_name=lines[train.line_code].name,
                        route_code=route.code,
                        direction_label=f"{train.stops[0].station_name} → {train.stops[-1].station_name}",
                        is_live=live,
                        board_scheduled_epoch=board_scheduled,
                        board_expected_epoch=board_expected,
                        alight_expected_epoch=alight_expected,
                        duration_seconds=alight_expected - board_expected,
                        delay_seconds=round(delay_s),
                        intermediate_stops=alight - board - 1,
                    )
                )

    if sort == "fastest":
        # Fastest to arrive, among trains leaving soon enough to matter.
        options.sort(key=lambda o: (o.alight_expected_epoch, o.board_expected_epoch))
    else:
        options.sort(key=lambda o: (o.board_expected_epoch, o.alight_expected_epoch))

    return JourneyPlan(
        from_station=origin,
        to_station=destination,
        sort=sort,
        options=options[:MAX_OPTIONS],
        interchange_hint=_interchange_hint(origin, destination, index),
    )


def _trip(train: TimetabledTrain, from_id: str, to_id: str) -> tuple[int, int] | None:
    """Stop indices where `train` can be boarded at `from_id` and left at
    `to_id`, if it calls at both in that order."""
    board = alight = None
    for i, stop in enumerate(train.stops):
        if stop.station_id == from_id:
            board = i
        elif stop.station_id == to_id and board is not None:
            alight = i
            break
    if board is None or alight is None:
        return None
    return board, alight


def _interchange_hint(
    origin: StationIndexEntry, destination: StationIndexEntry, index: Mapping[str, StationIndexEntry]
) -> str | None:
    """Where to change when no single route calls at both stations - which
    covers different lines (Thane to Bandra) and different branches of one
    line (Titwala on the Kasara branch to Badlapur on the Khopoli branch)."""
    members = route_station_ids()
    if any(origin.id in ids and destination.id in ids for ids in members.values()):
        return None

    def distance(a: StationIndexEntry, b: StationIndexEntry) -> float:
        return math.hypot(a.lat - b.lat, (a.lon - b.lon) * math.cos(math.radians(a.lat)))

    from_routes = [code for code, ids in members.items() if origin.id in ids]
    to_routes = [code for code, ids in members.items() if destination.id in ids]
    best: tuple[float, StationIndexEntry, str, str] | None = None
    for station in index.values():
        for from_code in from_routes:
            if station.id not in members[from_code]:
                continue
            for to_code in to_routes:
                if station.id not in members[to_code]:
                    continue
                detour = distance(origin, station) + distance(station, destination)
                if best is None or detour < best[0]:
                    best = (detour, station, from_code, to_code)
    if best is None:
        return "No direct train between these stations"

    routes = load_routes()
    _, station, from_code, to_code = best
    from_line, to_line = routes[from_code].line, routes[to_code].line
    if from_line.code == to_line.code:
        branch_end = routes[to_code].stations[-1].name
        return f"No direct train - change at {station.name} for the {branch_end} branch"
    return f"No direct train - change at {station.name} ({from_line.name} to {to_line.name} line)"
