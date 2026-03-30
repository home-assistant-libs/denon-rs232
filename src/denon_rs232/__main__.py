"""CLI to test a Denon receiver over RS232.

Usage:
    python -m denon_rs232 /dev/ttyUSB0
    python -m denon_rs232 /dev/ttyUSB0 --probe
    python -m denon_rs232 /dev/ttyUSB0 --zone3-prefix Z1
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import DenonReceiver, DenonState, ZONE3_PREFIX


def _format_db(db: float | None) -> str:
    if db is None:
        return "?"
    if db == -80.0:
        return "MIN"
    if db >= 0:
        return f"+{db:.1f} dB"
    return f"{db:.1f} dB"


def _format_enum(val: object | None) -> str:
    if val is None:
        return "?"
    if hasattr(val, "value"):
        return val.value
    return str(val)


def _print_state(state: DenonState) -> None:
    print()
    print("=== Receiver Status ===")
    print()

    print(
        f"  Power:           {'ON' if state.power else 'STANDBY' if state.power is not None else '?'}"
    )
    print(
        f"  Main zone:       {'ON' if state.main_zone else 'OFF' if state.main_zone is not None else '?'}"
    )
    print(f"  Volume:          {_format_db(state.volume)}")
    print(
        f"  Mute:            {'ON' if state.mute else 'OFF' if state.mute is not None else '?'}"
    )
    print(f"  Input source:    {_format_enum(state.input_source)}")
    print(f"  Surround mode:   {state.surround_mode or '?'}")
    print(f"  Digital input:   {_format_enum(state.digital_input)}")

    if state.video_select is not None:
        print(f"  Video select:    {_format_enum(state.video_select)}")
    if state.rec_select is not None:
        print(f"  Rec select:      {_format_enum(state.rec_select)}")

    # Parameter settings
    ps_lines: list[str] = []
    if state.tone_defeat is not None:
        ps_lines.append(f"Tone defeat {'ON' if state.tone_defeat else 'OFF'}")
    if state.surround_back is not None:
        ps_lines.append(f"Surround back: {state.surround_back.value}")
    if state.cinema_eq is not None:
        ps_lines.append(f"Cinema EQ {'ON' if state.cinema_eq else 'OFF'}")
    if state.mode_setting is not None:
        ps_lines.append(f"Mode: {state.mode_setting.value}")
    if state.room_eq is not None:
        ps_lines.append(f"Room EQ: {state.room_eq.value}")
    if ps_lines:
        print()
        print("  Parameters:")
        for line in ps_lines:
            print(f"    {line}")

    # Channel volumes
    if state.channel_volumes:
        print()
        print("  Channel volumes:")
        for ch, db in sorted(state.channel_volumes.items()):
            print(f"    {ch:>3s}:  {_format_db(db)}")

    # Tuner
    if state.tuner_frequency or state.tuner_preset:
        print()
        print("  Tuner:")
        if state.tuner_band:
            print(f"    Band:       {state.tuner_band.value}")
        if state.tuner_frequency:
            print(f"    Frequency:  {state.tuner_frequency}")
        if state.tuner_preset:
            print(f"    Preset:     {state.tuner_preset}")
        if state.tuner_mode:
            print(f"    Mode:       {state.tuner_mode.value}")

    # Zones
    for label, zone in [("Zone 2", state.zone2), ("Zone 3", state.zone3)]:
        if zone.power is not None:
            print()
            print(f"  {label}:")
            print(f"    Power:   {'ON' if zone.power else 'OFF'}")
            if zone.input_source is not None:
                print(f"    Source:  {zone.input_source.value}")
            if zone.volume is not None:
                print(f"    Volume:  {_format_db(zone.volume)}")

    print()


async def _run(port: str, probe: bool, zone3_prefix: str) -> None:
    receiver = DenonReceiver(port, zone3_prefix=zone3_prefix)

    print(f"Connecting to {port}...")
    try:
        await receiver.connect()
        print("Querying receiver state...")
        await receiver.query_state()
    except ConnectionError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    try:
        _print_state(receiver.state)

        if probe:
            print("Probing input sources (this will briefly switch inputs)...")
            print()
            sources = await receiver.probe_sources()
            print(f"Available sources ({len(sources)}):")
            for source in sorted(sources, key=lambda s: s.value):
                print(f"  - {source.value}")
            print()
    finally:
        await receiver.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test a Denon receiver over RS232",
    )
    parser.add_argument("port", help="Serial port (e.g. /dev/ttyUSB0)")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Probe available input sources",
    )
    parser.add_argument(
        "--zone3-prefix",
        default=ZONE3_PREFIX,
        choices=["Z1", "Z3"],
        help="Zone 3 command prefix (Z1 for AVR-3803/3805, Z3 for modern; default: Z3)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.port, args.probe, args.zone3_prefix))


if __name__ == "__main__":
    main()
