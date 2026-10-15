"""Synthetic addresses for engine regressions; no vendor files or personal data.

The layout is deliberately invented. It exercises rendering and transport/state
handling, and makes no claim about actual HELIX addresses or protocol correctness.
"""

from itertools import count

import pytest

from helixtune.mapping import ChannelAddrs, DeviceMapping
from helixtune.model import CHANNELS, EQ_BANDS


@pytest.fixture
def synthetic_mapping():
    addresses = count(1)

    def section(keys):
        return {key: next(addresses) for key in keys}

    device_map = DeviceMapping.__new__(DeviceMapping)
    device_map.master = next(addresses)
    device_map.channels = [ChannelAddrs(
        eq=[section(("B2", "B1", "B0", "A2", "A1")) for _ in range(EQ_BANDS)],
        xo_bq=[section(("B2", "B1", "B0", "A2", "A1")) for _ in range(7)],
        xo_fo=[section(("B1", "B0", "A1")) for _ in range(2)],
        delay=next(addresses), invert=next(addresses), gain=next(addresses),
        mute=next(addresses), mix=section(("L", "R")),
    ) for _ in CHANNELS]
    return device_map
