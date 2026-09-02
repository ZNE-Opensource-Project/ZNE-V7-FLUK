from __future__ import annotations

import os
import functools

from discord.ext import commands

BLACKLISTED_GUILD = os.getenv("BLACKLISTED_GUILD")


def is_blacklisted(func):
    @functools.wraps(func)
    async def wrapper(cog_self, ctx: commands.Context, *args, **kwargs):
        if BLACKLISTED_GUILD and ctx.guild and str(ctx.guild.id) == BLACKLISTED_GUILD:
            await ctx.reply("no", delete_after=10)
            return
        return await func(cog_self, ctx, *args, **kwargs)

    return wrapper
