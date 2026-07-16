from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from src.config import settings


class QdrantManager:
    """
    Manages connections and administrative operations for the Qdrant vector database.
    """
    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=int(settings.QDRANT_PORT)
        )

    def init_qdrant(self):
        """
        Initialises the target vector collection with the correct dimensions and
        distance metric on startup. Safe to call on every start — uses exists check.
        """
        collection_name = settings.QDRANT_COLLECTION_NAME
        try:
            if not self.client.collection_exists(collection_name):
                print(f"Creating Qdrant collection '{collection_name}'...")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qdrant_models.VectorParams(
                        size=settings.QDRANT_VECTOR_SIZE,
                        distance=qdrant_models.Distance.COSINE
                    )
                )
                print(f"Qdrant collection '{collection_name}' created successfully.")
            else:
                print(f"Qdrant collection '{collection_name}' already exists.")
        except Exception as e:
            print(f"CRITICAL: Failed to initialise Qdrant collection: {e}")
            raise e


# Export a global instance
qdrant_manager = QdrantManager()
