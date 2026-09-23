"""FastAPI application entrypoint.

Wires together the telemetry source (the timetable-driven simulator until
an authorised live feed exists - swap it in by implementing
`TelemetrySource`/`ScheduleProvider`),
the position processor, the live-position cache, and the WebSocket
broadcast hub, then runs one background task that ticks the whole
pipeline and fans results out to every connected client.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_journeys import router as journeys_router
from app.api.routes_service_day import router as service_day_router
from app.api.routes_stations import router as stations_router
from app.api.routes_trains import router as trains_router
from app.api.ws import router as ws_router
from app.config import get_settings
from app.schemas.websocket import SnapshotMessage
from app.services.live_cache import LiveTrainCache
from app.services.position_processor import PositionProcessor
from app.services.simulator.engine import TimetableTelemetrySource
from app.services.timetable import load_timetable
from app.services.track_matching import get_all_routes
from app.services.websocket_manager import ConnectionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _run_pipeline(app: FastAPI) -> None:
    source: TimetableTelemetrySource = app.state.telemetry_source
    processor: PositionProcessor = app.state.position_processor
    cache: LiveTrainCache = app.state.live_cache
    manager: ConnectionManager = app.state.connection_manager

    async for fixes in source.stream():
        updates = processor.process_batch(fixes)
        cache.apply(updates)
        # A train with no active run has finished its journey: it leaves
        # the map rather than lingering as "stale".
        for train_id in cache.train_ids():
            if source.get_active_run(train_id) is None:
                cache.remove(train_id)
                processor.forget(train_id)
        snapshot = cache.snapshot()
        if manager.active_connection_count:
            await manager.broadcast(
                SnapshotMessage(server_time_epoch=time.time(), trains=snapshot)
            )


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    routes = get_all_routes()

    timetable = load_timetable()
    source = TimetableTelemetrySource(
        routes=routes,
        timetable=timetable,
        tick_seconds=settings.simulation_tick_seconds,
    )
    app.state.timetable = timetable
    app.state.telemetry_source = source
    app.state.position_processor = PositionProcessor(routes=routes, schedule_provider=source)
    app.state.live_cache = LiveTrainCache(stale_after_seconds=settings.stale_after_seconds)
    app.state.connection_manager = ConnectionManager()

    pipeline_task = asyncio.create_task(_run_pipeline(app))
    logger.info(
        "RailView running the official timetable: %d trains (%d beyond the network), %d on the map now",
        len(timetable.trains),
        len(timetable.unplaced),
        len(source.running_train_ids),
    )
    try:
        yield
    finally:
        pipeline_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pipeline_task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="RailView API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_origin_regex=settings.cors_allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(stations_router)
    app.include_router(trains_router)
    app.include_router(journeys_router)
    app.include_router(service_day_router)
    app.include_router(ws_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
