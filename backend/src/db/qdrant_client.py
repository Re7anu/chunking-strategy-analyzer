from qdrant_client import QdrantClient
from qdrant_client.http import models
from src.config import settings

qdrant_client = None

def get_qdrant_client():
    global qdrant_client
    if qdrant_client is None:
        qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=int(settings.QDRANT_PORT))
    return qdrant_client

def init_qdrant():
    client = get_qdrant_client()
    collection_name = "analyzer_chunks"
    
    try:
        collections = client.get_collections()
        exists = any(c.name == collection_name for c in collections.collections)
        
        if not exists:
            print(f"Creating Qdrant collection '{collection_name}'...")
            client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=384,  # 384 dimensions for all-MiniLM-L6-v2
                    distance=models.Distance.COSINE
                )
            )
            print(f"Qdrant collection '{collection_name}' created successfully.")
        else:
            print(f"Qdrant collection '{collection_name}' already exists.")
    except Exception as e:
        print(f"Error initializing Qdrant: {e}")
