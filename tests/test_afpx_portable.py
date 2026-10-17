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
