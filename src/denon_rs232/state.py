"""Runtime state dataclasses for denon_rs232."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .const import (
    DigitalInputMode,
    InputSource,
    ModeSetting,
    RoomEQ,
    SurroundBack,
    TunerBand,
    TunerMode,
)


@dataclass
class ZoneState:
    """State for Zone 2 or Zone 3."""

    power: bool | None = None
    input_source: InputSource | None = None
    volume: float | None = None

    def copy(self) -> ZoneState:
        return replace(self)


@dataclass
class MainZoneState(ZoneState):
    """State for the main listening zone.

    Extends ZoneState (power, input_source, volume) with main-zone-only
    fields such as mute, surround mode, channel volumes, and tuner state.
    """

    mute: bool | None = None
    volume_max: float | None = None
    volume_min: float | None = None
    #: Surround mode name. Kept as str because the receiver returns many
    #: combined mode names (e.g. "DOLBY D+PL2X C", "M CH IN+PL2X M").
    surround_mode: str | None = None

    # Channel volumes. Event-only. Keyed by channel: FL, FR, C, SW, SL, SR, SBL, SBR, SB.
    channel_volumes: dict[str, float] = field(default_factory=dict)

    # Parameter settings. Event-only. Populated from PS? responses and PS events.
    tone_defeat: bool | None = None
    surround_back: SurroundBack | None = None
    cinema_eq: bool | None = None
    mode_setting: ModeSetting | None = None
    #: Event-only. The receiver does not include room_eq in PS? responses.
    room_eq: RoomEQ | None = None

    # Digital / video / rec (queryable)
    digital_input: DigitalInputMode | None = None
    video_select: InputSource | None = None
    rec_select: InputSource | None = None

    # Tuner (frequency and preset are queryable; band and mode are event-only)
    tuner_frequency: str | None = None
    tuner_preset: str | None = None
    #: Event-only. Updated from TM events.
    tuner_band: TunerBand | None = None
    #: Event-only. Updated from TM events. AUTO or MANUAL.
    tuner_mode: TunerMode | None = None

    def copy(self) -> MainZoneState:
        return replace(self, channel_volumes=dict(self.channel_volumes))


@dataclass
class ReceiverState:
    """Current state of the Denon receiver."""

    power: bool | None = None
    main_zone: MainZoneState = field(default_factory=MainZoneState)
    zone_2: ZoneState = field(default_factory=ZoneState)
    zone_3: ZoneState = field(default_factory=ZoneState)

    def copy(self) -> ReceiverState:
        return replace(
            self,
            main_zone=self.main_zone.copy(),
            zone_2=replace(self.zone_2),
            zone_3=replace(self.zone_3),
        )
