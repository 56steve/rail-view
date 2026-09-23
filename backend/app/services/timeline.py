"""Per-train stop timeline: every halt of the current run with its state
and the best available time (observed arrival, or expected given the
current delay)."""

from app.schemas.train import StopState, StopTime
from app.services.position_processor import TrainContext, station_out


def build_timeline(context: TrainContext) -> list[StopTime]:
    stops: list[StopTime] = []
    for stop in context.run.plan.stops:
        code = stop.station.station.code
        observed = context.observed_arrivals.get(code)
        scheduled = context.published_epoch(stop)

        state: StopState
        if stop is context.current_stop:
            state = "at_platform"
        elif stop is context.next_stop:
            state = "next"
        elif context.has_passed(stop):
            state = "departed"
        else:
            state = "upcoming"

        if state in ("departed", "at_platform"):
            # Passed before we started tracking this train: the observed
            # time is genuinely unknown, so fall back to the timetable.
            expected = observed if observed is not None else scheduled
        else:
            expected = max(scheduled + context.delay_s, context.updated_at_epoch)

        stops.append(
            StopTime(
                station=station_out(stop.station),
                state=state,
                scheduled_epoch=scheduled,
                expected_epoch=expected,
                observed_arrival_epoch=observed,
            )
        )
    return stops
