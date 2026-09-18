"""Geographic <-> local planar coordinate conversion.

GPS-to-track matching needs a locally-flat (Euclidean) coordinate system:
projecting a point onto a line and measuring distance-along-line is only
meaningful in a system where distances are actually in metres, which raw
lat/lon degrees are not (a degree of longitude shrinks as latitude grows).

We use a simple equirectangular (azimuthal) approximation around a fixed
origin. Mumbai spans roughly 19.0-19.3 deg N, so the whole Central Line
MVP corridor is under 20km from the origin - well within the range where
this approximation's error stays under a metre, which is more than
sufficient for track-matching and visualization purposes. A production
system covering the full multi-city network would switch to a proper
projected CRS (e.g. UTM zone 43N, EPSG:32643) via PostGIS ST_Transform;
this module's interface (`to_local` / `to_latlon`) is intentionally the
seam where that swap would happen.

The frontend's `lib/geo.ts` mirrors this exact formula (same ORIGIN
constant, same scale) so a chainage/lat-lon position computed here lands
in the identical spot in the Three.js scene without the backend needing to
know anything about scene units.
"""

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000.0

# Fixed local-projection origin: Thane station. Must match
# frontend/lib/geo.ts ORIGIN exactly.
ORIGIN_LAT = 19.1868
ORIGIN_LON = 72.9750

_ORIGIN_LAT_RAD = math.radians(ORIGIN_LAT)


@dataclass(frozen=True, slots=True)
class LocalPoint:
    """Planar coordinates in metres, relative to ORIGIN. x = east, y = north."""

    x: float
    y: float


def to_local(lat: float, lon: float) -> LocalPoint:
    """Convert WGS84 lat/lon (degrees) to local planar metres."""
    x = math.radians(lon - ORIGIN_LON) * math.cos(_ORIGIN_LAT_RAD) * EARTH_RADIUS_M
    y = math.radians(lat - ORIGIN_LAT) * EARTH_RADIUS_M
    return LocalPoint(x=x, y=y)


def to_latlon(point: LocalPoint) -> tuple[float, float]:
    """Inverse of `to_local`. Returns (lat, lon) in degrees."""
    lat = ORIGIN_LAT + math.degrees(point.y / EARTH_RADIUS_M)
    lon = ORIGIN_LON + math.degrees(point.x / (EARTH_RADIUS_M * math.cos(_ORIGIN_LAT_RAD)))
    return lat, lon


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres. Used where exact geodesic distance
    matters more than planar-projection speed (e.g. total route length
    sanity checks), independent of the local-projection approximation.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))
