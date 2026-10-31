from datetime import datetime
from types import SimpleNamespace

import pytest

from display import create_app
from utils import StatsStore

BASE = 'http://127.0.0.1:5000'


@pytest.fixture
def site(tmp_path):
    store = StatsStore(tmp_path, clock=lambda: datetime(2026, 10, 31, 12))
    controller = SimpleNamespace(status=lambda: {'paused': store.paused, 'errors': store.errors,
                                                'running': True, 'autostart': False},
                                 set_paused=store.set_paused, request_stop=lambda: None)
    app = create_app(store, controller)
    app.testing = True
    return app, store, app.test_client()


def test_local_host_only_and_no_external_resources(site):
    app, _, client = site
    assert client.get('/', base_url='http://attacker.example:5000').status_code == 403
    response = client.get('/', base_url=BASE)
    assert response.status_code == 200
    assert "connect-src 'self'" in response.headers['Content-Security-Policy']
    assert response.headers['Cache-Control'] == 'no-store'
    assert 'https://' not in response.get_data(as_text=True)
    assert client.get('/status', base_url=BASE, headers={'Origin': 'https://evil.example'}).status_code == 403


def test_controls_require_origin_and_secret(site):
    app, store, client = site
    route = '/control/pause'
    assert client.post('/end_program', base_url=BASE).status_code == 403
    assert client.post(route, base_url=BASE).status_code == 403
    secret = app.config['CONTROL_TOKEN']
    assert client.post(route, base_url=BASE, headers={'X-KMCounter-Token': secret,
                       'Origin': 'https://evil.example'}).status_code == 403
    headers = {'X-KMCounter-Token': secret, 'Origin': BASE}
    assert client.post(route, base_url=BASE, headers=headers).status_code == 200
    assert store.paused
    assert client.post('/control/resume', base_url=BASE, headers=headers).status_code == 200
    assert not store.paused


@pytest.mark.parametrize('events', ['empty', 'keyboard', 'mouse', 'both'])
def test_empty_single_counts_and_totals(site, events):
    _, store, client = site
    if events in ('keyboard', 'both'):
        store.count_key('a')
    if events in ('mouse', 'both'):
        store.count_click('Button.left', 5, 5, (0, 0, 100, 100))
    response = client.post('/fetch_key_counts', base_url=BASE,
                           json={'start_time': '2026-10-31T00:00', 'end_time': '2026-10-31T23:59'})
    assert response.status_code == 200
    counts, rates = response.json
    assert all(0 <= value <= 1 for value in rates.values())
    totals = client.get('/fetch_total_key_counts', base_url=BASE).json
    assert sum(totals.values()) == {'empty': 0, 'keyboard': 1, 'mouse': 1, 'both': 2}[events]


def test_invalid_query_has_readable_error(site):
    _, _, client = site
    response = client.post('/fetch_key_counts', base_url=BASE, json={'start_time': 'bad'})
    assert response.status_code == 400
    assert 'error' in response.json
