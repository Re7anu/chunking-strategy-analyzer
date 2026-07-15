import re
import numpy as np
from src.clients.embedding_client import get_embeddings

def split_into_sentences(text: str) -> list[str]:
    """
    Splits document text into sentences using regex boundary matching,
    preserving punctuation.
    """
    sentence_endings = re.compile(r'(?<=[.!?])\s+')
    raw_sentences = sentence_endings.split(text)
    return [s.strip() for s in raw_sentences if s.strip()]

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """
    Calculates cosine similarity between two vector lists.
    """
    a = np.array(v1)
    b = np.array(v2)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))

def chunk_semantic(
    text: str, 
    chunk_size: int = 1000, 
    semantic_threshold: float = None
) -> list[str]:
    """
    Splits text into sentences, generates embeddings for adjacent sentence segments,
    and cuts chunks where cosine similarity drops below a threshold.
    """
    raw_sentences = split_into_sentences(text)
    if not raw_sentences:
        return []
    if len(raw_sentences) == 1:
        return [raw_sentences[0]]

    # Optimization: Group very short sentences (e.g. figures, citations, short lines)
    # together before embedding to drastically cut down API calls.
    sentences = []
    temp = ""
    for s in raw_sentences:
        # Group up to 100 characters together as a semantic unit
        if len(temp) + len(s) < 100:
            temp = temp + " " + s if temp else s
        else:
            if temp and temp.strip():
                sentences.append(temp)
            temp = s
    if temp and temp.strip():
        sentences.append(temp)

    # Ensure we still have sentences to evaluate
    if not sentences:
        return []
    if len(sentences) == 1:
        return [sentences[0]]

    print(f"Semantic Chunker: Pacing embeddings for {len(sentences)} sentence segments...")
    embeddings = get_embeddings(sentences)

    # Calculate cosine similarity between consecutive sentences
    similarities = []
    for i in range(len(embeddings) - 1):
        similarities.append(cosine_similarity(embeddings[i], embeddings[i+1]))

    # Determine similarity split threshold
    if semantic_threshold is not None:
        threshold = semantic_threshold
    else:
        # Dynamic threshold: mean - 0.6 * standard_deviation
        mean_sim = np.mean(similarities) if similarities else 0.8
        std_sim = np.std(similarities) if similarities else 0.05
        threshold = mean_sim - 0.6 * std_sim
        print(f"Semantic Chunker: Calculated dynamic threshold = {threshold:.4f} (mean: {mean_sim:.4f}, std: {std_sim:.4f})")

    # Group sentences into chunks based on threshold
    chunks = []
    current_chunk_sentences = []
    current_len = 0

    for i, sentence in enumerate(sentences):
        current_chunk_sentences.append(sentence)
        current_len += len(sentence)

        if i < len(sentences) - 1:
            similarity = similarities[i]
            
            # Split conditions:
            # 1. Similarity drops below threshold and current chunk meets minimum length (e.g., 150 characters)
            # 2. Or, adding the next sentence would exceed target chunk size
            is_semantic_split = similarity < threshold
            is_too_large = current_len + len(sentences[i+1]) > chunk_size
            is_min_length_met = current_len >= 150

            if (is_semantic_split and is_min_length_met) or is_too_large:
                chunks.append(" ".join(current_chunk_sentences))
                current_chunk_sentences = []
                current_len = 0

    if current_chunk_sentences:
        chunks.append(" ".join(current_chunk_sentences))

    return chunks
