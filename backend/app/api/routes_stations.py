from fastapi import APIRouter, HTTPException

from app.data.mumbai_network import load_network
from app.schemas.station import LineOut, NetworkOut, RouteOut, RunningLanesOut, StationIndexEntry
from app.services.position_processor import station_out
from app.services.station_index import station_index
from app.services.track_matching import RailwayRoute, get_all_routes

router = APIRouter(prefix="/api", tags=["network"])


@router.get("/network", response_model=NetworkOut)
def get_network() -> NetworkOut:
    """Every line and route's static geometry in one payload - what the
    client loads on start to draw the whole network."""
    network = load_network()
    return NetworkOut(
        attribution=network.attribution,
        generated_at=network.generated_at,
        lines=[LineOut(code=line.code, name=line.name, color_hex=line.color_hex) for line in network.lines.values()],
        routes=[_route_out(route) for route in get_all_routes().values()],
    )


@router.get("/routes/{route_id}", response_model=RouteOut)
def get_route_detail(route_id: str) -> RouteOut:
    routes = get_all_routes()
    if route_id not in routes:
        raise HTTPException(status_code=404, detail=f"Unknown route_id '{route_id}'")
    return _route_out(routes[route_id])


@router.get("/stations", response_model=list[StationIndexEntry])
def list_stations() -> list[StationIndexEntry]:
    return sorted(station_index().values(), key=lambda s: s.name)


def _route_out(route: RailwayRoute) -> RouteOut:
    seed = route.seed
    return RouteOut(
        route_id=seed.code,
        line_code=seed.line.code,
        line_name=seed.line.name,
        color_hex=seed.line.color_hex,
        name=seed.name,
        length_m=route.length_m,
        origin_name=seed.stations[0].name,
        destination_name=seed.stations[-1].name,
        stations=[station_out(sc) for sc in route.stations],
        polyline=[[lat, lon] for lat, lon in seed.track],
        running_lanes=RunningLanesOut(
            forward=[[c, d] for c, d in seed.running_lanes.forward],
            backward=[[c, d] for c, d in seed.running_lanes.backward],
        ),
    )
