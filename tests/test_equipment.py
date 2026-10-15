from pathlib import Path

import pytest
from conftest import owner_client

from helixtune import equipment as eq
from helixtune.api import create_app
from helixtune.devicefile import load_at01
from helixtune.engine import Engine
from helixtune.model import Crossover, Role, Tune

AT01 = Path(__file__).resolve().parents[1] / "artifacts/extracted/app/deviceFiles/DSPPro2.at01"


def test_sealed_box_math():
    d = eq.SystemDesign()
    box = eq.Component(kind=eq.Kind.ENCLOSURE, specs={"type": eq.Spec(value="sealed"), "volume": eq.Spec(value=30)})
    sub = eq.Component(kind=eq.Kind.SUBWOOFER, enclosure=box.id, specs={
        "fs": eq.Spec(value=30), "qts": eq.Spec(value=0.4), "vas": eq.Spec(value=60)})
    d.components += [box, sub]
    a = eq.analyze(d, sub.id)
    # alpha = 2 -> Qtc = 0.4*sqrt(3) = 0.693, Fc = 30*sqrt(3) = 52.0
    assert a["derived"]["qtc"] == pytest.approx(0.693, abs=0.001)
    assert a["derived"]["fc_hz"] == pytest.approx(52.0, abs=0.1)
    assert a["derived"]["f3_hz"] == pytest.approx(52.0, rel=0.03)  # Qtc ~0.707 -> F3 ~ Fc


def test_ported_subsonic():
    d = eq.SystemDesign()
    box = eq.Component(kind=eq.Kind.ENCLOSURE, specs={"type": eq.Spec(value="ported"), "volume": eq.Spec(value=50),
                                                      "port_tuning": eq.Spec(value=32)})
    sub = eq.Component(kind=eq.Kind.SUBWOOFER, enclosure=box.id,
                       specs={"fs": eq.Spec(value=28), "qts": eq.Spec(value=0.35), "vas": eq.Spec(value=70)})
    d.components += [box, sub]
    assert eq.analyze(d, sub.id)["derived"]["recommended_subsonic_hz"] == 22


def test_seed_from_tune():
    t = Tune()
    t.channel("E").role, t.channel("E").name = Role.TWEETER, "Front L High"
    d = eq.seed(t)
    spk = [c for c in d.components if c.kind is eq.Kind.SPEAKER]
    assert [c.channels for c in spk] == [["E"]]
    assert any(c.model == "UMIK-1" and c.serial == "7015199" for c in d.components)


@pytest.mark.skipif(not AT01.exists(), reason="vendor device files not extracted")
def test_recorded_fs_tightens_safety(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    c.put("/api/channels/E/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 1800})
    assert c.patch("/api/channels/E", json={"role": "tweeter", "name": "Front L High"}).status_code == 200
    spk = c.post("/api/equipment", json={"kind": "speaker", "name": "Tweeter L", "channels": ["E"]}).json()
    r = c.patch(f"/api/equipment/{spk['id']}", json={"specs": {"fs": {"value": 1100, "unit": "Hz", "source": "test"}}})
    assert r.status_code == 200
    # 2 x 1100 Hz = 2200 Hz minimum now; 1800 Hz high-pass edits are rejected
    r = c.patch("/api/channels/E", json={"gain_db": -1})
    assert r.status_code == 409 and "2200" in r.json()["problems"][0]
    # a manufacturer minimum stricter than 2xFs wins
    c.patch(f"/api/equipment/{spk['id']}", json={"specs": {"hp_min": {"value": 2600, "unit": "Hz", "source": "test"}}})
    assert "2600" in c.patch("/api/channels/E", json={"gain_db": -1}).json()["problems"][0]
    c.patch(f"/api/equipment/{spk['id']}", json={"specs": {"hp_min": None}})
    assert c.put("/api/channels/E/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 2500}).status_code == 409
    # Removing specs cannot silently relax a physical-output floor.
    c.patch(f"/api/equipment/{spk['id']}", json={"specs": {"fs": None}})
    assert c.put("/api/channels/E/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 1800}).status_code == 409
    assert c.put("/api/protections/E", json={"protection": {"min_hp_hz": 1500, "fs_factor": 2},
                                           "confirm": "RECONFIGURE"}).status_code == 200
    assert c.put("/api/channels/E/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 1800}).status_code == 200
    # wiring integrity
    assert c.post("/api/connections", json={"src": spk["id"], "dst": "nope", "signal": "speaker"}).status_code == 404


@pytest.mark.skipif(not AT01.exists(), reason="vendor device files not extracted")
def test_media_and_positions(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    png = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                        "1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082")
    m = c.post("/api/media", files={"file": ("cab.png", png, "image/png")}, data={"caption": "cab top-down"}).json()
    assert c.get(m["url"]).content == png
    assert c.post("/api/media", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 422
    comp = c.get("/api/design").json()["components"][0]
    c.patch(f"/api/equipment/{comp['id']}", json={"image": m["id"]})
    c.put("/api/design/vehicle", json={"layout_image": m["id"]})
    r = c.put("/api/design/positions", json={"view": "flow", "positions": {comp["id"]: {"x": 10, "y": 20}}})
    assert r.json()["updated"] == 1
    d = c.get("/api/design").json()
    assert d["components"][0]["flow_pos"] == {"x": 10, "y": 20} and d["components"][0]["image"] == m["id"]
    # deleting media clears references
    c.delete(f"/api/media/{m['id']}")
    d = c.get("/api/design").json()
    assert d["components"][0]["image"] is None and d["vehicle"]["layout_image"] is None
    assert c.get(m["url"]).status_code == 404


def test_legacy_port_names_upgraded():
    d = eq.SystemDesign()
    dsp = eq.Component(kind=eq.Kind.DSP)
    spk = eq.Component(kind=eq.Kind.SPEAKER, channels=["A"])
    d.components += [dsp, spk]
    d.connections.append(eq.Connection(src=dsp.id, src_port="Out A", dst=spk.id, signal=eq.Signal.LINE))
    assert eq.normalize_ports(d)
    assert (d.connections[0].src_port, d.connections[0].dst_port) == ("outA", "in")
    assert not eq.normalize_ports(d)  # idempotent



@pytest.mark.skipif(not AT01.exists(), reason="vendor device files not extracted")
def test_manufacturer_lowpass_limit(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    c.put("/api/channels/A/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 60})
    c.patch("/api/channels/A", json={"role": "midbass"})
    spk = c.post("/api/equipment", json={"kind": "speaker", "channels": ["A"],
                                         "specs": {"lp_max": {"value": 3500, "unit": "Hz", "source": "test"}}}).json()
    r = c.patch("/api/channels/A", json={"gain_db": -1})
    assert r.status_code == 409 and "low-pass none is above" in r.json()["problems"][0]
    assert c.put("/api/channels/A/lp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 400}).status_code == 200



def test_shared_enclosure_splits_volume():
    d = eq.SystemDesign()
    box = eq.Component(kind=eq.Kind.ENCLOSURE, specs={"type": eq.Spec(value="sealed"), "volume": eq.Spec(value=60)})
    subs = [eq.Component(kind=eq.Kind.SUBWOOFER, enclosure=box.id, specs={
        "fs": eq.Spec(value=30), "qts": eq.Spec(value=0.4), "vas": eq.Spec(value=60)}) for _ in range(2)]
    d.components += [box, *subs]
    # 60 L shared by two -> 30 L each -> same result as test_sealed_box_math
    assert eq.analyze(d, subs[0].id)["derived"]["qtc"] == pytest.approx(0.693, abs=0.001)
