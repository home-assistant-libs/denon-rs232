"""Tests for denon_rs232 query, control, and event handling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from conftest import (
    DEFAULT_QUERY_RESPONSES,
    MockSerialConnection,
    connect_with_defaults,
)

from denon_rs232 import (
    _MULTI_RESPONSE_PREFIXES,
    _SINGLE_RESPONSE_PREFIXES,
    DenonReceiver,
    MainZoneState,
    ReceiverState,
    DigitalInputMode,
    InputSource,
    ModeSetting,
    RoomEQ,
    SurroundBack,
    TunerBand,
    TunerMode,
    _channel_volume_to_param,
    _parse_channel_volume_param,
    _parse_volume_param,
    _volume_to_param,
)
from denon_rs232.models import AVR_X2700H


# -- Master volume conversion tests --


def test_parse_volume_zero_db():
    assert _parse_volume_param("80") == 0.0


def test_parse_volume_max_18db():
    assert _parse_volume_param("98") == 18.0


def test_parse_volume_min():
    assert _parse_volume_param("99") == -80.0


def test_parse_volume_negative():
    assert _parse_volume_param("60") == -20.0


def test_parse_volume_half_db_positive():
    assert _parse_volume_param("805") == 0.5


def test_parse_volume_half_db_negative():
    assert _parse_volume_param("795") == -0.5


def test_parse_volume_half_db_large():
    assert _parse_volume_param("505") == -29.5


def test_volume_to_param_zero_db():
    assert _volume_to_param(0.0) == "80"


def test_volume_to_param_max():
    assert _volume_to_param(18.0) == "98"


def test_volume_to_param_min():
    assert _volume_to_param(-80.0) == "99"


def test_volume_to_param_negative():
    assert _volume_to_param(-20.0) == "60"


def test_volume_to_param_half_db():
    assert _volume_to_param(0.5) == "805"


def test_volume_to_param_half_db_negative():
    assert _volume_to_param(-0.5) == "795"


def test_volume_roundtrip():
    for db in [-80, -20, -10.5, -0.5, 0, 0.5, 10, 18]:
        assert _parse_volume_param(_volume_to_param(db)) == db


# -- Channel volume conversion tests --


def test_parse_channel_volume_zero_db():
    assert _parse_channel_volume_param("50") == 0.0


def test_parse_channel_volume_max():
    assert _parse_channel_volume_param("62") == 12.0


def test_parse_channel_volume_min():
    assert _parse_channel_volume_param("38") == -12.0


def test_parse_channel_volume_off():
    assert _parse_channel_volume_param("00") == -50.0


def test_parse_channel_volume_half_db():
    assert _parse_channel_volume_param("505") == 0.5


def test_channel_volume_to_param_zero():
    assert _channel_volume_to_param(0.0) == "50"


def test_channel_volume_to_param_max():
    assert _channel_volume_to_param(12.0) == "62"


def test_channel_volume_to_param_min():
    assert _channel_volume_to_param(-12.0) == "38"


def test_channel_volume_to_param_half():
    assert _channel_volume_to_param(0.5) == "505"


def test_channel_volume_roundtrip():
    for db in [-12, -6.5, -1, 0, 0.5, 6, 12]:
        assert _parse_channel_volume_param(_channel_volume_to_param(db)) == db


# -- State tests --


def test_initial_state():
    state = ReceiverState()
    assert state.power is None
    assert state.main_zone.power is None
    assert state.main_zone.mute is None
    assert state.main_zone.volume is None
    assert state.main_zone.volume_max is None
    assert state.main_zone.volume_min is None
    assert state.main_zone.input_source is None
    assert state.main_zone.surround_mode is None
    assert state.main_zone.channel_volumes == {}
    assert state.zone_2.power is None
    assert state.zone_3.power is None


def test_state_copy():
    state = ReceiverState(
        power=True,
        main_zone=MainZoneState(
            volume=0.0,
            volume_max=18.0,
            volume_min=-80.0,
        ),
    )
    state.main_zone.channel_volumes["FL"] = 0.0
    state.zone_2.power = True
    copy = state.copy()
    assert copy.power is True
    assert copy.main_zone.volume == 0.0
    assert copy.main_zone.volume_max == 18.0
    assert copy.main_zone.volume_min == -80.0
    assert copy.main_zone.channel_volumes == {"FL": 0.0}
    assert copy.zone_2.power is True
    # Verify deep copy
    copy.power = False
    copy.main_zone.channel_volumes["FL"] = 5.0
    copy.zone_2.power = False
    assert state.power is True
    assert state.main_zone.channel_volumes["FL"] == 0.0
    assert state.zone_2.power is True


# -- Connection tests --


async def test_connect_verifies_power(mock_serial):
    recv = DenonReceiver("/dev/ttyUSB0")

    async def fake_open(*args, **kwargs):
        return mock_serial.reader, mock_serial.writer

    mock_serial._query_responses = dict(DEFAULT_QUERY_RESPONSES)

    with patch(
        "denon_rs232.receiver.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        await recv.connect()

    assert recv.state.power is True
    sent_queries = [data.decode("ascii") for data in mock_serial.written_data]
    assert sent_queries == ["PW?\r"]

    await recv.disconnect()


async def test_query_state_populates_full_state(receiver):
    """query_state() should populate state from all startup queries."""
    state = receiver.state
    assert state.power is True
    assert state.main_zone.power is True
    assert state.main_zone.volume == 0.0
    assert state.main_zone.volume_max == 18.0
    assert state.main_zone.volume_min == -80.0
    assert state.main_zone.mute is False
    assert state.main_zone.input_source == InputSource.CD
    assert state.main_zone.surround_mode == "STEREO"
    assert state.main_zone.digital_input == DigitalInputMode.AUTO
    assert state.main_zone.video_select == InputSource.DVD
    assert state.main_zone.rec_select == InputSource.CD
    assert state.main_zone.tuner_frequency == "105000"
    assert state.main_zone.tuner_preset == "A1"
    assert state.main_zone.tuner_band == TunerBand.FM
    assert state.main_zone.tuner_mode == TunerMode.AUTO
    assert state.main_zone.tone_defeat is False
    assert state.main_zone.surround_back == SurroundBack.OFF
    assert state.main_zone.cinema_eq is False
    assert state.main_zone.mode_setting == ModeSetting.CINEMA
    assert state.main_zone.channel_volumes["FL"] == 0.0
    assert state.main_zone.channel_volumes["FR"] == 0.0
    assert state.zone_2.power is False
    assert state.zone_3.power is False


async def test_receiver_exposes_shared_player_objects(receiver):
    """Receiver should expose live player objects for main and zones."""
    assert receiver.power is True
    assert receiver.main.power is True
    assert receiver.main.input_source == InputSource.CD
    assert receiver.main.volume == 0.0
    assert receiver.main.volume_min == -80.0
    assert receiver.main.volume_max == 18.0
    assert receiver.main.mute is False
    assert receiver.zone_2.power is False
    assert receiver.zone_3.power is False


async def test_query_state_queries_all_prefixes(mock_serial):
    """query_state() should send ? queries for all startup prefixes."""
    recv = await connect_with_defaults(mock_serial)

    # Check all expected query commands were sent.
    # Z1 in _MULTI_RESPONSE_PREFIXES is replaced by the configured zone3 prefix (Z3).
    expected = set(_SINGLE_RESPONSE_PREFIXES) | {
        "Z3" if p == "Z1" else p for p in _MULTI_RESPONSE_PREFIXES
    }
    sent_queries = {
        data[:-1].decode("ascii").replace("?", "")
        for data in mock_serial.written_data
        if data.endswith(b"?\r")
    }
    assert expected == sent_queries

    await recv.disconnect()


async def test_query_state_skips_known_unsupported_model_queries(mock_serial):
    """Known model capabilities should trim unsupported startup probes."""
    recv = await connect_with_defaults(mock_serial, model=AVR_X2700H)

    sent_queries = {
        data[:-1].decode("ascii").replace("?", "")
        for data in mock_serial.written_data
        if data.endswith(b"?\r")
    }

    assert "SR" not in sent_queries
    assert "TF" not in sent_queries
    assert "TP" not in sent_queries
    assert "Z3" not in sent_queries

    state = recv.state
    assert state.main_zone.rec_select is None
    assert state.main_zone.tuner_frequency is None
    assert state.main_zone.tuner_preset is None
    assert state.zone_3.power is None

    await recv.disconnect()


async def test_connect_timeout_raises():
    recv = DenonReceiver("/dev/ttyUSB0")
    mock = MockSerialConnection()
    # No auto-responses: power query will timeout

    async def fake_open(*args, **kwargs):
        return mock.reader, mock.writer

    with patch(
        "denon_rs232.receiver.serialx.open_serial_connection",
        side_effect=fake_open,
    ):
        with pytest.raises(ConnectionError, match="No response"):
            await recv.connect()


async def test_disconnect(receiver):
    await receiver.disconnect()
    assert not receiver.connected


async def test_written_command_format(receiver, mock_serial):
    assert b"PW?\r" in mock_serial.written_data


# -- Power & main zone command tests --


async def test_power_on(receiver, mock_serial):
    await receiver.power_on()
    assert b"PWON\r" in mock_serial.written_data


async def test_power_standby(receiver, mock_serial):
    await receiver.power_standby()
    assert b"PWSTANDBY\r" in mock_serial.written_data


async def test_main_player_power_on(receiver, mock_serial):
    await receiver.main.power_on()
    assert b"ZMON\r" in mock_serial.written_data


async def test_main_zone_on(receiver, mock_serial):
    await receiver.main.main_zone_on()
    assert b"ZMON\r" in mock_serial.written_data


async def test_main_zone_off(receiver, mock_serial):
    await receiver.main.main_zone_off()
    assert b"ZMOFF\r" in mock_serial.written_data


# -- Master volume command tests --


async def test_volume_up(receiver, mock_serial):
    await receiver.main.volume_up()
    assert b"MVUP\r" in mock_serial.written_data


async def test_volume_down(receiver, mock_serial):
    await receiver.main.volume_down()
    assert b"MVDOWN\r" in mock_serial.written_data


async def test_set_volume(receiver, mock_serial):
    await receiver.main.set_volume(0.0)
    assert b"MV80\r" in mock_serial.written_data


async def test_set_volume_half_db(receiver, mock_serial):
    await receiver.main.set_volume(-10.5)
    assert b"MV695\r" in mock_serial.written_data


# -- Channel volume command tests --


async def test_channel_volume_up(receiver, mock_serial):
    await receiver.main.channel_volume_up("FL")
    assert b"CVFL UP\r" in mock_serial.written_data


async def test_channel_volume_down(receiver, mock_serial):
    await receiver.main.channel_volume_down("C")
    assert b"CVC DOWN\r" in mock_serial.written_data


async def test_set_channel_volume(receiver, mock_serial):
    await receiver.main.set_channel_volume("SW", 3.0)
    assert b"CVSW 53\r" in mock_serial.written_data


async def test_set_channel_volume_half_db(receiver, mock_serial):
    await receiver.main.set_channel_volume("FR", -2.5)
    assert b"CVFR 475\r" in mock_serial.written_data


# -- Mute command tests --


async def test_mute_on(receiver, mock_serial):
    await receiver.main.mute_on()
    assert b"MUON\r" in mock_serial.written_data


async def test_mute_off(receiver, mock_serial):
    await receiver.main.mute_off()
    assert b"MUOFF\r" in mock_serial.written_data


# -- Input source command tests --


async def test_select_input_source(receiver, mock_serial):
    await receiver.main.select_input_source(InputSource.DVD)
    assert b"SIDVD\r" in mock_serial.written_data


async def test_select_input_source_with_slash(receiver, mock_serial):
    await receiver.main.select_input_source(InputSource.DBS_SAT)
    assert b"SIDBS/SAT\r" in mock_serial.written_data


# -- Surround mode command tests --


async def test_set_surround_mode(receiver, mock_serial):
    await receiver.main.set_surround_mode("STEREO")
    assert b"MSSTEREO\r" in mock_serial.written_data


async def test_set_surround_mode_with_spaces(receiver, mock_serial):
    await receiver.main.set_surround_mode("DOLBY PRO LOGIC")
    assert b"MSDOLBY PRO LOGIC\r" in mock_serial.written_data


# -- Parameter settings command tests --


async def test_tone_defeat_on(receiver, mock_serial):
    await receiver.main.tone_defeat_on()
    assert b"PSTONE DEFEAT ON\r" in mock_serial.written_data


async def test_tone_defeat_off(receiver, mock_serial):
    await receiver.main.tone_defeat_off()
    assert b"PSTONE DEFEAT OFF\r" in mock_serial.written_data


async def test_set_surround_back(receiver, mock_serial):
    await receiver.main.set_surround_back(SurroundBack.MTRX_ON)
    assert b"PSSB:MTRX ON\r" in mock_serial.written_data


async def test_cinema_eq_on(receiver, mock_serial):
    await receiver.main.cinema_eq_on()
    assert b"PSCINEMA EQ.ON\r" in mock_serial.written_data


async def test_cinema_eq_off(receiver, mock_serial):
    await receiver.main.cinema_eq_off()
    assert b"PSCINEMA EQ.OFF\r" in mock_serial.written_data


async def test_set_mode_setting(receiver, mock_serial):
    await receiver.main.set_mode_setting(ModeSetting.MUSIC)
    assert b"PSMODE : MUSIC\r" in mock_serial.written_data


async def test_set_room_eq(receiver, mock_serial):
    await receiver.main.set_room_eq(RoomEQ.FLAT)
    assert b"PSROOM EQ:FLAT\r" in mock_serial.written_data


# -- Digital input command tests --


async def test_set_digital_input(receiver, mock_serial):
    await receiver.main.set_digital_input(DigitalInputMode.AUTO)
    assert b"SDAUTO\r" in mock_serial.written_data


async def test_set_digital_input_ext(receiver, mock_serial):
    await receiver.main.set_digital_input(DigitalInputMode.EXT_IN_1)
    assert b"SDEXT.IN-1\r" in mock_serial.written_data


# -- Video select command tests --


async def test_set_video_select(receiver, mock_serial):
    await receiver.main.set_video_select(InputSource.DVD)
    assert b"SVDVD\r" in mock_serial.written_data


async def test_cancel_video_select(receiver, mock_serial):
    await receiver.main.cancel_video_select()
    assert b"SVSOURCE\r" in mock_serial.written_data


# -- Rec select command tests --


async def test_set_rec_select(receiver, mock_serial):
    await receiver.main.set_rec_select(InputSource.CD)
    assert b"SRCD\r" in mock_serial.written_data


async def test_cancel_rec_select(receiver, mock_serial):
    await receiver.main.cancel_rec_select()
    assert b"SRSOURCE\r" in mock_serial.written_data


# -- Tuner command tests --


async def test_tuner_frequency_up(receiver, mock_serial):
    await receiver.main.tuner_frequency_up()
    assert b"TFUP\r" in mock_serial.written_data


async def test_tuner_frequency_down(receiver, mock_serial):
    await receiver.main.tuner_frequency_down()
    assert b"TFDOWN\r" in mock_serial.written_data


async def test_set_tuner_frequency(receiver, mock_serial):
    await receiver.main.set_tuner_frequency("105000")
    assert b"TF105000\r" in mock_serial.written_data


async def test_tuner_preset_up(receiver, mock_serial):
    await receiver.main.tuner_preset_up()
    assert b"TPUP\r" in mock_serial.written_data


async def test_tuner_preset_down(receiver, mock_serial):
    await receiver.main.tuner_preset_down()
    assert b"TPDOWN\r" in mock_serial.written_data


async def test_set_tuner_preset(receiver, mock_serial):
    await receiver.main.set_tuner_preset("A1")
    assert b"TPA1\r" in mock_serial.written_data


async def test_set_tuner_band(receiver, mock_serial):
    await receiver.main.set_tuner_band(TunerBand.FM)
    assert b"TMFM\r" in mock_serial.written_data


async def test_set_tuner_mode(receiver, mock_serial):
    await receiver.main.set_tuner_mode(TunerMode.AUTO)
    assert b"TMAUTO\r" in mock_serial.written_data


# -- Zone 2 command tests --


async def test_zone2_power_on(receiver, mock_serial):
    await receiver.zone_2.power_on()
    assert b"Z2ON\r" in mock_serial.written_data


async def test_zone2_player_power_on(receiver, mock_serial):
    await receiver.zone_2.power_on()
    assert b"Z2ON\r" in mock_serial.written_data


async def test_zone2_power_standby(receiver, mock_serial):
    await receiver.zone_2.power_standby()
    assert b"Z2OFF\r" in mock_serial.written_data


async def test_zone2_select_input_source(receiver, mock_serial):
    await receiver.zone_2.select_input_source(InputSource.CD)
    assert b"Z2CD\r" in mock_serial.written_data


async def test_zone2_volume_up(receiver, mock_serial):
    await receiver.zone_2.volume_up()
    assert b"Z2UP\r" in mock_serial.written_data


async def test_zone2_set_volume(receiver, mock_serial):
    await receiver.zone_2.set_volume(0.0)
    assert b"Z280\r" in mock_serial.written_data


# -- Zone 3 command tests (default Z3 prefix) --


async def test_zone3_power_on(receiver, mock_serial):
    await receiver.zone_3.power_on()
    assert b"Z3ON\r" in mock_serial.written_data


async def test_zone3_player_power_on(receiver, mock_serial):
    await receiver.zone_3.power_on()
    assert b"Z3ON\r" in mock_serial.written_data


async def test_zone3_power_standby(receiver, mock_serial):
    await receiver.zone_3.power_standby()
    assert b"Z3OFF\r" in mock_serial.written_data


async def test_zone3_select_input_source(receiver, mock_serial):
    await receiver.zone_3.select_input_source(InputSource.TUNER)
    assert b"Z3TUNER\r" in mock_serial.written_data


async def test_zone3_set_volume(receiver, mock_serial):
    await receiver.zone_3.set_volume(-10.0)
    assert b"Z370\r" in mock_serial.written_data


# -- Query tests --


async def test_query_power(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("PWSTANDBY")

    task = asyncio.create_task(respond())
    result = await receiver.query_power()
    await task
    assert result is False


async def test_query_volume(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("MVMAX 98")
        mock_serial.inject_response("MVMIN 99")
        mock_serial.inject_response("MV75")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_volume()
    await task
    assert result == -5.0
    assert receiver.state.main_zone.volume_max == 18.0
    assert receiver.state.main_zone.volume_min == -80.0


async def test_query_mute(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("MUOFF")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_mute()
    await task
    assert result is False


async def test_query_main_zone(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("ZMON")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_power()
    await task
    assert result is True


async def test_query_input_source(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SIDVD")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_input_source()
    await task
    assert result == InputSource.DVD


async def test_query_surround_mode(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("MSDOLBY PL2X C")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_surround_mode()
    await task
    assert result == "DOLBY PL2X C"


async def test_query_digital_input(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SDAUTO")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_digital_input()
    await task
    assert result == DigitalInputMode.AUTO


async def test_query_digital_input_no_returns_none(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SDNO")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_digital_input()
    await task
    assert result is None


async def test_query_video_select(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SVDVD")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_video_select()
    await task
    assert result == InputSource.DVD


async def test_query_video_select_off_returns_none(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SVOFF")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_video_select()
    await task
    assert result is None


async def test_query_rec_select(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("SRCD")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_rec_select()
    await task
    assert result == InputSource.CD


async def test_query_tuner_frequency(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("TF105000")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_tuner_frequency()
    await task
    assert result == "105000"


async def test_query_tuner_preset(receiver, mock_serial):
    async def respond():
        await asyncio.sleep(0.05)
        mock_serial.inject_response("TPA1")

    task = asyncio.create_task(respond())
    result = await receiver.main.query_tuner_preset()
    await task
    assert result == "A1"


# -- Event tests: input source --


async def test_input_source_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SIDVD")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.input_source == InputSource.DVD


async def test_input_source_event_with_slash(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SIDBS/SAT")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.input_source == InputSource.DBS_SAT


# -- Event tests: surround mode --


async def test_surround_mode_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MSDIRECT")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.surround_mode == "DIRECT"


async def test_surround_mode_event_combined(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MSDOLBY D+PL2X C")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.surround_mode == "DOLBY D+PL2X C"


# -- Event tests: channel volume --


async def test_channel_volume_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVFL 52")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.channel_volumes["FL"] == 2.0


async def test_channel_volume_event_subwoofer(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVSW 55")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.channel_volumes["SW"] == 5.0


async def test_channel_volume_event_surround_back_left(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVSBL 48")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.channel_volumes["SBL"] == -2.0


async def test_channel_volume_event_accepts_unknown_channel(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVFH 51")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.channel_volumes["FH"] == 1.0


async def test_channel_volume_up_event_no_state_change(receiver, mock_serial):
    """CV UP/DOWN events should not update state."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVFL UP")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_duplicate_channel_volume_event_no_state_change(receiver, mock_serial):
    """Duplicate channel volume values should not notify subscribers."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVFL 50")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_multiple_channel_volume_events(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("CVFL 50")
    mock_serial.inject_response("CVFR 52")
    mock_serial.inject_response("CVC 48")
    await asyncio.sleep(0.1)

    assert len(states) == 2
    assert states[-1].main_zone.channel_volumes["FL"] == 0.0
    assert states[-1].main_zone.channel_volumes["FR"] == 2.0
    assert states[-1].main_zone.channel_volumes["C"] == -2.0


# -- Event tests: parameter settings --


async def test_tone_defeat_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSTONE DEFEAT ON")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tone_defeat is True


async def test_tone_defeat_off_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSTONE DEFEAT ON")
    await asyncio.sleep(0.05)
    mock_serial.inject_response("PSTONE DEFEAT OFF")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tone_defeat is False


async def test_surround_back_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSSB:MTRX ON")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.surround_back == SurroundBack.MTRX_ON


async def test_surround_back_off_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSSB:MTRX ON")
    await asyncio.sleep(0.05)
    mock_serial.inject_response("PSSB:OFF")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.surround_back == SurroundBack.OFF


async def test_cinema_eq_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSCINEMA EQ.ON")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.cinema_eq is True


async def test_mode_setting_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSMODE : MUSIC")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.mode_setting == ModeSetting.MUSIC


async def test_room_eq_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PSROOM EQ:FLAT")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.room_eq == RoomEQ.FLAT


# -- Event tests: digital input --


async def test_digital_input_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SDANALOG")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.digital_input == DigitalInputMode.ANALOG


async def test_digital_input_no_event(receiver, mock_serial, caplog):
    """SD NO should clear digital_input to None without warning."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SDNO")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.digital_input is None
    assert "Unknown digital input mode: NO" not in caplog.text


# -- Event tests: video select --


async def test_video_select_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SVCD")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.video_select == InputSource.CD


async def test_video_select_source_event(receiver, mock_serial):
    """SV SOURCE should clear video_select to None."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SVSOURCE")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.video_select is None


async def test_video_select_off_event(receiver, mock_serial, caplog):
    """SV OFF should clear video_select to None without warning."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SVOFF")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.video_select is None
    assert "Unknown video source: OFF" not in caplog.text


# -- Event tests: rec select --


async def test_rec_select_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SRCDR/TAPE1")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.rec_select == InputSource.CDR_TAPE1


async def test_rec_select_source_event(receiver, mock_serial):
    """SR SOURCE should clear rec_select to None."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("SRSOURCE")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.rec_select is None


# -- Event tests: tuner --


async def test_tuner_frequency_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("TF106000")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tuner_frequency == "106000"


async def test_tuner_frequency_up_no_state(receiver, mock_serial):
    """TF UP/DOWN should not update state."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("TFUP")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_tuner_preset_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("TPB2")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tuner_preset == "B2"


async def test_tuner_band_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("TMAM")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tuner_band == TunerBand.AM


async def test_tuner_mode_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("TMMANUAL")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.tuner_mode == TunerMode.MANUAL


# -- Event tests: zone 2 --


async def test_zone2_power_on_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z2ON")
    await asyncio.sleep(0.1)

    assert states[-1].zone_2.power is True


async def test_zone2_power_off_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z2ON")
    await asyncio.sleep(0.05)
    mock_serial.inject_response("Z2OFF")
    await asyncio.sleep(0.1)

    assert states[-1].zone_2.power is False


async def test_zone2_source_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z2DVD")
    await asyncio.sleep(0.1)

    assert states[-1].zone_2.input_source == InputSource.DVD


async def test_zone2_volume_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z280")
    await asyncio.sleep(0.1)

    assert states[-1].zone_2.volume == 0.0


async def test_zone2_volume_up_no_state(receiver, mock_serial):
    """Z2 UP/DOWN should not trigger state change."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z2UP")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_zone2_source_cancel_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    # Set a source first
    mock_serial.inject_response("Z2DVD")
    await asyncio.sleep(0.05)
    # Cancel it
    mock_serial.inject_response("Z2SOURCE")
    await asyncio.sleep(0.1)

    assert states[-1].zone_2.input_source is None


# -- Event tests: zone 3 (both Z3 and Z1 prefixes) --


async def test_zone3_power_on_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z3ON")
    await asyncio.sleep(0.1)

    assert states[-1].zone_3.power is True


async def test_zone3_source_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z3TUNER")
    await asyncio.sleep(0.1)

    assert states[-1].zone_3.input_source == InputSource.TUNER


async def test_zone3_sleep_timer_event_ignored(receiver, mock_serial, caplog):
    """Zone sleep timer payloads should not be treated as sources."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z3SLPOFF")
    await asyncio.sleep(0.1)

    assert len(states) == 0
    assert "Unknown zone source: SLPOFF" not in caplog.text


async def test_zone3_volume_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z370")
    await asyncio.sleep(0.1)

    assert states[-1].zone_3.volume == -10.0


async def test_zone3_legacy_z1_prefix_event(receiver, mock_serial):
    """Z1 prefix (legacy AVR-3803/3805) should also update zone3 state."""
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("Z1ON")
    await asyncio.sleep(0.1)

    assert states[-1].zone_3.power is True


# -- Existing event/subscriber tests --


async def test_subscribe_receives_events(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MV75")
    await asyncio.sleep(0.1)

    assert len(states) == 1
    assert states[0].main_zone.volume == -5.0


async def test_unsubscribe(receiver, mock_serial):
    states: list[ReceiverState] = []
    unsub = receiver.subscribe(lambda s: states.append(s))
    unsub()

    mock_serial.inject_response("MV75")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_power_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PWSTANDBY")
    await asyncio.sleep(0.1)

    assert states[-1].power is False


async def test_duplicate_power_event_no_state_change(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PWON")
    await asyncio.sleep(0.1)

    assert len(states) == 0


async def test_mute_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MUON")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.mute is True


async def test_main_zone_event(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("ZMOFF")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.power is False


async def test_max_volume_event(receiver, mock_serial):
    """MVMAX messages should update the stored max volume."""
    states: list[ReceiverState] = []
    receiver._state.main_zone.volume_max = None
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MVMAX 98")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.volume_max == 18.0
    assert states[-1].main_zone.volume == 0.0


async def test_min_volume_event(receiver, mock_serial):
    """MVMIN messages should update the stored min volume."""
    states: list[ReceiverState] = []
    receiver._state.main_zone.volume_min = None
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("MVMIN 99")
    await asyncio.sleep(0.1)

    assert states[-1].main_zone.volume_min == -80.0
    assert states[-1].main_zone.volume == 0.0


async def test_multiple_events(receiver, mock_serial):
    states: list[ReceiverState] = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.inject_response("PWSTANDBY")
    mock_serial.inject_response("MV75")
    mock_serial.inject_response("MUON")
    await asyncio.sleep(0.1)

    assert len(states) == 3
    assert states[-1].power is False
    assert states[-1].main_zone.volume == -5.0
    assert states[-1].main_zone.mute is True


async def test_bad_callback_doesnt_break(receiver, mock_serial):
    """An exception in a subscriber shouldn't prevent other processing."""

    def bad_callback(state):
        raise RuntimeError("oops")

    good_states: list[ReceiverState] = []
    receiver.subscribe(bad_callback)
    receiver.subscribe(lambda s: good_states.append(s))

    mock_serial.inject_response("PWSTANDBY")
    await asyncio.sleep(0.1)

    assert len(good_states) == 1


# -- Teardown tests --


async def test_read_error_closes_writer():
    """A read error should close the writer and mark disconnected."""
    mock = MockSerialConnection()
    recv = await connect_with_defaults(mock)

    assert recv.connected

    mock.reader.set_exception(OSError("device unplugged"))
    await asyncio.sleep(0.1)

    assert not recv.connected
    mock.writer.close.assert_called_once()
    mock.writer.wait_closed.assert_called()


async def test_read_eof_closes_writer():
    """EOF on the reader should close the writer and mark disconnected."""
    mock = MockSerialConnection()
    recv = await connect_with_defaults(mock)

    assert recv.connected

    mock.reader.feed_eof()
    await asyncio.sleep(0.1)

    assert not recv.connected
    mock.writer.close.assert_called_once()
    mock.writer.wait_closed.assert_called()


async def test_write_error_closes_reader():
    """A write error should tear down the connection including the read loop."""
    mock = MockSerialConnection()
    recv = await connect_with_defaults(mock)

    assert recv.connected
    read_task = recv._read_task

    mock.writer.drain = AsyncMock(side_effect=OSError("device unplugged"))

    with pytest.raises(OSError, match="device unplugged"):
        await recv.power_on()

    assert not recv.connected
    mock.writer.close.assert_called_once()
    assert read_task.cancelled() or read_task.done()


async def test_query_write_error_closes_reader():
    """A write error during a query should tear down the connection."""
    mock = MockSerialConnection()
    recv = await connect_with_defaults(mock)

    assert recv.connected

    mock.writer.drain = AsyncMock(side_effect=OSError("device unplugged"))

    with pytest.raises(OSError, match="device unplugged"):
        await recv.query_power()

    assert not recv.connected
    mock.writer.close.assert_called_once()
    assert len(recv._pending_queries) == 0


async def test_read_error_notifies_none(receiver, mock_serial):
    """Subscribers receive None when the connection is lost via read error."""
    states = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.reader.set_exception(OSError("device unplugged"))
    await asyncio.sleep(0.1)

    assert states[-1] is None


async def test_read_eof_notifies_none(receiver, mock_serial):
    """Subscribers receive None when the connection is lost via EOF."""
    states = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.reader.feed_eof()
    await asyncio.sleep(0.1)

    assert states[-1] is None


async def test_write_error_notifies_none(receiver, mock_serial):
    """Subscribers receive None when the connection is lost via write error."""
    states = []
    receiver.subscribe(lambda s: states.append(s))

    mock_serial.writer.drain = AsyncMock(side_effect=OSError("device unplugged"))

    with pytest.raises(OSError):
        await receiver.power_on()

    assert states[-1] is None


async def test_disconnect_notifies_none(receiver, mock_serial):
    """Subscribers receive None on explicit disconnect."""
    states = []
    receiver.subscribe(lambda s: states.append(s))

    await receiver.disconnect()

    assert states[-1] is None
