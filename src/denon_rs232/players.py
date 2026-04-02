"""Player abstractions for denon_rs232."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from .const import (
    DigitalInputMode,
    InputSource,
    ModeSetting,
    RoomEQ,
    SurroundBack,
    TunerBand,
    TunerMode,
)
from .protocol import (
    channel_volume_to_param,
    parse_volume_param,
    volume_to_param,
)
from .state import MainZoneState, ZoneState

if TYPE_CHECKING:
    from .receiver import DenonReceiver


class _BasePlayer:
    """Shared stateful control surface for the main receiver and zones."""

    def __init__(
        self,
        receiver: DenonReceiver,
        state: ZoneState,
        *,
        power_command: str,
        power_standby_parameter: str,
        input_source_command: str,
        volume_command: str,
    ) -> None:
        self._receiver = receiver
        self._state = state
        self._power_command = power_command
        self._power_standby_parameter = power_standby_parameter
        self._input_source_command = input_source_command
        self._volume_command = volume_command

    @property
    def power(self) -> bool | None:
        """Return the current power state for this player."""
        return self._state.power

    @property
    def input_source(self) -> InputSource | None:
        """Return the current input source for this player."""
        return self._state.input_source

    @property
    def volume(self) -> float | None:
        """Return the current volume for this player."""
        return self._state.volume

    @property
    def volume_min(self) -> float | None:
        """Return the shared minimum volume."""
        return self._receiver._state.main_zone.volume_min

    @property
    def volume_max(self) -> float | None:
        """Return the shared maximum volume."""
        return self._receiver._state.main_zone.volume_max

    async def power_on(self) -> None:
        """Turn this player on."""
        await self._receiver._send_command(self._power_command, "ON")

    async def power_standby(self) -> None:
        """Turn this player off/standby."""
        await self._receiver._send_command(
            self._power_command,
            self._power_standby_parameter,
        )

    async def select_input_source(self, source: InputSource) -> None:
        """Select an input source for this player."""
        await self._receiver._send_command(
            self._input_source_command,
            source.value,
        )

    async def volume_up(self) -> None:
        """Increase this player's volume."""
        await self._receiver._send_command(self._volume_command, "UP")

    async def volume_down(self) -> None:
        """Decrease this player's volume."""
        await self._receiver._send_command(self._volume_command, "DOWN")

    async def set_volume(self, db: float) -> None:
        """Set this player's volume in dB."""
        await self._receiver._send_command(
            self._volume_command,
            volume_to_param(db),
        )


class MainPlayer(_BasePlayer):
    """Stateful control surface for the receiver's main output."""

    _state: MainZoneState

    def __init__(self, receiver: DenonReceiver, state: MainZoneState) -> None:
        super().__init__(
            receiver,
            state,
            power_command="ZM",
            power_standby_parameter="OFF",
            input_source_command="SI",
            volume_command="MV",
        )

    @property
    def mute(self) -> bool | None:
        """Return the current mute state."""
        return self._state.mute

    async def mute_on(self) -> None:
        """Mute the main player."""
        await self._receiver._send_command("MU", "ON")

    async def mute_off(self) -> None:
        """Unmute the main player."""
        await self._receiver._send_command("MU", "OFF")

    async def query_power(self) -> bool:
        """Query the main-zone power state."""
        resp = await self._receiver._query("ZM")
        return resp == "ON"

    async def main_zone_on(self) -> None:
        """Turn the main listening zone on."""
        await self.power_on()

    async def main_zone_off(self) -> None:
        """Turn the main listening zone off."""
        await self.power_standby()

    async def query_main_zone(self) -> bool:
        """Query the main listening zone power state."""
        return await self.query_power()

    async def query_volume(self) -> float:
        """Query the current master volume."""
        resp = await self._receiver._query("MV")
        return parse_volume_param(resp)

    async def channel_volume_up(self, channel: str) -> None:
        """Adjust a channel volume up."""
        await self._receiver._send_command("CV", f"{channel} UP")

    async def channel_volume_down(self, channel: str) -> None:
        """Adjust a channel volume down."""
        await self._receiver._send_command("CV", f"{channel} DOWN")

    async def set_channel_volume(self, channel: str, db: float) -> None:
        """Set a channel volume in dB."""
        await self._receiver._send_command(
            "CV",
            f"{channel} {channel_volume_to_param(db)}",
        )

    async def query_mute(self) -> bool:
        """Query the current mute state."""
        resp = await self._receiver._query("MU")
        return resp == "ON"

    async def query_input_source(self) -> InputSource:
        """Query the active input source."""
        return InputSource(await self._receiver._query("SI"))

    async def set_surround_mode(self, mode: str) -> None:
        """Set surround mode."""
        await self._receiver._send_command("MS", mode)

    async def query_surround_mode(self) -> str:
        """Query the current surround mode."""
        return await self._receiver._query("MS")

    async def tone_defeat_on(self) -> None:
        """Enable tone defeat."""
        await self._receiver._send_command("PS", "TONE DEFEAT ON")

    async def tone_defeat_off(self) -> None:
        """Disable tone defeat."""
        await self._receiver._send_command("PS", "TONE DEFEAT OFF")

    async def set_surround_back(self, mode: SurroundBack) -> None:
        """Set surround back mode."""
        await self._receiver._send_command("PS", f"SB:{mode.value}")

    async def cinema_eq_on(self) -> None:
        """Enable cinema EQ."""
        await self._receiver._send_command("PS", "CINEMA EQ.ON")

    async def cinema_eq_off(self) -> None:
        """Disable cinema EQ."""
        await self._receiver._send_command("PS", "CINEMA EQ.OFF")

    async def set_mode_setting(self, mode: ModeSetting) -> None:
        """Set decoder mode."""
        await self._receiver._send_command("PS", f"MODE : {mode.value}")

    async def set_room_eq(self, mode: RoomEQ) -> None:
        """Set room EQ."""
        await self._receiver._send_command("PS", f"ROOM EQ:{mode.value}")

    async def set_digital_input(self, mode: DigitalInputMode) -> None:
        """Set digital input mode."""
        await self._receiver._send_command("SD", mode.value)

    async def query_digital_input(self) -> DigitalInputMode | None:
        """Query the current digital input mode."""
        param = await self._receiver._query("SD")
        if param == "NO":
            return None
        return DigitalInputMode(param)

    async def set_video_select(self, source: InputSource) -> None:
        """Set video select source."""
        await self._receiver._send_command("SV", source.value)

    async def cancel_video_select(self) -> None:
        """Cancel video select."""
        await self._receiver._send_command("SV", "SOURCE")

    async def query_video_select(self) -> InputSource | None:
        """Query the active video select source."""
        param = await self._receiver._query("SV")
        if param in ("SOURCE", "OFF"):
            return None
        return InputSource(param)

    async def set_rec_select(self, source: InputSource) -> None:
        """Set recording source."""
        await self._receiver._send_command("SR", source.value)

    async def cancel_rec_select(self) -> None:
        """Cancel recording source selection."""
        await self._receiver._send_command("SR", "SOURCE")

    async def query_rec_select(self) -> InputSource:
        """Query the current recording source."""
        return InputSource(await self._receiver._query("SR"))

    async def tuner_frequency_up(self) -> None:
        """Increment tuner frequency."""
        await self._receiver._send_command("TF", "UP")

    async def tuner_frequency_down(self) -> None:
        """Decrement tuner frequency."""
        await self._receiver._send_command("TF", "DOWN")

    async def set_tuner_frequency(self, freq: str) -> None:
        """Set tuner frequency directly."""
        await self._receiver._send_command("TF", freq)

    async def query_tuner_frequency(self) -> str:
        """Query the current tuner frequency."""
        return await self._receiver._query("TF")

    async def tuner_preset_up(self) -> None:
        """Increment tuner preset."""
        await self._receiver._send_command("TP", "UP")

    async def tuner_preset_down(self) -> None:
        """Decrement tuner preset."""
        await self._receiver._send_command("TP", "DOWN")

    async def set_tuner_preset(self, preset: str) -> None:
        """Set tuner preset directly."""
        await self._receiver._send_command("TP", preset)

    async def query_tuner_preset(self) -> str:
        """Query the current tuner preset."""
        return await self._receiver._query("TP")

    async def set_tuner_band(self, band: TunerBand) -> None:
        """Set tuner band."""
        await self._receiver._send_command("TM", band.value)

    async def set_tuner_mode(self, mode: TunerMode) -> None:
        """Set tuning mode."""
        await self._receiver._send_command("TM", mode.value)


class ZonePlayer(_BasePlayer):
    """Stateful control surface for a Denon zone."""


DenonPlayer: TypeAlias = MainPlayer | ZonePlayer
