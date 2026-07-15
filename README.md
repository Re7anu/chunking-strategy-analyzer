# NexusRAG: Chunking Strategy Analyzer

NexusRAG is a visual playground and diagnostic sandbox designed to analyze, evaluate, and compare different document chunking strategies for Retrieval-Augmented Generation (RAG) applications. It runs a local hybrid search pipeline combining full-text keyword indexing and dense vector embeddings inside PostgreSQL using `pgvector`.

---

## 🚀 Key Features

* **4 Chunking Strategies**:
  * **Fixed-Size Chunker**: Sliding character window with boundary alignment to preserve complete words.
  * **Recursive Chunker**: Delimiter-hierarchy splits traversing paragraphs, sentences, lines, and words.
  * **Semantic Shift Chunker**: Sentence-level partitioning based on cosine similarity thresholds calculated using local embeddings.
  * **Page-Based Chunker**: Slices documents directly on physical PDF page breaks, tagging chunks with numerical page metadata.
* **Hyperparameter Matrix Controls**: Granular UI configuration cards that allow adjusting target sizes, overlaps, and semantic thresholds for each strategy independently during ingestion.
* **RRF Hybrid Search Sandbox**: Visualizes how Reciprocal Rank Fusion (RRF) combines sparse keyword search ranks and dense semantic vector search ranks into a unified score.
* **Side-by-Side Comparison Dashboard**: Renders retrieved matches from all 4 strategies side-by-side using sticky headers, unified scroll heights, and content-based deduplication (`GROUP BY content`).
* **Instant Conversational Support Chat**: Streams answers based on retrieved context using the upgraded `gemini-3.5-flash` model.
* **100% Local Embeddings**: Uses `all-MiniLM-L6-v2` SentenceTransformer locally to generate 384-dimensional vectors. No cloud API rate limits, costs, or quotas for embeddings.

---

## 🛠️ Technology Stack

* **Backend**: FastAPI, Uvicorn, psycopg2-binary (PostgreSQL client), PyPDF, SentenceTransformers, google-genai SDK, numpy.
* **Frontend**: HTML5, Vanilla JavaScript, and Tailwind-inspired CSS (curated deep slate design with glassmorphism).
* **Database**: PostgreSQL 16 + `pgvector` extension.

---

## 📂 Codebase File Structure

* [main.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/main.py): FastAPI application routes, static mounts, and RRF search SQL queries.
* [settings.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/settings.py): Central configuration file managing credentials, database hosts, and model names.
* [db_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/db_client.py): PostgreSQL connection pooling, fallback schema creation, and automatic vector dimension checkers.
* [embedding_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/embedding_client.py): Loads the local `all-MiniLM-L6-v2` transformer and batches embeddings.
* [gemini_client.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/gemini_client.py): Handles context-augmented SSE support chat streams using `gemini-3.5-flash`.
* [init.sql](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/init.sql): Schema definition for the 384-dimensional HNSW vector index and GIN text search indices.
* [chunking/router.py](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/chunking/router.py): Unified strategy router for fixed-size, recursive, semantic, and page-based chunk splitters.
* [Dockerfile](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/Dockerfile): Configures compile headers, installs dependencies, and runs the FastAPI container.
* [docker-compose.yml](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/docker-compose.yml): Coordinates the database and web service stack with persistent cache directories.

---

## 🐳 Quick Start: Running in Docker (Recommended)

1. Ensure **Docker Desktop** is running on your machine.
2. Verify that your API key is configured inside the [.env](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/.env) file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
3. Spin up the application and database container stack:
   ```bash
   docker compose up -d --build
   ```
4. Check startup logs and monitor the model download (on first boot):
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

## 🐍 Alternative Start: Running Locally (Host Machine)

### 1. Prerequisites
* **Python 3.10+** installed on your system.
* **PostgreSQL** running locally with the `pgvector` extension enabled. Create a database named `rag_db`.

### 2. Setup environment variables
Configure your [.env](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/.env) file with your local database credentials:
```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=rag_db
GEMINI_API_KEY=your_gemini_api_key
```

### 3. Install packages and run
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Start FastAPI server
uvicorn main:app --host 0.0.0.0 --port 3000
```
Visit `http://localhost:3000` to access the application dashboard.
