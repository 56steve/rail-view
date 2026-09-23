"""Curated network definitions: lines, the routes trains run on within
each line, and which stations each route calls at, in travel order.

This is the one hand-maintained input to `build_osm_data.py`. Station
*positions* and *track geometry* come from OpenStreetMap; membership and
order come from here because OSM route relations for the Mumbai suburban
network are incomplete and inconsistently ordered.

A line (Central, Western...) is what commuters and the UI talk about. A
route is one end-to-end path trains actually run on: the Central line
forks at Kalyan, so it has a Kasara route and a Karjat route that share
track up to Kalyan. Short workings (e.g. CSMT-Thane) are runs over part
of a route, not routes of their own.

`ref` values are the Indian Railways station codes as tagged on the OSM
station element, which is how the build script finds each station.

Fast-halt flags are the core halts of fast services and are approximate:
individual fast workings vary, which per-train timetable data captures.
Beyond Kalyan every Central local, fast or slow, calls at every station.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StationDef:
    ref: str
    name: str
    fast_halt: bool = False
    osm_id: str | None = None
    override_latlon: tuple[float, float] | None = None
    override_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RouteDef:
    code: str
    stations: tuple[StationDef, ...]


@dataclass(frozen=True, slots=True)
class LineDef:
    code: str
    name: str
    color_hex: str
    routes: tuple[RouteDef, ...]


WESTERN = LineDef(
    code="WR",
    name="Western",
    color_hex="#8B7CF6",
    routes=(
        RouteDef(
            code="WR-BVI",
            stations=(
                StationDef("CCG", "Churchgate", fast_halt=True),
                StationDef("MEL", "Marine Lines"),
                StationDef("CYR", "Charni Road"),
                StationDef("GTR", "Grant Road"),
                StationDef("MMCT", "Mumbai Central", fast_halt=True),
                StationDef("MX", "Mahalaxmi"),
                StationDef("PL", "Lower Parel"),
                StationDef("PBHD", "Prabhadevi"),
                StationDef("DDR", "Dadar", fast_halt=True),
                StationDef("MRU", "Matunga Road"),
                StationDef("MM", "Mahim"),
                StationDef("BA", "Bandra", fast_halt=True),
                StationDef("KHAR", "Khar Road"),
                StationDef("STC", "Santacruz"),
                StationDef("VLP", "Vile Parle"),
                StationDef("ADH", "Andheri", fast_halt=True),
                # OSM tags both the Western and Harbour platforms at
                # Jogeshwari with ref JOS, so the Western one is pinned.
                StationDef("JOS", "Jogeshwari", osm_id="node/12189363305"),
                StationDef("RMAR", "Ram Mandir"),
                StationDef("GMN", "Goregaon"),
                StationDef("MDD", "Malad"),
                StationDef("KILE", "Kandivali"),
                StationDef("BVI", "Borivali", fast_halt=True),
            ),
        ),
    ),
)

_CENTRAL_TO_KALYAN = (
    StationDef("CSMT", "CSMT", fast_halt=True),
    StationDef("MSD", "Masjid"),
    StationDef("SNRD", "Sandhurst Road"),
    StationDef("BY", "Byculla", fast_halt=True),
    StationDef("CHG", "Chinchpokli"),
    StationDef("CRD", "Currey Road"),
    StationDef("PR", "Parel"),
    StationDef("DR", "Dadar", fast_halt=True),
    StationDef("MTN", "Matunga"),
    StationDef("SIN", "Sion"),
    StationDef("CLA", "Kurla"),
    StationDef("VVH", "Vidyavihar"),
    StationDef("GC", "Ghatkopar", fast_halt=True),
    StationDef("VK", "Vikhroli"),
    StationDef("KJRD", "Kanjurmarg"),
    StationDef("BND", "Bhandup"),
    StationDef("NHU", "Nahur"),
    StationDef("MLND", "Mulund", fast_halt=True),
    StationDef("TNA", "Thane", fast_halt=True),
    StationDef("KLVA", "Kalva"),
    StationDef("MBQ", "Mumbra"),
    StationDef("DIVA", "Diva"),
    StationDef("KOPR", "Kopar"),
    StationDef("DI", "Dombivli", fast_halt=True),
    StationDef("THK", "Thakurli"),
    StationDef("KYN", "Kalyan", fast_halt=True),
)

CENTRAL = LineDef(
    code="CR",
    name="Central",
    color_hex="#4C8DFF",
    routes=(
        RouteDef(
            code="CR-KSRA",
            stations=(
                *_CENTRAL_TO_KALYAN,
                StationDef("SHAD", "Shahad", fast_halt=True),
                StationDef("ABY", "Ambivli", fast_halt=True),
                StationDef("TLA", "Titwala", fast_halt=True),
                StationDef("KDV", "Khadavli", fast_halt=True),
                StationDef("VSD", "Vasind", fast_halt=True),
                StationDef("ASO", "Asangaon", fast_halt=True),
                StationDef("ATG", "Atgaon", fast_halt=True),
                StationDef("THS", "Thansit", fast_halt=True),
                StationDef("KE", "Khardi", fast_halt=True),
                StationDef("OMB", "Umbermali", fast_halt=True),
                StationDef("KSRA", "Kasara", fast_halt=True),
            ),
        ),
        RouteDef(
            code="CR-KJT",
            stations=(
                *_CENTRAL_TO_KALYAN,
                StationDef("VLDI", "Vithalwadi", fast_halt=True),
                StationDef("ULNR", "Ulhasnagar", fast_halt=True),
                StationDef("ABH", "Ambarnath", fast_halt=True),
                StationDef("BUD", "Badlapur", fast_halt=True),
                StationDef("VGI", "Vangani", fast_halt=True),
                StationDef("SHLU", "Shelu", fast_halt=True),
                StationDef("NRL", "Neral", fast_halt=True),
                StationDef("BVS", "Bhivpuri Road", fast_halt=True),
                StationDef("KJT", "Karjat", fast_halt=True),
            ),
        ),
    ),
)

HARBOUR = LineDef(
    code="HR",
    name="Harbour",
    color_hex="#2BC4A4",
    routes=(
        RouteDef(
            code="HR-VSH",
            stations=(
                StationDef("CSMT", "CSMT"),
                StationDef("MSD", "Masjid"),
                StationDef("SNRD", "Sandhurst Road"),
                StationDef("DKRD", "Dockyard Road"),
                StationDef("RRD", "Reay Road"),
                StationDef("CTGN", "Cotton Green"),
                StationDef("SVE", "Sewri"),
                StationDef(
                    "VDLR",
                    "Wadala Road",
                    override_latlon=(19.0170, 72.8589),
                    override_reason=(
                        "Not tagged as a railway station in OSM; positioned beside "
                        "the adjacent Wadala Bridge monorail stop and snapped to the "
                        "Harbour track."
                    ),
                ),
                StationDef("GTBN", "GTB Nagar"),
                StationDef("CHF", "Chunabhatti"),
                StationDef("CLA", "Kurla"),
                StationDef("TKNG", "Tilak Nagar"),
                StationDef("CMBR", "Chembur"),
                StationDef("GV", "Govandi"),
                StationDef("MNKD", "Mankhurd"),
                StationDef("VSH", "Vashi"),
            ),
        ),
    ),
)

TRANS_HARBOUR = LineDef(
    code="THR",
    name="Trans-Harbour",
    color_hex="#F5A524",
    routes=(
        RouteDef(
            code="THR-VSH",
            stations=(
                StationDef("TNA", "Thane"),
                StationDef("AIRL", "Airoli"),
                StationDef("RABE", "Rabale"),
                StationDef("GNSL", "Ghansoli"),
                StationDef("KPHN", "Kopar Khairane"),
                StationDef("TUH", "Turbhe"),
                StationDef("SNCR", "Sanpada"),
                StationDef("VSH", "Vashi"),
            ),
        ),
    ),
)

LINES: tuple[LineDef, ...] = (WESTERN, CENTRAL, HARBOUR, TRANS_HARBOUR)
