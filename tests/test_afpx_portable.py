"""Synthetic preset XML; no vendor binary, personal preset or hardware required."""
import xml.etree.ElementTree as ET

import pytest

from helixtune import afpx
from helixtune.model import Role


@pytest.mark.parametrize(('code', 'label'), [
    (11, 'Front Center Low'), (12, 'F Sum'), (13, 'Rear L Full'),
    (24, 'Rear Sum'), (25, 'Subwoofer 1'), (26, 'Subwoofer 2'),
    (29, 'Line Out 1'), (36, 'Line Out 8'), (37, 'Subwoofer L'), (38, 'Subwoofer R'),
])
def test_imported_channel_names_match_corrected_pc_tool_table(code, label):
    root = ET.fromstring(f'<ATF Dev="15"><OC ON="0" CN="{code}" /></ATF>')
    tune, _ = afpx.to_tune(root, 'synthetic')
    assert tune.channel('A').name == label
    if label.startswith('Subwoofer'):
        assert tune.channel('A').role == Role.SUBWOOFER


@pytest.mark.parametrize('code', [-1, 99])
def test_unknown_name_code_cannot_index_into_end_of_table(code):
    tune, _ = afpx.to_tune(ET.fromstring(f'<ATF Dev="15"><OC ON="0" CN="{code}" /></ATF>'), 'synthetic')
    assert tune.channel('A').name == f'CN{code}'


@pytest.mark.parametrize('parameter', ['90', '45', '56.25'])
def test_unknown_p_is_reported_without_claiming_or_applying_phase(parameter):
    root = ET.fromstring(f'<ATF Dev="15"><OC ON="0" CN="25" CINV="0"><T T="218" P="{parameter}" PM="3" /></OC></ATF>')
    tune, report = afpx.to_tune(root, 'synthetic')
    assert tune.channel('A').delay_ms == pytest.approx(218 / 96000 * 1000, abs=0.0001)
    assert not tune.channel('A').invert
    warning = next(w for w in report.warnings if 'T.P=' in w)
    assert f'T.P={parameter}' in warning and 'PM=3' in warning
    assert 'unknown' in warning and 'not applied' in warning
    assert '°' not in warning


def _oc(attrs, fils):
    return ET.fromstring(f'<ATF Dev="15"><OC ON="0" CN="25" {attrs}>{fils}</OC></ATF>')


HP20 = '<Fil FN="31" T="16" F="20" G="-24" />'
LP95 = '<Fil FN="30" T="15" F="95" G="-12" />'
EQ1 = '<Fil FN="0" T="17" F="40" G="3" Q="2" />'


def test_bypassed_high_pass_imports_without_a_filter():
    """H3 (review 2026-11-10): the 2022 stored tune has subs hpBy=1 but an active-looking HP filter."""
    tune, rep = afpx.to_tune(_oc('hpBy="1" lpBy="0" EqBy="0"', HP20 + LP95), 'synthetic')
    ch = tune.channel('A')
    assert ch.hp is None and ch.lp is not None and ch.lp.freq_hz == 95
    assert any('high-pass is bypassed' in w for w in rep.warnings)


def test_bypassed_low_pass_and_eq_are_honoured():
    tune, rep = afpx.to_tune(_oc('hpBy="0" lpBy="1" EqBy="1"', HP20 + LP95 + EQ1), 'synthetic')
    ch = tune.channel('A')
    assert ch.hp is not None and ch.lp is None
    assert not ch.eq[0].enabled and ch.eq[0].gain_db == 3 and ch.eq[0].freq_hz == 40
    assert any('EQ is bypassed' in w for w in rep.warnings)


def test_no_bypass_flags_keep_filters():
    tune, rep = afpx.to_tune(_oc('', HP20 + LP95 + EQ1), 'synthetic')
    ch = tune.channel('A')
    assert ch.hp.freq_hz == 20 and ch.lp.freq_hz == 95 and ch.eq[0].enabled
    assert not any('bypass' in w for w in rep.warnings)


def test_unknown_bypass_value_keeps_the_filter_and_warns():
    tune, rep = afpx.to_tune(_oc('hpBy="7"', HP20), 'synthetic')
    assert tune.channel('A').hp is not None
    assert any("unknown hpBy='7'" in w for w in rep.warnings)


def test_unknown_crossover_type_code_is_reported():
    tune, rep = afpx.to_tune(_oc('', '<Fil FN="31" T="12" F="80" G="-24" />'), 'synthetic')
    assert tune.channel('A').hp is None
    assert any('unknown high-pass type code 12' in w for w in rep.warnings)
