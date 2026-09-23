"""Curated network definitions: lines, the routes trains run on within
each line, and which stations each route calls at, in travel order.

This is the one hand-maintained input to `build_osm_data.py`. Station
*positions* and *track geometry* come from OpenStreetMap; membership and
order come from here because OSM route relations for the Mumbai suburban
network are incomplete and inconsistently ordered.

A line (Central, Western...) is what commuters and the UI talk about. A
route is one end-to-end path trains actually run on: the Central line
forks at Kalyan, so it has a Kasara route and a Khopoli route (via
Karjat) that share track up to Kalyan; the Harbour line forks at Wadala
Road towards Panvel and Goregaon. Short workings (e.g. CSMT-Thane) are runs over part
of a route, not routes of their own.

`ref` values are the Indian Railways station codes as tagged on the OSM
station element, which is how the build script finds each station.

Fast-halt flags are the core halts of fast services and are approximate:
individual fast workings vary, which per-train timetable data captures.
Beyond Kalyan every Central local, fast or slow, calls at every station.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class StationDef:
    ref: str
    name: str
    fast_halt: bool = False
    osm_id: str | None = None
    override_latlon: tuple[float, float] | None = None
    override_reason: str | None = None
    # Where a route reverses at the station, how close its track must pass:
    # the train runs into the platform and back out rather than turning at
    # the junction beyond it.
    reversal_snap_m: float | None = None


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
            code="WR-VR",
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
                StationDef("DIC", "Dahisar"),
                StationDef("MIRA", "Mira Road"),
                StationDef("BYR", "Bhayandar", fast_halt=True),
                StationDef("NIG", "Naigaon"),
                StationDef("BSR", "Vasai Road", fast_halt=True),
                StationDef("NSP", "Nallasopara", fast_halt=True),
                StationDef("VR", "Virar", fast_halt=True),
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
            code="CR-KP",
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
                StationDef("PDI", "Palasdhari", fast_halt=True),
                StationDef("KLY", "Kelavli", fast_halt=True),
                StationDef("DLV", "Dolavli", fast_halt=True),
                StationDef("LWJ", "Lowjee", fast_halt=True),
                StationDef("KHPI", "Khopoli", fast_halt=True),
            ),
        ),
    ),
)

_HARBOUR_CSMT_TO_WADALA = (
    StationDef("CSMT", "CSMT"),
    StationDef("MSD", "Masjid"),
    StationDef("SNRD", "Sandhurst Road"),
    StationDef("DKRD", "Dockyard Road"),
    StationDef("RRD", "Reay Road"),
    StationDef("CTGN", "Cotton Green"),
    StationDef("SVE", "Sewri"),
)

_WADALA_ROAD = StationDef(
    "VDLR",
    "Wadala Road",
    override_latlon=(19.0162, 72.8589),
    override_reason=(
        "No station element in OSM, but its four platforms are mapped "
        "('Vadala Road (Harbour Line)', ways 236381659-236381661); the "
        "station is placed at their centre."
    ),
)

# Wadala Road to Goregaon along the Harbour line's own tracks beside the
# Western line; the Harbour platform at Jogeshwari is pinned.
_HARBOUR_WADALA_TO_GOREGAON = (
    StationDef("KCE", "King's Circle"),
    StationDef("MM", "Mahim"),
    StationDef("BA", "Bandra"),
    StationDef("KHAR", "Khar Road"),
    StationDef("STC", "Santacruz"),
    StationDef("VLP", "Vile Parle"),
    StationDef("ADH", "Andheri"),
    StationDef("JOS", "Jogeshwari", osm_id="node/12189351698"),
    StationDef("RMAR", "Ram Mandir"),
    StationDef("GMN", "Goregaon"),
)

# Shared by the Harbour line and Trans-Harbour trains to Panvel.
_JUINAGAR_TO_PANVEL = (
    StationDef("JNJ", "Juinagar"),
    StationDef("NEU", "Nerul"),
    StationDef("SWDV", "Seawoods Darave Karave"),
    StationDef("BEPR", "Belapur CBD"),
    StationDef("KHAG", "Kharghar"),
    # Both tagged station=light_rail in OSM, which the ref lookup skips.
    StationDef("MANR", "Mansarovar", osm_id="node/1435294693"),
    StationDef("KNDS", "Khandeshwar", osm_id="node/1645802025"),
    StationDef(
        "PNVL",
        "Panvel",
        override_latlon=(18.9901, 73.1214),
        override_reason=(
            "Harbour and Trans-Harbour trains terminate in bay platforms beside the main "
            "station; both OSM Panvel elements (the long-distance station and the "
            "suburban station area) sit 100 m or more off those tracks, so the station "
            "is placed at the bay platforms' buffer stops."
        ),
    ),
)

_HARBOUR_WADALA_TO_PANVEL = (
    StationDef("GTBN", "GTB Nagar"),
    StationDef("CHF", "Chunabhatti"),
    StationDef("CLA", "Kurla"),
    StationDef("TKNG", "Tilak Nagar"),
    StationDef("CMBR", "Chembur"),
    StationDef("GV", "Govandi"),
    StationDef("MNKD", "Mankhurd"),
    StationDef("VSH", "Vashi"),
    StationDef("SNCR", "Sanpada"),
    *_JUINAGAR_TO_PANVEL,
)

HARBOUR = LineDef(
    code="HR",
    name="Harbour",
    color_hex="#2BC4A4",
    routes=(
        RouteDef(
            code="HR-PNVL",
            stations=(*_HARBOUR_CSMT_TO_WADALA, _WADALA_ROAD, *_HARBOUR_WADALA_TO_PANVEL),
        ),
        RouteDef(
            code="HR-GMN",
            stations=(*_HARBOUR_CSMT_TO_WADALA, _WADALA_ROAD, *_HARBOUR_WADALA_TO_GOREGAON),
        ),
        # Panvel - Goregaon services reverse at Wadala Road: both branches
        # leave it northwards, with no curve joining them.
        RouteDef(
            code="HR-PLGN",
            stations=(
                *reversed(_HARBOUR_WADALA_TO_PANVEL),
                replace(_WADALA_ROAD, reversal_snap_m=40.0),
                *_HARBOUR_WADALA_TO_GOREGAON,
            ),
        ),
    ),
)

_TRANS_HARBOUR_TO_TURBHE = (
    StationDef("TNA", "Thane"),
    StationDef("DIGH", "Digha Gaon"),
    StationDef("AIRL", "Airoli"),
    StationDef("RABE", "Rabale"),
    StationDef("GNSL", "Ghansoli"),
    StationDef("KPHN", "Kopar Khairane"),
    StationDef("TUH", "Turbhe"),
)

TRANS_HARBOUR = LineDef(
    code="THR",
    name="Trans-Harbour",
    color_hex="#F5A524",
    routes=(
        RouteDef(
            code="THR-VSH",
            stations=(*_TRANS_HARBOUR_TO_TURBHE, StationDef("SNCR", "Sanpada"), StationDef("VSH", "Vashi")),
        ),
        RouteDef(
            code="THR-PNVL",
            stations=(*_TRANS_HARBOUR_TO_TURBHE, *_JUINAGAR_TO_PANVEL),
        ),
    ),
)

LINES: tuple[LineDef, ...] = (WESTERN, CENTRAL, HARBOUR, TRANS_HARBOUR)
