from src.chunking.recursive import RecursiveCharacterSplitter

def chunk_page_based(
    pages: list[dict], 
    chunk_size: int = 1500, 
    chunk_overlap: int = 200
) -> list[dict]:
    """
    Partitions documents based on page structures.
    If a page's content is larger than chunk_size, it splits it recursively,
    while preserving pageNumber metadata for each sub-chunk.
    
    Expected pages input: [{"number": int, "text": str}]
    Returns: [{"content": str, "metadata": {"pageNumber": int}}]
    """
    if not pages:
        return []

    chunks = []
    recursive_splitter = RecursiveCharacterSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    for page in pages:
        page_num = page.get("number", 1)
        page_text = page.get("text", "").strip()
        
        if not page_text:
            continue

        # If page text is within chunk limit, keep as single chunk
        if len(page_text) <= chunk_size:
            chunks.append({
                "content": page_text,
                "metadata": {
                    "pageNumber": page_num
                }
            })
        else:
            # Split page text recursively
            sub_splits = recursive_splitter.split_text(page_text)
            for split in sub_splits:
                chunks.append({
                    "content": split,
                    "metadata": {
                        "pageNumber": page_num
                    }
                })

    return chunks
