import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Database Configurations
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "rag_db")

# Model Configurations
# Local sentence-transformers model name
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Gemini Chat Model name for RAG generation
CHAT_MODEL_NAME = "gemini-3.5-flash"
