from __future__ import annotations
import discord
from discord.ext import commands

PER_PAGE = 10


def _format_cooldown(cmd: commands.Command) -> str | None:
    cd = getattr(cmd, "_buckets", None)
    if cd and cd._cooldown:
        per = cd._cooldown.per
        if per >= 3600:
            return f"{per // 3600} hour{'s' if per >= 7200 else ''}"
        if per >= 60:
            return f"{per // 60} minute{'s' if per >= 120 else ''}"
        return f"{per} second{'s' if per != 1 else ''}"
    return None


def _format_command(cmd: commands.Command) -> str:
    alias_str = ", ".join(f"`{a}`" for a in cmd.aliases) if cmd.aliases else "No Aliases available"
    cooldown_str = _format_cooldown(cmd) or "No Cooldown"
    description = cmd.description or cmd.help or "No description"
    return f"📂 `{cmd.name}` = {description}\n↳ {alias_str}; {cooldown_str}."


def _build_embed(page: int, all_commands: list[commands.Command]) -> discord.Embed:
    total_pages = max(1, (len(all_commands) + PER_PAGE - 1) // PER_PAGE)
    start = page * PER_PAGE
    end = start + PER_PAGE
    page_commands = all_commands[start:end]

    lines = [_format_command(cmd) for cmd in page_commands]

    embed = discord.Embed(
        description=(
            "## ZNE HELP\n"
            "welcome to ZNE v7 \"Fluk\"\n"
            "https://zne.breed.rip\n\n"
            + "\n".join(lines)
            + f"\n\nPage {page + 1}/{total_pages}"
        ),
    ).set_thumbnail(url="https://zne.breed.rip/assets/zne.png")

    return embed


class HelpPaginator(discord.ui.View):
    def __init__(self, all_commands: list[commands.Command], timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.page = 0
        self.all_commands = all_commands
        self.total_pages = max(1, (len(all_commands) + PER_PAGE - 1) // PER_PAGE)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        embed = _build_embed(self.page, self.all_commands)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        embed = _build_embed(self.page, self.all_commands)
        await interaction.response.edit_message(embed=embed, view=self)


class Meta(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="help")
    async def help(self, ctx: commands.Context) -> None:
        all_commands = sorted(self.bot.commands, key=lambda c: c.name)
        embed = _build_embed(0, all_commands)
        view = HelpPaginator(all_commands)
        await ctx.reply(embed=embed, view=view)

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        latency = round(self.bot.latency * 1000)
        await ctx.reply(f"it took **{latency}ms** to ping discord gateway.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Meta(bot))