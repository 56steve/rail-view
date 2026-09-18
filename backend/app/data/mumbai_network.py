"""Static seed geometry for the Mumbai suburban railway network.

MVP scope covers the Central Line between Thane and Dadar only. The data
model below (``LineSeed`` / ``StationSeed``) is deliberately line-agnostic
so the Western, Harbour, and Trans-Harbour lines can be added as additional
``LineSeed`` entries in ``RAILWAY_LINES`` without touching any downstream
code (track matching, simulator, API routes, or the frontend).

IMPORTANT - data provenance:
Station coordinates here are approximate, sourced from general public
geographic knowledge, NOT a surveyed feed. They are accurate enough to
demonstrate GPS-to-track matching and 3D visualization, but MUST be
replaced with authoritative geometry (an official GTFS feed from Indian
Railways/CRIS, or OpenStreetMap `railway=rail` way data for the Central
Line) before this is used for real commuter-facing ETAs. The track
polyline is a straight-line interpolation between consecutive stations,
not the true curved track centerline - also a placeholder for real
survey/OSM geometry.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StationSeed:
    code: str
    name: str
    lat: float
    lon: float
    sequence: int  # position along the line, 0 = the "up" terminus (Thane)


@dataclass(frozen=True, slots=True)
class LineSeed:
    code: str
    name: str
    color_hex: str
    stations: tuple[StationSeed, ...]


CENTRAL_LINE = LineSeed(
    code="CR",
    name="Central Line",
    color_hex="#E0483C",
    stations=(
        StationSeed("TNA", "Thane", 19.1868, 72.9750, 0),
        StationSeed("MUL", "Mulund", 19.1726, 72.9425, 1),
        StationSeed("NHU", "Nahur", 19.1567, 72.9494, 2),
        StationSeed("BND", "Bhandup", 19.1487, 72.9367, 3),
        StationSeed("KJMG", "Kanjurmarg", 19.1294, 72.9370, 4),
        StationSeed("VK", "Vikhroli", 19.1097, 72.9270, 5),
        StationSeed("GC", "Ghatkopar", 19.0863, 72.9081, 6),
        StationSeed("VVH", "Vidyavihar", 19.0768, 72.8981, 7),
        StationSeed("KRL", "Kurla", 19.0728, 72.8826, 8),
        StationSeed("CHF", "Chunabhatti", 19.0524, 72.8776, 9),
        StationSeed("SIN", "Sion", 19.0448, 72.8619, 10),
        StationSeed("MTN", "Matunga", 19.0272, 72.8555, 11),
        StationSeed("DR", "Dadar", 19.0186, 72.8440, 12),
    ),
)

# Registry of every line the network supports. Only CR is populated for the
# MVP; WR / HR / THR are added here once their station geometry is sourced.
RAILWAY_LINES: dict[str, LineSeed] = {
    CENTRAL_LINE.code: CENTRAL_LINE,
}

DEFAULT_ROUTE_ID = "CR-thane-dadar"
