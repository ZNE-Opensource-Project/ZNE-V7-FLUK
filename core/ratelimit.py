from __future__ import annotations
from __future__ import annotations
import os
import asyncio
import logging
from pathlib import Path
from asyncio import Lock
from time import time, sleep as _sync_sleep
from typing import Any
from msgspec import encode, decode

from aiohttp import ClientSession, ClientResponse


class routebucket:
    __slots__ = ("limit", "remaining", "reset")

    def __init__(self):
        self.limit: int = 0
        self.remaining: int = 0
        self.reset: float = 0.0


class limiter:
    """handles rate limits. fast enough to not get 429'd but efficient enough to not waste reqs."""

    __slots__ = (
        "http",
        "buckets",
        "locks",
        "global_lock",
        "total_lock",
        "history",
        "path",
        "loop_task",
    )

    @property
    def session(self) -> ClientSession | None:
        return getattr(
            self.http, "_HTTPClient__session", getattr(self.http, "_session", None)
        )

    def __init__(self, http: Any):
        self.http = http
        self.path = Path("data/cache/ratelimits.bin")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.buckets: dict[str, routebucket] = {}
        self._load_mmap()
        self.locks: dict[str, Lock] = {}
        self.global_lock = Lock()
        self.total_lock = Lock()
        self.history: list[float] = []
        self.loop_task = None

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(5.0)
            await self._sync_to_disk()

    def _load_mmap(self):
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        try:
            fd = os.open(self.path, os.O_RDONLY)
            try:
                import mmap

                with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as mm:
                    data = decode(bytes(mm), type=dict[str, routebucket])
                    self.buckets.update(data)
            finally:
                os.close(fd)
        except Exception:
            pass

    async def _sync_to_disk(self):
        try:
            temp_path = self.path.with_suffix(f".{os.getpid()}.tmp")
            data = encode(self.buckets)

            def _write():
                with open(temp_path, "wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, self.path)

            await asyncio.to_thread(_write)
        except Exception:
            pass

    def _get_lock(self, route: str) -> Lock:
        if route not in self.locks:
            self.locks[route] = Lock()
        return self.locks[route]

    async def request(
        self, method: str, route: str, url: str, **kwargs: Any
    ) -> ClientResponse:
        if not self.loop_task:
            self.loop_task = asyncio.create_task(self._flush_loop())

        if "gateway" in url.lower():
            return await self.session.request(method, url, **kwargs)

        lock = self._get_lock(route)
        while True:
            sleep_time = 0.0
            async with self.total_lock:
                now = time()
                self.history = [t for t in self.history if now - t < 1.0]
                if len(self.history) >= 50:
                    sleep_time = max(0.0, 1.0 - (now - self.history[0]))
                else:
                    self.history.append(now)

            if sleep_time > 0.0:
                await asyncio.sleep(sleep_time)
                continue

            async with lock:
                b = self.buckets.get(route)
                if not b:
                    b = routebucket()
                    self.buckets[route] = b

                now = time()
                if b.reset > 0 and now >= b.reset:
                    b.remaining = b.limit
                    b.reset = 0.0

                if b.remaining <= 0:
                    sleep_time = min(max(0.0, b.reset - now) + 0.05, 10.0)
                else:
                    b.remaining -= 1

            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                continue

            async with self.global_lock:
                pass

            res = await self.session.request(method, url, **kwargs)

            lim = res.headers.get("x-ratelimit-limit")
            rem = res.headers.get("x-ratelimit-remaining")
            after = res.headers.get("x-ratelimit-reset-after")

            if lim or rem is not None or after or res.status == 429:
                async with lock:
                    b = self.buckets[route]
                    if lim:
                        b.limit = int(lim)
                    if rem is not None:
                        b.remaining = int(rem)
                    if after:
                        b.reset = time() + float(after) + 0.1

                    if res.status == 429:
                        retry = 2.5
                        try:
                            data = await res.json()
                            retry = float(data.get("retry_after", retry))
                        except Exception:
                            pass
                        logging.warning(f"429 | {route} | retry:{retry:.2f}s")
                        b.remaining = 0
                        b.reset = time() + retry
                        is_global = res.headers.get("x-ratelimit-global")
                        if is_global:
                            await asyncio.sleep(retry + 0.3)

            if res.status == 429:
                continue

            return res

    async def close(self):
        if self.loop_task:
            self.loop_task.cancel()
        await self._sync_to_disk()
