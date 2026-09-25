"""The live snapshot's wire format."""

import zlib
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.train import TrainPositionUpdate
from app.schemas.websocket import SnapshotTableMessage
from app.services.live_cache import LiveTrainCache
from app.services.live_wire import (
    FULL_FIELDS,
    MOVING_FIELDS,
    ROUNDING,
    RUN_FIELDS,
    SNAPSHOT_FIELDS,
    STATION_FIELDS,
    Snapshot,
    encode_snapshot,
)
from app.services.position_processor import PositionProcessor
from app.services.simulator.engine import TimetableTelemetrySource
from app.services.timetable import load_timetable
from app.services.track_matching import get_all_routes

WEDNESDAY_EVENING = datetime(2026, 9, 23, 18, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()


@pytest.fixture(scope="module")
def evening_trains() -> list[TrainPositionUpdate]:
    """The network at the evening peak, as the pipeline produces it."""
    now = WEDNESDAY_EVENING
    source = TimetableTelemetrySource(
        get_all_routes(), load_timetable(), 1.0, seed=1, clock=lambda: now
    )
    processor = PositionProcessor(routes=get_all_routes(), schedule_provider=source)
    cache = LiveTrainCache(stale_after_seconds=15.0)
    for step in range(3):
        cache.apply(processor.process_batch(source.tick(now + step)))
    return cache.snapshot()


def decode(payload: str) -> list[dict[str, object]]:
    """What the client does with a snapshot: rows back into positions."""
    message = SnapshotTableMessage.model_validate_json(payload)
    trains = []
    for row in message.trains:
        train = dict(zip(message.fields, row, strict=True))
        for name in STATION_FIELDS:
            code = train[name]
            train[name] = None if code is None else {"code": code, "name": message.stations[code]}
        trains.append(train)
    return trains


def test_every_position_field_is_a_column() -> None:
    assert tuple(TrainPositionUpdate.model_fields) == SNAPSHOT_FIELDS
    assert set(SNAPSHOT_FIELDS) >= STATION_FIELDS
    assert set(ROUNDING) <= set(SNAPSHOT_FIELDS)


def test_a_snapshot_decodes_to_the_same_positions(
    evening_trains: list[TrainPositionUpdate],
) -> None:
    assert len(evening_trains) > 100
    decoded = decode(encode_snapshot(WEDNESDAY_EVENING, evening_trains))

    assert len(decoded) == len(evening_trains)
    for original, train in zip(evening_trains, decoded, strict=True):
        expected = original.model_dump()
        for name, places in ROUNDING.items():
            assert train[name] == pytest.approx(expected[name], abs=10**-places)
            expected[name] = train[name]
        assert train == expected


def test_a_snapshot_is_compact(evening_trains: list[TrainPositionUpdate]) -> None:
    payload = encode_snapshot(WEDNESDAY_EVENING, evening_trains)
    # As plain objects this is ~1 KB a train.
    assert len(payload.encode()) / len(evening_trains) < 250


def test_an_empty_network_encodes() -> None:
    message = SnapshotTableMessage.model_validate_json(encode_snapshot(WEDNESDAY_EVENING, []))
    assert message.trains == []
    assert message.stations == {}
    assert tuple(message.fields) == SNAPSHOT_FIELDS


# -- the lean format (v2): full tables now and then, moving parts between --


def inflate(payload: bytes) -> str:
    return zlib.decompress(payload, -15).decode()


def test_train_coordinates_stay_off_the_wire() -> None:
    assert not {"lat", "lon", "heading_deg"} & set(FULL_FIELDS)
    assert set(MOVING_FIELDS) < set(FULL_FIELDS)
    assert "train_id" in MOVING_FIELDS
    assert not RUN_FIELDS & set(MOVING_FIELDS)
    assert set(FULL_FIELDS) == set(MOVING_FIELDS) | RUN_FIELDS


def test_a_full_snapshot_carries_every_wire_field(evening_trains: list[TrainPositionUpdate]) -> None:
    message = SnapshotTableMessage.model_validate_json(
        Snapshot(WEDNESDAY_EVENING, evening_trains, full=True).payload("table")
    )
    assert message.full
    assert tuple(message.fields) == FULL_FIELDS
    assert len(message.trains) == len(evening_trains)


def test_a_moving_snapshot_carries_only_what_changes(evening_trains: list[TrainPositionUpdate]) -> None:
    message = SnapshotTableMessage.model_validate_json(
        Snapshot(WEDNESDAY_EVENING, evening_trains, full=False).payload("table")
    )
    assert not message.full
    assert tuple(message.fields) == MOVING_FIELDS
    assert [row[0] for row in message.trains] == [t.train_id for t in evening_trains]


def test_deflate_is_the_table_compressed(evening_trains: list[TrainPositionUpdate]) -> None:
    snapshot = Snapshot(WEDNESDAY_EVENING, evening_trains, full=False)
    compressed = snapshot.payload("deflate")
    assert isinstance(compressed, bytes)
    assert inflate(compressed) == snapshot.payload("table")
    # What a phone receives per train per second, down from ~200 bytes.
    assert len(compressed) / len(evening_trains) < 40


def test_legacy_clients_get_the_original_table(evening_trains: list[TrainPositionUpdate]) -> None:
    snapshot = Snapshot(WEDNESDAY_EVENING, evening_trains, full=False)
    assert snapshot.payload("legacy") == encode_snapshot(WEDNESDAY_EVENING, evening_trains)


def test_each_format_is_encoded_once(evening_trains: list[TrainPositionUpdate]) -> None:
    snapshot = Snapshot(WEDNESDAY_EVENING, evening_trains, full=True)
    assert snapshot.payload("deflate") is snapshot.payload("deflate")
