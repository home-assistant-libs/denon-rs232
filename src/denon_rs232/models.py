"""Known Denon receiver models and their capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from .const import DigitalInputMode, InputSource


@dataclass(frozen=True)
class ReceiverModel:
    """Known capabilities of a Denon receiver model."""

    name: str
    input_sources: frozenset[InputSource]
    digital_inputs: frozenset[DigitalInputMode]
    surround_modes: tuple[str, ...]
    #: Zone 3 command prefix: "Z1" for legacy (AVR-3803/3805), "Z3" for modern.
    #: None means the model has no Zone 3.
    zone3_prefix: str | None = None
    #: Query prefixes to skip during connect() because the receiver does not
    #: answer them even though older models may.
    unsupported_startup_queries: frozenset[str] = frozenset()


# -- Common source/digital sets used across multiple models --

_LEGACY_SOURCES = frozenset(
    {
        InputSource.PHONO,
        InputSource.CD,
        InputSource.TUNER,
        InputSource.DVD,
        InputSource.VDP,
        InputSource.TV,
        InputSource.DBS_SAT,
        InputSource.VCR_1,
        InputSource.VCR_2,
        InputSource.V_AUX,
        InputSource.CDR_TAPE1,
    }
)

_GEN1_DIGITAL = frozenset(
    {
        DigitalInputMode.AUTO,
        DigitalInputMode.PCM,
        DigitalInputMode.DTS,
        DigitalInputMode.ANALOG,
        DigitalInputMode.EXT_IN_1,
    }
)

_GEN1_DIGITAL_FULL = _GEN1_DIGITAL | frozenset(
    {
        DigitalInputMode.RF,
        DigitalInputMode.EXT_IN_2,
    }
)

_GEN2_DIGITAL = frozenset(
    {
        DigitalInputMode.AUTO,
        DigitalInputMode.HDMI,
        DigitalInputMode.DIGITAL,
        DigitalInputMode.ANALOG,
        DigitalInputMode.EXT_IN_1,
    }
)

_GEN3_DIGITAL = frozenset(
    {
        DigitalInputMode.AUTO,
        DigitalInputMode.HDMI,
        DigitalInputMode.DIGITAL,
        DigitalInputMode.ANALOG,
    }
)

# -- Common surround mode sets --

_COMMON_SURROUND = (
    "DIRECT",
    "PURE DIRECT",
    "STEREO",
    "MULTI CH IN",
    "MULTI CH DIRECT",
    "MULTI CH PURE D",
)

_DSP_SURROUND = (
    "WIDE SCREEN",
    "SUPER STADIUM",
    "ROCK ARENA",
    "JAZZ CLUB",
    "CLASSIC CONCERT",
    "MONO MOVIE",
    "MATRIX",
    "VIDEO GAME",
    "VIRTUAL",
)

_LEGACY_SURROUND = (
    *_COMMON_SURROUND,
    "DOLBY PRO LOGIC",
    "DOLBY PL2",
    "DOLBY PL2X",
    "DOLBY DIGITAL",
    "DOLBY D EX",
    "DTS NEO:6",
    "DTS SURROUND",
    "DTS ES DSCRT6.1",
    "DTS ES MTRX6.1",
    "5CH STEREO",
    "7CH STEREO",
    *_DSP_SURROUND,
)

_TRANSITION_SURROUND = (
    *_COMMON_SURROUND,
    "AUTO",
    "DOLBY PRO LOGIC",
    "DOLBY PL2",
    "DOLBY PL2X",
    "DOLBY DIGITAL",
    "DOLBY D EX",
    "DOLBY DIGITAL+",
    "DOLBY HD",
    "DTS NEO:6",
    "DTS SURROUND",
    "DTS ES DSCRT6.1",
    "DTS ES MTRX6.1",
    "DTS96/24",
    "MCH STEREO",
    "5CH STEREO",
    "7CH STEREO",
    *_DSP_SURROUND,
)

_MODERN_SURROUND = (
    *_COMMON_SURROUND,
    "AUTO",
    "DOLBY DIGITAL",
    "DOLBY DIGITAL+",
    "DOLBY HD",
    "DOLBY SURROUND",
    "DTS SURROUND",
    "DTS HD",
    "DTS HD MSTR",
    "MCH STEREO",
    *_DSP_SURROUND,
)


# -- Legacy era (~2003-2005) --

AVR_3803 = ReceiverModel(
    name="AVR-3803 / AVC-3570 / AVR-2803",
    input_sources=_LEGACY_SOURCES
    | frozenset(
        {
            InputSource.VCR_3,
            InputSource.MD_TAPE2,
        }
    ),
    digital_inputs=_GEN1_DIGITAL_FULL,
    surround_modes=_LEGACY_SURROUND,
    zone3_prefix="Z1",
)

AVR_3805 = ReceiverModel(
    name="AVR-3805 / AVC-3890",
    input_sources=_LEGACY_SOURCES,
    digital_inputs=_GEN1_DIGITAL,
    surround_modes=_LEGACY_SURROUND,
    zone3_prefix="Z1",
)

AVR_987 = ReceiverModel(
    name="AVR-987",
    input_sources=_LEGACY_SOURCES
    | frozenset(
        {
            InputSource.HDP,
            InputSource.DVR,
            InputSource.TV_CBL,
            InputSource.NET_USB,
        }
    ),
    digital_inputs=_GEN1_DIGITAL,
    surround_modes=_LEGACY_SURROUND,
    zone3_prefix="Z3",
)


# -- Transition era (~2006-2009) --

AVR_2308CI = ReceiverModel(
    name="AVR-2308CI / AVC-2308",
    input_sources=_LEGACY_SOURCES
    | frozenset(
        {
            InputSource.HDP,
            InputSource.DVR,
            InputSource.TV_CBL,
        }
    ),
    digital_inputs=_GEN1_DIGITAL,
    surround_modes=_TRANSITION_SURROUND,
)

AVR_2808CI = ReceiverModel(
    name="AVR-2808CI / AVC-2808 / AVR-988",
    input_sources=_LEGACY_SOURCES
    | frozenset(
        {
            InputSource.HDP,
            InputSource.DVR,
            InputSource.TV_CBL,
            InputSource.NET_USB,
        }
    ),
    digital_inputs=_GEN1_DIGITAL,
    surround_modes=_TRANSITION_SURROUND,
    zone3_prefix="Z3",
)

AVR_4308CI = ReceiverModel(
    name="AVR-4308CI",
    input_sources=_LEGACY_SOURCES
    | frozenset(
        {
            InputSource.HDP,
            InputSource.DVR,
            InputSource.TV_CBL,
            InputSource.NET_USB,
            InputSource.DOCK,
            InputSource.HDRADIO,
            InputSource.XM,
            InputSource.IPOD,
        }
    ),
    digital_inputs=_GEN1_DIGITAL,
    surround_modes=_TRANSITION_SURROUND,
    zone3_prefix="Z3",
)

AVR_3310CI = ReceiverModel(
    name="AVR-3310CI / AVR-990 / AVC-3310",
    input_sources=frozenset(
        {
            InputSource.PHONO,
            InputSource.CD,
            InputSource.TUNER,
            InputSource.DVD,
            InputSource.TV,
            InputSource.SAT_CBL,
            InputSource.DVR,
            InputSource.HDP,
            InputSource.V_AUX,
            InputSource.NET_USB,
            InputSource.DOCK,
            InputSource.HDRADIO,
            InputSource.IPOD,
        }
    ),
    digital_inputs=_GEN2_DIGITAL,
    surround_modes=_TRANSITION_SURROUND,
    zone3_prefix="Z3",
)


# -- Modern era (~2012+) --

AVR_X1000 = ReceiverModel(
    name="AVR-X1000 / AVR-E300",
    input_sources=frozenset(
        {
            InputSource.CD,
            InputSource.TUNER,
            InputSource.DVD,
            InputSource.BD,
            InputSource.TV,
            InputSource.SAT_CBL,
            InputSource.MPLAY,
            InputSource.GAME,
            InputSource.V_AUX,
            InputSource.AUX1,
            InputSource.NET,
            InputSource.USB_IPOD,
            InputSource.PANDORA,
            InputSource.SIRIUSXM,
            InputSource.SPOTIFY,
            InputSource.FLICKR,
            InputSource.IRADIO,
            InputSource.SERVER,
            InputSource.FAVORITES,
            InputSource.LASTFM,
        }
    ),
    digital_inputs=_GEN3_DIGITAL,
    surround_modes=_MODERN_SURROUND,
)

AVR_X4000 = ReceiverModel(
    name="AVR-X4000",
    input_sources=frozenset(
        {
            InputSource.PHONO,
            InputSource.CD,
            InputSource.TUNER,
            InputSource.DVD,
            InputSource.BD,
            InputSource.TV,
            InputSource.SAT_CBL,
            InputSource.MPLAY,
            InputSource.GAME,
            InputSource.V_AUX,
            InputSource.AUX1,
            InputSource.AUX2,
            InputSource.NET,
            InputSource.BT,
            InputSource.USB_IPOD,
            InputSource.PANDORA,
            InputSource.SIRIUSXM,
            InputSource.SPOTIFY,
            InputSource.FLICKR,
            InputSource.IRADIO,
            InputSource.SERVER,
            InputSource.FAVORITES,
            InputSource.LASTFM,
            InputSource.HDRADIO,
        }
    ),
    digital_inputs=_GEN3_DIGITAL,
    surround_modes=_MODERN_SURROUND,
    zone3_prefix="Z3",
)

AVR_X4200W = ReceiverModel(
    name="AVR-X4200W / AVR-X3200W / AVR-X2200W / AVR-X1200W",
    input_sources=frozenset(
        {
            InputSource.PHONO,
            InputSource.CD,
            InputSource.TUNER,
            InputSource.DVD,
            InputSource.BD,
            InputSource.TV,
            InputSource.SAT_CBL,
            InputSource.MPLAY,
            InputSource.GAME,
            InputSource.V_AUX,
            InputSource.AUX1,
            InputSource.AUX2,
            InputSource.NET,
            InputSource.BT,
            InputSource.USB_IPOD,
            InputSource.PANDORA,
            InputSource.SIRIUSXM,
            InputSource.SPOTIFY,
            InputSource.FLICKR,
            InputSource.IRADIO,
            InputSource.SERVER,
            InputSource.FAVORITES,
            InputSource.LASTFM,
            InputSource.HDRADIO,
        }
    ),
    digital_inputs=_GEN3_DIGITAL,
    surround_modes=(
        *_MODERN_SURROUND,
        "DOLBY ATMOS",
        "DTS:X",
        "DTS:X MSTR",
        "AURO3D",
        "AURO2DSURR",
    ),
    zone3_prefix="Z3",
)

AVR_X2700H = ReceiverModel(
    name="AVR-X2700H",
    input_sources=frozenset(
        {
            InputSource.PHONO,
            InputSource.CD,
            InputSource.TUNER,
            InputSource.DVD,
            InputSource.BD,
            InputSource.TV,
            InputSource.SAT_CBL,
            InputSource.MPLAY,
            InputSource.GAME,
            InputSource.AUX1,
            InputSource.AUX2,
            InputSource.NET,
            InputSource.BT,
            InputSource.USB_IPOD,
            InputSource.EIGHT_K,
        }
    ),
    digital_inputs=_GEN3_DIGITAL,
    surround_modes=(
        *_MODERN_SURROUND,
        "DOLBY ATMOS",
        "DTS:X",
        "DTS:X MSTR",
    ),
    unsupported_startup_queries=frozenset(
        {
            "SR",
            "TF",
            "TP",
        }
    ),
)

# -- Other (unknown model) --

OTHER = ReceiverModel(
    name="Other",
    input_sources=frozenset(InputSource),
    digital_inputs=frozenset(DigitalInputMode),
    surround_modes=(
        *_COMMON_SURROUND,
        "AUTO",
        "DOLBY PRO LOGIC",
        "DOLBY PL2",
        "DOLBY PL2X",
        "DOLBY DIGITAL",
        "DOLBY D EX",
        "DOLBY DIGITAL+",
        "DOLBY HD",
        "DOLBY SURROUND",
        "DOLBY ATMOS",
        "DTS NEO:6",
        "DTS SURROUND",
        "DTS ES DSCRT6.1",
        "DTS ES MTRX6.1",
        "DTS96/24",
        "DTS HD",
        "DTS HD MSTR",
        "DTS:X",
        "DTS:X MSTR",
        "MCH STEREO",
        "5CH STEREO",
        "7CH STEREO",
        *_DSP_SURROUND,
        "AURO3D",
        "AURO2DSURR",
    ),
)

#: All known receiver models, for iteration.
ALL_MODELS: tuple[ReceiverModel, ...] = (
    AVR_3803,
    AVR_3805,
    AVR_987,
    AVR_2308CI,
    AVR_2808CI,
    AVR_4308CI,
    AVR_3310CI,
    AVR_X1000,
    AVR_X4000,
    AVR_X4200W,
    AVR_X2700H,
)

#: Models keyed by identifier string, for lookup. Includes "other".
MODELS: dict[str, ReceiverModel] = {
    "avr_3803": AVR_3803,
    "avr_3805": AVR_3805,
    "avr_987": AVR_987,
    "avr_2308ci": AVR_2308CI,
    "avr_2808ci": AVR_2808CI,
    "avr_4308ci": AVR_4308CI,
    "avr_3310ci": AVR_3310CI,
    "avr_x1000": AVR_X1000,
    "avr_x4000": AVR_X4000,
    "avr_x4200w": AVR_X4200W,
    "avr_x2700h": AVR_X2700H,
    "other": OTHER,
}
