from pathlib import Path

import pytest
from conftest import owner_client

from helixtune.api import create_app
from helixtune.devicefile import load_at01
from helixtune.engine import Engine

AT01 = Path(__file__).resolve().parents[1] / "artifacts/extracted/app/deviceFiles/DSPPro2.at01"
pytestmark = pytest.mark.skipif(not AT01.exists(), reason="vendor device files not extracted")


@pytest.fixture
def c(tmp_path):
    return owner_client(create_app(Engine.from_param_map(load_at01(AT01), tmp_path)))


def test_ui_and_tune_served(c):
    assert "Helix Unwound" in c.get("/").text and "Helix Unwound" in c.get("/legacy").text
    assert len(c.get("/api/tune").json()["channels"]) == 10


def test_edit_flow_and_revision(c):
    r0 = c.get("/api/status").json()["revision"]
    assert c.patch("/api/channels/a", json={"name": "Tweeter L", "role": "tweeter"}).status_code == 409
    assert c.put("/api/channels/A/hp", json={"type": "linkwitz_riley", "slope_db": 24, "freq_hz": 3000}).status_code == 200
    assert c.patch("/api/channels/A", json={"name": "Tweeter L", "role": "tweeter"}).status_code == 200
    assert c.patch("/api/channels/A/eq/3", json={"enabled": True, "freq_hz": 6000, "gain_db": -3}).status_code == 200
    assert c.get("/api/status").json()["revision"] == r0 + 3  # rejected edit does not bump
    resp = c.get("/api/response?channels=A&points=50").json()
    assert len(resp["channels"]["A"]) == 50 and resp["channels"]["A"][0] < -60  # high-passed lows


def test_agent_cannot_full_push(c):
    from fastapi.testclient import TestClient

    c.post("/api/device/connect", json={"port": "emulator", "allow_writes": True})
    agent = TestClient(c.app, headers={"Authorization": f"Bearer {c.app.state.access.token('agent')}"})
    r = agent.post("/api/device/push-full", json={"confirm": "OVERWRITE"}, headers={"x-helixtune-source": "ui"})
    assert r.status_code == 403
    assert c.post("/api/device/push-full", json={"confirm": "OVERWRITE"}).status_code == 200
    assert c.get("/api/status").json()["device"]["baselined"] is True


def test_bad_inputs(c):
    assert c.patch("/api/channels/Z", json={"gain_db": 0}).status_code == 404
    assert c.patch("/api/channels/A/eq/31", json={"gain_db": 0}).status_code == 404
    assert c.patch("/api/channels/A", json={"gain_db": 50}).status_code == 422


def test_custom_themes_shared(c):
    pal = {f"base0{i:X}": f"#{i:02x}{i:02x}{i:02x}" for i in range(16)}
    assert c.post("/api/themes", json={"name": "Mine", "variant": "dark", "palette": pal}).status_code == 200
    assert [t["name"] for t in c.get("/api/themes").json()] == ["Mine"]
    bad = dict(pal, base05="red")
    assert c.post("/api/themes", json={"name": "Bad", "variant": "dark", "palette": bad}).status_code == 422
    c.delete("/api/themes/Mine")
    assert c.get("/api/themes").json() == []
