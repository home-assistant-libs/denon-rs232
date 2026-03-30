"""Tests for denon_rs232 receiver model definitions."""

from denon_rs232 import DigitalInputMode, InputSource
from denon_rs232.models import (
    ALL_MODELS,
    AVR_2308CI,
    AVR_2808CI,
    AVR_3310CI,
    AVR_3803,
    AVR_3805,
    AVR_4308CI,
    AVR_987,
    AVR_X1000,
    AVR_X2700H,
    AVR_X4000,
    AVR_X4200W,
)


# -- AVR-3805 (legacy) --


def test_avr_3805_excludes_invalid_sources():
    """AVR-3805 should not include VCR-3 or MD/TAPE2."""
    assert InputSource.VCR_3 not in AVR_3805.input_sources
    assert InputSource.MD_TAPE2 not in AVR_3805.input_sources


def test_avr_3805_includes_valid_sources():
    assert InputSource.CD in AVR_3805.input_sources
    assert InputSource.DVD in AVR_3805.input_sources
    assert InputSource.DBS_SAT in AVR_3805.input_sources


def test_avr_3805_excludes_invalid_digital():
    """AVR-3805 should not include RF or EXT.IN-2."""
    assert DigitalInputMode.RF not in AVR_3805.digital_inputs
    assert DigitalInputMode.EXT_IN_2 not in AVR_3805.digital_inputs


def test_avr_3805_includes_valid_digital():
    assert DigitalInputMode.AUTO in AVR_3805.digital_inputs
    assert DigitalInputMode.EXT_IN_1 in AVR_3805.digital_inputs


def test_avr_3805_zone3_prefix():
    assert AVR_3805.zone3_prefix == "Z1"


# -- AVR-3803 (legacy with full digital set) --


def test_avr_3803_includes_vcr3_and_md():
    """AVR-3803 has VCR-3 and MD/TAPE2."""
    assert InputSource.VCR_3 in AVR_3803.input_sources
    assert InputSource.MD_TAPE2 in AVR_3803.input_sources


def test_avr_3803_includes_rf_and_ext2():
    """AVR-3803 has Gen1 full digital set including RF and EXT.IN-2."""
    assert DigitalInputMode.RF in AVR_3803.digital_inputs
    assert DigitalInputMode.EXT_IN_2 in AVR_3803.digital_inputs


def test_avr_3803_zone3_prefix():
    assert AVR_3803.zone3_prefix == "Z1"


# -- AVR-2308CI (transition, no zone 3) --


def test_avr_2308ci_no_zone3():
    assert AVR_2308CI.zone3_prefix is None


def test_avr_2308ci_has_hdp():
    assert InputSource.HDP in AVR_2308CI.input_sources


def test_avr_2308ci_no_modern_sources():
    assert InputSource.BD not in AVR_2308CI.input_sources
    assert InputSource.MPLAY not in AVR_2308CI.input_sources


# -- AVR-3310CI (transition to modern digital) --


def test_avr_3310ci_has_hdmi_digital():
    """AVR-3310CI uses Gen2 digital inputs with HDMI and DIGITAL."""
    assert DigitalInputMode.HDMI in AVR_3310CI.digital_inputs
    assert DigitalInputMode.DIGITAL in AVR_3310CI.digital_inputs


def test_avr_3310ci_no_legacy_digital():
    """AVR-3310CI should not have PCM/DTS/RF individual digital modes."""
    assert DigitalInputMode.PCM not in AVR_3310CI.digital_inputs
    assert DigitalInputMode.RF not in AVR_3310CI.digital_inputs


def test_avr_3310ci_zone3():
    assert AVR_3310CI.zone3_prefix == "Z3"


# -- AVR-X1000 (modern, no zone 3) --


def test_avr_x1000_modern_sources():
    assert InputSource.BD in AVR_X1000.input_sources
    assert InputSource.MPLAY in AVR_X1000.input_sources
    assert InputSource.GAME in AVR_X1000.input_sources
    assert InputSource.SAT_CBL in AVR_X1000.input_sources


def test_avr_x1000_streaming():
    assert InputSource.SPOTIFY in AVR_X1000.input_sources
    assert InputSource.PANDORA in AVR_X1000.input_sources


def test_avr_x1000_no_zone3():
    assert AVR_X1000.zone3_prefix is None


def test_avr_x1000_no_legacy_sources():
    assert InputSource.VDP not in AVR_X1000.input_sources
    assert InputSource.DBS_SAT not in AVR_X1000.input_sources
    assert InputSource.VCR_1 not in AVR_X1000.input_sources


# -- AVR-X4000 (modern with zone 3 and BT) --


def test_avr_x4000_has_bt():
    assert InputSource.BT in AVR_X4000.input_sources


def test_avr_x4000_zone3():
    assert AVR_X4000.zone3_prefix == "Z3"


def test_avr_x4000_gen3_digital():
    assert DigitalInputMode.AUTO in AVR_X4000.digital_inputs
    assert DigitalInputMode.HDMI in AVR_X4000.digital_inputs
    assert DigitalInputMode.DIGITAL in AVR_X4000.digital_inputs
    assert DigitalInputMode.ANALOG in AVR_X4000.digital_inputs
    assert DigitalInputMode.EXT_IN_1 not in AVR_X4000.digital_inputs


# -- AVR-X4200W (newest) --


def test_avr_x4200w_has_all_modern():
    assert InputSource.BT in AVR_X4200W.input_sources
    assert InputSource.HDRADIO in AVR_X4200W.input_sources
    assert InputSource.SPOTIFY in AVR_X4200W.input_sources


def test_avr_x4200w_zone3():
    assert AVR_X4200W.zone3_prefix == "Z3"


# -- AVR-X2700H (modern with 8K source) --


def test_avr_x2700h_has_8k_and_modern_core_sources():
    assert InputSource.EIGHT_K in AVR_X2700H.input_sources
    assert InputSource.BD in AVR_X2700H.input_sources
    assert InputSource.MPLAY in AVR_X2700H.input_sources
    assert InputSource.NET in AVR_X2700H.input_sources


def test_avr_x2700h_no_zone3():
    assert AVR_X2700H.zone3_prefix is None


def test_avr_x2700h_skips_known_unsupported_startup_queries():
    assert AVR_X2700H.unsupported_startup_queries == {"SR", "TF", "TP"}


# -- General model checks --


def test_all_models_tuple():
    """ALL_MODELS should contain all defined models."""
    assert len(ALL_MODELS) == 11
    assert AVR_3805 in ALL_MODELS
    assert AVR_X4200W in ALL_MODELS
    assert AVR_X2700H in ALL_MODELS


def test_all_models_have_auto_digital():
    """Every model should support AUTO digital input mode."""
    for model in ALL_MODELS:
        assert DigitalInputMode.AUTO in model.digital_inputs, model.name


def test_all_models_have_cd():
    """Every model should support CD input."""
    for model in ALL_MODELS:
        assert (
            InputSource.CD in model.digital_inputs
            or InputSource.CD in model.input_sources
        ), model.name
