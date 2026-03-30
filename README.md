# denon-rs232

Async Python library to control Denon AV receivers over RS232 serial, built on [serialx](https://github.com/puddly/serialx).

## Installation

```bash
pip install denon-rs232
```

Requires Python 3.12+.

## Quick start

```python
import asyncio
from denon_rs232 import DenonReceiver, InputSource

async def main():
    receiver = DenonReceiver("/dev/ttyUSB0")
    await receiver.connect()
    await receiver.query_state()

    # State is fully populated after query_state()
    print(f"Power: {receiver.state.power}")
    print(f"Volume: {receiver.state.volume} dB")
    print(f"Input: {receiver.state.input_source}")

    # Control the receiver
    await receiver.set_volume(-30.0)
    await receiver.select_input_source(InputSource.DVD)

    await receiver.disconnect()

asyncio.run(main())
```

## CLI

A built-in CLI lets you quickly test your serial connection:

```bash
# Query and print receiver status
python -m denon_rs232 /dev/ttyUSB0

# Also probe which input sources the receiver accepts
python -m denon_rs232 /dev/ttyUSB0 --probe

# Use legacy zone 3 prefix for AVR-3803/3805
python -m denon_rs232 /dev/ttyUSB0 --zone3-prefix Z1
```

## Features

### Full state after query

`connect()` only opens and verifies the serial connection. Call `query_state()` when you want the current receiver state populated into the `state` property. After that, state is kept up to date via events from the receiver.

```python
receiver = DenonReceiver("/dev/ttyUSB0")
await receiver.connect()
await receiver.query_state()

state = receiver.state
state.power          # PowerState.ON / PowerState.STANDBY
state.main_zone      # True / False
state.volume         # float in dB (0.0 = reference, -80.0 = min, +18.0 = max)
state.mute           # True / False
state.input_source   # InputSource enum
state.surround_mode  # str (e.g. "STEREO", "DOLBY DIGITAL", "DTS SURROUND")
state.digital_input  # DigitalInputMode enum
state.video_select   # InputSource or None
state.rec_select     # InputSource or None
```

### Event subscription

Subscribe to state changes to react in real-time. Callbacks receive a `DenonState` snapshot on updates, or `None` when the connection is lost.

```python
def on_state_change(state):
    if state is None:
        print("Disconnected!")
        return
    print(f"Volume: {state.volume} dB, Source: {state.input_source}")

unsub = receiver.subscribe(on_state_change)
# Later:
unsub()  # stop receiving events
```

### Power

```python
await receiver.power_on()
await receiver.power_standby()
power = await receiver.query_power()  # PowerState.ON / PowerState.STANDBY
```

### Main zone

```python
await receiver.main_zone_on()
await receiver.main_zone_off()
on = await receiver.query_main_zone()  # bool
```

### Master volume

Volume is represented in dB: 0.0 dB is the reference level, -80.0 is minimum, +18.0 is maximum. Half-dB steps are supported.

```python
await receiver.set_volume(-25.0)     # set to -25 dB
await receiver.set_volume(-25.5)     # half-dB step
await receiver.volume_up()
await receiver.volume_down()
db = await receiver.query_volume()   # float
```

### Channel volumes

Individual channel levels, relative to the master volume. 0.0 dB is neutral, range is -12.0 to +12.0 dB. Available channels depend on the speaker configuration: FL, FR, C, SW, SL, SR, SBL, SBR, SB.

```python
await receiver.set_channel_volume("FL", 2.0)   # front left +2 dB
await receiver.set_channel_volume("SW", -3.5)  # subwoofer -3.5 dB
await receiver.channel_volume_up("C")
await receiver.channel_volume_down("FR")

# All channel volumes are in state after connect:
state.channel_volumes  # {"FL": 0.0, "FR": 0.0, "C": -1.0, ...}
```

### Mute

```python
await receiver.mute_on()
await receiver.mute_off()
muted = await receiver.query_mute()  # bool
```

### Input source

```python
from denon_rs232 import InputSource

await receiver.select_input_source(InputSource.BD)
source = await receiver.query_input_source()  # InputSource enum
```

Available sources depend on the model. See [Input sources](#input-sources) below.

### Surround mode

Surround mode is kept as a plain string because receivers return many combined mode names (e.g. `"DOLBY D+PL2X C"`, `"DTS HD MSTR"`).

```python
await receiver.set_surround_mode("STEREO")
await receiver.set_surround_mode("DOLBY DIGITAL")
await receiver.set_surround_mode("DTS SURROUND")
await receiver.set_surround_mode("DIRECT")
await receiver.set_surround_mode("PURE DIRECT")
await receiver.set_surround_mode("MCH STEREO")
mode = await receiver.query_surround_mode()  # str
```

### Digital input mode

```python
from denon_rs232 import DigitalInputMode

await receiver.set_digital_input(DigitalInputMode.AUTO)
await receiver.set_digital_input(DigitalInputMode.HDMI)
await receiver.set_digital_input(DigitalInputMode.DIGITAL)
await receiver.set_digital_input(DigitalInputMode.ANALOG)
mode = await receiver.query_digital_input()  # DigitalInputMode enum or None ("NO")
```

Legacy models also support `PCM`, `DTS`, `RF`, `EXT_IN_1`, `EXT_IN_2`.

### Video / recording source select

Override the video or recording source independently from the main input source:

```python
await receiver.set_video_select(InputSource.DVD)
await receiver.cancel_video_select()  # return to following input
source = await receiver.query_video_select()

await receiver.set_rec_select(InputSource.CD)
await receiver.cancel_rec_select()
source = await receiver.query_rec_select()
```

### Parameter settings

```python
from denon_rs232 import SurroundBack, ModeSetting, RoomEQ

# Tone defeat
await receiver.tone_defeat_on()
await receiver.tone_defeat_off()

# Surround back speakers
await receiver.set_surround_back(SurroundBack.PL2X_CINEMA)
await receiver.set_surround_back(SurroundBack.OFF)

# Cinema EQ
await receiver.cinema_eq_on()
await receiver.cinema_eq_off()

# Decoder mode
await receiver.set_mode_setting(ModeSetting.CINEMA)
await receiver.set_mode_setting(ModeSetting.MUSIC)

# Room EQ (pre-Audyssey models)
await receiver.set_room_eq(RoomEQ.FLAT)
```

All parameter settings are available in `state` after connect:

```python
state.tone_defeat     # bool
state.surround_back   # SurroundBack enum
state.cinema_eq       # bool
state.mode_setting    # ModeSetting enum
state.room_eq         # RoomEQ enum (event-only, not in PS? response)
```

### Tuner

```python
from denon_rs232 import TunerBand, TunerMode

await receiver.set_tuner_band(TunerBand.FM)
await receiver.set_tuner_mode(TunerMode.AUTO)
await receiver.set_tuner_frequency("105000")  # FM 105.0 MHz
await receiver.set_tuner_preset("A1")
await receiver.tuner_frequency_up()
await receiver.tuner_frequency_down()
await receiver.tuner_preset_up()
await receiver.tuner_preset_down()

freq = await receiver.query_tuner_frequency()  # str
preset = await receiver.query_tuner_preset()   # str
```

Tuner band and mode are available via events (`state.tuner_band`, `state.tuner_mode`).

### Multi-zone

Zone 2 and Zone 3 can be controlled independently. Zone state (power, source, volume) is populated by `query_state()` and updated via events.

```python
# Zone 2
await receiver.zone2_power_on()
await receiver.zone2_power_standby()
await receiver.zone2_select_input_source(InputSource.TUNER)
await receiver.zone2_set_volume(-30.0)
await receiver.zone2_volume_up()
await receiver.zone2_volume_down()

# Zone 3
await receiver.zone3_power_on()
await receiver.zone3_power_standby()
await receiver.zone3_select_input_source(InputSource.CD)
await receiver.zone3_set_volume(-35.0)
await receiver.zone3_volume_up()
await receiver.zone3_volume_down()
```

Zone state in `state`:

```python
state.zone2.power   # bool
state.zone2.source  # InputSource
state.zone2.volume  # float in dB
state.zone3.power   # bool
state.zone3.source  # InputSource
state.zone3.volume  # float in dB
```

**Zone 3 prefix**: Legacy models (AVR-3803, AVR-3805) use the `Z1` command prefix for Zone 3. Modern models use `Z3`. The default is `Z3`; pass `zone3_prefix="Z1"` for legacy models:

```python
receiver = DenonReceiver("/dev/ttyUSB0", zone3_prefix="Z1")
```

### Source probing

Discover which input sources the receiver actually supports by trying each one:

```python
sources = await receiver.probe_sources()
# frozenset({InputSource.CD, InputSource.DVD, InputSource.TUNER, ...})
```

This briefly switches through all input sources and restores the original when done. Nothing should be playing during probing.

### Receiver models

Pre-defined model capabilities are available in `denon_rs232.models`:

```python
from denon_rs232.models import AVR_3805, AVR_X4000, ALL_MODELS

# Check if a source is supported by a specific model
InputSource.BD in AVR_X4000.input_sources       # True
InputSource.BD in AVR_3805.input_sources         # False

# Get the zone 3 prefix for a model
AVR_3805.zone3_prefix   # "Z1"
AVR_X4000.zone3_prefix  # "Z3"

# Iterate all models
for model in ALL_MODELS:
    print(f"{model.name}: {len(model.input_sources)} sources")
```

Available models:

| Constant | Models | Era | Zone 3 | Digital |
|----------|--------|-----|--------|---------|
| `AVR_3803` | AVR-3803 / AVC-3570 / AVR-2803 | ~2003 | Z1 | Gen 1 (PCM/DTS/RF) |
| `AVR_3805` | AVR-3805 / AVC-3890 | ~2004 | Z1 | Gen 1 (PCM/DTS) |
| `AVR_987` | AVR-987 | ~2005 | Z3 | Gen 1 |
| `AVR_2308CI` | AVR-2308CI / AVC-2308 | ~2007 | -- | Gen 1 |
| `AVR_2808CI` | AVR-2808CI / AVC-2808 / AVR-988 | ~2007 | Z3 | Gen 1 |
| `AVR_4308CI` | AVR-4308CI | ~2008 | Z3 | Gen 1 |
| `AVR_3310CI` | AVR-3310CI / AVR-990 / AVC-3310 | ~2009 | Z3 | Gen 2 (HDMI/DIGITAL) |
| `AVR_X1000` | AVR-X1000 / AVR-E300 | ~2013 | -- | Gen 3 (HDMI/DIGITAL) |
| `AVR_X4000` | AVR-X4000 | ~2013 | Z3 | Gen 3 |
| `AVR_X4200W` | AVR-X4200W / X3200W / X2200W / X1200W | ~2015 | Z3 | Gen 3 |

### Connection handling

The library handles connection errors gracefully:

- If the receiver doesn't respond during `connect()`, a `ConnectionError` is raised.
- If the serial connection is lost (cable unplugged, device error), subscribers receive `None` and `connected` becomes `False`.
- Write errors during commands propagate the exception and tear down the connection.

```python
try:
    await receiver.connect()
except ConnectionError:
    print("Receiver not responding")
```

## Input sources

Available input sources vary by model era:

| Source | Protocol value | Era |
|--------|---------------|-----|
| `PHONO` | PHONO | Legacy |
| `CD` | CD | Legacy |
| `TUNER` | TUNER | Legacy |
| `DVD` | DVD | Legacy |
| `VDP` | VDP | Legacy |
| `TV` | TV | Legacy |
| `DBS_SAT` | DBS/SAT | Legacy |
| `VCR_1` | VCR-1 | Legacy |
| `VCR_2` | VCR-2 | Legacy |
| `VCR_3` | VCR-3 | Legacy |
| `V_AUX` | V.AUX | Legacy |
| `CDR_TAPE1` | CDR/TAPE1 | Legacy |
| `MD_TAPE2` | MD/TAPE2 | Legacy |
| `HDP` | HDP | Transition |
| `DVR` | DVR | Transition |
| `TV_CBL` | TV/CBL | Transition |
| `SAT` | SAT | Transition |
| `NET_USB` | NET/USB | Transition |
| `DOCK` | DOCK | Transition |
| `IPOD` | IPOD | Transition |
| `BD` | BD | Modern |
| `SAT_CBL` | SAT/CBL | Modern |
| `MPLAY` | MPLAY | Modern |
| `GAME` | GAME | Modern |
| `AUX1` | AUX1 | Modern |
| `AUX2` | AUX2 | Modern |
| `NET` | NET | Modern |
| `BT` | BT | Modern |
| `USB_IPOD` | USB/IPOD | Modern |
| `PANDORA` | PANDORA | Streaming |
| `SIRIUSXM` | SIRIUSXM | Streaming |
| `SPOTIFY` | SPOTIFY | Streaming |
| `FLICKR` | FLICKR | Streaming |
| `IRADIO` | IRADIO | Streaming |
| `SERVER` | SERVER | Streaming |
| `FAVORITES` | FAVORITES | Streaming |
| `LASTFM` | LASTFM | Streaming |
| `XM` | XM | Radio |
| `SIRIUS` | SIRIUS | Radio |
| `HDRADIO` | HDRADIO | Radio |
| `DAB` | DAB | Radio |

Not all sources exist on every receiver. Use `probe_sources()` or a `ReceiverModel` definition to determine which sources your receiver supports.

## Serial connection

The library uses [serialx](https://github.com/puddly/serialx) for async serial communication. All Denon RS232 receivers use 9600 baud, 8 data bits, no parity, 1 stop bit.

Most receivers have a DB-9 connector. The AVR-3803 / AVC-3570 uses a 3.5mm stereo mini plug (Tip=RXD, Ring=TXD, Sleeve=GND).

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Run tests with verbose output
uv run pytest -v
```

## License

MIT
