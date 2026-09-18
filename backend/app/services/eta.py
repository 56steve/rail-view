"""Pure functions for delay and ETA arithmetic, kept separate from the
position processor so they're trivially unit-testable without any track
or telemetry setup.
"""

MINIMUM_ETA_SPEED_KMH = 15.0


def compute_delay_seconds(actual_elapsed_s: float, scheduled_elapsed_s: float) -> float:
    """Positive => running behind the timetable. Negative => ahead of it."""
    return actual_elapsed_s - scheduled_elapsed_s


def compute_eta_seconds(distance_to_next_station_m: float, current_speed_kmh: float) -> float:
    """Time to cover the remaining distance to the next station.

    Falls back to a floor speed when the train is stopped/crawling so a
    dwelling train doesn't report an infinite ETA.
    """
    effective_kmh = max(current_speed_kmh, MINIMUM_ETA_SPEED_KMH)
    speed_m_s = effective_kmh * 1000 / 3600
    return max(distance_to_next_station_m, 0.0) / speed_m_s
