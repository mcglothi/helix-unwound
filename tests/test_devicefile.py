from pathlib import Path

import pytest

from helixtune import devicefile

DEVICE_FILES = Path(__file__).resolve().parents[1] / "artifacts/extracted/app/deviceFiles"
needs_vendor = pytest.mark.skipif(not DEVICE_FILES.exists(), reason="vendor device files not extracted")


def test_parse_param_header_splits_header_and_params():
    pm = devicefile.parse_param_header(
        "#define HEADERVERSION R1\n#define SLADD 6180\n#define MOD_MASTERVOLUME_ALG0_TARGET_ADDR 123\n"
    )
    assert pm.header == {"HEADERVERSION": "R1", "SLADD": "6180"}
    assert pm.params == {"MASTERVOLUME_ALG0_TARGET": 123}
    assert pm.safeload_base == 6180


@needs_vendor
def test_load_dsp_pro_mk2_map():
    pm = devicefile.load_at01(DEVICE_FILES / "DSPPro2.at01")
    assert pm.header["MATCHINGAF"] == "DSPPro2.AF1"
    assert pm.safeload_base == 6180
    assert len(pm.params) > 2800
    assert pm.find(r"^EQUALIZER_")


@needs_vendor
def test_load_dsp_pro_mk2_program():
    img = devicefile.load_af1(DEVICE_FILES / "DSPPro2.AF1")
    assert img.version == "VR1"
    assert img.register_init[0] == (0xF8, 0x90)
    assert len(img.words) > 1000
