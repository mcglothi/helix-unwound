"""Exercise actual cookies and bearer capabilities without hardware or user state."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from helixtune.access import AccessControl, COOKIE, SessionLimit
from helixtune.api import create_app
from helixtune.engine import Engine


@pytest.fixture
def setup(tmp_path, synthetic_mapping):
    engine = Engine(mapping=synthetic_mapping, data_dir=tmp_path)
    app = create_app(engine)
    clock = [100.0]
    app.state.access._clock = lambda: clock[0]
    browser = TestClient(app)
    return engine, app, browser, clock


def login(app, browser):
    response = browser.post('/api/session', json={'token': app.state.access.token('owner')})
    assert response.status_code == 200
    return browser.cookies.get(COOKIE), response


def replay(app, cookie):
    return TestClient(app, cookies={COOKIE: cookie})


def test_cookie_is_distinct_from_bearer_and_server_retains_only_digest(setup):
    _, app, browser, _ = setup
    cookie, response = login(app, browser)
    access = app.state.access
    assert cookie not in [access.token('owner'), access.token('agent')]
    assert access.authenticate(cookie) is None
    assert cookie not in access._sessions
    assert len(access._sessions) == 1
    assert access.token('owner') not in response.text
    assert cookie not in response.text
    assert response.json()['expires_in'] == 12 * 60 * 60
    assert 'max-age=43200' in response.headers['set-cookie'].lower()
    assert response.headers['cache-control'] == 'no-store'
    assert browser.get('/api/tune').status_code == 200
    assert browser.get('/api/tune', headers={'Authorization': f'Bearer {cookie}'}).status_code == 401


@pytest.mark.parametrize('principal', ['owner', 'agent'])
def test_permanent_credentials_are_never_accepted_as_cookies(setup, principal):
    _, app, _, _ = setup
    browser = replay(app, app.state.access.token(principal))
    assert browser.get('/api/status').status_code == 401


def test_logout_revokes_copied_cookie_but_not_other_browser_or_owner_token(setup):
    _, app, first, _ = setup
    copied, _ = login(app, first)
    second = TestClient(app)
    login(app, second)
    assert first.delete('/api/session', headers={'Origin': 'http://testserver'}).status_code == 200
    assert replay(app, copied).get('/api/status').status_code == 401
    assert second.get('/api/status').status_code == 200
    owner = TestClient(app, headers={'Authorization': f'Bearer {app.state.access.token("owner")}'})
    assert owner.get('/api/status').status_code == 200


def test_session_expires_at_absolute_deadline_even_with_activity(setup):
    _, app, browser, clock = setup
    copied, _ = login(app, browser)
    expiry = clock[0] + app.state.access.session_ttl
    clock[0] = expiry - 1
    assert browser.get('/api/status').status_code == 200
    clock[0] = expiry
    assert replay(app, copied).get('/api/status').status_code == 401
    assert not app.state.access._sessions
    login(app, browser)
    assert browser.get('/api/status').status_code == 200


def test_restart_invalidates_sessions_without_rotating_role_credentials(setup):
    engine, app, browser, _ = setup
    cookie, _ = login(app, browser)
    again = create_app(engine)
    assert again.state.access.token('owner') == app.state.access.token('owner')
    assert replay(again, cookie).get('/api/status').status_code == 401
    assert browser.get('/api/status').status_code == 200  # old instance only


def test_repeat_bootstrap_rotates_and_revokes_previous_session(setup):
    _, app, browser, _ = setup
    old, _ = login(app, browser)
    new, _ = login(app, browser)
    assert new != old
    assert len(app.state.access._sessions) == 1
    assert replay(app, old).get('/api/status').status_code == 401
    assert browser.get('/api/status').status_code == 200


def test_failed_or_cross_origin_bootstrap_cannot_replace_valid_session(setup):
    _, app, browser, _ = setup
    old, _ = login(app, browser)
    response = browser.post('/api/session', json={'token': 'invalid'})
    assert response.status_code == 401
    assert response.headers['cache-control'] == 'no-store'
    assert browser.cookies.get(COOKIE) == old
    assert browser.post('/api/session', json={'token': app.state.access.token('owner')},
                        headers={'Origin': 'http://evil.example'}).status_code == 403
    assert browser.cookies.get(COOKIE) == old
    assert browser.get('/api/status').status_code == 200


def test_origin_failure_does_not_revoke_session(setup):
    _, app, browser, _ = setup
    copied, _ = login(app, browser)
    for origin in [None, 'null', 'http://testserver:9999']:
        headers = {} if origin is None else {'Origin': origin}
        assert browser.delete('/api/session', headers=headers).status_code == 403
    assert replay(app, copied).get('/api/status').status_code == 200


def test_https_cookie_is_secure_and_logout_matches_attributes(setup):
    _, app, _, _ = setup
    browser = TestClient(app, base_url='https://testserver')
    _, response = login(app, browser)
    assert '; secure' in response.headers['set-cookie'].lower()
    response = browser.delete('/api/session', headers={'Origin': 'https://testserver'})
    assert response.status_code == 200
    assert '; secure' in response.headers['set-cookie'].lower()
    assert not browser.cookies


def test_session_capacity_is_bounded_rotation_allowed_and_expiry_frees_slots(setup):
    _, app, first, clock = setup
    app.state.access._max_sessions = 1
    old, _ = login(app, first)
    second = TestClient(app)
    response = second.post('/api/session', json={'token': app.state.access.token('owner')})
    assert response.status_code == 429
    assert first.get('/api/status').status_code == 200
    new, _ = login(app, first)  # may replace its own slot
    assert new != old
    clock[0] += app.state.access.session_ttl
    login(app, second)
    assert len(app.state.access._sessions) == 1


def test_concurrent_signins_do_not_exceed_capacity(tmp_path):
    access = AccessControl(tmp_path, max_sessions=2)
    def start(_):
        try:
            return access.start_session(access.token('owner'))
        except SessionLimit:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(start, range(8)))
    assert len(set(value for value in results if value)) == 2
    assert len(access._sessions) == 2


@pytest.mark.parametrize('cookie', ['', 'invalid', 'hs_' + 'x' * 43, 'non-ascii-☃'])
def test_unknown_or_malformed_session_is_unauthenticated(tmp_path, cookie):
    access = AccessControl(tmp_path)
    assert access.authenticate_session(cookie) is None
    access.revoke_session(cookie)
