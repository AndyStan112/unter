import httpx
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from unter import places


def test_search_caches_results_and_requires_an_explicit_query(monkeypatch):
    calls = []
    def reply(request):
        calls.append(request)
        return httpx.Response(200, json={'features': [{'geometry': {'coordinates': [21.22,45.75]},
            'properties': {'name': 'Square', 'city': 'Timisoara'}}]})
    real = httpx.AsyncClient
    monkeypatch.setattr(places.httpx, 'AsyncClient', lambda **kw: real(transport=httpx.MockTransport(reply), **kw))
    places.cache.clear()
    monkeypatch.setattr(places, 'last_request', 0)
    app = FastAPI(); app.include_router(places.router)
    with TestClient(app) as client:
        assert client.get('/places?q=ab').status_code == 422
        first = client.get('/places?q=Square')
        assert first.status_code == 200 and first.json()[0]['label'] == 'Square, Timisoara'
        assert client.get('/places?q=Square').json() == first.json()
        assert client.get('/places?q=Another').status_code == 429
    assert len(calls) == 1


def test_search_failure_leaves_map_selection_available(monkeypatch):
    real = httpx.AsyncClient
    monkeypatch.setattr(places.httpx, 'AsyncClient', lambda **kw: real(
        transport=httpx.MockTransport(lambda request: httpx.Response(503)), **kw))
    places.cache.clear()
    monkeypatch.setattr(places, 'last_request', 0)
    app = FastAPI(); app.include_router(places.router)
    with TestClient(app) as client:
        response = client.get('/places?q=Missing')
    assert response.status_code == 503 and 'map pin' in response.json()['detail']
