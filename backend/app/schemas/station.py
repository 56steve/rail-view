from pydantic import BaseModel


class StationOut(BaseModel):
    code: str
    name: str
    lat: float
    lon: float
    sequence: int
    chainage_m: float
    fast_halt: bool


class StationRef(BaseModel):
    """A station named in a live train position. Codes are unique across
    the network; everything else about a station comes from the network
    data, which clients load once."""

    code: str
    name: str


class LineOut(BaseModel):
    code: str
    name: str
    color_hex: str


class RunningLanesOut(BaseModel):
    """Sideways offset of each direction's running track from the route
    centreline: [chainage_m, offset_m] breakpoints, linear in between,
    offset positive to the left facing increasing chainage. Mumbai runs
    on the left, so the two directions keep to different tracks."""

    forward: list[list[float]]
    backward: list[list[float]]


class RouteOut(BaseModel):
    """Static geometry for one route (an end-to-end path within a line,
    e.g. Central's CSMT-Kasara), fetched once by the client to draw the 3D
    track and station markers before any live train data arrives.
    """

    route_id: str
    line_code: str
    line_name: str
    color_hex: str
    name: str
    length_m: float
    origin_name: str
    destination_name: str
    stations: list[StationOut]
    # Ordered [lat, lon] track centerline (OSM-derived, map-matched). The
    # client derives chainage from this exact polyline, so it must be the
    # same one the backend matches positions against.
    polyline: list[list[float]]
    running_lanes: RunningLanesOut


class NetworkOut(BaseModel):
    attribution: str
    generated_at: str
    lines: list[LineOut]
    routes: list[RouteOut]


class StationIndexEntry(BaseModel):
    """A commuter-facing station, merged across lines by name (e.g. the
    Western and Central platforms at Dadar are one 'Dadar')."""

    id: str
    name: str
    lat: float
    lon: float
    lines: list[str]
