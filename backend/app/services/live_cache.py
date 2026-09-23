"""In-memory cache of the most recent known position per train.

This is what makes "don't invent new positions, mark stale instead"
possible: every broadcast tick re-publishes every train we've ever seen
using its LAST known update, flipping status to "stale" once it's older
than `stale_after_seconds` instead of dropping it or fabricating a new
position for it.
"""

from __future__ import annotations

import time

from app.schemas.train import TrainPositionUpdate


class LiveTrainCache:
    def __init__(self, stale_after_seconds: float) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._latest: dict[str, TrainPositionUpdate] = {}

    def apply(self, updates: list[TrainPositionUpdate]) -> None:
        for update in updates:
            self._latest[update.train_id] = update

    def snapshot(self, now_epoch: float | None = None) -> list[TrainPositionUpdate]:
        now_epoch = now_epoch if now_epoch is not None else time.time()
        result: list[TrainPositionUpdate] = []
        for train_id, update in list(self._latest.items()):
            age_s = now_epoch - update.last_updated_epoch
            if age_s > self._stale_after_seconds and update.status != "stale":
                update = update.model_copy(update={"status": "stale"})
                self._latest[train_id] = update
            result.append(update)
        return result

    def get(self, train_id: str, now_epoch: float | None = None) -> TrainPositionUpdate | None:
        return next((u for u in self.snapshot(now_epoch) if u.train_id == train_id), None)

    def live_train_ids(self, now_epoch: float | None = None) -> set[str]:
        return {u.train_id for u in self.snapshot(now_epoch) if u.status == "live"}
