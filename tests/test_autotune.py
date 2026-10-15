import math

import numpy as np
import pytest

from helixtune import autotune
from helixtune import measurements as M
from helixtune.dsp import filters as F
from helixtune.model import Crossover, Tune

FS = 96000.0
G = M.GRID


def test_fit_removes_a_known_peak():
    peak = autotune._peak_db(250, 7.0, 3.0, FS, G)
    bands, met = autotune.fit_eq(peak, np.zeros_like(G), G, 60, 2000, FS, max_bands=4, max_boost=3)
    assert bands, "should place at least one band"
    f, g, q = bands[0]
    assert abs(math.log2(f / 250)) < 0.15 and g < -5
    assert met["rms_after"] < met["rms_before"] / 3


def test_fit_caps_boost_and_never_stacks_bands():
    dip = autotune._peak_db(1000, -10.0, 2.0, FS, G)
    bands, _ = autotune.fit_eq(dip, np.zeros_like(G), G, 200, 5000, FS, max_bands=6, max_boost=3)
    assert all(g <= 3 for _, g, _ in bands)
    fs_ = sorted(f for f, _, _ in bands)
    assert all(math.log2(b / a) >= 1 / 6 - 1e-9 for a, b in zip(fs_, fs_[1:]))


def test_fit_ignores_out_of_band_errors():
    bump = autotune._peak_db(5000, 9.0, 2.0, FS, G)
    bands, _ = autotune.fit_eq(bump, np.zeros_like(G), G, 60, 1000, FS, max_bands=4, max_boost=3)
    assert bands == []


def test_alignment_from_distances():
    t = Tune()
    p = autotune.propose_alignment(t, {"A": 150, "B": 100, "C": 0})
    delays = {e.channel: e.value for e in p.edits}
    assert "C" not in delays  # zero/absent distances ignored
    assert delays.get("A", 0) == 0  # farthest driver is the reference
    assert delays["B"] == pytest.approx(50 / 100 / 343 * 1000, abs=1e-3)


def test_proposal_merges_onto_current_tune():
    t = Tune()
    p = autotune.propose_alignment(t, {"A": 150, "B": 100})
    t2 = t.model_copy(deep=True)
    t2.channel("C").hp = Crossover(freq_hz=300)  # unrelated edit after the proposal was made
    applied = p.apply_to(t2)
    assert applied.channel("C").hp.freq_hz == 300
    assert applied.channel("B").delay_ms > 1.4
