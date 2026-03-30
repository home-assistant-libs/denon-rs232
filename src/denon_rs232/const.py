"""Constants and enums shared across the denon_rs232 package."""

from enum import Enum

BAUD_RATE = 9600
COMMAND_TIMEOUT = 2.0  # seconds to wait for a response
MULTI_RESPONSE_DELAY = 0.3  # seconds to wait for multi-response query results
PROBE_TIMEOUT = 0.8  # seconds to wait for each probe attempt
CR = b"\r"

# Volume range constants (dB)
MIN_VOLUME_DB = -80.0
MAX_VOLUME_DB = 18.0
VOLUME_DB_RANGE = MAX_VOLUME_DB - MIN_VOLUME_DB  # 98.0

# Prefixes that return a single response to "?", safe for _query().
_SINGLE_RESPONSE_PREFIXES = (
    "PW",
    "ZM",
    "MV",
    "MU",
    "SI",
    "MS",
    "SD",
    "SV",
    "SR",
    "TF",
    "TP",
)

# Prefixes that return multiple responses to "?", state populated via _process_message.
_MULTI_RESPONSE_PREFIXES = ("CV", "PS", "TM", "Z2", "Z1")

# Zone 3 prefix: legacy models (AVR-3803/3805) use "Z1", modern models use "Z3".
ZONE3_PREFIX = "Z3"


class InputSource(Enum):
    """Input sources available on the Denon receiver."""

    # Legacy sources (~2003-2007)
    PHONO = "PHONO"
    CD = "CD"
    TUNER = "TUNER"
    DVD = "DVD"
    VDP = "VDP"
    TV = "TV"
    DBS_SAT = "DBS/SAT"
    VCR_1 = "VCR-1"
    VCR_2 = "VCR-2"
    VCR_3 = "VCR-3"
    V_AUX = "V.AUX"
    CDR_TAPE1 = "CDR/TAPE1"
    MD_TAPE2 = "MD/TAPE2"

    # Transition era (~2006-2009)
    HDP = "HDP"
    DVR = "DVR"
    TV_CBL = "TV/CBL"
    SAT = "SAT"
    NET_USB = "NET/USB"
    DOCK = "DOCK"
    IPOD = "IPOD"

    # Modern era (~2012-2016)
    BD = "BD"
    SAT_CBL = "SAT/CBL"
    MPLAY = "MPLAY"
    GAME = "GAME"
    AUX1 = "AUX1"
    AUX2 = "AUX2"
    NET = "NET"
    BT = "BT"
    USB_IPOD = "USB/IPOD"
    EIGHT_K = "8K"

    # Streaming / online services
    PANDORA = "PANDORA"
    SIRIUSXM = "SIRIUSXM"
    SPOTIFY = "SPOTIFY"
    FLICKR = "FLICKR"
    IRADIO = "IRADIO"
    SERVER = "SERVER"
    FAVORITES = "FAVORITES"
    LASTFM = "LASTFM"

    # Radio services (region-specific)
    XM = "XM"
    SIRIUS = "SIRIUS"
    HDRADIO = "HDRADIO"
    DAB = "DAB"


class DigitalInputMode(Enum):
    """Digital input modes."""

    AUTO = "AUTO"
    # Gen 1 (legacy ~2003-2007)
    PCM = "PCM"
    DTS = "DTS"
    RF = "RF"
    ANALOG = "ANALOG"
    EXT_IN_1 = "EXT.IN-1"
    EXT_IN_2 = "EXT.IN-2"
    # Gen 2+ (~2009+)
    HDMI = "HDMI"
    DIGITAL = "DIGITAL"


class SurroundBack(Enum):
    """Surround back speaker modes."""

    MTRX_ON = "MTRX ON"
    NON_MTRX = "NON MTRX"
    PL2X_CINEMA = "PL2X CINEMA"
    PL2X_MUSIC = "PL2X MUSIC"
    OFF = "OFF"


class ModeSetting(Enum):
    """Decoder mode settings (for PL2/PL2x/NEO:6)."""

    MUSIC = "MUSIC"
    CINEMA = "CINEMA"
    GAME = "GAME"
    PRO_LOGIC = "PRO LOGIC"


class RoomEQ(Enum):
    """Room EQ modes."""

    NORMAL = "NORMAL"
    FRONT = "FRONT"
    FLAT = "FLAT"
    MANUAL = "MANUAL"
    OFF = "OFF"


class TunerBand(Enum):
    """Tuner bands."""

    AM = "AM"
    FM = "FM"


class TunerMode(Enum):
    """Tuning modes."""

    AUTO = "AUTO"
    MANUAL = "MANUAL"
