from src.chunking.fixed_size import chunk_fixed_size
from src.chunking.recursive import chunk_recursive
from src.chunking.semantic import chunk_semantic
from src.chunking.page_based import chunk_page_based

def chunk_document(text: str, options: dict) -> list[dict]:
    """
    Central routing function for document chunking.
    Options dict expects:
      - strategy: 'fixed-size' | 'recursive' | 'semantic' | 'page-based'
      - chunk_size: int
      - chunk_overlap: int
      - semantic_threshold: float (optional)
      - pages: list of {"number": int, "text": str} (optional)
      - base_metadata: dict
    """
    strategy = options.get("strategy", "fixed-size")
    chunk_size = int(options.get("chunk_size", 1000))
    chunk_overlap = int(options.get("chunk_overlap", 200))
    semantic_threshold = options.get("semantic_threshold")
    pages = options.get("pages", [])
    base_metadata = options.get("base_metadata", {})

    formatted_chunks = []

    if strategy == "fixed-size":
        raw_chunks = chunk_fixed_size(text, chunk_size, chunk_overlap)
        for i, content in enumerate(raw_chunks):
            meta = base_metadata.copy()
            meta.update({
                "chunkIndex": i,
                "charCount": len(content),
                "strategy": "fixed-size"
            })
            formatted_chunks.append({"content": content, "metadata": meta})

    elif strategy == "recursive":
        raw_chunks = chunk_recursive(text, chunk_size, chunk_overlap)
        for i, content in enumerate(raw_chunks):
            meta = base_metadata.copy()
            meta.update({
                "chunkIndex": i,
                "charCount": len(content),
                "strategy": "recursive"
            })
            formatted_chunks.append({"content": content, "metadata": meta})

    elif strategy == "semantic":
        raw_chunks = chunk_semantic(text, chunk_size, semantic_threshold)
        for i, content in enumerate(raw_chunks):
            meta = base_metadata.copy()
            meta.update({
                "chunkIndex": i,
                "charCount": len(content),
                "strategy": "semantic"
            })
            formatted_chunks.append({"content": content, "metadata": meta})

    elif strategy == "page-based":
        raw_dict_chunks = chunk_page_based(pages, chunk_size, chunk_overlap)
        for i, chunk in enumerate(raw_dict_chunks):
            meta = base_metadata.copy()
            meta.update({
                "chunkIndex": i,
                "charCount": len(chunk["content"]),
                "pageNumber": chunk["metadata"]["pageNumber"],
                "strategy": "page-based"
            })
            formatted_chunks.append({"content": chunk["content"], "metadata": meta})
    else:
        raise ValueError(f"Unsupported chunking strategy: {strategy}")

    return formatted_chunks
