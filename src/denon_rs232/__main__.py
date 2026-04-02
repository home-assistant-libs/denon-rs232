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

from . import DenonReceiver, ReceiverState, ZONE3_PREFIX


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


def _print_state(state: ReceiverState) -> None:
    print()
    print("=== Receiver Status ===")
    print()

    mz = state.main_zone

    print(
        f"  Power:           {'ON' if state.power else 'STANDBY' if state.power is not None else '?'}"
    )
    print(
        f"  Main zone:       {'ON' if mz.power else 'OFF' if mz.power is not None else '?'}"
    )
    print(f"  Volume:          {_format_db(mz.volume)}")
    print(
        f"  Mute:            {'ON' if mz.mute else 'OFF' if mz.mute is not None else '?'}"
    )
    print(f"  Input source:    {_format_enum(mz.input_source)}")
    print(f"  Surround mode:   {mz.surround_mode or '?'}")
    print(f"  Digital input:   {_format_enum(mz.digital_input)}")

    if mz.video_select is not None:
        print(f"  Video select:    {_format_enum(mz.video_select)}")
    if mz.rec_select is not None:
        print(f"  Rec select:      {_format_enum(mz.rec_select)}")

    # Parameter settings
    ps_lines: list[str] = []
    if mz.tone_defeat is not None:
        ps_lines.append(f"Tone defeat {'ON' if mz.tone_defeat else 'OFF'}")
    if mz.surround_back is not None:
        ps_lines.append(f"Surround back: {mz.surround_back.value}")
    if mz.cinema_eq is not None:
        ps_lines.append(f"Cinema EQ {'ON' if mz.cinema_eq else 'OFF'}")
    if mz.mode_setting is not None:
        ps_lines.append(f"Mode: {mz.mode_setting.value}")
    if mz.room_eq is not None:
        ps_lines.append(f"Room EQ: {mz.room_eq.value}")
    if ps_lines:
        print()
        print("  Parameters:")
        for line in ps_lines:
            print(f"    {line}")

    # Channel volumes
    if mz.channel_volumes:
        print()
        print("  Channel volumes:")
        for ch, db in sorted(mz.channel_volumes.items()):
            print(f"    {ch:>3s}:  {_format_db(db)}")

    # Tuner
    if mz.tuner_frequency or mz.tuner_preset:
        print()
        print("  Tuner:")
        if mz.tuner_band:
            print(f"    Band:       {mz.tuner_band.value}")
        if mz.tuner_frequency:
            print(f"    Frequency:  {mz.tuner_frequency}")
        if mz.tuner_preset:
            print(f"    Preset:     {mz.tuner_preset}")
        if mz.tuner_mode:
            print(f"    Mode:       {mz.tuner_mode.value}")

    # Zones
    for label, zone in [("Zone 2", state.zone_2), ("Zone 3", state.zone_3)]:
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
