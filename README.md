# NexusRAG: Financial Audit RAG & Chunking Strategy Analyzer

NexusRAG is a full-stack Retrieval-Augmented Generation (RAG) platform and diagnostic sandbox designed specifically for **financial document auditing and chunking strategy evaluation**.

Financial reports (such as SEC 10-K/10-Q filings, earnings releases, and corporate balance sheets) present unique challenges for standard RAG systems: multi-column tables, accounting parentheticals for negative values `(e.g. (1,250) = -$1,250M)`, and strict fiscal year/quarter alignments. Slicing these documents with naive fixed character counts frequently breaks tables and isolates figures from their context.

NexusRAG solves this by providing a unified environment to **ingest financial documentation, benchmark 4 distinct chunking strategies side-by-side, visualize hybrid RRF retrieval ranks, and query documents with an AI Financial Analyst assistant**.

---

## Key Features

### 1. Layout-Aware Financial Document Parsing
* **Markdown Table Preservation**: Uses `pdfplumber` to extract multi-column financial statements and convert table grids into clean Markdown tables prior to chunking.
* **Automated Metadata Extraction**: Automatically parses fiscal year (e.g. `2024`, `2025`) and fiscal quarter (`Q1`, `Q2`, `Q3`, `Q4`, `FY`) from document filenames or content headers.

### 2. 4 Benchmark Chunking Strategies
* **Fixed-Size Chunker**: Sliding character window with boundary alignment to prevent cutting words or line breaks mid-sentence.
* **Recursive Chunker**: Traversing delimiter hierarchy (`\n\n`, `\n`, space) to preserve paragraph and sentence integrity.
* **Semantic Shift Chunker**: Sentence-level partitioning that detects topic boundaries using cosine similarity drops between embeddings.
* **Page-Based Chunker**: Slices documents strictly on physical PDF page boundaries while tagging each chunk with page numbers.

### 3. Granular Hyperparameter & Ingestion Matrix Controls
* Configure target chunk sizes, sliding window overlaps, and semantic similarity thresholds per strategy.
* Ingest documents under a single strategy or across **all 4 strategies simultaneously** for side-by-side comparative analysis.

### 4. Reciprocal Rank Fusion (RRF) Hybrid Search Sandbox
* Combines **dense vector semantic search** (384-dimensional local embeddings stored in Qdrant) with **in-memory sparse lexical keyword matching**.
* Calculates RRF scores ($RRF\_Score = \frac{1}{k + rank_{sem}} + \frac{1}{k + rank_{key}}$) to surface relevant context chunks.
* Supports metadata filtering by fiscal year and quarter.

### 5. Side-by-Side Comparative Analysis Dashboard
* Executes search queries across all 4 chunking strategies in parallel.
* Displays matches side-by-side in comparative columns with similarity percentage scores, RRF ranks, and expandable chunk previews.

### 6. Interactive Streaming Financial Support Chat
* Streams answers in real-time using Google Gemini (`gemini-3.1-flash-lite`) via Server-Sent Events (SSE).
* **Document Scoping**: Attach or detach specific uploaded documents to individual chat threads to control the exact retrieval context.
* **Guardrailed Financial Prompt**: System instructions optimized for mathematical accuracy, table grid interpretation, parenthetical loss handling, and prompt injection defense.
* **Auto-Titling**: Automatically generates a concise thread title after the first user query.

### 7. Multi-User Authentication & Thread Persistence
* JWT-based user authentication (`bcrypt` password hashing, registration, login, and user profile management).
* Relational PostgreSQL storage for user accounts, active sessions, document libraries, chat threads, message histories, and document attachments.

---

## Technology Stack

* **Backend**: FastAPI, Uvicorn, Python 3.10+, `pdfplumber`, PyPDF, SentenceTransformers, `google-genai` SDK, `psycopg2-binary`, `bcrypt`, `python-jose`.
* **Frontend**: HTML5, Vanilla JavaScript modules (`auth.js`, `chat.js`, `ingest.js`, `sandbox.js`, `state.js`), Vanilla CSS with a deep slate dark theme and glassmorphism styling.
* **Vector Database**: **Qdrant** (port `6333`) — Stores 384-dimensional vector embeddings and payload metadata.
* **Relational Database**: **PostgreSQL 16** (port `5432`) — Stores user accounts, sessions, document library entries, threads, messages, and attachments.
* **Embedding Model**: `all-MiniLM-L6-v2` running 100% locally on CPU via SentenceTransformers (no API costs or rate limits).

---

## Codebase File Structure

```text
Chunking Strategy Analyzer/
├── .env                       # Root environment variables (GEMINI_API_KEY, DB settings)
├── docker-compose.yml         # Container orchestration (web, postgres, qdrant)
├── README.md                  # Project documentation
│
├── backend/
│   ├── Dockerfile             # Container image build configuration
│   ├── requirements.txt       # Python dependencies
│   ├── main.py                # FastAPI application entry point
│   └── src/
│       ├── config/
│       │   └── settings.py    # Centralized configuration & environment variables
│       ├── db/
│       │   ├── db_client.py        # PostgreSQL connection pool & schema verification
│       │   ├── qdrant_client.py    # Qdrant client setup & collection lifecycle
│       │   ├── persistence_store.py# SQL queries for threads, messages, & documents
│       │   ├── user_store.py       # SQL queries for user accounts & sessions
│       │   └── init.sql            # Initial PostgreSQL database schema
│       ├── auth/
│       │   ├── router.py           # Auth endpoints (/register, /login, /me, /logout)
│       │   ├── jwt_handler.py      # JWT token generation & verification
│       │   ├── dependencies.py     # FastAPI get_current_user security dependency
│       │   ├── models.py           # Pydantic schemas for authentication
│       │   └── validators.py       # Input validation & email regex checks
│       ├── routers/
│       │   ├── chat.py             # Chat threads, attachments, & streaming endpoints
│       │   ├── ingest.py           # Raw text & PDF document ingestion endpoints
│       │   └── search.py           # RRF sandbox & comparative analysis endpoints
│       ├── services/
│       │   └── rag_service.py      # Core RRF hybrid search implementation
│       ├── clients/
│       │   ├── embedding_client.py # Local SentenceTransformer embedding model runner
│       │   ├── gemini_client.py    # Gemini API streaming & thread auto-titling
│       │   └── prompts.py          # System instructions & chat title templates
│       ├── chunking/
│       │   ├── fixed_size.py       # Fixed character size sliding window chunker
│       │   ├── recursive.py        # Delimiter hierarchy recursive chunker
│       │   ├── semantic.py         # Cosine similarity shift chunker
│       │   └── page_based.py       # PDF page boundary chunker
│       ├── chunker_manager.py      # Central router for chunking strategies
│       └── utils/
│           └── financial_parser.py # PDF layout-aware table extractor & metadata detector
│
└── frontend/
    ├── index.html             # Single-Page Application (SPA) structure
    ├── app.css                # Custom CSS styles (dark slate theme, glassmorphism)
    ├── app.js                 # App initialization & tab switching
    ├── auth.js                # Auth UI controller (login/register/logout modals)
    ├── chat.js                # Streaming chat controller & thread management
    ├── ingest.js              # Ingestion form modes & drag-and-drop PDF handler
    ├── sandbox.js             # RRF Sandbox & comparative dashboard UI
    └── state.js               # Global application state & helper utilities
```

---

## Quick Start: Running in Docker (Recommended)

1. Ensure **Docker Desktop** is running on your machine.
2. Configure your Gemini API key inside the root [.env](file:///C:/Users/rehan/OneDrive/Desktop/Chunking%20Strategy%20Analyzer/.env) file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   ```
3. Start the application, Qdrant, and PostgreSQL containers:
   ```bash
   docker compose up -d --build
   ```
4. Monitor startup logs and model downloading:
   ```bash
   docker compose logs -f
   ```
5. Open your browser and navigate to:
   ```text
   http://localhost:3000
   ```

*To stop the container stack:*
```bash
docker compose down
```

---

## Alternative Start: Running Locally (Host Machine)

### 1. Prerequisites
* **Python 3.10+** installed.
* **PostgreSQL 16** running locally with a database named `rag_db`.
* **Qdrant** running locally on port `6333`.

### 2. Configure Environment
Set your credentials in `backend/.env`:
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

### 3. Install & Run
```bash
# Navigate to backend folder
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn main:app --host 0.0.0.0 --port 3000
```
Open `http://localhost:3000` in your browser.
