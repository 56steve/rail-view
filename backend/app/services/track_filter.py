"""1-D constant-velocity Kalman filter along the track.

Differencing consecutive track-matched fixes is not usable as a speed:
along-track GPS noise of ~6m per fix turns into ~30 km/h of phantom speed
at a 1s update rate, so a train standing at a platform would appear to
move and a moving train's speed would swing wildly. Filtering chainage
with a constant-velocity model gives a smooth position (what the client
renders) and a stable speed/direction estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

# Along-track GPS measurement noise (m, 1 sigma) - matches the jitter the
# simulator injects and typical consumer GPS.
MEASUREMENT_SIGMA_M = 6.0
# How hard a train can plausibly accelerate/brake (m/s^2, 1 sigma).
ACCELERATION_SIGMA = 0.6
INITIAL_SPEED_SIGMA_M_S = 20.0


@dataclass(slots=True)
class TrackFilter:
    chainage_m: float
    velocity_m_s: float
    timestamp_s: float
    # Covariance matrix [[p00, p01], [p01, p11]].
    p00: float
    p01: float
    p11: float

    @classmethod
    def start(cls, chainage_m: float, timestamp_s: float) -> TrackFilter:
        return cls(
            chainage_m=chainage_m,
            velocity_m_s=0.0,
            timestamp_s=timestamp_s,
            p00=MEASUREMENT_SIGMA_M**2,
            p01=0.0,
            p11=INITIAL_SPEED_SIGMA_M_S**2,
        )

    def update(self, measured_chainage_m: float, timestamp_s: float) -> None:
        dt = max(timestamp_s - self.timestamp_s, 1e-3)

        # Predict (constant velocity, white-noise acceleration).
        s = self.chainage_m + self.velocity_m_s * dt
        v = self.velocity_m_s
        q = ACCELERATION_SIGMA**2
        p00 = self.p00 + 2 * dt * self.p01 + dt * dt * self.p11 + q * dt**4 / 4
        p01 = self.p01 + dt * self.p11 + q * dt**3 / 2
        p11 = self.p11 + q * dt**2

        # Update with the measured chainage.
        innovation = measured_chainage_m - s
        residual_var = p00 + MEASUREMENT_SIGMA_M**2
        k0, k1 = p00 / residual_var, p01 / residual_var
        self.chainage_m = s + k0 * innovation
        self.velocity_m_s = v + k1 * innovation
        self.p00 = (1 - k0) * p00
        self.p01 = (1 - k0) * p01
        self.p11 = p11 - k1 * p01
        self.timestamp_s = timestamp_s
