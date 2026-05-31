"""Embedding generator for local asyncpg-based vector indexer."""
from typing import List


class EmbeddingGenerator:
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    def embed_single(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]
