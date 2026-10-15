import pytest
from pydantic import ValidationError

from helixtune.dsp.fixed import word_824
from helixtune.model import CHANNELS, Channel, Tune


def test_channel_order_is_normalized_without_losing_identity():
    channels = Tune().channels
    channels[0].gain_db = -20
    tune = Tune(channels=list(reversed(channels)))
    assert "".join(c.id for c in tune.channels) == CHANNELS
    assert tune.channel("A").gain_db == -20


@pytest.mark.parametrize("case", ["missing", "duplicate", "extra", "unknown"])
def test_incomplete_or_ambiguous_physical_outputs_rejected(case):
    data = Tune().model_dump()
    if case == "missing":
        data["channels"].pop()
    elif case == "duplicate":
        data["channels"][-1]["id"] = "A"
    elif case == "extra":
        data["channels"].append(data["channels"][0])
    else:
        data["channels"][-1]["id"] = "Z"
    with pytest.raises(ValidationError):
        Tune.model_validate(data)


def test_lowercase_channel_id_normalized():
    assert Channel(id="a").id == "A"


@pytest.mark.parametrize("rate", [48000, 192000, 0, float("nan"), float("inf")])
def test_unsupported_sample_rate_rejected(rate):
    with pytest.raises(ValidationError):
        Tune(sample_rate=rate)


def test_renderer_uses_physical_ids_even_if_list_mutated(synthetic_mapping):
    tune = Tune()
    tune.channel("A").gain_db = -20
    tune.channel("J").gain_db = -6
    expected = synthetic_mapping.render(tune)
    tune.channels.reverse()  # in-memory mutations bypass model validation
    image = synthetic_mapping.render(tune)
    assert image == expected
    assert image[synthetic_mapping.channels[0].gain] == word_824(0.1)
    assert image[synthetic_mapping.channels[-1].gain] == word_824(10 ** (-6 / 20))
