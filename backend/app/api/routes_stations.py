from fastapi import APIRouter, HTTPException

from app.data.mumbai_network import DEFAULT_ROUTE_ID, RAILWAY_LINES
from app.schemas.station import RouteOut, StationOut
from app.services.track_matching import get_route

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.get("", response_model=list[RouteOut])
def list_routes() -> list[RouteOut]:
    """Every route the API currently serves. MVP has exactly one
    (Thane<->Dadar on the Central Line); more lines register here as
    `app.data.mumbai_network.RAILWAY_LINES` grows.
    """
    return [_build_route_out(code) for code in RAILWAY_LINES]


@router.get("/{route_id}", response_model=RouteOut)
def get_route_detail(route_id: str) -> RouteOut:
    if route_id != DEFAULT_ROUTE_ID:
        raise HTTPException(status_code=404, detail=f"Unknown route_id '{route_id}'")
    return _build_route_out("CR")


def _build_route_out(line_code: str) -> RouteOut:
    route = get_route(line_code)
    stations = [
        StationOut(
            code=sc.station.code,
            name=sc.station.name,
            lat=sc.station.lat,
            lon=sc.station.lon,
            sequence=sc.station.sequence,
            chainage_m=sc.chainage_m,
        )
        for sc in route.stations
    ]
    polyline = [[sc.station.lat, sc.station.lon] for sc in route.stations]
    return RouteOut(
        route_id=DEFAULT_ROUTE_ID,
        line_code=route.line_seed.code,
        line_name=route.line_seed.name,
        color_hex=route.line_seed.color_hex,
        length_m=route.length_m,
        origin_name=stations[0].name,
        destination_name=stations[-1].name,
        stations=stations,
        polyline=polyline,
    )
