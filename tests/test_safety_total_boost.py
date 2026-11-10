"""H1 (review 2026-11-10): EQ boosts are limited in total per output, not only per band."""

from helixtune import safety
from helixtune.model import EqBand, EqType, Tune

POLICY = safety.SafetyPolicy()


def _peak(freq, gain, q=1.0):
    return EqBand(type=EqType.PEAK, freq_hz=freq, gain_db=gain, q=q, enabled=True)


def _problems(tune, previous=None, prefix="E"):
    return [p for p in safety.check(tune, POLICY, previous=previous) if p.startswith(prefix)]


def test_stacked_bands_within_per_band_limits_are_refused_in_total():
    tune = Tune(name="stacked")
    ch = tune.channel("E")
    for i in range(len(ch.eq)):
        ch.eq[i] = _peak(5000, 3.0)
    problems = _problems(tune, previous=Tune(name="flat"))
    assert any("combine to" in p and "5000 Hz" in p for p in problems), problems


def test_a_narrow_peak_between_grid_points_is_still_found():
    tune = Tune(name="narrow")
    ch = tune.channel("E")
    ch.gain_db = 6.0
    ch.eq[0] = _peak(1234.5, 9.0, q=20.0)
    problems = _problems(tune)
    assert any("combine to +15.0 dB" in p for p in problems), problems


def test_a_typical_tune_passes():
    tune = Tune(name="typical")
    ch = tune.channel("E")
    ch.gain_db = 3.0
    ch.eq[0] = _peak(1000, 4.0)
    ch.eq[1] = _peak(3000, -6.0)
    assert _problems(tune) == []


def test_a_muted_output_is_not_checked_for_total_boost():
    tune = Tune(name="muted")
    ch = tune.channel("E")
    ch.mute = True
    for i in range(len(ch.eq)):
        ch.eq[i] = _peak(5000, 3.0)
    assert not any("combine to" in p for p in _problems(tune))


def test_small_steps_that_add_up_at_one_frequency_are_refused():
    old = Tune(name="old")
    new = Tune(name="new")
    new.channel("E").eq[0] = _peak(1000, 3.0)
    new.channel("E").eq[1] = _peak(1000, 3.0)
    problems = _problems(new, previous=old)
    assert any("output raised by 6.0 dB at 1000 Hz" in p for p in problems), problems


def test_gain_and_band_steps_that_add_up_are_refused():
    old = Tune(name="old")
    new = Tune(name="new")
    new.channel("E").gain_db = 3.0
    new.channel("E").eq[0] = _peak(1000, 3.0)
    problems = _problems(new, previous=old)
    assert any("output raised by" in p for p in problems), problems


def test_one_allowed_step_raises_nothing():
    old = Tune(name="old")
    new = Tune(name="new")
    new.channel("E").eq[0] = _peak(1000, 3.0)
    assert _problems(new, previous=old) == []


def test_an_existing_step_message_is_not_repeated_as_a_combined_one():
    old = Tune(name="old")
    new = Tune(name="new")
    new.channel("E").gain_db = 4.0
    problems = _problems(new, previous=old)
    assert len(problems) == 1 and "gain raised by 4.0 dB" in problems[0], problems


def test_moving_or_removing_a_crossover_is_not_a_boost_step():
    from helixtune.model import Crossover, XoType

    old = Tune(name="old")
    old.channel("A").hp = Crossover(type=XoType.LINKWITZ_RILEY, slope_db=24, freq_hz=80)
    lowered = old.model_copy(deep=True)
    lowered.channel("A").hp.freq_hz = 50
    removed = old.model_copy(deep=True)
    removed.channel("A").hp = None
    assert _problems(lowered, previous=old, prefix="A") == []
    assert _problems(removed, previous=old, prefix="A") == []
