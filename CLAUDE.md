# denon-rs232

Async Python library to control Denon AV receivers over RS232 serial.

## Project structure

```
src/denon_rs232/
  __init__.py    -- Main library: enums, DenonState, DenonReceiver class
  models.py      -- ReceiverModel dataclass and per-model definitions
  __main__.py    -- CLI: python -m denon_rs232 PORT [--probe] [--zone3-prefix Z1|Z3]

tests/
  conftest.py          -- MockSerialConnection, fixtures (receiver, mock_serial), DEFAULT_QUERY_RESPONSES
  test_denon_rs232.py  -- Query, control, event, and teardown tests
  test_probe.py        -- Source probing tests
  test_models.py       -- Model definition tests
```

## Architecture

- Uses `serialx` (`open_serial_connection`) for async serial I/O (9600 baud, 8N1).
- Denon RS232 protocol: `PREFIX + PARAM + CR (0x0D)`. Query with `PREFIX?`. Responses within 200ms.
- `connect()` only opens/verifies the serial connection via `PW?`.
- `query_state()` fetches current receiver state (single-response via `_query()`, multi-response via fire-and-forget + `asyncio.sleep(MULTI_RESPONSE_DELAY)`).
- After querying, state is kept current via a background `_read_loop` that processes events.
- `state` property returns a deep copy of `DenonState`.
- Subscribers get `DenonState` on changes, `None` on disconnect.

## Key design decisions

- `surround_mode` is `str`, not an enum -- 38+ combined mode values with special chars (e.g. "DOLBY D+PL2X C").
- Zone 3 prefix is configurable: `"Z1"` for legacy AVR-3803/3805, `"Z3"` (default) for modern models. Both Z1 and Z3 events always update `state.zone3`.
- `_SINGLE_RESPONSE_PREFIXES` use `_query()` (blocks waiting for response). `_MULTI_RESPONSE_PREFIXES` use fire-and-forget + sleep.
- Video/rec select: `SOURCE` response maps to `None` state. Separate `cancel_*` methods for sending SOURCE command.
- `probe_sources()` uses `_send_and_wait()` to try each `InputSource`, restores original at end.
- Module-level constants `MULTI_RESPONSE_DELAY`, `PROBE_TIMEOUT` are overridden in `tests/conftest.py` for speed.

## Testing

- `pytest` with `pytest-asyncio`, `asyncio_mode = "auto"`.
- `MockSerialConnection` uses a real `asyncio.StreamReader` with a mock writer. `_on_write` synchronously feeds responses into the reader for queries (`_query_responses` dict) and calls `_command_handler` for set commands.
- `DEFAULT_QUERY_RESPONSES` provides startup responses for all prefixes. Cleared after `connect()` in the `receiver` fixture so individual tests control responses.
- Run: `uv run pytest` or `python -m pytest tests/`

## Enums

`InputSource` (42 values across legacy/transition/modern/streaming/radio eras), `DigitalInputMode` (Gen1: PCM/DTS/RF, Gen2+: HDMI/DIGITAL), `PowerState`, `SurroundBack`, `ModeSetting`, `RoomEQ`, `TunerBand`, `TunerMode`.

## Protocol reference

Protocol PDFs analyzed in `~/Downloads/Denon/PROTOCOL_ANALYSIS.md` covering 19 documents and ~30 models from 2003-2016. `comparison_result.json` has per-model connection info.
