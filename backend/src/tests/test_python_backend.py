import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.chunking.fixed_size import chunk_fixed_size
from src.chunking.recursive import chunk_recursive
from src.chunking.page_based import chunk_page_based
from src.chunker_manager import chunk_document

def test_chunkers():
    test_text = "This is a simple text segment. It contains multiple sentences. Let's see if we can chunk it properly."
    
    # 1. Test Fixed Size
    chunks_fixed = chunk_fixed_size(test_text, chunk_size=30, chunk_overlap=5)
    print(f"Fixed chunks: {chunks_fixed}")
    assert len(chunks_fixed) > 0, "Fixed size chunker failed"
    
    # 2. Test Recursive
    chunks_rec = chunk_recursive(test_text, chunk_size=30, chunk_overlap=5)
    print(f"Recursive chunks: {chunks_rec}")
    assert len(chunks_rec) > 0, "Recursive chunker failed"
    
    # 3. Test Page-Based
    pages = [{"number": 1, "text": "Page one text here."}, {"number": 2, "text": "Page two text here."}]
    chunks_page = chunk_page_based(pages, chunk_size=50, chunk_overlap=5)
    print(f"Page chunks: {chunks_page}")
    assert len(chunks_page) == 2, "Page chunker failed"
    
    # 4. Test Router
    routed_chunks = chunk_document(test_text, {
        "strategy": "fixed-size",
        "chunk_size": 30,
        "chunk_overlap": 5,
        "base_metadata": {"title": "Test Title"}
    })
    print(f"Routed chunks count: {len(routed_chunks)}")
    print(f"Sample routed chunk: {routed_chunks[0]}")
    assert len(routed_chunks) > 0, "Router chunker failed"
    
    print("\n--- ALL PYTHON CHUNKER MODULE TESTS PASSED ---")

if __name__ == "__main__":
    test_chunkers()
