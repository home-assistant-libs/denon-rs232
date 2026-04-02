"""Receiver implementation for denon_rs232."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

import serialx

from .const import (
    BAUD_RATE,
    COMMAND_TIMEOUT,
    CR,
    DigitalInputMode,
    InputSource,
    ModeSetting,
    MULTI_RESPONSE_DELAY,
    PROBE_TIMEOUT,
    RoomEQ,
    SurroundBack,
    TunerBand,
    TunerMode,
    ZONE3_PREFIX,
    _MULTI_RESPONSE_PREFIXES,
    _SINGLE_RESPONSE_PREFIXES,
)
from .players import MainPlayer, ZonePlayer
from .protocol import (
    PendingQuery,
    _ZONE_VOL_RE,
    parse_channel_volume_param,
    parse_volume_param,
)
from .state import MainZoneState, ReceiverState, ZoneState

if TYPE_CHECKING:
    from .models import ReceiverModel

_LOGGER = logging.getLogger(__name__)


StateCallback = Callable[[ReceiverState | None], None]


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
        self._state = ReceiverState()
        self.main = MainPlayer(self, self._state.main_zone)
        self.zone_2 = ZonePlayer(
            self,
            self._state.zone_2,
            power_command="Z2",
            power_standby_parameter="OFF",
            input_source_command="Z2",
            volume_command="Z2",
        )
        self.zone_3 = ZonePlayer(
            self,
            self._state.zone_3,
            power_command=self._zone3_prefix,
            power_standby_parameter="OFF",
            input_source_command=self._zone3_prefix,
            volume_command=self._zone3_prefix,
        )
        self._subscribers: list[StateCallback] = []
        self._pending_queries: list[PendingQuery] = []
        self._write_lock = asyncio.Lock()
        self._connected = False

    @property
    def model(self) -> ReceiverModel | None:
        """Return the receiver model, if set."""
        return self._model

    @property
    def state(self) -> ReceiverState:
        """Return a copy of the current state."""
        return self._state.copy()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def power(self) -> bool | None:
        """Return the current receiver chassis power state."""
        return self._state.power

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

    async def power_on(self) -> None:
        """Turn the receiver chassis on."""
        await self._send_command("PW", "ON")

    async def power_standby(self) -> None:
        """Put the receiver chassis in standby."""
        await self._send_command("PW", "STANDBY")

    async def query_power(self) -> bool:
        """Query the receiver chassis power state."""
        resp = await self._query("PW")
        if resp == "ON":
            return True
        if resp == "STANDBY":
            return False
        raise ValueError(f"Unknown power state: {resp}")

    async def query_state(self) -> None:
        """Query all initial state from the receiver."""
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

        for prefix in _MULTI_RESPONSE_PREFIXES:
            if prefix == "Z1":
                if self._model is not None and self._model.zone3_prefix is None:
                    continue
                prefix = self._zone3_prefix

            if prefix in unsupported_queries:
                continue

            await self._send_command(prefix, "?")
            await asyncio.sleep(MULTI_RESPONSE_DELAY)

    async def probe_sources(
        self, timeout: float | None = None
    ) -> frozenset[InputSource]:
        """Probe which input sources the receiver supports."""
        if not self._connected:
            raise ConnectionError("Not connected")

        if timeout is None:
            timeout = PROBE_TIMEOUT

        original = self._state.main_zone.input_source
        available: set[InputSource] = set()

        if original is not None:
            available.add(original)

        for source in InputSource:
            if source == original:
                continue
            resp = await self._send_and_wait("SI", source.value, timeout=timeout)
            if resp == source.value:
                available.add(source)

        if original is not None:
            await self._send_and_wait("SI", original.value)

        return frozenset(available)

    async def _send_and_wait(
        self, prefix: str, param: str, timeout: float | None = None
    ) -> str | None:
        """Send a command and wait for a response with the given prefix."""
        if timeout is None:
            timeout = PROBE_TIMEOUT

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = PendingQuery(prefix=prefix, future=future)
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
        pending = PendingQuery(prefix=command, future=future)
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
        """Set a MainZoneState attribute only when the value changed."""
        return self._set_attr_value(self._state.main_zone, attr, new_value)

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
                changed = self._set_attr_value(self._state, "power", True)
            elif param == "STANDBY":
                changed = self._set_attr_value(self._state, "power", False)
            else:
                _LOGGER.warning("Unknown power state: %s", param)

        elif prefix == "ZM":
            changed = self._set_state_value("power", param == "ON")

        elif prefix == "MV":
            try:
                changed = self._set_state_value("volume", parse_volume_param(param))
            except (ValueError, IndexError):
                _LOGGER.warning("Could not parse volume: %s", param)

        elif prefix == "MVMAX":
            try:
                changed = self._set_state_value("volume_max", parse_volume_param(param))
            except (ValueError, IndexError):
                _LOGGER.warning("Could not parse max volume: %s", param)

        elif prefix == "MVMIN":
            try:
                changed = self._set_state_value("volume_min", parse_volume_param(param))
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
                    new_value = parse_channel_volume_param(val)
                    if self._state.main_zone.channel_volumes.get(channel) != new_value:
                        self._state.main_zone.channel_volumes[channel] = new_value
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
                        "digital_input",
                        DigitalInputMode(param),
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
            changed = self._process_zone_param(self._state.zone_2, param)

        elif prefix == "Z1":
            changed = self._process_zone_param(self._state.zone_3, param)

        elif prefix == "Z3":
            changed = self._process_zone_param(self._state.zone_3, param)

        for pending in list(self._pending_queries):
            if pending.prefix == prefix and not pending.future.done():
                pending.future.set_result(param)

        if changed:
            self._notify_subscribers()

    def _process_ps_param(self, param: str) -> bool:
        """Process a PS (parameter setting) parameter."""
        if param == "TONE DEFEAT ON":
            return self._set_state_value("tone_defeat", True)
        if param == "TONE DEFEAT OFF":
            return self._set_state_value("tone_defeat", False)
        if param.startswith("SB:"):
            try:
                return self._set_state_value("surround_back", SurroundBack(param[3:]))
            except ValueError:
                _LOGGER.warning("Unknown surround back mode: %s", param)
                return False
        if param == "CINEMA EQ.ON":
            return self._set_state_value("cinema_eq", True)
        if param == "CINEMA EQ.OFF":
            return self._set_state_value("cinema_eq", False)
        if param.startswith("MODE : "):
            try:
                return self._set_state_value("mode_setting", ModeSetting(param[7:]))
            except ValueError:
                _LOGGER.warning("Unknown mode setting: %s", param)
                return False
        if param.startswith("ROOM EQ:"):
            try:
                return self._set_state_value("room_eq", RoomEQ(param[8:]))
            except ValueError:
                _LOGGER.warning("Unknown room EQ mode: %s", param)
                return False

        _LOGGER.debug("Unknown PS parameter: %s", param)
        return False

    def _process_zone_param(self, zone: ZoneState, param: str) -> bool:
        """Process a Z2/Z1/Z3 parameter."""
        if param == "ON":
            return self._set_attr_value(zone, "power", True)
        if param == "OFF":
            return self._set_attr_value(zone, "power", False)
        if param in ("UP", "DOWN"):
            return False
        if _ZONE_VOL_RE.match(param):
            try:
                return self._set_attr_value(zone, "volume", parse_volume_param(param))
            except (ValueError, IndexError):
                return False
        if param.startswith("SLP"):
            return False
        if param == "SOURCE":
            return self._set_attr_value(zone, "input_source", None)
        try:
            return self._set_attr_value(zone, "input_source", InputSource(param))
        except ValueError:
            _LOGGER.warning("Unknown zone source: %s", param)
            return False

    def _notify_subscribers(self) -> None:
        """Notify all subscribers of a state change or disconnect."""
        state = self._state.copy() if self._connected else None
        for callback in self._subscribers:
            try:
                callback(state)
            except Exception:
                _LOGGER.exception("Error in state change callback %s", callback)
