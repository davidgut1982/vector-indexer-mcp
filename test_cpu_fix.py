#!/usr/bin/env python3
"""Test that embedding model loads on CPU without CUDA errors."""

import os
import sys

# Force CPU mode (same as systemd service)
os.environ['CUDA_VISIBLE_DEVICES'] = ''

# Load the embedding model
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

print(f"Loading embedding model: {EMBEDDING_MODEL}")
print(f"CUDA_VISIBLE_DEVICES: '{os.environ.get('CUDA_VISIBLE_DEVICES', 'not set')}'")

try:
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"✓ Model loaded successfully")
    print(f"✓ Device: {model.device}")

    # Test encoding
    test_text = "This is a test sentence"
    embedding = model.encode(test_text, normalize_embeddings=True)
    print(f"✓ Encoding test successful")
    print(f"✓ Embedding shape: {embedding.shape}")
    print("\n SUCCESS: No CUDA errors - model running on CPU")
    sys.exit(0)

except Exception as e:
    print(f"\n✗ FAILED: {e}")
    sys.exit(1)
