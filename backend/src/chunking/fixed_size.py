def chunk_fixed_size(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    """
    Splits text into chunks of target character size with sliding overlap window,
    adjusting boundaries to preserve word and line boundaries where possible.
    """
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    chunks = []
    start_idx = 0
    
    while start_idx < len(text):
        end_idx = start_idx + chunk_size

        # Find word or line boundary to avoid splitting mid-word
        if end_idx < len(text):
            last_space = text.rfind(' ', start_idx, end_idx)
            last_newline = text.rfind('\n', start_idx, end_idx)
            boundary = max(last_space, last_newline)
            
            # Ensure the adjusted chunk is not too small (at least 50% of target size)
            if boundary > start_idx + (chunk_size // 2):
                end_idx = boundary

        chunk = text[start_idx:end_idx].strip()
        if chunk:
            chunks.append(chunk)
            
        start_idx = end_idx - chunk_overlap
        # Prevent infinite loops if overlap is misconfigured
        if start_idx >= end_idx:
            start_idx = end_idx

    return chunks
