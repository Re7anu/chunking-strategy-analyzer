# NexusRAG: Chunking Strategy Analyzer

NexusRAG is a visual playground and diagnostic sandbox designed to analyze, evaluate, and compare different document chunking strategies for Retrieval-Augmented Generation (RAG) applications. It runs a local hybrid search pipeline combining in-memory lexical keyword matching and dense vector search inside Qdrant, using PostgreSQL for user metadata and thread persistence.

---

## Key Features

* **4 Chunking Strategies**:
  * **Fixed-Size Chunker**: Sliding character window with boundary alignment to preserve complete words.
  * **Recursive Chunker**: Delimiter-hierarchy splits traversing paragraphs, sentences, lines, and words.
  * **Semantic Shift Chunker**: Sentence-level partitioning based on cosine similarity thresholds calculated using local embeddings.
  * **Page-Based Chunker**: Slices documents directly on physical PDF page breaks, tagging chunks with numerical page metadata.
* **Hyperparameter Matrix Controls**: Granular UI configuration cards that allow adjusting target sizes, overlaps, and semantic thresholds for each strategy independently during ingestion.
* **RRF Hybrid Search Sandbox**: Visualizes how Reciprocal Rank Fusion (RRF) combines sparse keyword search ranks and dense semantic vector search ranks into a unified score.
* **Side-by-Side Comparison Dashboard**: Renders retrieved matches from all 4 strategies side-by-side using sticky headers, unified scroll heights, and content-based deduplication.
* **Instant Conversational Support Chat**: Streams answers based on retrieved context using the `gemini-3.1-flash-lite` model.
* **100% Local Embeddings**: Uses `all-MiniLM-L6-v2` SentenceTransformers locally to generate 384-dimensional vectors. No cloud API rate limits, costs, or quotas for embeddings.

---

## Technology Stack

* **Backend**: FastAPI, Uvicorn, psycopg2-binary (PostgreSQL client), PyPDF, SentenceTransformers, google-genai SDK, numpy.
* **Frontend**: HTML5, Vanilla JavaScript, and CSS (clean deep slate styling with glassmorphism).
* **Database**: Qdrant (vector index) + PostgreSQL 16 (session/thread relational database).

---

## Codebase File Structure

* [backend/main.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/main.py): FastAPI application entry point, lifespan initialization, and router mounting.
* [backend/src/config/settings.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/config/settings.py): Central configuration file managing credentials, database hosts, and model parameters.
* [backend/src/db/db_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/db/db_client.py): PostgreSQL connection pooling, fallback schema verification, and users tables setup.
* [backend/src/db/persistence_store.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/db/persistence_store.py): SQL database operations (chat threads, message histories, document libraries).
* [backend/src/db/init.sql](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/db/init.sql): SQL schema template loaded during PostgreSQL startup.
* [backend/src/db/qdrant_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/db/qdrant_client.py): Qdrant client lifecycle operations and collection setup.
* [backend/src/services/rag_service.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/services/rag_service.py): Core Reciprocal Rank Fusion (RRF) hybrid search implementation.
* [backend/src/routers/](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/routers/): Sub-routers for API endpoints:
  * [chat.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/routers/chat.py): Thread CRUD, document library matching, and streaming chat.
  * [ingest.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/routers/ingest.py): Document ingestion pipelines (Markdown text and layout-aware PDF parsers).
  * [search.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/routers/search.py): Hybrid search query evaluation and strategy comparisons.
* [backend/src/clients/](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/clients/): Integrations with external SDKs:
  * [embedding_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/clients/embedding_client.py): Manages local sentence transformer models.
  * [gemini_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/clients/gemini_client.py): Controls conversation title generation and SSE streaming.
  * [prompts.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/backend/src/clients/prompts.py): System instructions and chat thread title templates for the financial analyst RAG role.
* [docker-compose.yml](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/docker-compose.yml): Coordinates the PostgreSQL database, Qdrant vector database, and FastAPI web container stack.

---

## Quick Start: Running in Docker (Recommended)

1. Ensure **Docker Desktop** is running on your machine.
2. Verify that your Gemini API key is configured inside the root [.env](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/.env) file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
3. Spin up the application, Qdrant, and PostgreSQL database container stack:
   ```bash
   docker compose up -d --build
   ```
4. Check startup logs and monitor the embedding model download (on first boot):
   ```bash
   docker compose logs -f
   ```
5. Open your browser and navigate to:
   ```text
   http://localhost:3000
   ```

*To shut down the container stack, run:*
```bash
docker compose down
```

---

## Alternative Start: Running Locally (Host Machine)

### 1. Prerequisites
* **Python 3.10+** installed on your system.
* **PostgreSQL** running locally with a database named `rag_db`.
* **Qdrant** installed and running locally on port `6333`.

### 2. Setup environment variables
Configure your `backend/.env` file with your local credentials:
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=rag_db
QDRANT_HOST=localhost
QDRANT_PORT=6333
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Install packages and run
```bash
# Navigate to the backend directory
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Start FastAPI server
uvicorn main:app --host 0.0.0.0 --port 3000
```
Visit `http://localhost:3000` in your browser.
