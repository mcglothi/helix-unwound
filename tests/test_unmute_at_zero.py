"""Explicit 'Unmute at 0 dB' (2026-10-18: the positive-gain unmute rule blocked Tim from unmuting
his +5 dB midbasses, with no usable way forward in the UI)."""
import pytest

from conftest import owner_client
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.model import Tune


@pytest.fixture
def client(synthetic_mapping, tmp_path):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    t = Tune()
    for cid in ("A", "B"):
        t.channel(cid).link_group = 2
        t.channel(cid).gain_db = 5.0
        t.channel(cid).mute = True
    engine.tune = t                       # starting state (offline), as an imported preset would be
    with owner_client(create_app(engine)) as c:
        yield c, engine


def test_plain_unmute_at_positive_gain_is_still_refused(client):
    c, engine = client
    r = c.patch("/api/channels/A", json={"mute": False})
    assert r.status_code == 409 and "unmuting with positive gain" in str(r.json()["problems"])
    assert engine.tune.channel("A").mute


def test_unmute_at_zero_is_one_edit_for_the_linked_pair(client):
    c, engine = client
    depth = len(engine.history)
    r = c.post("/api/channels/A/unmute-at-zero", json={"reviewed_gain_db": {"A": 5.0, "B": 5.0}})
    assert r.status_code == 200, r.text
    for cid in ("A", "B"):
        assert (engine.tune.channel(cid).gain_db, engine.tune.channel(cid).mute) == (0.0, False)
    assert len(engine.history) == depth + 1                               # atomic: one undo step
    assert engine.tune.channel("C").mute is False and engine.tune.channel("C").gain_db == 0.0


def test_a_stale_review_changes_nothing(client):
    c, engine = client
    for reviewed in ({"A": 4.0, "B": 5.0}, {"A": 5.0}):                   # changed level / missed partner
        r = c.post("/api/channels/A/unmute-at-zero", json={"reviewed_gain_db": reviewed})
        assert r.status_code >= 400 and "review again" in r.text
    assert engine.tune.channel("A").mute and engine.tune.channel("B").gain_db == 5.0


def test_never_raises_gain(client):
    c, engine = client
    c.patch("/api/channels/A?link=false", json={"gain_db": -3.0})
    r = c.post("/api/channels/A/unmute-at-zero", json={"reviewed_gain_db": {"A": -3.0, "B": 5.0}})
    assert r.status_code == 200
    assert engine.tune.channel("A").gain_db == -3.0 and engine.tune.channel("B").gain_db == 0.0
