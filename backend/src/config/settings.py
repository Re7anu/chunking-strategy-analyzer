import os
from dotenv import load_dotenv

# Load environment variables from .env — called ONLY here, once.
load_dotenv()

# ─── Database ─────────────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "rag_db")

# Connection pool size
DB_POOL_MIN = 1
DB_POOL_MAX = 20

# ─── Gemini ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ─── Models ───────────────────────────────────────────────────────────────────
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
CHAT_MODEL_NAME = os.getenv("CHAT_MODEL_NAME", "gemini-3.5-flash")
CHAT_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.3"))

# ─── Chunking ─────────────────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE = int(os.getenv("DEFAULT_CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "200"))
DEFAULT_SEMANTIC_THRESHOLD = os.getenv("DEFAULT_SEMANTIC_THRESHOLD")
if DEFAULT_SEMANTIC_THRESHOLD:
    DEFAULT_SEMANTIC_THRESHOLD = float(DEFAULT_SEMANTIC_THRESHOLD)

# ─── Qdrant ───────────────────────────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "analyzer_chunks")
QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "384"))
# Hybrid search constants
QDRANT_SEMANTIC_CANDIDATES = int(os.getenv("QDRANT_SEMANTIC_CANDIDATES", "50"))
QDRANT_RRF_K = int(os.getenv("QDRANT_RRF_K", "60"))

# ─── JWT Authentication ───────────────────────────────────────────────────────
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))

# ─── Session and Search Limits ────────────────────────────────────────────────
DEFAULT_SESSION_NAME = os.getenv("DEFAULT_SESSION_NAME", "Default Session")
SEARCH_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", "5"))
COMPARE_RESULT_LIMIT = int(os.getenv("COMPARE_RESULT_LIMIT", "3"))

