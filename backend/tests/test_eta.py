import pytest

from app.services.eta import MINIMUM_ETA_SPEED_KMH, compute_delay_seconds, compute_eta_seconds


def test_positive_delay_means_running_late() -> None:
    assert compute_delay_seconds(actual_elapsed_s=300, scheduled_elapsed_s=240) == 60


def test_negative_delay_means_running_early() -> None:
    assert compute_delay_seconds(actual_elapsed_s=200, scheduled_elapsed_s=240) == -40


def test_eta_uses_actual_speed_when_above_floor() -> None:
    # 60 km/h = ~16.67 m/s; 1000m away -> 60s
    eta = compute_eta_seconds(distance_to_next_station_m=1000, current_speed_kmh=60)
    assert eta == pytest.approx(60.0, rel=0.01)


def test_eta_floors_speed_when_train_is_stopped() -> None:
    eta_stopped = compute_eta_seconds(distance_to_next_station_m=1000, current_speed_kmh=0)
    eta_at_floor = compute_eta_seconds(distance_to_next_station_m=1000, current_speed_kmh=MINIMUM_ETA_SPEED_KMH)
    assert eta_stopped == pytest.approx(eta_at_floor)


def test_eta_for_zero_distance_is_zero() -> None:
    assert compute_eta_seconds(distance_to_next_station_m=0, current_speed_kmh=50) == 0
