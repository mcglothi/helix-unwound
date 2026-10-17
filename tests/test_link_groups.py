"""PC-Tool link groups (.afpx LG): edits to one channel are copied to its linked partners.

Behaviour pinned to the 2026-10-17 USB captures: an EQ, crossover, gain, mute or polarity
edit on output A was written to both A and B (LG=2); a delay edit was written to A only.
Synthetic addresses and an in-memory emulator; no vendor files or personal data.
"""
import xml.etree.ElementTree as ET

import pytest

from conftest import owner_client
from helixtune import afpx
from helixtune.api import create_app
from helixtune.engine import Engine
from helixtune.model import Tune


@pytest.fixture
def client(synthetic_mapping, tmp_path):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    t = Tune()
    for cid, group in (("A", 2), ("B", 2), ("C", 0)):
        t.channel(cid).link_group = group
    t.channel("A").eq[0].freq_hz, t.channel("B").eq[0].freq_hz = 25.0, 80.0
    t.channel("A").delay_ms, t.channel("B").delay_ms = 1.0, 0.0
    engine.apply(t, "test", "linked fixture")
    with owner_client(create_app(engine)) as c:
        yield c, engine


def ch(engine, cid):
    return engine.tune.channel(cid)


def test_linked_channel_fields_copy_but_delay_name_and_routing_stay_separate(client):
    c, engine = client
    r = c.patch("/api/channels/A", json={"gain_db": -3.0, "mute": True, "invert": True,
                                          "delay_ms": 2.5, "name": "Left"})
    assert r.status_code == 200, r.text
    a, b = ch(engine, "A"), ch(engine, "B")
    assert (b.gain_db, b.mute, b.invert) == (-3.0, True, True)
    assert (a.delay_ms, b.delay_ms) == (2.5, 0.0)
    assert b.name != "Left"
    assert ch(engine, "C").gain_db == 0.0


def test_band_edit_copies_the_whole_edited_band_like_pc_tool(client):
    c, engine = client
    c.patch("/api/channels/B/eq/2?link=false", json={"gain_db": -4.0, "enabled": True})
    b_band2 = ch(engine, "B").eq[1].model_copy()
    assert c.patch("/api/channels/A/eq/1", json={"gain_db": 3.0, "enabled": True}).status_code == 200
    a, b = ch(engine, "A").eq[0], ch(engine, "B").eq[0]
    assert b == a and b.freq_hz == 25.0          # B's own 80 Hz is replaced by A's band
    assert ch(engine, "B").eq[1] == b_band2 and ch(engine, "A").eq[1] != b_band2  # other bands untouched


def test_crossover_and_eq_reset_follow_the_link(client):
    c, engine = client
    xo = {"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 70}
    assert c.put("/api/channels/A/hp", json=xo).status_code == 200
    assert ch(engine, "B").hp == ch(engine, "A").hp and ch(engine, "B").hp.freq_hz == 70
    assert c.put("/api/channels/B/hp", content="null", headers={"Content-Type": "application/json"}).status_code == 200
    assert ch(engine, "A").hp is None
    c.patch("/api/channels/B/eq/2", json={"gain_db": 2.0, "enabled": True})
    assert c.post("/api/channels/A/eq/reset").status_code == 200
    assert not any(bd.enabled for bd in ch(engine, "B").eq)


def test_link_false_and_unlinking_edit_one_channel(client):
    c, engine = client
    assert c.patch("/api/channels/A?link=false", json={"gain_db": -6.0}).status_code == 200
    assert ch(engine, "B").gain_db == 0.0
    assert c.patch("/api/channels/A", json={"link_group": 0}).status_code == 200
    assert ch(engine, "B").link_group == 2       # unlinking A does not touch B's setting
    c.patch("/api/channels/A", json={"mute": True})
    assert ch(engine, "B").mute is False
    assert engine.tune.linked("B") == ["B"]


def test_unlinked_channel_edits_only_itself(client):
    c, engine = client
    c.patch("/api/channels/C", json={"gain_db": -2.0})
    assert [x.gain_db for x in engine.tune.channels if x.id != "C"] == [ch(engine, i).gain_db for i in "ABDEFGHIJ"]
    assert ch(engine, "A").gain_db == 0.0


def _preset(lg_a, lg_b, cn_b="8"):
    root = ET.Element("ATF", Dev="15", V="4.80b")
    for on, cn, lg in ((0, "7", lg_a), (1, cn_b, lg_b)):
        ET.SubElement(root, "OC", ON=str(on), CN=cn, LG=lg, MT="1")
    return root


def test_afpx_import_reads_link_groups_and_rejects_odd_values():
    t, rep = afpx.to_tune(_preset("2", "2"), "x")
    assert t.linked("A") == ["A", "B"]
    t, rep = afpx.to_tune(_preset("2", "x9"), "x")
    assert t.channel("B").link_group == 0 and any("link group" in w for w in rep.warnings)
    t, _ = afpx.to_tune(_preset("2", "2", cn_b="0"), "x")   # unassigned output never links
    assert t.linked("A") == ["A"]
