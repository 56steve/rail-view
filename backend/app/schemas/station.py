from pydantic import BaseModel


class StationOut(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    sequence: int
    chainage_m: float


class RouteOut(BaseModel):
    """Static geometry for a route, fetched once by the client to draw the
    3D track and station markers before any live train data arrives.
    """

    route_id: str
    line_code: str
    line_name: str
    color_hex: str
    length_m: float
    origin_name: str
    destination_name: str
    stations: list[StationOut]
    # Ordered [lat, lon] pairs describing the track centerline. Consecutive
    # station geometry is a straight-line placeholder (see
    # app/data/mumbai_network.py) - the frontend renders whatever polyline
    # this list describes, so swapping in real survey geometry here is a
    # data-only change.
    polyline: list[list[float]]
