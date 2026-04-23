"""Event bus: sync emit, async fan-out to each client's queue."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from events import Event

from loguru import logger


class Client(ABC):
    """Base class for event consumers.

    Subclasses implement ``handle(event)``. The bus enqueues events via
    ``enqueue()`` from sync code; a background task drains the queue and calls
    ``handle()`` so slow clients never block emitters.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def enqueue(self, event: Event) -> None:
        self._queue.put_nowait(event)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._queue.put_nowait(None)
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            event = await self._queue.get()
            if event is None:
                return
            try:
                await self.handle(event)
            except Exception as e:
                logger.exception(
                    "Client {} failed on event {}: {}", type(self).__name__, event, e
                )

    @abstractmethod
    async def handle(self, event: Event) -> None: ...


class EventBus:
    def __init__(self) -> None:
        self._clients: list[Client] = []

    def add_client(self, client: Client) -> None:
        self._clients.append(client)

    def emit(self, event: Event) -> None:
        for client in self._clients:
            client.enqueue(event)

    async def start(self) -> None:
        for client in self._clients:
            await client.start()

    async def stop(self) -> None:
        for client in self._clients:
            await client.stop()
