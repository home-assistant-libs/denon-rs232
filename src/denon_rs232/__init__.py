"""Async library to control Denon receivers over RS232 using serialx."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ReceiverModel

import serialx

from .const import (
    BAUD_RATE,
    COMMAND_TIMEOUT,
    CR,
    DigitalInputMode,
    MAX_VOLUME_DB,
    InputSource,
    ModeSetting,
    MIN_VOLUME_DB,
    MULTI_RESPONSE_DELAY,
    PROBE_TIMEOUT,
    RoomEQ,
    SurroundBack,
    TunerBand,
    TunerMode,
    VOLUME_DB_RANGE,
    ZONE3_PREFIX,
    _MULTI_RESPONSE_PREFIXES,
    _SINGLE_RESPONSE_PREFIXES,
)
from .state import DenonState, ZoneState

_LOGGER = logging.getLogger(__name__)

_ZONE_VOL_RE = re.compile(r"^\d{2,3}$")


# -- Volume helpers --


def _parse_volume_param(param: str) -> float:
    """Convert a master volume parameter string to a dB value.

    The protocol encodes master volume as:
      2-digit: 00-99 where 80=0dB, 98=+18dB(MAX), 99=MIN
      3-digit: half-dB step, e.g. "805" = +0.5dB, "795" = -0.5dB
    """
    if param == "99":
        return -80.0  # MIN sentinel

    if len(param) == 3:
        whole = int(param[:2])
        return (whole - 80) + 0.5
    else:
        return int(param) - 80


def _volume_to_param(db: float) -> str:
    """Convert a dB value to the master volume protocol parameter.

    Accepts values from -80 (MIN) to +18 (MAX).
    """
    if db <= -80:
        return "99"

    raw = db + 80
    whole = int(raw)
    if raw - whole >= 0.5:
        return f"{whole:02d}5"
    return f"{whole:02d}"


def _parse_channel_volume_param(param: str) -> float:
    """Convert a channel volume parameter string to a dB value.

    Channel volume: 00-62, where 50=0dB, 62=+12dB(MAX), 38=-12dB(MIN).
    00=OFF (SW in DIRECT mode). Half-dB steps use 3 chars.
    """
    if len(param) == 3:
        whole = int(param[:2])
        return (whole - 50) + 0.5
    return int(param) - 50


def _channel_volume_to_param(db: float) -> str:
    """Convert a dB value to the channel volume protocol parameter."""
    raw = db + 50
    whole = int(raw)
    if raw - whole >= 0.5:
        return f"{whole:02d}5"
    return f"{whole:02d}"


# Type alias for state change callbacks
# Receives DenonState on updates, None on disconnect.
StateCallback = Callable[[DenonState | None], None]


@dataclass
class _PendingQuery:
    """A pending query waiting for a response."""

    prefix: str
    future: asyncio.Future[str]


class DenonReceiver:
    """Async controller for a Denon receiver over RS232."""

    def __init__(
        self,
        port: str,
        zone3_prefix: str = ZONE3_PREFIX,
        model: ReceiverModel | None = None,
    ) -> None:
        self._port = port
        self._model = model
        self._zone3_prefix = (
            model.zone3_prefix or ZONE3_PREFIX if model else zone3_prefix
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: serialx.SerialStreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._state = DenonState()
        self._subscribers: list[StateCallback] = []
        self._pending_queries: list[_PendingQuery] = []
        self._write_lock = asyncio.Lock()
        self._connected = False

    @property
    def model(self) -> ReceiverModel | None:
        """Return the receiver model, if set."""
        return self._model

    @property
    def state(self) -> DenonState:
        """Return a copy of the current state."""
        return self._state.copy()

    @property
    def connected(self) -> bool:
        return self._connected

    def subscribe(self, callback: StateCallback) -> Callable[[], None]:
        """Subscribe to state changes. Returns an unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)

    async def connect(self) -> None:
        """Open the serial connection, verify, and query all state."""
        self._reader, self._writer = await serialx.open_serial_connection(
            self._port,
            baudrate=BAUD_RATE,
        )
        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())

        # Verify connection by querying power status
        try:
            await self.query_power()
        except TimeoutError:
            await self.disconnect()
            raise ConnectionError(
                f"No response from receiver on {self._port}"
            ) from None

        _LOGGER.info("Connected to Denon receiver on %s", self._port)

    async def disconnect(self) -> None:
        """Close the serial connection."""
        await self._teardown()
        _LOGGER.info("Disconnected from Denon receiver")

    async def query_state(self) -> None:
        """Query all initial state from the receiver."""
        # Single-response prefixes use _query() to wait for the response.
        unsupported_queries = (
            self._model.unsupported_startup_queries if self._model is not None else ()
        )
        for prefix in _SINGLE_RESPONSE_PREFIXES:
            if prefix == "PW" or prefix in unsupported_queries:
                continue
            try:
                await self._query(prefix)
            except TimeoutError:
                pass

        # Multi-response prefixes send the query and wait briefly for all
        # responses to arrive (protocol guarantees responses within 200ms).
        for prefix in _MULTI_RESPONSE_PREFIXES:
            if prefix == "Z1":
                if self._model is not None and self._model.zone3_prefix is None:
                    continue
                prefix = self._zone3_prefix

            if prefix in unsupported_queries:
                continue

            await self._send_command(prefix, "?")
            await asyncio.sleep(MULTI_RESPONSE_DELAY)

    # -- Power commands --

    async def power_on(self) -> None:
        await self._send_command("PW", "ON")

    async def power_standby(self) -> None:
        await self._send_command("PW", "STANDBY")

    async def query_power(self) -> bool:
        resp = await self._query("PW")
        if resp == "ON":
            return True
        if resp == "STANDBY":
            return False
        raise ValueError(f"Unknown power state: {resp}")

    # -- Main zone commands --

    async def main_zone_on(self) -> None:
        await self._send_command("ZM", "ON")

    async def main_zone_off(self) -> None:
        await self._send_command("ZM", "OFF")

    async def query_main_zone(self) -> bool:
        resp = await self._query("ZM")
        return resp == "ON"

    # -- Master volume commands --

    async def volume_up(self) -> None:
        await self._send_command("MV", "UP")

    async def volume_down(self) -> None:
        await self._send_command("MV", "DOWN")

    async def set_volume(self, db: float) -> None:
        """Set master volume in dB. 0dB is normal, +18 is max, -80 is min."""
        await self._send_command("MV", _volume_to_param(db))

    async def query_volume(self) -> float:
        resp = await self._query("MV")
        return _parse_volume_param(resp)

    # -- Channel volume commands --

    async def channel_volume_up(self, channel: str) -> None:
        """Adjust a channel volume up. Channel: FL, FR, C, SW, SL, SR, SBL, SBR, SB."""
        await self._send_command("CV", f"{channel} UP")

    async def channel_volume_down(self, channel: str) -> None:
        """Adjust a channel volume down."""
        await self._send_command("CV", f"{channel} DOWN")

    async def set_channel_volume(self, channel: str, db: float) -> None:
        """Set a channel volume in dB. 0dB is normal, +12 max, -12 min."""
        await self._send_command("CV", f"{channel} {_channel_volume_to_param(db)}")

    # -- Mute commands --

    async def mute_on(self) -> None:
        await self._send_command("MU", "ON")

    async def mute_off(self) -> None:
        await self._send_command("MU", "OFF")

    async def query_mute(self) -> bool:
        resp = await self._query("MU")
        return resp == "ON"

    # -- Input source commands --

    async def select_input_source(self, source: InputSource) -> None:
        """Select input source."""
        await self._send_command("SI", source.value)

    async def query_input_source(self) -> InputSource:
        return InputSource(await self._query("SI"))

    # -- Surround mode commands --

    async def set_surround_mode(self, mode: str) -> None:
        """Set surround mode. e.g. STEREO, DIRECT, DOLBY DIGITAL, etc."""
        await self._send_command("MS", mode)

    async def query_surround_mode(self) -> str:
        return await self._query("MS")

    # -- Parameter settings commands --

    async def tone_defeat_on(self) -> None:
        await self._send_command("PS", "TONE DEFEAT ON")

    async def tone_defeat_off(self) -> None:
        await self._send_command("PS", "TONE DEFEAT OFF")

    async def set_surround_back(self, mode: SurroundBack) -> None:
        """Set surround back mode."""
        await self._send_command("PS", f"SB:{mode.value}")

    async def cinema_eq_on(self) -> None:
        await self._send_command("PS", "CINEMA EQ.ON")

    async def cinema_eq_off(self) -> None:
        await self._send_command("PS", "CINEMA EQ.OFF")

    async def set_mode_setting(self, mode: ModeSetting) -> None:
        """Set decoder mode."""
        await self._send_command("PS", f"MODE : {mode.value}")

    async def set_room_eq(self, mode: RoomEQ) -> None:
        """Set room EQ.

        Note: room EQ state is event-only; the receiver does not include it
        in PS? responses.
        """
        await self._send_command("PS", f"ROOM EQ:{mode.value}")

    # -- Digital input mode commands --

    async def set_digital_input(self, mode: DigitalInputMode) -> None:
        """Set digital input mode."""
        await self._send_command("SD", mode.value)

    async def query_digital_input(self) -> DigitalInputMode | None:
        param = await self._query("SD")
        if param == "NO":
            return None
        return DigitalInputMode(param)

    # -- Video select commands --

    async def set_video_select(self, source: InputSource) -> None:
        """Set video select source."""
        await self._send_command("SV", source.value)

    async def cancel_video_select(self) -> None:
        """Cancel video select (return to following input source)."""
        await self._send_command("SV", "SOURCE")

    async def query_video_select(self) -> InputSource | None:
        param = await self._query("SV")
        if param in ("SOURCE", "OFF"):
            return None
        return InputSource(param)

    # -- Rec select commands --

    async def set_rec_select(self, source: InputSource) -> None:
        """Set recording source."""
        await self._send_command("SR", source.value)

    async def cancel_rec_select(self) -> None:
        """Cancel recording source selection."""
        await self._send_command("SR", "SOURCE")

    async def query_rec_select(self) -> InputSource:
        return InputSource(await self._query("SR"))

    # -- Tuner commands --

    async def tuner_frequency_up(self) -> None:
        await self._send_command("TF", "UP")

    async def tuner_frequency_down(self) -> None:
        await self._send_command("TF", "DOWN")

    async def set_tuner_frequency(self, freq: str) -> None:
        """Set tuner frequency directly (6 digits). >050000=AM kHz, <050000=FM MHz."""
        await self._send_command("TF", freq)

    async def query_tuner_frequency(self) -> str:
        return await self._query("TF")

    async def tuner_preset_up(self) -> None:
        await self._send_command("TP", "UP")

    async def tuner_preset_down(self) -> None:
        await self._send_command("TP", "DOWN")

    async def set_tuner_preset(self, preset: str) -> None:
        """Set tuner preset directly. e.g. A1, B3."""
        await self._send_command("TP", preset)

    async def query_tuner_preset(self) -> str:
        return await self._query("TP")

    async def set_tuner_band(self, band: TunerBand) -> None:
        """Set tuner band."""
        await self._send_command("TM", band.value)

    async def set_tuner_mode(self, mode: TunerMode) -> None:
        """Set tuning mode."""
        await self._send_command("TM", mode.value)

    # -- Zone 2 commands --

    async def zone2_power_on(self) -> None:
        await self._send_command("Z2", "ON")

    async def zone2_power_standby(self) -> None:
        await self._send_command("Z2", "OFF")

    async def zone2_select_input_source(self, source: InputSource) -> None:
        await self._send_command("Z2", source.value)

    async def zone2_volume_up(self) -> None:
        await self._send_command("Z2", "UP")

    async def zone2_volume_down(self) -> None:
        await self._send_command("Z2", "DOWN")

    async def zone2_set_volume(self, db: float) -> None:
        """Set zone 2 volume in dB. Same scale as master volume."""
        await self._send_command("Z2", _volume_to_param(db))

    # -- Zone 3 commands (prefix: Z1 for AVR-3803/3805, Z3 for modern models) --

    async def zone3_power_on(self) -> None:
        await self._send_command(self._zone3_prefix, "ON")

    async def zone3_power_standby(self) -> None:
        await self._send_command(self._zone3_prefix, "OFF")

    async def zone3_select_input_source(self, source: InputSource) -> None:
        await self._send_command(self._zone3_prefix, source.value)

    async def zone3_volume_up(self) -> None:
        await self._send_command(self._zone3_prefix, "UP")

    async def zone3_volume_down(self) -> None:
        await self._send_command(self._zone3_prefix, "DOWN")

    async def zone3_set_volume(self, db: float) -> None:
        """Set zone 3 volume in dB. Same scale as master volume."""
        await self._send_command(self._zone3_prefix, _volume_to_param(db))

    # -- Probing --

    async def probe_sources(
        self, timeout: float | None = None
    ) -> frozenset[InputSource]:
        """Probe which input sources the receiver supports.

        Tries setting each input source and checks if the receiver accepts it.
        Restores the original input source when done.

        Warning: This will briefly switch through all input sources.
        Nothing should be playing during probing.
        """
        if not self._connected:
            raise ConnectionError("Not connected")

        if timeout is None:
            timeout = PROBE_TIMEOUT

        original = self._state.input_source
        available: set[InputSource] = set()

        # Current source is definitely available
        if original is not None:
            available.add(original)

        for source in InputSource:
            if source == original:
                continue
            resp = await self._send_and_wait("SI", source.value, timeout=timeout)
            if resp == source.value:
                available.add(source)

        # Restore original input source
        if original is not None:
            await self._send_and_wait("SI", original.value)

        return frozenset(available)

    # -- Internal methods --

    async def _send_and_wait(
        self, prefix: str, param: str, timeout: float | None = None
    ) -> str | None:
        """Send a command and wait for a response with the given prefix.

        Returns the response parameter, or None if no response within timeout.
        """
        if timeout is None:
            timeout = PROBE_TIMEOUT

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = _PendingQuery(prefix=prefix, future=future)
        self._pending_queries.append(pending)
        try:
            await self._send_command(prefix, param)
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError:
            return None
        finally:
            if pending in self._pending_queries:
                self._pending_queries.remove(pending)

    async def _send_command(self, command: str, parameter: str) -> None:
        """Send a command to the receiver."""
        assert self._writer is not None
        msg = f"{command}{parameter}\r".encode("ascii")
        _LOGGER.debug("Sending: %s", msg)
        try:
            async with self._write_lock:
                self._writer.write(msg)
                await self._writer.drain()
        except Exception:
            _LOGGER.exception("Error writing to serial port")
            await self._teardown()
            raise

    async def _query(self, command: str) -> str:
        """Send a query and wait for the response."""
        assert self._writer is not None
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = _PendingQuery(prefix=command, future=future)
        self._pending_queries.append(pending)

        try:
            msg = f"{command}?\r".encode("ascii")
            _LOGGER.debug("Querying: %s", msg)
            try:
                async with self._write_lock:
                    self._writer.write(msg)
                    await self._writer.drain()
            except Exception:
                _LOGGER.exception("Error writing to serial port")
                await self._teardown()
                raise
            return await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        finally:
            if pending in self._pending_queries:
                self._pending_queries.remove(pending)

    async def _teardown(self) -> None:
        """Tear down the connection after an error."""
        if not self._connected:
            return
        self._connected = False

        current = asyncio.current_task()

        if self._read_task is not None and self._read_task is not current:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        self._read_task = None

        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

        self._notify_subscribers()

    async def _read_loop(self) -> None:
        """Continuously read and process messages from the receiver."""
        assert self._reader is not None
        buf = b""

        while self._connected:
            try:
                data = await self._reader.read(256)
            except Exception:
                if not self._connected:
                    return
                _LOGGER.exception("Error reading from serial port")
                await self._teardown()
                return

            if not data:
                _LOGGER.warning("Serial connection closed")
                await self._teardown()
                return

            buf += data

            while CR in buf:
                line, buf = buf.split(CR, 1)
                if not line:
                    continue
                message = line.decode("ascii", errors="replace").strip()
                if message:
                    self._process_message(message)

    @staticmethod
    def _set_attr_value(target: object, attr: str, new_value: object) -> bool:
        """Set an attribute only when the value changed."""
        if getattr(target, attr) == new_value:
            return False
        setattr(target, attr, new_value)
        return True

    def _set_state_value(self, attr: str, new_value: object) -> bool:
        """Set a DenonState attribute only when the value changed."""
        return self._set_attr_value(self._state, attr, new_value)

    def _process_message(self, message: str) -> None:
        """Parse and process a message from the receiver."""
        _LOGGER.debug("Received: %s", message)

        if len(message) < 2:
            return

        prefix = message[:2]
        param = message[2:]

        if prefix == "MV" and param.startswith("MAX"):
            prefix = "MVMAX"
            param = param.removeprefix("MAX").strip()
        elif prefix == "MV" and param.startswith("MIN"):
            prefix = "MVMIN"
            param = param.removeprefix("MIN").strip()

        changed = False

        if prefix == "PW":
            if param == "ON":
                changed = self._set_state_value("power", True)
            elif param == "STANDBY":
                changed = self._set_state_value("power", False)
            else:
                _LOGGER.warning("Unknown power state: %s", param)

        elif prefix == "ZM":
            changed = self._set_state_value("main_zone", param == "ON")

        elif prefix == "MV":
            try:
                changed = self._set_state_value("volume", _parse_volume_param(param))
            except (ValueError, IndexError):
                _LOGGER.warning("Could not parse volume: %s", param)

        elif prefix == "MVMAX":
            try:
                changed = self._set_state_value(
                    "volume_max", _parse_volume_param(param)
                )
            except (ValueError, IndexError):
                _LOGGER.warning("Could not parse max volume: %s", param)

        elif prefix == "MVMIN":
            try:
                changed = self._set_state_value(
                    "volume_min", _parse_volume_param(param)
                )
            except (ValueError, IndexError):
                _LOGGER.warning("Could not parse min volume: %s", param)

        elif prefix == "MU":
            changed = self._set_state_value("mute", param == "ON")

        elif prefix == "SI":
            try:
                changed = self._set_state_value("input_source", InputSource(param))
            except ValueError:
                _LOGGER.warning("Unknown input source: %s", param)

        elif prefix == "MS":
            changed = self._set_state_value("surround_mode", param)

        elif prefix == "CV":
            channel, sep, val = param.partition(" ")
            if sep and val not in ("UP", "DOWN"):
                try:
                    new_value = _parse_channel_volume_param(val)
                    if self._state.channel_volumes.get(channel) != new_value:
                        self._state.channel_volumes[channel] = new_value
                        changed = True
                except (ValueError, IndexError):
                    _LOGGER.warning("Could not parse channel volume: %s", param)

        elif prefix == "PS":
            changed = self._process_ps_param(param)

        elif prefix == "SD":
            if param == "NO":
                changed = self._set_state_value("digital_input", None)
            else:
                try:
                    changed = self._set_state_value(
                        "digital_input", DigitalInputMode(param)
                    )
                except ValueError:
                    _LOGGER.warning("Unknown digital input mode: %s", param)

        elif prefix == "SV":
            if param in ("SOURCE", "OFF"):
                changed = self._set_state_value("video_select", None)
            else:
                try:
                    changed = self._set_state_value("video_select", InputSource(param))
                except ValueError:
                    _LOGGER.warning("Unknown video source: %s", param)

        elif prefix == "SR":
            if param == "SOURCE":
                changed = self._set_state_value("rec_select", None)
            else:
                try:
                    changed = self._set_state_value("rec_select", InputSource(param))
                except ValueError:
                    _LOGGER.warning("Unknown rec source: %s", param)

        elif prefix == "TF":
            if param not in ("UP", "DOWN"):
                changed = self._set_state_value("tuner_frequency", param)

        elif prefix == "TP":
            if param not in ("UP", "DOWN"):
                changed = self._set_state_value("tuner_preset", param)

        elif prefix == "TM":
            try:
                changed = self._set_state_value("tuner_band", TunerBand(param))
            except ValueError:
                try:
                    changed = self._set_state_value("tuner_mode", TunerMode(param))
                except ValueError:
                    _LOGGER.warning("Unknown tuner setting: %s", param)

        elif prefix == "Z2":
            changed = self._process_zone_param(self._state.zone2, param)

        elif prefix == "Z1":
            changed = self._process_zone_param(self._state.zone3, param)

        elif prefix == "Z3":
            changed = self._process_zone_param(self._state.zone3, param)

        # Resolve any pending queries for this prefix
        for pending in list(self._pending_queries):
            if pending.prefix == prefix and not pending.future.done():
                pending.future.set_result(param)

        if changed:
            self._notify_subscribers()

    def _process_ps_param(self, param: str) -> bool:
        """Process a PS (parameter setting) parameter. Returns True if state changed."""
        if param == "TONE DEFEAT ON":
            return self._set_state_value("tone_defeat", True)
        elif param == "TONE DEFEAT OFF":
            return self._set_state_value("tone_defeat", False)
        elif param.startswith("SB:"):
            try:
                return self._set_state_value("surround_back", SurroundBack(param[3:]))
            except ValueError:
                _LOGGER.warning("Unknown surround back mode: %s", param)
                return False
        elif param == "CINEMA EQ.ON":
            return self._set_state_value("cinema_eq", True)
        elif param == "CINEMA EQ.OFF":
            return self._set_state_value("cinema_eq", False)
        elif param.startswith("MODE : "):
            try:
                return self._set_state_value("mode_setting", ModeSetting(param[7:]))
            except ValueError:
                _LOGGER.warning("Unknown mode setting: %s", param)
                return False
        elif param.startswith("ROOM EQ:"):
            try:
                return self._set_state_value("room_eq", RoomEQ(param[8:]))
            except ValueError:
                _LOGGER.warning("Unknown room EQ mode: %s", param)
                return False
        else:
            _LOGGER.debug("Unknown PS parameter: %s", param)
            return False

    def _process_zone_param(self, zone: ZoneState, param: str) -> bool:
        """Process a Z2/Z1 (zone) parameter. Returns True if state changed."""
        if param == "ON":
            return self._set_attr_value(zone, "power", True)
        elif param == "OFF":
            return self._set_attr_value(zone, "power", False)
        elif param in ("UP", "DOWN"):
            return False
        elif _ZONE_VOL_RE.match(param):
            try:
                return self._set_attr_value(zone, "volume", _parse_volume_param(param))
            except (ValueError, IndexError):
                return False
        elif param.startswith("SLP"):
            return False
        elif param == "SOURCE":
            return self._set_attr_value(zone, "input_source", None)
        else:
            try:
                return self._set_attr_value(zone, "input_source", InputSource(param))
            except ValueError:
                _LOGGER.warning("Unknown zone source: %s", param)
                return False

    def _notify_subscribers(self, state: DenonState | None = None) -> None:
        """Notify all subscribers of a state change or disconnect (None)."""
        if state is None and self._connected:
            state = self._state.copy()
        for callback in self._subscribers:
            try:
                callback(state)
            except Exception:
                _LOGGER.exception("Error in state change callback %s", callback)
