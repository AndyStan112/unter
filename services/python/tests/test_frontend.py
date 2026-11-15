from fastapi import FastAPI
from starlette.testclient import TestClient
from unter.frontend import FrontendFiles
import pytest


@pytest.fixture
def browser(tmp_path):
    (tmp_path / 'ride').mkdir()
    (tmp_path / 'index.html').write_text('<title>Dashboard</title>')
    (tmp_path / 'ride' / 'index.html').write_text('<title>Ride</title>')
    (tmp_path / 'ride' / 'sw.js').write_text('// ride worker')
    app = FastAPI()
    app.mount('/', FrontendFiles(directory=tmp_path, html=True))
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize('path', ['/', '/reports', '/schedule', '/activity', '/proposals'])
def test_dashboard_routes_can_reload(browser, path):
    response = browser.get(path)
    assert response.status_code == 200
    assert '<title>Dashboard</title>' in response.text
    assert response.headers['cache-control'] == 'no-cache'


@pytest.mark.parametrize('path', ['/ride/', '/ride/passenger', '/ride/driver'])
def test_ride_routes_use_the_pwa_entry(browser, path):
    response = browser.get(path)
    assert response.status_code == 200
    assert '<title>Ride</title>' in response.text
    assert response.headers['cache-control'] == 'no-cache'


@pytest.mark.parametrize('path', ['/assets/missing.js', '/api/missing', '/other', '/ride/missing'])
def test_missing_assets_and_unknown_routes_are_not_spa_html(browser, path):
    assert browser.get(path).status_code == 404


def test_worker_is_revalidated(browser):
    assert browser.get('/ride/sw.js').headers['cache-control'] == 'no-cache'
