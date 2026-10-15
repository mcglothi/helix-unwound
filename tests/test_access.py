import stat
from urllib.parse import parse_qs, urlsplit

import pytest
import httpx
from fastapi.testclient import TestClient

from helixtune.access import AccessControl, COOKIE, read_token, token_path
from helixtune.api import create_app
from helixtune.cli import main
from helixtune.engine import Engine


@pytest.fixture
def clients(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    app = create_app(engine)
    return (engine, app, TestClient(app),
            TestClient(app, headers={"Authorization": f"Bearer {app.state.access.token('owner')}"}),
            TestClient(app, headers={"Authorization": f"Bearer {app.state.access.token('agent')}"}))


def test_credentials_persist_with_owner_only_file_permissions(tmp_path):
    first = AccessControl(tmp_path)
    again = AccessControl(tmp_path)
    for principal in ("owner", "agent"):
        assert again.authenticate(first.token(principal)) == principal
        assert stat.S_IMODE(token_path(tmp_path, principal).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "auth").stat().st_mode) == 0o700
    assert again.authenticate("invalid") is None
    assert again.authenticate("non-ascii-☃") is None


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/tune", None), ("GET", "/api/media", None),
    ("PATCH", "/api/channels/A", {"gain_db": -1}),
    ("POST", "/api/device/connect", {"port": "emulator"}),
])
def test_anonymous_requests_cannot_access_state_or_mutate(clients, method, path, body):
    _, _, anonymous, _, _ = clients
    response = anonymous.request(method, path, json=body, headers={"x-helixtune-source": "ui"})
    assert response.status_code == 401


@pytest.mark.parametrize("path,method,body", [
    ("/api/device/connect", "POST", {"port": "emulator", "allow_writes": True}),
    ("/api/device/push-full", "POST", {"confirm": "OVERWRITE"}),
    ("/api/device/disconnect", "POST", None),
    ("/api/protections/A", "PUT", {"protection": {}, "confirm": "RECONFIGURE"}),
])
def test_agent_cannot_acquire_owner_capabilities_by_spoofing_source(clients, path, method, body):
    _, _, _, _, agent = clients
    for source in ("ui", "owner", "anything"):
        response = agent.request(method, path, json=body, headers={"x-helixtune-source": source})
        assert response.status_code == 403


def test_agent_can_tune_and_audit_identity_comes_from_credential(clients):
    engine, _, _, owner, agent = clients
    assert agent.get("/api/protections").status_code == 200
    assert agent.patch("/api/channels/A", json={"gain_db": -1}, headers={"x-helixtune-source": "owner"}).status_code == 200
    assert engine.events[-1].source == "agent"
    assert owner.post("/api/device/connect", json={"port": "emulator", "allow_writes": True}).status_code == 200
    # An audit label can neither grant nor remove the authenticated owner's capability.
    assert owner.post("/api/device/push-full", json={"confirm": "OVERWRITE"}, headers={"x-helixtune-source": "agent"}).status_code == 200
    assert agent.patch("/api/channels/A", json={"gain_db": -2}).status_code == 200


def test_owner_browser_session_is_httponly_and_logout_clears_it(clients):
    _, app, browser, _, _ = clients
    response = browser.post("/api/session", json={"token": app.state.access.token("owner")})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert browser.get("/api/status").status_code == 200
    assert browser.delete("/api/session", headers={"Origin": "http://testserver"}).status_code == 200
    assert browser.get("/api/status").status_code == 401


def test_agent_cannot_exchange_token_for_owner_browser_session(clients):
    _, app, browser, _, _ = clients
    assert browser.post("/api/session", json={"token": app.state.access.token("agent")}).status_code == 401
    browser.cookies.set(COOKIE, app.state.access.token("agent"))
    assert browser.get("/api/status").status_code == 401


@pytest.mark.parametrize("origin", ["http://evil.example", "http://testserver:9999", "null"])
def test_cookie_authenticated_mutations_reject_other_origins(clients, origin):
    _, app, browser, _, _ = clients
    browser.post("/api/session", json={"token": app.state.access.token("owner")})
    assert browser.patch("/api/master", json={"gain_db": -1}, headers={"Origin": origin}).status_code == 403
    assert browser.patch("/api/master", json={"gain_db": -1}, headers={"Origin": "http://testserver"}).status_code == 200


def test_bad_bearer_cannot_fall_back_to_owner_cookie(clients):
    _, app, browser, _, _ = clients
    browser.post("/api/session", json={"token": app.state.access.token("owner")})
    assert browser.get("/api/status", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_cookie_mutations_require_origin_even_when_header_missing(clients):
    _, app, browser, _, _ = clients
    browser.post("/api/session", json={"token": app.state.access.token("owner")})
    assert browser.patch("/api/master", json={"gain_db": -1}).status_code == 403


def test_agent_cannot_erase_limits_via_role_and_equipment_metadata(clients):
    _, _, _, owner, agent = clients
    assert owner.put("/api/channels/A/hp", json={"freq_hz": 3000}).status_code == 200
    assert owner.patch("/api/channels/A", json={"role": "tweeter"}).status_code == 200
    component = owner.post("/api/equipment", json={"kind": "speaker", "channels": ["A"],
        "specs": {"hp_min": {"value": 2600}}}).json()
    assert agent.patch("/api/channels/A", json={"role": "unused"}).status_code == 200
    assert agent.patch(f"/api/equipment/{component['id']}", json={"specs": {"hp_min": None}}).status_code == 200
    assert agent.delete(f"/api/equipment/{component['id']}").status_code == 200
    assert agent.put("/api/channels/A/hp", json={"freq_hz": 2000}).status_code == 409
    assert agent.put("/api/channels/A/hp").status_code == 422
    assert agent.put("/api/channels/A/hp", content="null", headers={"Content-Type": "application/json"}).status_code == 409
    assert owner.put("/api/protections/A", json={"protection": {}, "confirm": "yes"}).status_code == 400
    assert owner.post("/api/device/connect", json={"port": "emulator"}).status_code == 200
    assert owner.put("/api/protections/A", json={"protection": {}, "confirm": "RECONFIGURE"}).status_code == 400
    owner.post("/api/device/disconnect")
    assert owner.put("/api/protections/A", json={"protection": {}, "confirm": "RECONFIGURE"}).status_code == 200
    assert agent.put("/api/channels/A/hp", content="null", headers={"Content-Type": "application/json"}).status_code == 200


def test_open_command_uses_loopback_fragment_and_never_prints_credential(tmp_path, monkeypatch, capsys):
    access = AccessControl(tmp_path)
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    assert main(["open", "--data", str(tmp_path), "--port", "8766"]) == 0
    parsed = urlsplit(opened[0])
    assert parsed.netloc == "127.0.0.1:8766"
    assert parsed.query == ""
    assert access.authenticate(parse_qs(parsed.fragment)["token"][0]) == "owner"
    assert capsys.readouterr().out == ""


def test_mcp_uses_agent_credential_for_both_read_paths(clients, monkeypatch):
    from helixtune import mcp_server

    _, app, _, _, _ = clients
    monkeypatch.setenv("HELIXTUNE_DATA_DIR", str(clients[0].data_dir))
    monkeypatch.delenv("HELIXTUNE_TOKEN", raising=False)
    real_client = mcp_server.httpx.Client
    requests = []
    def reply(request):
        requests.append(request)
        return httpx.Response(200, json={"name": "test", "master_gain_db": 0, "channels": []})
    transport = httpx.MockTransport(reply)
    principals = []

    def client(**kwargs):
        token = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        principals.append(app.state.access.authenticate(token))
        return real_client(**kwargs, transport=transport)
    monkeypatch.setattr(mcp_server.httpx, "Client", client)
    mcp_server._call("GET", "/api/status")
    mcp_server.get_overview()
    mcp_server._call("PUT", "/api/channels/A/hp", None)
    assert principals == ["agent", "agent", "agent"]
    assert requests[-1].content == b"null"
    assert requests[-1].headers["content-type"] == "application/json"


def test_missing_credential_file_does_not_create_credentials(tmp_path):
    with pytest.raises(RuntimeError, match="start helixtune serve"):
        read_token(tmp_path, "agent")
    assert not (tmp_path / "auth").exists()
