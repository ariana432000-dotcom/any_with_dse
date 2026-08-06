"""
Embedding providers — a pluggable abstraction selected via .env.

Business logic never imports a provider directly; it calls `get_embedding_function()`
(a Chroma-compatible callable) or `get_provider()` (for raw vectors). New
providers are added by subclassing `EmbeddingProvider` and registering in
`_REGISTRY` — the Open/Closed principle in practice.

Supported out of the box: ollama (default, keyless/local), openai, sentence-
transformers (local CPU). All are lazy: importing this module never requires the
provider's SDK to be installed unless that provider is actually selected.
"""

from __future__ import annotations

import abc
from typing import Callable, Sequence

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# A Chroma EmbeddingFunction is any callable: (list[str]) -> list[list[float]].
EmbeddingFunction = Callable[[Sequence[str]], list[list[float]]]


def _as_list(x) -> list[str]:
    """Normalize Chroma's input (str or list) to a list of strings."""
    if x is None:
        return []
    if isinstance(x, str):
        return [x]
    return list(x)


class EmbeddingProvider(abc.ABC):
    """Uniform interface over any embedding backend."""

    name: str = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    @abc.abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector per input text."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def as_chroma_function(self) -> EmbeddingFunction:
        """Adapter so the provider can be handed straight to a Chroma collection.

        Implements the current Chroma EmbeddingFunction protocol: __call__(input),
        name(), plus embed_documents/embed_query used by the query path.
        """
        provider = self

        class _EF:
            def __call__(self, input):  # noqa: A002  (Chroma passes `input=`)
                return provider.embed(_as_list(input))

            def embed_documents(self, input=None, texts=None):  # noqa: A002
                return provider.embed(_as_list(input if input is not None else texts))

            def embed_query(self, input=None, text=None):  # noqa: A002
                items = _as_list(input if input is not None else text)
                return provider.embed(items)[0]

            @staticmethod
            def name() -> str:
                return f"{provider.name}:{provider.model}"

            @staticmethod
            def is_legacy() -> bool:
                return False

            def get_config(self) -> dict:
                return {"provider": provider.name, "model": provider.model}

            @staticmethod
            def build_from_config(config: dict):  # pragma: no cover - not used
                return None

        return _EF()


class OllamaEmbeddingProvider(EmbeddingProvider):
    name = "ollama"

    def __init__(self, model: str, base_url: str) -> None:
        super().__init__(model)
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import requests

        out: list[list[float]] = []
        for t in texts:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": t},
                timeout=60,
            )
            resp.raise_for_status()
            out.append(resp.json()["embedding"])
        return out


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(self, model: str, api_key: str) -> None:
        super().__init__(model)
        if not api_key:
            raise ValueError("OpenAI embeddings selected but OPENAI_API_KEY is empty")
        self._api_key = api_key
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        resp = self._client_lazy().embeddings.create(model=self.model, input=list(texts))
        return [d.embedding for d in resp.data]


class SentenceTransformerProvider(EmbeddingProvider):
    name = "sentence-transformers"

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self._model = None

    def _model_lazy(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vecs = self._model_lazy().encode(list(texts), convert_to_numpy=True)
        return [v.tolist() for v in vecs]


# Registry: provider-key -> factory(settings) -> EmbeddingProvider
_REGISTRY: dict[str, Callable[[], EmbeddingProvider]] = {
    "ollama": lambda: OllamaEmbeddingProvider(
        settings.EMBED_MODEL, settings.OLLAMA_BASE_URL
    ),
    "openai": lambda: OpenAIEmbeddingProvider(
        settings.EMBEDDING_MODEL_OPENAI, settings.OPENAI_API_KEY
    ),
    "sentence-transformers": lambda: SentenceTransformerProvider(
        settings.EMBEDDING_MODEL_ST
    ),
}

_provider_singleton: EmbeddingProvider | None = None


def get_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (singleton)."""
    global _provider_singleton
    if _provider_singleton is None:
        key = settings.EMBEDDING_PROVIDER.lower().strip()
        if key not in _REGISTRY:
            raise ValueError(
                f"Unknown EMBEDDING_PROVIDER '{key}'. "
                f"Options: {', '.join(_REGISTRY)}"
            )
        _provider_singleton = _REGISTRY[key]()
        log.info("Embedding provider: %s (model=%s)",
                 _provider_singleton.name, _provider_singleton.model)
    return _provider_singleton


def get_embedding_function() -> EmbeddingFunction:
    """Chroma-compatible embedding function for the configured provider."""
    return get_provider().as_chroma_function()


def reset_provider() -> None:
    """Test hook to force re-selection after changing env."""
    global _provider_singleton
    _provider_singleton = None
