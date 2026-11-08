import pytest
from agno.models.openai import OpenAIChat
from unter.model import CappedModel, MAX_MODEL_REQUESTS


async def test_requests_beyond_the_cap_never_reach_the_provider(monkeypatch):
    requests = []
    async def provider(self, *args, **kwargs):
        requests.append(kwargs)
        return 'provider-response'
    monkeypatch.setattr(OpenAIChat, 'ainvoke', provider)
    model = CappedModel(id='test-model', api_key='test')
    for _ in range(MAX_MODEL_REQUESTS):
        assert await model.ainvoke() == 'provider-response'
    with pytest.raises(RuntimeError, match='request limit'):
        await model.ainvoke()
    assert len(requests) == MAX_MODEL_REQUESTS == 2
