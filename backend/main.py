import os
import io
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pypdf import PdfReader

from src.config import settings
from src.db.db_client import init_db, get_db_connection, release_db_connection
from src.db.qdrant_client import init_qdrant, get_qdrant_client
from qdrant_client.http import models as qdrant_models
from src.clients.gemini_client import get_chat_stream
from src.clients.embedding_client import get_embedding, get_embeddings
from src.chunker_manager import chunk_document

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize PostgreSQL connection pool and Qdrant vector store on startup
    init_db()
    init_qdrant()
    yield

app = FastAPI(lifespan=lifespan)

# Note: API routes MUST be registered before mounting StaticFiles at "/" to prevent path collisions.

def run_hybrid_search(query: str, strategy: str = "all", limit: int = 5) -> list[dict]:
    """
    Simulates a hybrid Reciprocal Rank Fusion (RRF) search on Qdrant
    by performing a dense vector search and calculating lexical rank counts in memory.
    """
    query_embedding = get_embedding(query)
    q_client = get_qdrant_client()
    
    query_filter = None
    if strategy != "all":
        query_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="strategy",
                    match=qdrant_models.MatchValue(value=strategy)
                )
            ]
        )
        
    response = q_client.query_points(
        collection_name="analyzer_chunks",
        query=query_embedding,
        query_filter=query_filter,
        limit=50,
        with_payload=True
    )
    hits = response.points
    
    # Track semantic ranks
    semantic_ranks = {hit.id: idx + 1 for idx, hit in enumerate(hits)}
    
    # Calculate simple word matching lexical scores for keyword ranks
    query_tokens = [w.lower() for w in query.split() if len(w) > 2]
    def get_keyword_score(text):
        if not query_tokens:
            return 0
        text_lower = text.lower()
        score = 0
        for token in query_tokens:
            score += text_lower.count(token)
        return score

    hits_with_keyword = []
    for hit in hits:
        content = hit.payload.get("content", "")
        score = get_keyword_score(content)
        hits_with_keyword.append((hit, score))

    # Sort candidates by lexical matches
    hits_sorted_by_keyword = sorted(hits_with_keyword, key=lambda x: x[1], reverse=True)
    keyword_ranks = {item[0].id: idx + 1 for idx, item in enumerate(hits_sorted_by_keyword) if item[1] > 0}

    # Perform Reciprocal Rank Fusion (RRF)
    rrf_results = []
    for hit in hits:
        sem_rank = semantic_ranks[hit.id]
        key_rank = keyword_ranks.get(hit.id, 9999)  # Assign default rank if no match
        
        rrf_score = (1.0 / (60 + sem_rank)) + (1.0 / (60 + key_rank) if key_rank != 9999 else 0.0)
        
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

    # Sort final records by RRF score descending
    rrf_results.sort(key=lambda x: x["rrfScore"], reverse=True)
    return rrf_results[:limit]


@app.post("/api/ingest")
async def api_ingest(request: Request):
    """
    POST /api/ingest
    Ingests raw text, chunks it, generates embeddings, and saves to Qdrant.
    Supports single strategy or all strategies simultaneously.
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

        # Cast parameters
        parsed_chunk_size = int(chunk_size)
        parsed_chunk_overlap = int(chunk_overlap)
        parsed_threshold = float(semantic_threshold) if (semantic_threshold is not None and semantic_threshold != "") else None

        strategies_to_run = (
            ["fixed-size", "recursive", "semantic", "page-based"]
            if ingest_all_strategies
            else [strategy]
        )

        total_chunks = 0
        q_client = get_qdrant_client()
        
        for strat in strategies_to_run:
            # Apply strategy-specific parameter overrides
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
                    "dateAdded": metadata.get("dateAdded", "")
                }
            })

            print(f"Text Chunking complete: Split into {len(chunks)} chunks using '{strat}' (size={strat_chunk_size}).")
            
            if chunks:
                # Batch generate embeddings
                contents = [c["content"] for c in chunks]
                embeddings = get_embeddings(contents)

                points = []
                for i, chunk in enumerate(chunks):
                    embedding = embeddings[i]
                    point_id = str(uuid.uuid4())
                    
                    payload = {
                        "content": chunk["content"],
                        **chunk["metadata"]
                    }
                    
                    points.append(
                        qdrant_models.PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload=payload
                        )
                    )
                
                # Batch upsert points to Qdrant vector store
                q_client.upsert(
                    collection_name="analyzer_chunks",
                    points=points
                )
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
    configs: str = Form(None)
):
    """
    POST /api/ingest-pdf
    Accepts PDF upload, parses text page-by-page, chunks it, generates embeddings, and saves to Qdrant.
    """
    try:
        # Cast types
        parsed_chunk_size = int(chunkSize)
        parsed_chunk_overlap = int(chunkOverlap)
        parsed_threshold = float(semanticThreshold) if (semanticThreshold and semanticThreshold.strip()) else None
        ingest_all = ingestAllStrategies.lower() == "true"
        parsed_configs = json.loads(configs) if (configs and configs.strip()) else {}

        print(f"Parsing uploaded PDF '{file.filename}'...")
        file_bytes = await file.read()
        
        # Load PDF using PyPDF Reader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({
                "number": i + 1,
                "text": text
            })
            
        # Sort pages numerically just in case
        pages.sort(key=lambda p: p["number"])
        full_text = "\n\n".join([p["text"] for p in pages])
        
        print(f"PDF parsed successfully. Total pages: {len(pages)}. Character count: {len(full_text)}.")

        strategies_to_run = (
            ["fixed-size", "recursive", "semantic", "page-based"]
            if ingest_all
            else [strategy]
        )

        total_chunks = 0
        q_client = get_qdrant_client()
        
        for strat in strategies_to_run:
            # Apply strategy-specific parameter overrides
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
                    "dateAdded": ""
                }
            })

            print(f"PDF Chunking complete: Split into {len(chunks)} chunks using '{strat}' (size={strat_chunk_size}).")
            
            if chunks:
                # Batch generate embeddings
                contents = [c["content"] for c in chunks]
                embeddings = get_embeddings(contents)

                points = []
                for i, chunk in enumerate(chunks):
                    embedding = embeddings[i]
                    point_id = str(uuid.uuid4())
                    
                    payload = {
                        "content": chunk["content"],
                        **chunk["metadata"]
                    }
                    
                    points.append(
                        qdrant_models.PointStruct(
                            id=point_id,
                            vector=embedding,
                            payload=payload
                        )
                    )
                
                # Upsert to Qdrant
                q_client.upsert(
                    collection_name="analyzer_chunks",
                    points=points
                )
                total_chunks += len(chunks)

        return {
            "success": True,
            "message": f"Successfully ingested PDF document using {', '.join(strategies_to_run)}.",
            "chunksIngested": total_chunks,
            "pagesCount": len(pages)
        }
    except Exception as e:
        print(f"PDF Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF Ingestion failed: {str(e)}")


@app.post("/api/search")
async def api_search(request: Request):
    """
    POST /api/search
    Run Hybrid search simulation with RRF on Qdrant.
    Can be filtered by a specific strategy index.
    """
    try:
        body = await request.json()
        query = body.get("query")
        strategy = body.get("strategy", "all")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        results = run_hybrid_search(query, strategy=strategy, limit=5)

        return {
            "success": True,
            "query": query,
            "results": results
        }
    except Exception as e:
        print(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/api/compare")
async def api_compare(request: Request):
    """
    POST /api/compare
    Runs search query in parallel against all 4 strategies, returning lists of matched chunks.
    """
    try:
        body = await request.json()
        query = body.get("query")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        strategies = ["fixed-size", "recursive", "semantic", "page-based"]
        comparisons = {}

        for strat in strategies:
            # Query Qdrant for this specific strategy
            comparisons[strat] = run_hybrid_search(query, strategy=strat, limit=3)

        # Format comparisons as a list of column objects for frontend
        comparisons_list = []
        for strat_name, strat_results in comparisons.items():
            comparisons_list.append({
                "strategy": strat_name,
                "results": strat_results
            })

        return {
            "success": True,
            "query": query,
            "comparisons": comparisons_list
        }
    except Exception as e:
        print(f"Compare search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@app.post("/api/chat")
async def api_chat(request: Request):
    """
    POST /api/chat
    Performs RRF search for the target strategy and streams chat response using SSE.
    """
    try:
        body = await request.json()
        question = body.get("question")
        history = body.get("history", [])
        strategy = body.get("strategy", "all")

        if not question or not isinstance(question, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'question' in request body.")

        # 1. Retrieve top 5 context chunks from Qdrant using RRF
        results = run_hybrid_search(question, strategy=strategy, limit=5)
        
        context_blocks = []
        for i, res in enumerate(results):
            context_blocks.append(f"[Document Block {i + 1}]:\n{res['content']}")

        context = "\n\n".join(context_blocks)
        print(f"Qdrant Hybrid Search retrieved {len(context_blocks)} context chunks for chat.")

        # 2. Yield streaming content formatted as Server-Sent Events
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
