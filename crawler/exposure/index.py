"""
Chunking and local retrieval for COLLECT-007.

Splits normalised documents into passages and builds a local FAISS index
over local sentence-transformers embeddings (DEC-003) so extraction can
retrieve relevant passages instead of ingesting whole documents. No
passage or embedding is sent anywhere in this module.
"""

from __future__ import annotations

from typing import Protocol

from crawler.exposure.fetch import NormalizedDocument
from crawler.exposure.schema import RetrievedPassage

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """Local embeddings only; nothing leaves the machine."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).tolist()


def chunk_document(
    document: NormalizedDocument,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[RetrievedPassage]:
    passages: list[RetrievedPassage] = []
    for section in document.sections:
        words = section.text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = start + chunk_size // 6  # ~6 chars/word average
            chunk_words = words[start:end]
            text = " ".join(chunk_words)
            if text:
                passages.append(
                    RetrievedPassage(
                        text=text,
                        source_url=document.url,
                        document_type=document.document_type,
                        location=section.location,
                    )
                )
            if end >= len(words):
                break
            start = end - overlap // 6
            if start <= 0:
                start = end
    return passages


class PassageIndex:
    """FAISS-backed nearest-neighbour search over passage embeddings."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or SentenceTransformerEmbedder()
        self._passages: list[RetrievedPassage] = []
        self._index = None

    def build(self, passages: list[RetrievedPassage]) -> None:
        import faiss
        import numpy as np

        self._passages = passages
        if not passages:
            self._index = None
            return
        vectors = np.array(self._embedder.embed([p.text for p in passages]), dtype="float32")
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        self._index = index

    def query(self, text: str, *, top_k: int = 5) -> list[RetrievedPassage]:
        import numpy as np

        if self._index is None or not self._passages:
            return []
        vector = np.array(self._embedder.embed([text]), dtype="float32")
        _, indices = self._index.search(vector, min(top_k, len(self._passages)))
        return [self._passages[i] for i in indices[0] if i != -1]
