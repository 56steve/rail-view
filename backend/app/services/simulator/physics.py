"""Speed profile shared by the simulator and the timetable builder.

Both sides must use the exact same profile: the simulator moves trains
with it, and `schedule.build_run_plan` integrates it to produce the
timetable - including *within* a leg, since trains cover the first and
last few hundred metres of a leg much more slowly than the middle. If the
two diverged, a train running exactly to plan would read as early or late
mid-leg, and "delay" would reflect a modelling mismatch instead of the
dwell/speed variation it's meant to represent.
"""

from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache

ACCEL_DISTANCE_M = 250.0
BRAKE_DISTANCE_M = 300.0
MIN_SPEED_FRACTION = 0.12
_TABLE_STEP_M = 2.0


def profile_speed_m_s(since_last_stop_m: float, to_next_stop_m: float, cruise_m_s: float) -> float:
    """Target speed for a train `since_last_stop_m` past its last halt and
    `to_next_stop_m` short of its next one: linear ramp up after
    departing, linear ramp down approaching the halt, cruise in between.
    """
    speed = cruise_m_s
    if to_next_stop_m < BRAKE_DISTANCE_M:
        speed = min(speed, cruise_m_s * max(MIN_SPEED_FRACTION, to_next_stop_m / BRAKE_DISTANCE_M))
    if since_last_stop_m < ACCEL_DISTANCE_M:
        speed = min(speed, cruise_m_s * max(MIN_SPEED_FRACTION, since_last_stop_m / ACCEL_DISTANCE_M))
    return speed


class LegProfile:
    """Cumulative run time along one halt-to-halt leg, tabulated so any
    intermediate point's timetabled time is a cheap lookup."""

    def __init__(self, length_m: float, cruise_m_s: float) -> None:
        self.length_m = length_m
        self._distances = [0.0]
        self._times = [0.0]
        covered = elapsed = 0.0
        while covered < length_m:
            dx = min(_TABLE_STEP_M, length_m - covered)
            mid = covered + dx / 2
            elapsed += dx / profile_speed_m_s(mid, length_m - mid, cruise_m_s)
            covered += dx
            self._distances.append(covered)
            self._times.append(elapsed)

    @property
    def total_s(self) -> float:
        return self._times[-1]

    def time_at(self, distance_m: float) -> float:
        """Timetabled seconds to reach `distance_m` into the leg."""
        if distance_m <= 0:
            return 0.0
        if distance_m >= self.length_m:
            return self.total_s
        i = bisect_right(self._distances, distance_m)
        d0, d1 = self._distances[i - 1], self._distances[i]
        t0, t1 = self._times[i - 1], self._times[i]
        return t0 + (t1 - t0) * (distance_m - d0) / (d1 - d0)


@lru_cache(maxsize=4096)
def leg_profile(length_m: float, cruise_m_s: float) -> LegProfile:
    return LegProfile(length_m, cruise_m_s)


def leg_run_time_s(leg_m: float, cruise_m_s: float) -> float:
    return leg_profile(leg_m, cruise_m_s).total_s
