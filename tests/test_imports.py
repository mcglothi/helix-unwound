from pathlib import Path

import numpy as np
import pytest
from conftest import owner_client

from helixtune import afpx, measurements
from helixtune.api import create_app
from helixtune.devicefile import load_at01
from helixtune.engine import Engine
from helixtune.model import Role

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "captures/backups-2018/Helix Presets"
MDAT = ROOT / "captures/backups-2018/REW Measurements/01282018_REW Measurements.mdat"
AT01 = ROOT / "artifacts/extracted/app/deviceFiles/DSPPro2.at01"
pytestmark = pytest.mark.skipif(not (PRESETS.exists() and AT01.exists()), reason="private backups not present")


def test_afpx_roundtrip_xml(tmp_path):
    src = PRESETS / "BasicTune - DRV-TA.afpx"
    root = afpx.read_xml(src)
    afpx.write_xml(root, tmp_path / "x.afpx")
    assert afpx.read_xml(tmp_path / "x.afpx").get("Dev") == "15"


def test_afpx_import_maps_system():
    t, rep = afpx.load(PRESETS / "BasicTune - DRV-TA.afpx")
    roles = [c.role for c in t.channels]
    assert roles[:6] == [Role.MIDBASS, Role.MIDBASS, Role.MIDRANGE, Role.MIDRANGE, Role.TWEETER, Role.TWEETER]
    assert roles[8:] == [Role.SUBWOOFER, Role.SUBWOOFER]
    assert t.channel("E").hp.freq_hz == pytest.approx(3464.25)
    assert t.channel("I").gain_db == pytest.approx(4.0, abs=0.01)
    assert sum(b.enabled for b in t.channel("C").eq) == 10


def test_prediction_reflects_tune_change():
    base, _ = afpx.load(PRESETS / "Base - DRV-TA- No EQ.afpx")
    tuned, _ = afpx.load(PRESETS / "BasicTune - DRV-TA.afpx")
    ms = measurements.import_mdat(MDAT, base)
    mr = next(m for m in ms if m.name == "DS-MR")
    assert mr.channels == ["C"]
    g = measurements.GRID
    i = int(np.argmin(abs(g - 445)))
    meas = np.interp(np.log(g), np.log(mr.freqs), mr.spl)
    pred = measurements.predict(mr, tuned)
    # tuned preset has a -8 dB @ 444 Hz band on C; prediction must drop by roughly that much
    assert meas[i] - pred[i] > 6
    # unchanged tune -> prediction equals measurement
    assert np.allclose(measurements.predict(mr, base), meas, atol=1e-6)


def test_api_import_flow(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    with open(PRESETS / "M1-23122017-1405.afpx", "rb") as fh:
        r = c.post("/api/import/afpx", files={"file": ("M1-23122017-1405.afpx", fh)}).json()
    assert any("high-pass filter required" in p for p in r["safety_problems"])
    assert c.post(f"/api/snapshots/{r['snapshot']}/load").status_code == 409  # unsafe preset can't load
    with open(PRESETS / "Base - DRV-TA- No EQ.afpx", "rb") as fh:
        base = c.post("/api/import/afpx", files={"file": ("Base - DRV-TA- No EQ.afpx", fh)}).json()["snapshot"]
    with open(MDAT, "rb") as fh:
        ms = c.post("/api/import/mdat", files={"file": ("m.mdat", fh)}, data={"tune_snapshot": base}).json()
    assert len(ms) == 7
    curves = c.get(f"/api/measurements/{ms[0]['id']}/curves?points=50").json()
    assert len(curves["predicted"]) == 50 and curves["has_tune"]


def test_system_view(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    assert c.get("/api/system").json()["measurement_count"] == 0
    for name in ("Base - DRV-TA- No EQ.afpx", "BasicTune - DRV-TA.afpx"):
        with open(PRESETS / name, "rb") as fh:
            c.post("/api/import/afpx", files={"file": (name, fh)})
    with open(MDAT, "rb") as fh:
        c.post("/api/import/mdat", files={"file": ("m.mdat", fh)}, data={"tune_snapshot": "Base - DRV-TA- No EQ"})
    v = c.get("/api/system?points=64").json()
    assert v["measurement_count"] == 7
    assert set(v["groups"]) == {"subwoofer", "midbass", "midrange", "tweeter"}
    assert len(v["target"]) == len(v["predicted"]) == 64
    assert c.put("/api/targets/current", json={"name": "Flat"}).status_code == 200
    assert c.get("/api/system").json()["target_name"] == "Flat"


def test_proposals_and_ab(tmp_path):
    c = owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))
    for name in ("Base - DRV-TA- No EQ.afpx", "BasicTune - DRV-TA.afpx"):
        with open(PRESETS / name, "rb") as fh:
            c.post("/api/import/afpx", files={"file": (name, fh)})
    with open(MDAT, "rb") as fh:
        c.post("/api/import/mdat", files={"file": ("m.mdat", fh)}, data={"tune_snapshot": "Base - DRV-TA- No EQ"})
    c.post("/api/snapshots/Base - DRV-TA- No EQ/load")
    refused = c.post("/api/propose/auto-eq", json={"channels": ["C", "I"]}).json()
    assert refused["edits"] == [] and any("unknown" in n for n in refused["notes"])  # legacy provenance
    for m in c.get("/api/measurements").json():
        assert c.post(f"/api/measurements/{m['id']}/attest").status_code == 200
    p = c.post("/api/propose/auto-eq", json={"channels": ["C", "I"]}).json()
    chans = {e["channel"] for e in p["edits"]}
    assert chans == {"C", "I", "J"}  # subs measured together -> linked
    before = c.get("/api/system?points=64").json()["predicted"]
    prev = c.get(f"/api/proposals/{p['id']}/preview?points=64").json()["predicted"]
    assert prev != before
    assert c.get("/api/channels/C").json()["eq"][0]["enabled"] is False  # preview didn't apply
    assert c.post(f"/api/proposals/{p['id']}/apply").status_code == 200
    assert any(b["enabled"] for b in c.get("/api/channels/C").json()["eq"])
    assert c.get(f"/api/proposals/{p['id']}").status_code == 404
    # A/B
    c.put("/api/ab/A", json={})
    c.put("/api/ab/B", json={"snapshot": "BasicTune - DRV-TA"})
    assert c.post("/api/ab/toggle").json()["active"] == "B"
    assert c.get("/api/tune").json()["name"] == "BasicTune - DRV-TA"
    assert c.post("/api/ab/toggle").json()["active"] == "A"
    assert any(b["enabled"] for b in c.get("/api/channels/C").json()["eq"])  # A kept the auto-EQ


def test_afpx_routing_imports_mono_subs():
    t, _ = afpx.load(PRESETS / "BasicTune - DRV-TA.afpx")
    assert t.channel("A").mix == {"L": 1.0} and t.channel("B").mix == {"R": 1.0}
    assert t.channel("I").mix == {"L": 0.5, "R": 0.5} and t.channel("J").mix == {"L": 0.5, "R": 0.5}
