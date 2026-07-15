from sentence_transformers import SentenceTransformer
from src.config.settings import EMBEDDING_MODEL_NAME

# Load the model locally (caches in standard HuggingFace directory)
print(f"Loading local {EMBEDDING_MODEL_NAME} embedding model...")
model = SentenceTransformer(EMBEDDING_MODEL_NAME)
print("Local embedding model loaded successfully.")

def get_embedding(text: str) -> list[float]:
    """
    Generates a 384-dimensional vector embedding locally using all-MiniLM-L6-v2.
    """
    if not text or not text.strip():
        raise ValueError("Input text cannot be empty.")
    
    embedding = model.encode(text)
    return embedding.tolist()

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Generates a batch of 384-dimensional vector embeddings locally.
    """
    if not texts:
        return []
    
    embeddings = model.encode(texts)
    return embeddings.tolist()
