"""Direct-train journey planning over the live network.

For a from/to station pair, finds every live train whose current run
halts at both, in that order, and hasn't yet passed the boarding
station - with boarding and arrival times estimated from the timetable
plus each train's current delay. Journeys needing a change of line get an
interchange hint instead of a full multi-leg itinerary.
"""

import math
from collections.abc import Collection, Mapping

from app.data.mumbai_network import load_routes
from app.schemas.journey import JourneyOption, JourneyPlan, JourneySort
from app.schemas.station import StationIndexEntry
from app.services.position_processor import TrainContext
from app.services.station_index import route_station_ids, station_id_for_name, station_index

MAX_OPTIONS = 8


class UnknownStationError(LookupError):
    pass


def plan_journey(
    from_id: str,
    to_id: str,
    sort: JourneySort,
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
        for train_id, context in contexts.items():
            if train_id in live_train_ids:
                option = _option_for(train_id, context, from_id, to_id, now_epoch)
                if option is not None:
                    options.append(option)

    if sort == "fastest":
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


def _option_for(
    train_id: str, context: TrainContext, from_id: str, to_id: str, now_epoch: float
) -> JourneyOption | None:
    plan = context.run.plan
    board_index = alight_index = None
    for i, stop in enumerate(plan.stops):
        station_id = station_id_for_name(stop.station.station.name)
        if station_id == from_id:
            board_index = i
        elif station_id == to_id:
            alight_index = i
    if board_index is None or alight_index is None or alight_index < board_index:
        return None

    board, alight = plan.stops[board_index], plan.stops[alight_index]
    if context.has_passed(board):
        return None

    board_at = max(context.expected_epoch(board), now_epoch)
    alight_at = max(context.expected_epoch(alight), board_at)
    return JourneyOption(
        train_id=train_id,
        train_type=plan.train_type,
        line_code=plan.line_code,
        line_name=context.route.seed.line.name,
        route_code=plan.route_code,
        direction_label=f"{plan.origin.station.name} → {plan.destination.station.name}",
        board_expected_epoch=board_at,
        alight_expected_epoch=alight_at,
        duration_seconds=alight_at - board_at,
        delay_seconds=round(context.delay_s),
        intermediate_stops=alight_index - board_index - 1,
    )


def _interchange_hint(
    origin: StationIndexEntry, destination: StationIndexEntry, index: Mapping[str, StationIndexEntry]
) -> str | None:
    """Where to change when no single route calls at both stations - which
    covers different lines (Thane to Bandra) and different branches of one
    line (Titwala on the Kasara branch to Badlapur on the Karjat branch)."""
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
