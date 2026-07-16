import os
import io
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pypdf import PdfReader

from src.config import settings
from src.db.db_client import init_db, get_db_connection, release_db_connection
from src.db.qdrant_client import qdrant_manager
from src.auth.router import router as auth_router
from src.auth.dependencies import get_current_user
from src.auth.models import UserContext
from qdrant_client.http import models as qdrant_models
from src.clients.gemini_client import get_chat_stream
from src.clients.embedding_client import get_embedding, get_embeddings
from src.chunker_manager import chunk_document
from src.utils.financial_parser import parse_financial_pdf

# Alias frequently-used settings for readability
_COLLECTION = settings.QDRANT_COLLECTION_NAME
_RRF_K = settings.QDRANT_RRF_K
_CANDIDATES = settings.QDRANT_SEMANTIC_CANDIDATES


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize PostgreSQL connection pool (creates users/sessions tables) and Qdrant on startup
    init_db()
    qdrant_manager.init_qdrant()
    yield

app = FastAPI(lifespan=lifespan)

# Note: API routes MUST be registered before mounting StaticFiles at "/" to prevent path collisions.

# Register auth router — provides /api/auth/register, /api/auth/login, /api/auth/logout, /api/auth/me
app.include_router(auth_router)


# ─── Hybrid Search Helper ─────────────────────────────────────────────────────

def run_hybrid_search(
    query: str,
    user_id: str,
    session_id: str,
    strategy: str = "all",
    limit: int = 5,
    fiscal_year: int = None,
    quarter: str = None
) -> list[dict]:
    """
    Performs hybrid Reciprocal Rank Fusion (RRF) search scoped to a specific
    user and session. Dense vector candidates are fetched from Qdrant and
    lexical keyword ranks are calculated in memory.
    """
    query_embedding = get_embedding(query)
    q_client = qdrant_manager.client

    # Always scope results to this user's session
    must_conditions = [
        qdrant_models.FieldCondition(
            key="user_id",
            match=qdrant_models.MatchValue(value=user_id)
        ),
        qdrant_models.FieldCondition(
            key="session_id",
            match=qdrant_models.MatchValue(value=session_id)
        ),
    ]

    # Apply optional year/quarter filters
    if fiscal_year is not None:
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="fiscal_year",
                match=qdrant_models.MatchValue(value=int(fiscal_year))
            )
        )
    if quarter and quarter != "all" and quarter.strip() != "":
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="quarter",
                match=qdrant_models.MatchValue(value=quarter)
            )
        )

    # Optionally narrow to a specific chunking strategy
    if strategy != "all":
        must_conditions.append(
            qdrant_models.FieldCondition(
                key="strategy",
                match=qdrant_models.MatchValue(value=strategy)
            )
        )

    query_filter = qdrant_models.Filter(must=must_conditions)

    response = q_client.query_points(
        collection_name=_COLLECTION,
        query=query_embedding,
        query_filter=query_filter,
        limit=_CANDIDATES,
        with_payload=True
    )
    hits = response.points

    # Track semantic ranks
    semantic_ranks = {hit.id: idx + 1 for idx, hit in enumerate(hits)}

    # Calculate simple word-matching lexical scores for keyword ranks
    query_tokens = [w.lower() for w in query.split() if len(w) > 2]

    def get_keyword_score(text):
        if not query_tokens:
            return 0
        text_lower = text.lower()
        return sum(text_lower.count(token) for token in query_tokens)

    hits_with_keyword = [
        (hit, get_keyword_score(hit.payload.get("content", "")))
        for hit in hits
    ]

    hits_sorted_by_keyword = sorted(hits_with_keyword, key=lambda x: x[1], reverse=True)
    keyword_ranks = {
        item[0].id: idx + 1
        for idx, item in enumerate(hits_sorted_by_keyword)
        if item[1] > 0
    }

    # Reciprocal Rank Fusion (RRF)
    rrf_results = []
    for hit in hits:
        sem_rank = semantic_ranks[hit.id]
        key_rank = keyword_ranks.get(hit.id, 9999)

        rrf_score = (1.0 / (_RRF_K + sem_rank)) + (1.0 / (_RRF_K + key_rank) if key_rank != 9999 else 0.0)

        payload = hit.payload.copy()
        content = payload.pop("content", "")

        rrf_results.append({
            "id": hit.id,
            "content": content,
            "metadata": payload,
            "semanticRank": sem_rank,
            "keywordRank": key_rank if key_rank != 9999 else None,
            "rrfScore": rrf_score,
            "similarity": hit.score
        })

    rrf_results.sort(key=lambda x: x["rrfScore"], reverse=True)
    return rrf_results[:limit]


# ─── Ingestion Routes ─────────────────────────────────────────────────────────

@app.post("/api/ingest")
async def api_ingest(
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    POST /api/ingest
    Ingests raw text, chunks it with the selected strategy, embeds it,
    and upserts into Qdrant tagged with the current user and session.
    """
    try:
        body = await request.json()
        content = body.get("content")
        metadata = body.get("metadata", {})
        strategy = body.get("strategy", "fixed-size")
        chunk_size = body.get("chunkSize", settings.DEFAULT_CHUNK_SIZE)
        chunk_overlap = body.get("chunkOverlap", settings.DEFAULT_CHUNK_OVERLAP)
        semantic_threshold = body.get("semanticThreshold", settings.DEFAULT_SEMANTIC_THRESHOLD)
        ingest_all_strategies = body.get("ingestAllStrategies", False)
        configs = body.get("configs", {})
        fiscal_year = body.get("fiscalYear")
        quarter = body.get("quarter")

        # Convert values safely
        if fiscal_year is not None and str(fiscal_year).strip() != "":
            fiscal_year = int(fiscal_year)
        else:
            fiscal_year = None

        if quarter:
            quarter = str(quarter).strip()
            if quarter.lower() == "all" or quarter == "":
                quarter = None

        parsed_chunk_size = int(chunk_size)
        parsed_chunk_overlap = int(chunk_overlap)
        parsed_threshold = (
            float(semantic_threshold)
            if (semantic_threshold is not None and semantic_threshold != "")
            else None
        )

        strategies_to_run = (
            ["fixed-size", "recursive", "semantic", "page-based"]
            if ingest_all_strategies
            else [strategy]
        )

        total_chunks = 0
        q_client = qdrant_manager.client
        user_id = user_context.user_id
        session_id = user_context.session_id

        for strat in strategies_to_run:
            strat_config = configs.get(strat, {})
            strat_chunk_size = int(strat_config.get("chunkSize", parsed_chunk_size))
            strat_chunk_overlap = int(strat_config.get("chunkOverlap", parsed_chunk_overlap))

            strat_threshold = strat_config.get("semanticThreshold", parsed_threshold)
            if strat_threshold == "":
                strat_threshold = None
            else:
                strat_threshold = float(strat_threshold) if strat_threshold is not None else None

            chunks = chunk_document(content, {
                "strategy": strat,
                "chunk_size": strat_chunk_size,
                "chunk_overlap": strat_chunk_overlap,
                "semantic_threshold": strat_threshold,
                "base_metadata": {
                    "title": metadata.get("title", "Untitled Raw Text"),
                    "category": metadata.get("category", "General"),
                    "strategy": strat,
                    "dateAdded": metadata.get("dateAdded", ""),
                    "user_id": user_id,
                    "session_id": session_id,
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                }
            })

            print(f"Text Chunking complete: Split into {len(chunks)} chunks using '{strat}' (size={strat_chunk_size}).")

            if chunks:
                contents = [c["content"] for c in chunks]
                embeddings = get_embeddings(contents)

                points = []
                for i, chunk in enumerate(chunks):
                    points.append(
                        qdrant_models.PointStruct(
                            id=str(uuid.uuid4()),
                            vector=embeddings[i],
                            payload={
                                "content": chunk["content"],
                                **chunk["metadata"]
                            }
                        )
                    )

                q_client.upsert(collection_name=_COLLECTION, points=points)
                total_chunks += len(chunks)

        return {
            "success": True,
            "message": f"Successfully ingested document using {', '.join(strategies_to_run)}.",
            "chunksIngested": total_chunks
        }
    except Exception as e:
        print(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.post("/api/ingest-pdf")
async def api_ingest_pdf(
    file: UploadFile = File(...),
    title: str = Form("Uploaded PDF"),
    category: str = Form("General"),
    strategy: str = Form("fixed-size"),
    chunkSize: str = Form(str(settings.DEFAULT_CHUNK_SIZE)),
    chunkOverlap: str = Form(str(settings.DEFAULT_CHUNK_OVERLAP)),
    semanticThreshold: str = Form(None),
    ingestAllStrategies: str = Form("false"),
    configs: str = Form(None),
    fiscalYear: str = Form(None),
    quarter: str = Form(None),
    user_context: UserContext = Depends(get_current_user)
):
    """
    POST /api/ingest-pdf
    Accepts PDF upload, extracts text, chunks it, embeds it, and upserts to Qdrant
    scoped to the current user and session.
    """
    try:
        parsed_chunk_size = int(chunkSize)
        parsed_chunk_overlap = int(chunkOverlap)
        parsed_threshold = (
            float(semanticThreshold) if (semanticThreshold and semanticThreshold.strip()) else None
        )
        ingest_all = ingestAllStrategies.lower() == "true"
        parsed_configs = json.loads(configs) if (configs and configs.strip()) else {}

        print(f"Parsing uploaded PDF '{file.filename}'...")
        file_bytes = await file.read()

        # Parse PDF using layout-aware financial parser (extracts text and tables as Markdown)
        pages, auto_year, auto_quarter = parse_financial_pdf(file_bytes, file.filename)
        pages.sort(key=lambda p: p["number"])
        full_text = "\n\n".join([p["text"] for p in pages])

        # Use explicitly provided year/quarter or fallback to auto-detected ones
        final_year = None
        if fiscalYear and fiscalYear.strip() != "":
            try:
                final_year = int(fiscalYear)
            except ValueError:
                final_year = auto_year
        else:
            final_year = auto_year

        final_quarter = None
        if quarter and quarter.strip() != "":
            final_quarter = quarter.strip()
            if final_quarter.lower() == "all":
                final_quarter = None
        else:
            final_quarter = auto_quarter

        print(f"PDF parsed successfully. Total pages: {len(pages)}. Character count: {len(full_text)}.")

        strategies_to_run = (
            ["fixed-size", "recursive", "semantic", "page-based"]
            if ingest_all
            else [strategy]
        )

        total_chunks = 0
        q_client = qdrant_manager.client
        user_id = user_context.user_id
        session_id = user_context.session_id

        for strat in strategies_to_run:
            strat_config = parsed_configs.get(strat, {})
            strat_chunk_size = int(strat_config.get("chunkSize", parsed_chunk_size))
            strat_chunk_overlap = int(strat_config.get("chunkOverlap", parsed_chunk_overlap))

            strat_threshold = strat_config.get("semanticThreshold", parsed_threshold)
            if strat_threshold == "":
                strat_threshold = None
            else:
                strat_threshold = float(strat_threshold) if strat_threshold is not None else None

            chunks = chunk_document(full_text, {
                "strategy": strat,
                "chunk_size": strat_chunk_size,
                "chunk_overlap": strat_chunk_overlap,
                "semantic_threshold": strat_threshold,
                "pages": pages,
                "base_metadata": {
                    "title": title,
                    "category": category,
                    "source": file.filename,
                    "strategy": strat,
                    "dateAdded": "",
                    "user_id": user_id,
                    "session_id": session_id,
                    "fiscal_year": final_year,
                    "quarter": final_quarter,
                }
            })

            print(f"PDF Chunking complete: Split into {len(chunks)} chunks using '{strat}' (size={strat_chunk_size}).")

            if chunks:
                contents = [c["content"] for c in chunks]
                embeddings = get_embeddings(contents)

                points = []
                for i, chunk in enumerate(chunks):
                    points.append(
                        qdrant_models.PointStruct(
                            id=str(uuid.uuid4()),
                            vector=embeddings[i],
                            payload={
                                "content": chunk["content"],
                                **chunk["metadata"]
                            }
                        )
                    )

                q_client.upsert(collection_name=_COLLECTION, points=points)
                total_chunks += len(chunks)

        return {
            "success": True,
            "message": f"Successfully ingested PDF document using {', '.join(strategies_to_run)}.",
            "chunksIngested": total_chunks,
            "pagesCount": len(pages),
            "detectedYear": final_year,
            "detectedQuarter": final_quarter
        }
    except Exception as e:
        print(f"PDF Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF Ingestion failed: {str(e)}")


# ─── Search / Compare Routes ──────────────────────────────────────────────────

@app.post("/api/search")
async def api_search(
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    POST /api/search
    Hybrid RRF search scoped to the authenticated user's current session.
    """
    try:
        body = await request.json()
        query = body.get("query")
        strategy = body.get("strategy", "all")
        fiscal_year = body.get("fiscalYear")
        quarter = body.get("quarter")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        results = run_hybrid_search(
            query,
            user_id=user_context.user_id,
            session_id=user_context.session_id,
            strategy=strategy,
            limit=settings.SEARCH_RESULT_LIMIT,
            fiscal_year=fiscal_year,
            quarter=quarter
        )

        return {"success": True, "query": query, "results": results}
    except Exception as e:
        print(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/api/compare")
async def api_compare(
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    POST /api/compare
    Runs RRF search against all 4 strategies, scoped to the current user and session.
    """
    try:
        body = await request.json()
        query = body.get("query")
        fiscal_year = body.get("fiscalYear")
        quarter = body.get("quarter")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        strategies = ["fixed-size", "recursive", "semantic", "page-based"]
        comparisons_list = []

        for strat in strategies:
            results = run_hybrid_search(
                query,
                user_id=user_context.user_id,
                session_id=user_context.session_id,
                strategy=strat,
                limit=settings.COMPARE_RESULT_LIMIT,
                fiscal_year=fiscal_year,
                quarter=quarter
            )
            comparisons_list.append({"strategy": strat, "results": results})

        return {"success": True, "query": query, "comparisons": comparisons_list}
    except Exception as e:
        print(f"Compare search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


# ─── Chat Route ───────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def api_chat(
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    POST /api/chat
    Retrieves context chunks for the current session and streams the Gemini response via SSE.
    """
    try:
        body = await request.json()
        question = body.get("question")
        history = body.get("history", [])
        strategy = body.get("strategy", "all")
        fiscal_year = body.get("fiscalYear")
        quarter = body.get("quarter")

        if not question or not isinstance(question, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'question' in request body.")

        results = run_hybrid_search(
            question,
            user_id=user_context.user_id,
            session_id=user_context.session_id,
            strategy=strategy,
            limit=settings.SEARCH_RESULT_LIMIT,
            fiscal_year=fiscal_year,
            quarter=quarter
        )

        context_blocks = [
            f"[Document Block {i + 1}]:\n{res['content']}"
            for i, res in enumerate(results)
        ]
        context = "\n\n".join(context_blocks)
        print(f"Qdrant Hybrid Search retrieved {len(context_blocks)} context chunks for chat.")

        def event_generator():
            try:
                response_stream = get_chat_stream(question, context, history)
                for chunk in response_stream:
                    if chunk.text:
                        yield f"data: {json.dumps({'text': chunk.text})}\n\n"
            except Exception as stream_err:
                print(f"Chat streaming error: {stream_err}")
                yield f"data: {json.dumps({'error': str(stream_err)})}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except Exception as e:
        print(f"Chat routing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


# Mount frontend static files directory dynamically using absolute paths
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
