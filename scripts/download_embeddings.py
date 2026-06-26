#!/usr/bin/env python3
# EUNICE - Efficient Unified Neural Intelligence for Communication and Execution
# Copyright 2026 Ronny Koome
# Licensed under the Elastic License 2.0.
# See LICENSE for details.

"""
EUNICE Script: Download Embedding Model
Pre-downloads the sentence-transformer model so ChromaDB works offline.
"""
import sys
from pathlib import Path

# Add project root to path so config imports work
project_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(project_root))

from sentence_transformers import SentenceTransformer
from config import EMBEDDING_MODEL

print(f"Downloading embedding model: {EMBEDDING_MODEL}...")
model = SentenceTransformer(EMBEDDING_MODEL)
print(f"✓ Model downloaded and cached.")
print(f"  Location: ~/.cache/torch/sentence_transformers/")
print(f"  You can now use semantic memory offline.")
