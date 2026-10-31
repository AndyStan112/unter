"""An explicit provider-call budget around Agno's tool loop."""
from dataclasses import dataclass, field
from agno.models.openai import OpenAIChat


@dataclass
class HelloModel(OpenAIChat):
    _requests: int = field(default=0, init=False)

    async def ainvoke(self, *args, **kwargs):
        if self._requests >= 2:
            raise RuntimeError('Hello-world model request limit reached')
        self._requests += 1
        if self._requests == 2:
            # Agno retains a forced tool_choice across turns. Explicitly stop tools
            # after the first read so the second request can produce final text.
            kwargs['tool_choice'] = 'none'
        return await super().ainvoke(*args, **kwargs)
