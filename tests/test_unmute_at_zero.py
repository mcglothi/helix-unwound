"""Explicit 'Unmute at 0 dB' (2026-10-18: the positive-gain unmute rule blocked Tim from unmuting
his +5 dB midbasses, with no usable way forward in the UI)."""
import pytest

from conftest import owner_client
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.model import Role, Tune


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


@pytest.fixture
def playing(synthetic_mapping, tmp_path):
    """A/B linked and playing at +5 dB, as in Tim's tune."""
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    t = Tune()
    for cid in ("A", "B"):
        t.channel(cid).link_group = 2
        t.channel(cid).gain_db = 5.0
    engine.tune = t
    with owner_client(create_app(engine)) as c:
        yield c, engine


def test_mute_unmute_restores_the_previous_level_repeatedly(playing):
    """Tim 2026-10-18: a pro tool; mute/unmute during system testing must just go back."""
    c, engine = playing
    for _ in range(3):
        assert c.patch("/api/channels/A", json={"mute": True}).status_code == 200
        assert c.get("/api/status").json()["unmute_levels"] == {"A": 5.0, "B": 5.0}
        r = c.patch("/api/channels/A", json={"mute": False})
        assert r.status_code == 200, r.text
        assert [(engine.tune.channel(x).gain_db, engine.tune.channel(x).mute) for x in "AB"] == [(5.0, False)] * 2
    assert c.get("/api/status").json()["unmute_levels"] == {}


def test_raised_while_muted_still_needs_the_review(playing):
    c, engine = playing
    c.patch("/api/channels/A", json={"mute": True})
    assert c.patch("/api/channels/A", json={"gain_db": 6.0}).status_code == 200
    r = c.patch("/api/channels/A", json={"mute": False})
    assert r.status_code == 409 and "above the +5 dB it played at" in str(r.json()["problems"])
    assert c.post("/api/channels/A/unmute-at-zero", json={"reviewed_gain_db": {"A": 6.0, "B": 6.0}}).status_code == 200


def test_lowered_while_muted_unmutes_directly(playing):
    c, engine = playing
    c.patch("/api/channels/A", json={"mute": True})
    c.patch("/api/channels/A", json={"gain_db": 3.0})
    assert c.patch("/api/channels/A", json={"mute": False}).status_code == 200
    assert engine.tune.channel("B").gain_db == 3.0 and not engine.tune.channel("B").mute


def test_changed_routing_or_a_reconnect_forgets_the_level(playing):
    from helixtune.emulator import EmulatedDevice
    from helixtune.protocol.client import Client
    c, engine = playing
    c.patch("/api/channels/A", json={"mute": True})
    c.patch("/api/channels/A?link=false", json={"mix": {"R": 1.0}})                  # A rerouted while muted
    r = c.patch("/api/channels/A?link=false", json={"mute": False})
    assert r.status_code == 409 and "no remembered level" in str(r.json()["problems"])
    assert c.patch("/api/channels/B?link=false", json={"mute": False}).status_code == 200   # B untouched: fine
    c.patch("/api/channels/B?link=false", json={"mute": True})
    engine.attach(Client(EmulatedDevice(), timeout=0.05), "emulator")               # new connection
    assert engine.unmute_levels() == {}
    assert c.patch("/api/channels/B?link=false", json={"mute": False}).status_code == 409
    engine.detach()


@pytest.mark.parametrize("change", [lambda ch: setattr(ch, "mix", {"R": 1.0}),
                                    lambda ch: setattr(ch, "role", Role.TWEETER)])
def test_reroute_or_role_change_in_the_same_edit_as_unmute_is_refused(playing, change):
    """Codex review of ba497c7: memory must be checked against the proposed output, not the old one."""
    from helixtune.engine import SafetyRejected
    c, engine = playing
    c.patch("/api/channels/A?link=false", json={"mute": True})
    before = engine.tune.model_dump()

    def edit(t):
        change(t.channel("A"))
        t.channel("A").mute = False
    with pytest.raises(SafetyRejected, match="no remembered level"):
        engine.edit("test", "reroute + unmute", edit)
    assert engine.tune.model_dump() == before                              # not adopted
    assert c.patch("/api/channels/A?link=false", json={"mute": False}).status_code == 200   # same context: fine
