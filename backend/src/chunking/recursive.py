class RecursiveCharacterSplitter:
    """
    Splits text recursively using a hierarchy of delimiters:
    paragraphs (\n\n), sentences/lines (\n), words (space), and characters.
    It combines adjacent items as long as they fit under the chunk_size,
    preserving overlap.
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200, separators: list[str] = None):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

    def split_text(self, text: str) -> list[str]:
        return self._split_text(text, self.separators)

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]

        # Select first separator that appears in text
        separator = ""
        next_separators = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                next_separators = separators[i+1:]
                break
            if sep in text:
                separator = sep
                next_separators = separators[i+1:]
                break

        # Split text by delimiter
        if separator != "":
            splits = text.split(separator)
        else:
            splits = list(text)

        final_chunks = []
        current_chunk = []
        current_len = 0

        for s in splits:
            if len(s) > self.chunk_size:
                # Flush existing chunk buffer
                if current_chunk:
                    merged = separator.join(current_chunk)
                    if merged.strip():
                        final_chunks.append(merged.strip())
                    current_chunk = []
                    current_len = 0
                
                # Split the oversized item recursively using the next delimiters
                sub_splits = self._split_text(s, next_separators)
                final_chunks.extend(sub_splits)
            else:
                # Check if adding this split exceeds target size
                separator_overhead = len(separator) if current_chunk else 0
                if current_len + len(s) + separator_overhead > self.chunk_size:
                    if current_chunk:
                        merged = separator.join(current_chunk)
                        if merged.strip():
                            final_chunks.append(merged.strip())
                    
                    # Accumulate overlap elements from the end of the previous chunk
                    overlap_chunk = []
                    overlap_len = 0
                    for item in reversed(current_chunk):
                        sep_len = len(separator) if overlap_chunk else 0
                        if overlap_len + len(item) + sep_len <= self.chunk_overlap:
                            overlap_chunk.insert(0, item)
                            overlap_len += len(item) + sep_len
                        else:
                            break
                    current_chunk = overlap_chunk
                    current_len = overlap_len
                
                current_chunk.append(s)
                current_len += len(s) + (len(separator) if len(current_chunk) > 1 else 0)

        # Flush any remaining items in buffer
        if current_chunk:
            merged = separator.join(current_chunk)
            if merged.strip():
                final_chunks.append(merged.strip())

        return final_chunks

def chunk_recursive(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
    splitter = RecursiveCharacterSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return splitter.split_text(text)
