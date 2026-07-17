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
from src.clients.gemini_client import get_chat_stream, generate_conversation_title
from src.clients.embedding_client import get_embedding, get_embeddings
from src.chunker_manager import chunk_document
from src.utils.financial_parser import parse_financial_pdf
from src.db.persistence_store import (
    get_user_threads,
    create_chat_thread,
    delete_chat_thread,
    rename_chat_thread,
    get_thread_messages,
    save_chat_message,
    get_user_documents,
    register_user_document,
    get_thread_documents,
    attach_document_to_thread,
    detach_document_from_thread,
)

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
    quarter: str = None,
    thread_id: str = None
) -> list[dict]:
    """
    Performs hybrid Reciprocal Rank Fusion (RRF) search scoped to a specific
    user and session. Dense vector candidates are fetched from Qdrant and
    lexical keyword ranks are calculated in memory.
    """
    query_embedding = get_embedding(query)
    q_client = qdrant_manager.client

    # Always scope results to this user
    must_conditions = [
        qdrant_models.FieldCondition(
            key="user_id",
            match=qdrant_models.MatchValue(value=user_id)
        )
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

    # Apply thread document scoping (filter strictly to documents attached to the thread)
    if thread_id:
        attached_docs = get_thread_documents(thread_id)
        doc_ids = [d["id"] for d in attached_docs]
        if doc_ids:
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="document_id",
                    match=qdrant_models.MatchAny(any=doc_ids)
                )
            )
        else:
            # Force 0 results if no documents are attached to the thread
            must_conditions.append(
                qdrant_models.FieldCondition(
                    key="document_id",
                    match=qdrant_models.MatchValue(value="none-attached-placeholder-uuid")
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
    seen_contents = set()
    for hit in hits:
        payload = hit.payload.copy() if hit.payload else {}
        content = payload.pop("content", "")

        # De-duplicate identical text blocks (arising from multi-strategy ingestion or duplicate file uploads)
        norm_content = " ".join(content.lower().split())
        if norm_content in seen_contents:
            continue
        seen_contents.add(norm_content)

        sem_rank = semantic_ranks[hit.id]
        key_rank = keyword_ranks.get(hit.id, 9999)

        rrf_score = (1.0 / (_RRF_K + sem_rank)) + (1.0 / (_RRF_K + key_rank) if key_rank != 9999 else 0.0)

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
        thread_id = body.get("threadId")

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

        user_id = user_context.user_id
        session_id = user_context.session_id

        # Register raw text as a virtual document in the user's library
        title = metadata.get("title", "Untitled Raw Text").strip()
        filename = f"{title}.txt"
        
        doc_record = register_user_document(
            user_id=user_id,
            filename=filename,
            category=metadata.get("category", "General"),
            pages_count=1,
            chunks_count=0
        )
        doc_id = doc_record["id"]

        total_chunks = 0
        q_client = qdrant_manager.client

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
                    "title": title,
                    "category": metadata.get("category", "General"),
                    "strategy": strat,
                    "dateAdded": metadata.get("dateAdded", ""),
                    "user_id": user_id,
                    "session_id": session_id,
                    "fiscal_year": fiscal_year,
                    "quarter": quarter,
                    "document_id": doc_id,
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

        # Update final chunks count
        register_user_document(
            user_id=user_id,
            filename=filename,
            category=metadata.get("category", "General"),
            pages_count=1,
            chunks_count=total_chunks
        )

        # Auto-attach to chat thread if active
        if thread_id and thread_id.strip() != "":
            attach_document_to_thread(thread_id, doc_id)

        return {
            "success": True,
            "message": f"Successfully ingested document using {', '.join(strategies_to_run)}.",
            "chunksIngested": total_chunks,
            "documentId": doc_id,
            "filename": filename
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
    threadId: str = Form(None),
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

        user_id = user_context.user_id
        session_id = user_context.session_id

        # Register document metadata in database
        doc_record = register_user_document(
            user_id=user_id,
            filename=file.filename,
            category=category,
            pages_count=len(pages),
            chunks_count=0
        )
        doc_id = doc_record["id"]

        total_chunks = 0
        q_client = qdrant_manager.client

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
                    "document_id": doc_id,
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

        # Update final chunks count
        register_user_document(
            user_id=user_id,
            filename=file.filename,
            category=category,
            pages_count=len(pages),
            chunks_count=total_chunks
        )

        # Auto-attach to chat thread if active
        if threadId and threadId.strip() != "":
            attach_document_to_thread(threadId, doc_id)

        return {
            "success": True,
            "message": f"Successfully ingested PDF document using {', '.join(strategies_to_run)}.",
            "chunksIngested": total_chunks,
            "pagesCount": len(pages),
            "detectedYear": final_year,
            "detectedQuarter": final_quarter,
            "documentId": doc_id,
            "filename": file.filename
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

        threadId = body.get("threadId")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        results = run_hybrid_search(
            query,
            user_id=user_context.user_id,
            session_id=user_context.session_id,
            strategy=strategy,
            limit=settings.SEARCH_RESULT_LIMIT,
            fiscal_year=fiscal_year,
            quarter=quarter,
            thread_id=threadId
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
        threadId = body.get("threadId")

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
                quarter=quarter,
                thread_id=threadId
            )
            comparisons_list.append({"strategy": strat, "results": results})

        return {"success": True, "query": query, "comparisons": comparisons_list}
    except Exception as e:
        print(f"Compare search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


# ─── Chat Threads API ─────────────────────────────────────────────────────────

@app.get("/api/threads")
async def api_get_threads(user_context: UserContext = Depends(get_current_user)):
    """
    Returns all chat threads for the current user.
    """
    try:
        threads = get_user_threads(user_context.user_id)
        return {"success": True, "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/threads")
async def api_create_thread(
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Creates a new chat thread.
    """
    try:
        body = await request.json()
        title = body.get("title", "New Chat")
        thread = create_chat_thread(user_context.user_id, title)
        return {"success": True, "thread": thread}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/threads/{thread_id}")
async def api_delete_thread(
    thread_id: str,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Deletes a specific chat thread.
    """
    try:
        success = delete_chat_thread(user_context.user_id, thread_id)
        if not success:
            raise HTTPException(status_code=404, detail="Thread not found or unauthorized.")
        return {"success": True, "message": "Thread deleted successfully."}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/threads/{thread_id}")
async def api_rename_thread(
    thread_id: str,
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Renames a specific chat thread.
    """
    try:
        body = await request.json()
        title = body.get("title")
        if not title or not title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        success = rename_chat_thread(user_context.user_id, thread_id, title.strip())
        if not success:
            raise HTTPException(status_code=404, detail="Thread not found or unauthorized.")
        return {"success": True, "message": "Thread renamed successfully."}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/threads/{thread_id}/messages")
async def api_get_messages(
    thread_id: str,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Returns message history for a thread.
    """
    try:
        messages = get_thread_messages(thread_id)
        return {"success": True, "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Documents Library API ────────────────────────────────────────────────────

@app.get("/api/documents")
async def api_get_documents(user_context: UserContext = Depends(get_current_user)):
    """
    Returns all uploaded documents for the user.
    """
    try:
        documents = get_user_documents(user_context.user_id)
        return {"success": True, "documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/threads/{thread_id}/documents")
async def api_get_thread_documents(
    thread_id: str,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Returns all documents attached to a thread.
    """
    try:
        documents = get_thread_documents(thread_id)
        return {"success": True, "documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/threads/{thread_id}/documents")
async def api_attach_document(
    thread_id: str,
    request: Request,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Attaches a document to a thread.
    """
    try:
        body = await request.json()
        document_id = body.get("documentId")
        if not document_id:
            raise HTTPException(status_code=400, detail="Missing documentId.")
        attach_document_to_thread(thread_id, document_id)
        return {"success": True, "message": "Document attached to thread."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/threads/{thread_id}/documents/{document_id}")
async def api_detach_document(
    thread_id: str,
    document_id: str,
    user_context: UserContext = Depends(get_current_user)
):
    """
    Detaches a document from a thread.
    """
    try:
        success = detach_document_from_thread(thread_id, document_id)
        if not success:
            raise HTTPException(status_code=404, detail="Attachment not found.")
        return {"success": True, "message": "Document detached from thread."}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


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
        threadId = body.get("threadId")

        if not question or not isinstance(question, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'question' in request body.")

        # Programmatic Guardrail: Intercept prompts asking to reveal the system prompt/instructions
        q_lower = question.lower().strip()
        leak_keywords = ["system prompt", "system instruction", "system instructions", "repeat instructions", "reveal instructions", "ignore previous rules", "ignore rules", "output system prompt", "return your system prompt", "jailbreak"]
        is_leak_attempt = False
        
        # Check direct phrases
        if any(keyword in q_lower for keyword in leak_keywords):
            is_leak_attempt = True
            
        # Check combination of query verbs
        if "instruction" in q_lower or "prompt" in q_lower or "rules" in q_lower:
            if any(verb in q_lower for verb in ["repeat", "show", "what is", "reveal", "print", "get", "return", "output", "describe", "ignore"]):
                is_leak_attempt = True

        if is_leak_attempt:
            def leak_refusal_generator():
                refusal = "I am sorry, but I cannot reveal my system instructions or configuration prompt as they are confidential."
                yield f"data: {json.dumps({'text': refusal})}\n\n"
                if threadId and threadId.strip() != "":
                    save_chat_message(threadId, "user", question)
                    save_chat_message(threadId, "model", refusal)
                yield "data: [DONE]\n\n"
            return StreamingResponse(leak_refusal_generator(), media_type="text/event-stream")

        results = run_hybrid_search(
            question,
            user_id=user_context.user_id,
            session_id=user_context.session_id,
            strategy=strategy,
            limit=settings.SEARCH_RESULT_LIMIT,
            fiscal_year=fiscal_year,
            quarter=quarter,
            thread_id=threadId
        )

        context_blocks = [
            f"[Document Block {i + 1}]:\n{res['content']}"
            for i, res in enumerate(results)
        ]
        context = "\n\n".join(context_blocks)
        print(f"Qdrant Hybrid Search retrieved {len(context_blocks)} context chunks for chat.")

        def event_generator():
            accumulated = ""
            try:
                response_stream = get_chat_stream(question, context, history)
                for chunk in response_stream:
                    if chunk.text:
                        accumulated += chunk.text
                        yield f"data: {json.dumps({'text': chunk.text})}\n\n"
                
                # Persist the chat interaction if we have a valid threadId
                if threadId and threadId.strip() != "":
                    save_chat_message(threadId, "user", question)
                    save_chat_message(threadId, "model", accumulated)

                    # If this is the first query in the thread, automatically rename it using Gemini
                    if not history or len(history) == 0:
                        new_title = generate_conversation_title(question)
                        rename_chat_thread(user_context.user_id, threadId, new_title)
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
