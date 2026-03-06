"""Shared test fixtures for denon_rs232."""

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import denon_rs232
from denon_rs232 import DenonReceiver

# Speed up tests by reducing delays
denon_rs232.MULTI_RESPONSE_DELAY = 0.01
denon_rs232.PROBE_TIMEOUT = 0.01

# Default responses for all query prefixes during startup.
DEFAULT_QUERY_RESPONSES: dict[str, list[str]] = {
    "PW": ["PWON"],
    "ZM": ["ZMON"],
    "MV": ["MV80", "MVMAX 98"],
    "MU": ["MUOFF"],
    "SI": ["SICD"],
    "MS": ["MSSTEREO"],
    "SD": ["SDAUTO"],
    "SV": ["SVDVD"],
    "SR": ["SRCD"],
    "TF": ["TF105000"],
    "TP": ["TPA1"],
    "CV": ["CVFL 50", "CVFR 50", "CVC 50", "CVSW 50", "CVSL 50", "CVSR 50"],
    "PS": ["PSTONE DEFEAT OFF", "PSSB:OFF", "PSCINEMA EQ.OFF", "PSMODE : CINEMA"],
    "TM": ["TMFM", "TMAUTO"],
    "Z2": ["Z2OFF"],
    "Z3": ["Z3OFF"],
}


class MockSerialConnection:
    """Mock the serial reader/writer pair with auto-response support."""

    def __init__(self):
        self.reader = asyncio.StreamReader()
        self.writer = MagicMock()
        self.writer.write = MagicMock()
        self.writer.drain = AsyncMock()
        self.writer.close = MagicMock()
        self.writer.wait_closed = AsyncMock()
        self.written_data: list[bytes] = []
        self._query_responses: dict[str, list[str]] = {}
        self._command_handler: Callable[[str], None] | None = None
        self.writer.write.side_effect = self._on_write

    def _on_write(self, data: bytes) -> None:
        """Track written data and auto-respond to queries."""
        self.written_data.append(data)
        cmd = data.decode("ascii").rstrip("\r")
        if cmd.endswith("?"):
            prefix = cmd[:-1]
            for resp in self._query_responses.get(prefix, []):
                self.inject_response(resp)
        elif self._command_handler is not None:
            self._command_handler(cmd)

    def inject_response(self, message: str) -> None:
        """Simulate receiver sending a message."""
        self.reader.feed_data(f"{message}\r".encode("ascii"))


@pytest.fixture
async def mock_serial():
    return MockSerialConnection()


@pytest.fixture
async def receiver(mock_serial):
    """Create a connected DenonReceiver with mocked serial."""
    recv = DenonReceiver("/dev/ttyUSB0")
    mock_serial._query_responses = dict(DEFAULT_QUERY_RESPONSES)

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    with patch("denon_rs232.serialx.open_serial_connection", side_effect=fake_open):
        await recv.connect()

    # Clear auto-responses so tests can inject specific responses manually
    mock_serial._query_responses.clear()

    yield recv

    if recv.connected:
        await recv.disconnect()


async def connect_with_defaults(mock: MockSerialConnection) -> DenonReceiver:
    """Helper: connect a receiver with default auto-responses."""
    mock._query_responses = dict(DEFAULT_QUERY_RESPONSES)
    recv = DenonReceiver("/dev/ttyUSB0")

    async def fake_open(*args, **kwargs):
        return mock.reader, mock.writer

    with patch("denon_rs232.serialx.open_serial_connection", side_effect=fake_open):
        await recv.connect()

    return recv
