"""Embedding generation module for vector indexer.

Uses sentence-transformers to generate multilingual embeddings for text chunks.
Supports both single and batch embedding generation.
"""

import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generate embeddings using sentence-transformers.

    Uses paraphrase-multilingual-MiniLM-L12-v2 model for multilingual support,
    producing 384-dimensional vectors suitable for semantic search.

    Args:
        model_name: Sentence-transformers model name
        device: Device to run model on ('cpu', 'cuda', or None for auto)
    """

    def __init__(
        self,
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: str = None
    ):
        """Initialize the embedding generator."""
        self.model_name = model_name
        self.device = device

        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)

        # Get embedding dimension
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        logger.info(
            f"Embedding model loaded: dim={self.embedding_dim}, device={self.model.device}"
        )

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each as list of floats)

        Raises:
            ValueError: If texts is empty
        """
        if not texts:
            raise ValueError("Cannot embed empty text list")

        logger.debug(f"Embedding batch of {len(texts)} texts")

        # Generate embeddings
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        # Convert to list of lists
        embedding_list = embeddings.tolist()

        logger.debug(f"Generated {len(embedding_list)} embeddings")
        return embedding_list

    def embed_single(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector as list of floats

        Raises:
            ValueError: If text is empty
        """
        if not text.strip():
            raise ValueError("Cannot embed empty text")

        logger.debug("Embedding single text")

        # Generate embedding
        embedding = self.model.encode(
            text,
            show_progress_bar=False,
            convert_to_numpy=True
        )

        # Convert to list
        embedding_list = embedding.tolist()

        logger.debug(f"Generated embedding with {len(embedding_list)} dimensions")
        return embedding_list

    def get_embedding_dimension(self) -> int:
        """Get the dimensionality of embeddings produced by this model.

        Returns:
            Embedding dimension (e.g., 384 for MiniLM)
        """
        return self.embedding_dim

    def normalize_embedding(self, embedding: List[float]) -> List[float]:
        """Normalize embedding to unit length (L2 norm).

        Useful for cosine similarity comparisons.

        Args:
            embedding: Input embedding vector

        Returns:
            Normalized embedding vector
        """
        arr = np.array(embedding)
        norm = np.linalg.norm(arr)

        if norm == 0:
            return embedding

        normalized = (arr / norm).tolist()
        return normalized
