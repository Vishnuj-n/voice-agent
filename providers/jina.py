# Get your Jina AI API key for free: https://jina.ai/?sui=apikey

from __future__ import annotations

import httpx

from config import load_config
from providers.base import EmbeddingProvider

_JINA_EMBEDDINGS_URL = "https://api.jina.ai/v1/embeddings"

# jina-embeddings-v5-text-small produces 1024-dimensional embeddings.
# jina-embeddings-v5-text-nano  produces  768-dimensional embeddings.
_MODEL_DIMENSIONS: dict[str, int] = {
    "jina-embeddings-v5-text-small": 1024,
    "jina-embeddings-v5-text-nano": 768,
}


class JinaEmbeddingProvider(EmbeddingProvider):
    """Text embedding provider backed by the Jina AI Embeddings API.

    Defaults to jina-embeddings-v5-text-small (677 M params, 32 K context,
    1024-dimensional output, supports Matryoshka truncation).
    """

    def __init__(self, model: str | None = None) -> None:
        cfg = load_config()
        self._api_key: str = cfg.jina_api_key
        self._model: str = model or cfg.jina_embedding_model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, texts: list[str], task: str) -> list[list[float]]:
        """Call the Jina embeddings endpoint and return the embedding vectors.

        Args:
            texts: Input strings to embed.
            task:  Task hint — "retrieval.query" for queries, "retrieval.passage"
                   for stored documents.

        Returns:
            List of float vectors, one per input text.

        Raises:
            httpx.HTTPStatusError: on 4xx/5xx responses from the API.
            ValueError: if the API response cannot be parsed.
        """
        payload = {
            "model": self._model,
            "input": texts,
            "task": task,
            "embedding_type": "float",
            "normalized": True,
            "truncate": True,  # silently drop tokens beyond the model's max context
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    _JINA_EMBEDDINGS_URL,
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise httpx.HTTPStatusError(
                    f"Jina embeddings API error {exc.response.status_code}: "
                    f"{exc.response.text}",
                    request=exc.request,
                    response=exc.response,
                ) from exc

        data = response.json()

        try:
            # The API returns {"data": [{"embedding": [...], "index": N}, ...]}
            items: list[dict] = data["data"]
            # Re-order by the index field to guard against out-of-order responses.
            items.sort(key=lambda x: x["index"])
            return [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"Unexpected Jina embeddings response structure: {data}"
            ) from exc

    # ------------------------------------------------------------------
    # EmbeddingProvider interface
    # ------------------------------------------------------------------

    async def get_embedding(self, text: str) -> list[float]:
        """Generate a single query embedding.

        Uses the ``retrieval.query`` task hint so the model optimises the
        vector for nearest-neighbour retrieval against stored passages.

        Args:
            text: The input string (e.g. a user's search query).

        Returns:
            A list of floats representing the embedding vector.
        """
        vectors = await self._post([text], task="retrieval.query")
        return vectors[0]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate passage embeddings for a batch of texts.

        Uses the ``retrieval.passage`` task hint, which is appropriate when
        embedding documents to be stored and searched later.

        Args:
            texts: List of input strings (e.g. document chunks to index).

        Returns:
            List of float vectors, one per input text, in the same order.
        """
        if not texts:
            return []
        return await self._post(texts, task="retrieval.passage")
