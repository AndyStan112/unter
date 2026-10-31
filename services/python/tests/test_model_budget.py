import pytest
from agno.models.openai import OpenAIChat
from unter.model import HelloModel


async def test_forced_read_becomes_final_text_and_third_request_is_blocked(monkeypatch):
    requests=[]
    async def provider(self, *args, **kwargs):
        requests.append(kwargs['tool_choice'])
        return 'provider-response'
    monkeypatch.setattr(OpenAIChat,'ainvoke',provider)
    model=HelloModel(id='test-model',api_key='test')
    forced={'type':'function','function':{'name':'list_observations'}}
    await model.ainvoke(tool_choice=forced)
    await model.ainvoke(tool_choice=forced)
    with pytest.raises(RuntimeError,match='request limit'):
        await model.ainvoke(tool_choice=forced)
    assert requests==[forced,'none']
