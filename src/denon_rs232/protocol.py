"""Protocol helpers for denon_rs232."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

_ZONE_VOL_RE = re.compile(r"^\d{2,3}$")


def parse_volume_param(param: str) -> float:
    """Convert a master volume parameter string to a dB value."""
    if param == "99":
        return -80.0

    if len(param) == 3:
        whole = int(param[:2])
        return (whole - 80) + 0.5
    return int(param) - 80


def volume_to_param(db: float) -> str:
    """Convert a dB value to the master volume protocol parameter."""
    if db <= -80:
        return "99"

    raw = db + 80
    whole = int(raw)
    if raw - whole >= 0.5:
        return f"{whole:02d}5"
    return f"{whole:02d}"


def parse_channel_volume_param(param: str) -> float:
    """Convert a channel volume parameter string to a dB value."""
    if len(param) == 3:
        whole = int(param[:2])
        return (whole - 50) + 0.5
    return int(param) - 50


def channel_volume_to_param(db: float) -> str:
    """Convert a dB value to the channel volume protocol parameter."""
    raw = db + 50
    whole = int(raw)
    if raw - whole >= 0.5:
        return f"{whole:02d}5"
    return f"{whole:02d}"


@dataclass
class PendingQuery:
    """A pending query waiting for a response."""

    prefix: str
    future: asyncio.Future[str]
