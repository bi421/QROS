"""Standalone production worker composition and process entrypoint."""

from __future__ import annotations

import os
from threading import Event
from typing import Final

from supabase import create_client

from researchos.saas.datasets import DatasetStorage, DatasetStore, SupabaseDatasetStorage, SupabaseDatasetStore
from researchos.saas.queue import ResearchJobQueue, SupabaseResearchJobQueue
from researchos.saas.research_executor import GovernedResearchExecutor
from researchos.saas.store import ResearchJobStore
from researchos.saas.supabase_job_store import SupabaseResearchJobStore
from researchos.saas.worker import ResearchWorker

QUEUE_VISIBILITY_TIMEOUT_SECONDS: Final = 1200
IDLE_POLL_SECONDS: Final = 1.0


def build_production_worker() -> "StandaloneResearchWorker":
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)
    store = SupabaseResearchJobStore(client)
    dataset_store = SupabaseDatasetStore(client)
    dataset_storage = SupabaseDatasetStorage(client)
    queue = SupabaseResearchJobQueue(
        client,
        visibility_timeout_seconds=QUEUE_VISIBILITY_TIMEOUT_SECONDS,
    )
    return StandaloneResearchWorker(store, dataset_store, dataset_storage, queue)


class StandaloneResearchWorker:
    """Consume exactly the governed research queue and delegate job lifecycle to ResearchWorker."""

    def __init__(
        self,
        store: ResearchJobStore,
        dataset_store: DatasetStore,
        dataset_storage: DatasetStorage,
        queue: ResearchJobQueue,
    ) -> None:
        self._store = store
        self._dataset_store = dataset_store
        self._dataset_storage = dataset_storage
        self._queue = queue

    def run_forever(self, stop_event: Event | None = None) -> None:
        stop = stop_event or Event()
        while not stop.is_set():
            message = self._queue.receive()
            if message is None:
                stop.wait(IDLE_POLL_SECONDS)
                continue

            try:
                executor = GovernedResearchExecutor(
                    self._store,
                    self._dataset_store,
                    self._dataset_storage,
                    message.workspace_id,
                )
                worker = ResearchWorker(self._store, executor)
                worker.run_once(message.workspace_id, message.research_run_id)
            except Exception:
                job = self._store.get(message.workspace_id, message.research_run_id)
                if job is not None and job.status.value in {"succeeded", "failed", "cancelled"}:
                    self._queue.ack(message.message_id)
                continue
            self._queue.ack(message.message_id)


def main() -> None:
    build_production_worker().run_forever()


if __name__ == "__main__":
    main()


__all__ = ["StandaloneResearchWorker", "build_production_worker", "main"]
