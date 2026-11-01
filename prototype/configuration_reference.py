# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Recorded software/protocol settings, not credentials or input data."""
RECORDED_LLM = {'model': 'deepseek-flash', 'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high', 'temperature': None, 'max_tokens': 64000}
EMBEDDING = {'model': 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 'revision': 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42', 'dimensions': 384, 'backend': 'ONNX Runtime CPU, AVX2 uint8', 'pooling': 'attention-mask mean then per-document chunk mean then L2 normalization', 'max_tokens_per_chunk_including_specials': 128}
SOURCE_ONLY_RELEASE = True
