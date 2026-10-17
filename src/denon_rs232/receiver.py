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
    POWER_ON_DELAY,
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


class DenonConnectionError(ConnectionError):
    """Raised when the serial connection is not open or is lost."""


class DenonReceiver:
    """Async controller for a Denon receiver over RS232."""

    def __init__(
        self,
        port: str,
        zone3_prefix: str = ZONE3_PREFIX,
        model: ReceiverModel | None = None,
        zone_half_db_volume_step: bool = True,
    ) -> None:
        self._port = port
        self._model = model
        self._zone3_prefix = (
            model.zone3_prefix or ZONE3_PREFIX if model else zone3_prefix
        )
        self._zone_half_db_volume_step = (
            model.zone_half_db_volume_step if model else zone_half_db_volume_step
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: serialx.SerialStreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._teardown_task: asyncio.Task | None = None
        self._power_on_task: asyncio.Task | None = None
        self._state = ReceiverState()
        self.main = MainPlayer(self, self._state.main_zone)
        self.zone_2 = ZonePlayer(
            self,
            self._state.zone_2,
            power_command="Z2",
            power_standby_parameter="OFF",
            input_source_command="Z2",
            volume_command="Z2",
            half_db_volume_step = self._zone_half_db_volume_step,
        )
        self.zone_3 = ZonePlayer(
            self,
            self._state.zone_3,
            power_command=self._zone3_prefix,
            power_standby_parameter="OFF",
            input_source_command=self._zone3_prefix,
            volume_command=self._zone3_prefix,
            half_db_volume_step = self._zone_half_db_volume_step,
        )
        self._subscribers: list[StateCallback] = []
        self._pending_queries: list[PendingQuery] = []
        self._write_lock = asyncio.Lock()
        self._connected = False
        # Number of query_state() calls running. A wake-up query can still be
        # running when another query_state() starts.
        self._batching = 0
        self._batch_changed = False

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
        """Subscribe to state changes. Returns an unsubscribe function.

        Calling the unsubscribe function more than once is a no-op.
        """
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    async def connect(self) -> None:
        """Open the serial connection, verify, and query all state.

        Raises ``RuntimeError`` if already connected. Call ``disconnect()``
        first to reconnect. Raises ``DenonConnectionError`` if the port
        cannot be opened.
        """
        if self._connected:
            raise RuntimeError("Already connected")
        try:
            self._reader, self._writer = await serialx.open_serial_connection(
                self._port,
                baudrate=BAUD_RATE,
            )
        except serialx.SerialException as err:
            raise DenonConnectionError(str(err)) from err
        self._connected = True
        self._read_task = asyncio.create_task(self._read_loop())
        self._read_task.add_done_callback(self._on_read_task_done)

        try:
            await self.query_power()
        except TimeoutError:
            await self.disconnect()
            # An ESPHome proxy URL can carry its API key in the query string.
            raise ConnectionError(
                f"No response from receiver on {self._port.split('?', 1)[0]}"
            ) from None
        except BaseException:
            # Also on cancellation, so that the port is not left open.
            await self._teardown()
            raise

        _LOGGER.info("Connected to Denon receiver on %s", self._port.split("?", 1)[0])

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
        """Query all initial state from the receiver.

        How much a receiver in standby answers differs per model, and every
        unanswered query costs a full COMMAND_TIMEOUT. While in standby the
        queries therefore stop at the first one that goes unanswered.

        Subscriber notifications are suppressed while the queries run and
        fired once at the end if any value changed.
        """
        unsupported_queries = (
            self._model.unsupported_startup_queries if self._model is not None else ()
        )
        self._cancel_power_on_query()
        self._batching += 1
        try:
            # The known power state can be stale, so refresh it before deciding
            # which queries the receiver is able to answer.
            try:
                await self._query("PW")
            except TimeoutError:
                pass
            standby = self._state.power is False

            for prefix in _SINGLE_RESPONSE_PREFIXES:
                if prefix == "PW" or prefix in unsupported_queries:
                    continue
                try:
                    await self._query(prefix)
                except TimeoutError:
                    if standby:
                        break

            # These are not waited on, so they stay worth sending in standby.
            for prefix in _MULTI_RESPONSE_PREFIXES:
                if prefix == "Z1":
                    if self._model is not None and self._model.zone3_prefix is None:
                        continue
                    prefix = self._zone3_prefix

                if prefix in unsupported_queries:
                    continue

                await self._send_command(prefix, "?")
                await asyncio.sleep(MULTI_RESPONSE_DELAY)
        finally:
            self._batching -= 1

        # Overlapping calls report their changes once, when the last one ends.
        if not self._batching and self._batch_changed:
            self._batch_changed = False
            self._notify_subscribers()

    async def probe_sources(
        self, timeout: float | None = None
    ) -> frozenset[InputSource]:
        """Probe which input sources the receiver supports."""
        if not self._connected:
            raise DenonConnectionError("Not connected")

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
        if not self._connected or self._writer is None:
            raise DenonConnectionError("Not connected")
        msg = f"{command}{parameter}\r".encode("ascii")
        _LOGGER.debug("Sending: %s", msg)
        try:
            async with self._write_lock:
                self._writer.write(msg)
                await self._writer.drain()
        except Exception as err:
            _LOGGER.exception("Error writing to serial port")
            await self._teardown()
            raise DenonConnectionError(f"Error writing to serial port: {err}") from err

    async def _query(self, command: str, params: tuple[str, ...] | None = None) -> str:
        """Send a query and wait for the response.

        If ``params`` is given, responses with another parameter are ignored.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = PendingQuery(prefix=command, future=future, params=params)
        self._pending_queries.append(pending)

        try:
            await self._send_command(command, "?")
            return await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        finally:
            if pending in self._pending_queries:
                self._pending_queries.remove(pending)

    def _schedule_power_on_query(self) -> None:
        """Re-query state after the receiver leaves standby.

        Queries skipped while it was in standby are only answerable now, and
        the receiver needs a moment before it responds to them.
        """
        if self._power_on_task is not None and not self._power_on_task.done():
            return
        self._power_on_task = asyncio.create_task(self._delayed_query_state())

    def _cancel_power_on_query(self) -> None:
        """Drop a pending wake-up query.

        The wake-up query itself calls query_state(), which cancels here in
        turn, so the task must never cancel itself. The reference is kept
        until then so a teardown can stop a wake-up query that is running.
        """
        if self._power_on_task is None:
            return
        if self._power_on_task is not asyncio.current_task():
            self._power_on_task.cancel()
        self._power_on_task = None

    async def _delayed_query_state(self) -> None:
        """Wait for the receiver to wake up, then query its state."""
        await asyncio.sleep(POWER_ON_DELAY)
        try:
            await self.query_state()
        except Exception:
            _LOGGER.exception("Error querying state after power on")

    async def _teardown(self) -> None:
        """Tear down the connection after an error.

        The reader, writer and read task are dropped before anything is
        awaited, so a failure while closing an already-broken transport
        cannot leave a dead stream behind for later commands to write to.
        """
        if not self._connected:
            return
        self._connected = False

        # The receiver can no longer answer, so fail waiting queries now
        # instead of letting them run into their timeout.
        for pending in self._pending_queries:
            if not pending.future.done():
                pending.future.set_exception(DenonConnectionError("Connection lost"))
                # A query whose write failed never awaits its future, so
                # mark the error as retrieved to avoid an asyncio warning.
                pending.future.exception()

        read_task, self._read_task = self._read_task, None
        writer, self._writer = self._writer, None
        self._reader = None

        self._cancel_power_on_query()

        if read_task is not None and read_task is not asyncio.current_task():
            read_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                pass

        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                # The transport is already gone (e.g. the ESPHome proxy lost
                # its API connection); there is nothing left to clean up.
                _LOGGER.debug("Error closing serial port", exc_info=True)

        self._notify_subscribers()

    def _on_read_task_done(self, task: asyncio.Task) -> None:
        """Tear down the connection if the read loop died with an error."""
        if task.cancelled() or (err := task.exception()) is None:
            return
        _LOGGER.error("Read loop failed", exc_info=err)
        if self._read_task is not task:
            return
        # _teardown() would await the task and re-raise its error.
        self._read_task = None
        self._teardown_task = asyncio.get_running_loop().create_task(self._teardown())

    async def _read_loop(self) -> None:
        """Continuously read and process messages from the receiver."""
        reader = self._reader
        assert reader is not None
        buf = b""

        while self._connected:
            try:
                data = await reader.read(256)
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
                was_standby = self._state.power is False
                changed = self._set_attr_value(self._state, "power", True)
                if was_standby and not self._batching:
                    self._schedule_power_on_query()
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
            if (
                pending.prefix == prefix
                and (pending.params is None or param in pending.params)
                and not pending.future.done()
            ):
                pending.future.set_result(param)

        if changed:
            if self._batching:
                self._batch_changed = True
            else:
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
        # Iterate a copy: a subscriber may unsubscribe while being notified.
        for callback in list(self._subscribers):
            try:
                callback(state)
            except Exception:
                _LOGGER.exception("Error in state change callback %s", callback)
