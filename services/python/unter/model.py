"""An explicit provider-call budget around Agno's model."""
from dataclasses import dataclass, field
from agno.models.openai import OpenAIChat

# One request explains a report; the second is headroom. Nothing the model says can raise this.
MAX_MODEL_REQUESTS = 2


@dataclass
class CappedModel(OpenAIChat):
    max_requests: int = MAX_MODEL_REQUESTS
    _requests: int = field(default=0, init=False)

    async def ainvoke(self, *args, **kwargs):
        if self._requests >= self.max_requests:
            raise RuntimeError('Model request limit reached')
        self._requests += 1
        return await super().ainvoke(*args, **kwargs)
