"""Tests for denon_rs232 source probing."""

import pytest

from denon_rs232 import DenonReceiver, InputSource


async def test_probe_sources(receiver, mock_serial):
    """probe_sources should return only sources the receiver accepts."""
    valid_values = {"CD", "DVD", "TUNER", "TV"}

    def handle_command(cmd):
        if cmd.startswith("SI"):
            source_val = cmd[2:]
            if source_val in valid_values:
                mock_serial.inject_response(f"SI{source_val}")

    mock_serial._command_handler = handle_command

    result = await receiver.probe_sources()

    expected = {InputSource(v) for v in valid_values}
    assert result == expected


async def test_probe_sources_restores_original(receiver, mock_serial):
    """probe_sources should restore the original input source."""
    assert receiver.state.main_zone.input_source == InputSource.CD

    valid_values = {"CD", "DVD"}

    def handle_command(cmd):
        if cmd.startswith("SI"):
            source_val = cmd[2:]
            if source_val in valid_values:
                mock_serial.inject_response(f"SI{source_val}")

    mock_serial._command_handler = handle_command

    await receiver.probe_sources()

    # Last SI command written should be the restore to CD
    si_commands = [
        d
        for d in mock_serial.written_data
        if d.startswith(b"SI") and not d.endswith(b"?\r")
    ]
    assert si_commands[-1] == b"SICD\r"
    # State should be back to CD
    assert receiver.state.main_zone.input_source == InputSource.CD


async def test_probe_includes_current_source(receiver, mock_serial):
    """probe_sources should include the current source even without re-testing it."""
    # After connect, input source is CD. Even if no handler responds,
    # CD should be in the result because it's the current source.
    result = await receiver.probe_sources()

    assert InputSource.CD in result


async def test_probe_disconnected_raises():
    """probe_sources should raise if not connected."""
    recv = DenonReceiver("/dev/ttyUSB0")
    with pytest.raises(ConnectionError, match="Not connected"):
        await recv.probe_sources()
