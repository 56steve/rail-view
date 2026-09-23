"""Speed profile shared by the simulator and the timetable builders.

Both sides must use the exact same profile: the simulator moves trains
with it, and the run plans integrate it to know when a train is due at
any point - including *within* a leg, since trains cover the first and
last few hundred metres of a leg much more slowly than the middle. If the
two diverged, a train running exactly to plan would read as early or late
mid-leg, and "delay" would reflect a modelling mismatch instead of the
dwell and speed variation it's meant to represent.

Every speed in the profile is the cruise speed times a factor that depends
only on distances, so time along a leg scales exactly with 1 / cruise. The
profile is therefore tabulated once per leg length at unit cruise, and a
leg's cruise speed can be solved directly from how long the timetable
gives it.
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
    """Cumulative run time along one halt-to-halt leg at unit cruise speed
    (1 m/s), tabulated so any intermediate point's time is a lookup."""

    def __init__(self, length_m: float) -> None:
        self.length_m = length_m
        self._distances = [0.0]
        self._times = [0.0]
        covered = elapsed = 0.0
        while covered < length_m:
            dx = min(_TABLE_STEP_M, length_m - covered)
            mid = covered + dx / 2
            elapsed += dx / profile_speed_m_s(mid, length_m - mid, 1.0)
            covered += dx
            self._distances.append(covered)
            self._times.append(elapsed)

    @property
    def unit_total_s(self) -> float:
        return self._times[-1]

    def unit_time_at(self, distance_m: float) -> float:
        if distance_m <= 0:
            return 0.0
        if distance_m >= self.length_m:
            return self.unit_total_s
        i = bisect_right(self._distances, distance_m)
        d0, d1 = self._distances[i - 1], self._distances[i]
        t0, t1 = self._times[i - 1], self._times[i]
        return t0 + (t1 - t0) * (distance_m - d0) / (d1 - d0)

    def distance_at_unit_time(self, unit_time_s: float) -> float:
        if unit_time_s <= 0:
            return 0.0
        if unit_time_s >= self.unit_total_s:
            return self.length_m
        i = bisect_right(self._times, unit_time_s)
        t0, t1 = self._times[i - 1], self._times[i]
        d0, d1 = self._distances[i - 1], self._distances[i]
        return d0 + (d1 - d0) * (unit_time_s - t0) / (t1 - t0)


@lru_cache(maxsize=8192)
def leg_profile(length_m: float) -> LegProfile:
    return LegProfile(length_m)


def leg_run_time_s(leg_m: float, cruise_m_s: float) -> float:
    """Seconds to run a whole leg of `leg_m` at `cruise_m_s`."""
    return leg_profile(leg_m).unit_total_s / cruise_m_s


def leg_time_at_s(leg_m: float, cruise_m_s: float, distance_m: float) -> float:
    """Seconds to reach `distance_m` into a leg of `leg_m` at `cruise_m_s`."""
    return leg_profile(leg_m).unit_time_at(distance_m) / cruise_m_s


def leg_distance_at_m(leg_m: float, cruise_m_s: float, elapsed_s: float) -> float:
    """How far into a leg of `leg_m` a train running at `cruise_m_s` is,
    `elapsed_s` after departing."""
    return leg_profile(leg_m).distance_at_unit_time(elapsed_s * cruise_m_s)


def cruise_for_leg_time(leg_m: float, run_time_s: float) -> float:
    """The cruise speed that runs a leg of `leg_m` in exactly `run_time_s`."""
    if run_time_s <= 0:
        raise ValueError(f"a leg needs a positive run time, got {run_time_s}")
    return leg_profile(leg_m).unit_total_s / run_time_s
