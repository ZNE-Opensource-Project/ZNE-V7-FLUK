from __future__ import annotations
import os
import asyncio
import logging
import platform
from pathlib import Path
from datetime import datetime

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv # type: ignore

from core.operations import Operations
from core.ratelimit import limiter
from core.settings import Settings

load_dotenv()


class _RAMFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            import psutil

            process = psutil.Process(os.getpid())
            mb = process.memory_info().rss / 1024 / 1024
            record.msg = f"[NB] [ram:{int(mb):02d} mb] [{record.levelname}]- {record.msg}"
        except Exception:
            record.msg = f"[NB] [ram:00 mb] [{record.levelname}]- {record.msg}"
        return True


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(msg)s", datefmt="%H:%M:%S"))
    handler.addFilter(_RAMFilter())
    logger.handlers = [handler]
    logging.getLogger("discord").setLevel(logging.WARNING)
    return logger


class ZNE(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=os.getenv("PREFIX", "."),
            intents=intents,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=True, users=True, roles=True),
            owner_ids=[1470775670262202590, 519592249622003752]
        )
        self.log = _setup_logger()
        self.db_path = "data/zne.db"
        self.db: aiosqlite.Connection | None = None
        self.operations: Operations | None = None
        self.settings = Settings.load()
        self.start_time = datetime.utcnow()

    async def setup_hook(self) -> None:
        Path("data/cache").mkdir(parents=True, exist_ok=True)
        await self._init_db()
        self.operations = Operations(self)
        await self.operations.setup()
        await self._load_cogs()
        self.log.info(f"loaded {len(self.cogs)} cog(s)")

    async def _init_db(self) -> None:
        Path("data").mkdir(exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        await self.db.execute("PRAGMA journal_mode=WAL")
        schema_path = Path("core/schema/schema.sql")
        if schema_path.exists():
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            await self.db.executescript(sql)
            await self.db.commit()
        self.log.info("database initialized")

    async def _load_cogs(self) -> None:
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            return
        for ext in sorted(plugins_dir.glob("*.py")):
            if ext.name.startswith("_"):
                continue
            module = f"plugins.{ext.stem}"
            try:
                await self.load_extension(module)
                self.log.info(f"loaded extension: {module}")
            except Exception as e:
                self.log.error(f"failed to load {module}: {e}")

    async def on_ready(self) -> None:
        self.log.info(f"logged in as {self.user} ({self.user.id})")
        self.log.info(f"connected to {len(self.guilds)} guild(s)")
        self.log.info(f"python: {platform.python_version()} | discord.py: {discord.__version__}")

    async def close(self) -> None:
        if self.operations:
            await self.operations.close()
        if self.db:
            await self.db.close()
        await super().close()

    async def track_message(self, message_id: str, app_id: str, token: str, channel_id: int, author_id: int) -> None:
        if not self.db:
            return
        try:
            await self.db.execute(
                "INSERT OR REPLACE INTO messages (message_id, app_id, token, channel_id, author_id) VALUES (?, ?, ?, ?, ?)",
                (message_id, app_id, token, channel_id, author_id),
            )
            await self.db.commit()
        except Exception:
            pass


def run() -> None:
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN not set in environment (.env)")
    bot = ZNE()
    bot.run(token, log_handler=None)
