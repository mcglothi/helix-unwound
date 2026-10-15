import numpy as np
import pytest

from helixtune.dsp import filters as F
from helixtune.dsp import fixed

FS = 96000.0


def mag_db(sections, f):
    return 20 * np.log10(abs(F.cascade_response(sections, np.array([float(f)]), FS)[0]))


def test_peak_hits_gain_at_center():
    bq = F.eq_biquad(F.EqType.PEAK, 1000, 6.0, 1.4, FS)
    assert mag_db([bq], 1000) == pytest.approx(6.0, abs=0.01)
    assert abs(mag_db([bq], 20)) < 0.05


def test_shelves_reach_gain():
    lo = F.eq_biquad(F.EqType.LOW_SHELF, 100, -4.0, 0.707, FS)
    hi = F.eq_biquad(F.EqType.HIGH_SHELF, 8000, 3.0, 0.707, FS)
    assert mag_db([lo], 10) == pytest.approx(-4.0, abs=0.05)
    assert mag_db([hi], 40000) == pytest.approx(3.0, abs=0.1)


@pytest.mark.parametrize("slope", [12, 18, 24, 36, 48])
@pytest.mark.parametrize("hp", [True, False])
def test_butterworth_minus3_at_fc(slope, hp):
    b, f1 = F.crossover_sections(F.XoType.BUTTERWORTH, slope, 2000, FS, hp)
    assert len(b) * 2 + len(f1) == slope // 6
    assert mag_db(b + f1, 2000) == pytest.approx(-3.01, abs=0.05)


@pytest.mark.parametrize("slope", [12, 24, 36, 48])
def test_linkwitz_riley_minus6_and_sums_flat(slope):
    hp = sum(F.crossover_sections(F.XoType.LINKWITZ_RILEY, slope, 2000, FS, True), [])
    lp = sum(F.crossover_sections(F.XoType.LINKWITZ_RILEY, slope, 2000, FS, False), [])
    assert mag_db(hp, 2000) == pytest.approx(-6.02, abs=0.05)
    f = F.log_freqs(64, 100, 20000)
    total = F.cascade_response(hp, f, FS) + F.cascade_response(lp, f, FS) * (-1 if slope in (12, 36) else 1)
    assert np.max(np.abs(20 * np.log10(np.abs(total)))) < 0.05


def test_slope_actually_achieved():
    b, f1 = F.crossover_sections(F.XoType.BUTTERWORTH, 24, 1000, FS, True)
    drop = mag_db(b + f1, 125) - mag_db(b + f1, 250)
    assert drop == pytest.approx(-24, abs=1.0)


def test_824_roundtrip_and_sign():
    for x in (0.0, 1.0, -1.0, 1.999, -2.5, 127.9):
        assert fixed.from_824(int.from_bytes(fixed.word_824(x), "big")) == pytest.approx(x, abs=1e-7)
    assert fixed.word_824(1.0) == bytes.fromhex("01000000")
    assert fixed.word_824(-1.0) == bytes.fromhex("ff000000")
    with pytest.raises(OverflowError):
        fixed.to_824(200)
