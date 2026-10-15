"""Route-declared capabilities: agent writes are opt-in; new routes default to owner-only."""

import pytest
from fastapi.testclient import TestClient

from conftest import owner_client
from helixtune.api import agent_allowed, create_app
from helixtune.engine import Engine
from helixtune.measurements import GRID, Measurement


@pytest.fixture
def clients(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    app = create_app(engine)
    agent = TestClient(app, headers={"Authorization": f"Bearer {app.state.access.token('agent')}"})
    return engine, app, owner_client(app), agent


def test_new_undecorated_mutating_route_is_owner_only(clients):
    _, app, owner, agent = clients

    @app.post("/api/test-new-route")
    def new_route():
        return {"ok": True}

    @app.post("/api/test-opted-in")
    @agent_allowed
    def opted_in():
        return {"ok": True}

    assert agent.post("/api/test-new-route").status_code == 403
    assert owner.post("/api/test-new-route").status_code == 200
    assert agent.post("/api/test-opted-in").status_code == 200


def test_every_registered_delete_is_owner_only_except_proposal_discard(clients):
    _, app, _, _ = clients
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        if "DELETE" in methods and route.path != "/api/proposals/{pid}" and route.path != "/api/session":
            assert not getattr(route.endpoint, "__helixtune_agent__", False), route.path


def test_agent_destructive_and_device_routes_refused(clients):
    engine, _, owner, agent = clients
    m = Measurement(name="x", channels=["A"], freqs=GRID.tolist(), spl=[80.0] * len(GRID))
    engine.measurements.save(m)
    assert agent.delete(f"/api/measurements/{m.id}").status_code == 403
    assert agent.post(f"/api/measurements/{m.id}/attest").status_code == 403
    assert agent.delete("/api/media/abc").status_code == 403
    assert agent.delete("/api/themes/x").status_code == 403
    assert agent.post("/api/device/connect", json={"port": "emulator"}).status_code == 403
    assert agent.post("/api/device/push-full", json={"confirm": "OVERWRITE"}).status_code == 403
    assert agent.put("/api/protections/A", json={"protection": {}, "confirm": "RECONFIGURE"}).status_code == 403
    # reads and ordinary tuning remain available to agents
    assert agent.get("/api/tune").status_code == 200
    assert agent.patch("/api/channels/A", json={"name": "Midbass L"}).status_code == 200
    assert owner.delete(f"/api/measurements/{m.id}").status_code == 200


def test_scene_names_are_not_silently_overwritten(clients):
    _, _, owner, agent = clients
    assert agent.post("/api/snapshots", json={"name": "Daily"}).status_code == 200
    r = agent.post("/api/snapshots", json={"name": "Daily"})
    assert r.status_code == 409 and r.json()["error"] == "exists"
    assert agent.post("/api/snapshots", json={"name": "Daily", "overwrite": True}).status_code == 403
    assert owner.post("/api/snapshots", json={"name": "Daily"}).status_code == 409  # owner must ask explicitly
    assert owner.post("/api/snapshots", json={"name": "Daily", "overwrite": True}).status_code == 200


def test_routes_outside_api_prefix_are_not_public_by_default(clients):
    _, app, owner, agent = clients

    @app.post("/future-control")
    def future_control():
        return {"ok": True}

    @app.get("/future-read")
    def future_read():
        return {"ok": True}

    anon = TestClient(app)
    assert anon.post("/future-control").status_code == 401
    assert anon.get("/future-read").status_code == 401
    assert agent.post("/future-control").status_code == 403
    assert owner.post("/future-control").status_code == 200


def test_intentional_public_surfaces_stay_public(clients):
    _, app, _, _ = clients
    anon = TestClient(app)
    assert anon.get("/").status_code == 200
    assert anon.get("/manifest.json").status_code == 200
    assert anon.get("/api/status").status_code == 401
    assert anon.post("/api/session", json={"token": "x" * 40}).status_code == 401  # reachable, rejects bad token

