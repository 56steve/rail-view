import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        # Let the simulator tick at least once so live trains exist.
        deadline = time.time() + 5
        while time.time() < deadline and not test_client.get("/api/trains").json():
            time.sleep(0.2)
        yield test_client


def test_network_returns_all_lines_with_real_geometry(client) -> None:
    body = client.get("/api/network").json()
    assert {line["code"] for line in body["lines"]} == {"WR", "CR", "HR", "THR"}
    assert {r["line_code"] for r in body["routes"]} == {"WR", "CR", "HR", "THR"}
    assert {r["route_id"] for r in body["routes"] if r["line_code"] == "CR"} == {"CR-KSRA", "CR-KJT"}
    assert "OpenStreetMap" in body["attribution"]
    western = next(r for r in body["routes"] if r["line_code"] == "WR")
    assert len(western["polyline"]) > 50
    assert western["stations"][0]["name"] == "Churchgate"


def test_unknown_route_is_404(client) -> None:
    assert client.get("/api/routes/XX").status_code == 404


def test_stations_are_merged_by_name(client) -> None:
    stations = {s["id"]: s for s in client.get("/api/stations").json()}
    assert set(stations["dadar"]["lines"]) == {"CR", "WR"}
    assert set(stations["kurla"]["lines"]) == {"CR", "HR"}


def test_live_trains_cover_every_line(client) -> None:
    trains = client.get("/api/trains").json()
    assert {t["line_code"] for t in trains} == {"WR", "CR", "HR", "THR"}


def test_train_detail_has_a_timeline(client) -> None:
    train_id = client.get("/api/trains").json()[0]["train_id"]
    detail = client.get(f"/api/trains/{train_id}").json()
    assert detail["position"]["train_id"] == train_id
    states = {stop["state"] for stop in detail["stops"]}
    assert states & {"next", "at_platform"}


def test_unknown_train_is_404(client) -> None:
    assert client.get("/api/trains/NOPE").status_code == 404


def test_journey_endpoint(client) -> None:
    response = client.get("/api/journeys", params={"from": "thane", "to": "csmt", "sort": "soonest"})
    assert response.status_code == 200
    body = response.json()
    assert body["from_station"]["name"] == "Thane"
    times = [o["board_expected_epoch"] for o in body["options"]]
    assert times == sorted(times)


def test_journey_with_unknown_station_is_404(client) -> None:
    assert client.get("/api/journeys", params={"from": "atlantis", "to": "csmt"}).status_code == 404


def test_websocket_sends_an_initial_snapshot(client) -> None:
    with client.websocket_connect("/ws/live") as ws:
        message = ws.receive_json()
    assert message["type"] == "snapshot"
    assert len(message["trains"]) > 0
