from openai import AsyncOpenAI
from config import load_config
from providers.base import EmbeddingProvider

class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str | None = None):
        cfg = load_config()
        self._client = AsyncOpenAI(api_key=cfg.openai_api_key)
        self._model = model or cfg.openai_embedding_model  # "text-embedding-3-small"

    async def get_embedding(self, text: str) -> list[float]:
        resp = await self._client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]
