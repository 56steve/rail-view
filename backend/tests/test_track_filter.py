import random

import pytest

from app.services.track_filter import MEASUREMENT_SIGMA_M, TrackFilter


def run_filter(true_positions: list[float], seed: int = 3) -> TrackFilter:
    rng = random.Random(seed)
    f = TrackFilter.start(true_positions[0] + rng.gauss(0, MEASUREMENT_SIGMA_M), 0.0)
    for t, s in enumerate(true_positions[1:], start=1):
        f.update(s + rng.gauss(0, MEASUREMENT_SIGMA_M), float(t))
    return f


def test_stationary_train_reads_near_zero_speed_despite_gps_noise() -> None:
    f = run_filter([1000.0] * 60)
    assert abs(f.velocity_m_s) * 3.6 < 5
    assert f.chainage_m == pytest.approx(1000, abs=4)


def test_moving_train_speed_converges() -> None:
    speed = 15.0  # 54 km/h
    f = run_filter([500 + speed * t for t in range(60)])
    assert f.velocity_m_s == pytest.approx(speed, abs=1.5)


def test_filtered_position_is_less_noisy_than_raw_fixes() -> None:
    rng = random.Random(9)
    f = TrackFilter.start(0.0, 0.0)
    filtered_errors, raw_errors = [], []
    for t in range(1, 200):
        truth = 12.0 * t
        measured = truth + rng.gauss(0, MEASUREMENT_SIGMA_M)
        f.update(measured, float(t))
        if t > 20:
            filtered_errors.append(abs(f.chainage_m - truth))
            raw_errors.append(abs(measured - truth))
    assert sum(filtered_errors) < 0.7 * sum(raw_errors)


def test_direction_is_the_sign_of_velocity() -> None:
    f = run_filter([5000 - 12.0 * t for t in range(30)])
    assert f.velocity_m_s < 0
