#!/usr/bin/env python3
"""Test script for vector indexer pipeline components.

Run with: python test_pipeline.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add daemon to path
sys.path.insert(0, str(Path(__file__).parent))

from daemon.chunker import TextChunker
from daemon.embedder import EmbeddingGenerator


def test_chunker():
    """Test the TextChunker component."""
    print("\n=== Testing TextChunker ===")

    chunker = TextChunker(max_tokens=100, overlap_tokens=20)

    # Test text
    test_text = """This is a test document.
It has multiple lines.
Each line will be processed by the chunker.
The chunker respects line boundaries when possible.
This helps maintain semantic coherence in chunks.

Here's a new paragraph after a blank line.
The chunker will handle this appropriately.
Token counting uses tiktoken for accuracy.
Overlapping chunks help with search recall.
End of test document."""

    chunks = chunker.chunk_text(test_text)

    print(f"Generated {len(chunks)} chunks")
    print()

    for chunk in chunks:
        print(f"Chunk {chunk.index}:")
        print(f"  Lines: {chunk.start_line}-{chunk.end_line}")
        print(f"  Tokens: {chunk.token_count}")
        print(f"  Char offset: {chunk.char_offset}")
        print(f"  Content preview: {chunk.text[:80]}...")
        print()

    assert len(chunks) > 0, "Should generate at least one chunk"
    assert all(c.token_count <= 100 for c in chunks), "Chunks should respect max_tokens"

    print("✓ TextChunker tests passed")
    return True


def test_embedder():
    """Test the EmbeddingGenerator component."""
    print("\n=== Testing EmbeddingGenerator ===")

    embedder = EmbeddingGenerator()

    print(f"Model: {embedder.model_name}")
    print(f"Embedding dimension: {embedder.embedding_dim}")
    print()

    # Test single embedding
    test_text = "This is a test sentence for embedding generation."
    embedding = embedder.embed_single(test_text)

    print(f"Single embedding shape: {len(embedding)} dimensions")
    print(f"First 5 values: {embedding[:5]}")
    print()

    assert len(embedding) == 384, "Should produce 384-dim embeddings"
    assert all(isinstance(v, float) for v in embedding), "Should contain floats"

    # Test batch embedding
    test_texts = [
        "First test sentence.",
        "Second test sentence with different content.",
        "Third sentence to test batch processing."
    ]

    embeddings = embedder.embed_batch(test_texts)

    print(f"Batch embeddings: {len(embeddings)} vectors")
    assert len(embeddings) == len(test_texts), "Should produce one embedding per text"
    assert all(len(e) == 384 for e in embeddings), "All should be 384-dim"

    # Test normalization
    normalized = embedder.normalize_embedding(embedding)
    print(f"Normalized embedding L2 norm: {sum(x**2 for x in normalized)**0.5:.6f}")

    print("✓ EmbeddingGenerator tests passed")
    return True


def test_integration():
    """Test integration of chunker and embedder."""
    print("\n=== Testing Integration ===")

    chunker = TextChunker(max_tokens=200, overlap_tokens=30)
    embedder = EmbeddingGenerator()

    # Sample document
    sample_doc = """Vector search is a powerful technique for semantic similarity.

It works by converting text into high-dimensional vectors called embeddings.
These embeddings capture the semantic meaning of the text.

When you search, your query is also converted to an embedding.
Then we find the most similar embeddings in our database.
This allows for semantic search beyond simple keyword matching.

The quality of search depends on the embedding model used.
Multilingual models can handle multiple languages.
This is especially useful for Latvian text processing."""

    # Chunk the document
    chunks = chunker.chunk_text(sample_doc)
    print(f"Document chunked into {len(chunks)} pieces")

    # Generate embeddings for all chunks
    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.embed_batch(chunk_texts)

    print(f"Generated {len(embeddings)} embeddings")
    print()

    # Display summary
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        print(f"Chunk {i}:")
        print(f"  Tokens: {chunk.token_count}")
        print(f"  Lines: {chunk.start_line}-{chunk.end_line}")
        print(f"  Embedding: {len(embedding)}-dim vector")
        print(f"  Preview: {chunk.text[:60]}...")
        print()

    print("✓ Integration tests passed")
    return True


def main():
    """Run all tests."""
    print("Vector Indexer Pipeline Test Suite")
    print("=" * 50)

    try:
        # Test components
        test_chunker()
        test_embedder()
        test_integration()

        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        print("\nPipeline components are working correctly.")
        print("Ready to run worker: python -m daemon.worker")

        return 0

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
