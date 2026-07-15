import os
import io
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

from src.config import settings
from src.db.db_client import init_db, get_db_connection, release_db_connection
from src.clients.gemini_client import get_chat_stream
from src.clients.embedding_client import get_embedding, get_embeddings
from src.chunker_manager import chunk_document

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connection pool on startup
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

# Note: API routes MUST be registered before mounting StaticFiles at "/" to prevent path collisions.

@app.post("/api/ingest")
async def api_ingest(request: Request):
    """
    POST /api/ingest
    Ingests raw text, chunks it, generates embeddings, and saves to PostgreSQL.
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
        conn = get_db_connection()
        
        try:
            with conn.cursor() as cur:
                for strat in strategies_to_run:
                    # Apply strategy-specific parameter overrides
                    strat_config = configs.get(strat, {}) if 'configs' in locals() else {}
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

                    print(f"PDF Chunking complete: Split into {len(chunks)} chunks using '{strat}' (size={strat_chunk_size}).")
                    
                    if chunks:
                        # Batch generate embeddings
                        contents = [c["content"] for c in chunks]
                        embeddings = get_embeddings(contents)

                        for i, chunk in enumerate(chunks):
                            embedding = embeddings[i]
                            pg_vector_str = f"[{','.join(map(str, embedding))}]"
                            
                            cur.execute(
                                """
                                INSERT INTO analyzer_chunks (content, embedding, metadata)
                                VALUES (%s, %s, %s)
                                """,
                                (chunk["content"], pg_vector_str, json.dumps(chunk["metadata"]))
                            )
                        total_chunks += len(chunks)
                conn.commit()
        finally:
            release_db_connection(conn)

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
    Accepts PDF upload, parses text page-by-page, chunks it, generates embeddings, and saves to database.
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
        conn = get_db_connection()
        
        try:
            with conn.cursor() as cur:
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

                        for i, chunk in enumerate(chunks):
                            embedding = embeddings[i]
                            pg_vector_str = f"[{','.join(map(str, embedding))}]"
                            
                            cur.execute(
                                """
                                INSERT INTO analyzer_chunks (content, embedding, metadata)
                                VALUES (%s, %s, %s)
                                """,
                                (chunk["content"], pg_vector_str, json.dumps(chunk["metadata"]))
                            )
                        total_chunks += len(chunks)
                conn.commit()
        finally:
            release_db_connection(conn)

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
    Run Hybrid Reciprocal Rank Fusion (RRF) search on the database.
    Can be filtered by a specific strategy index.
    """
    try:
        body = await request.json()
        query = body.get("query")
        strategy = body.get("strategy", "all")

        if not query or not isinstance(query, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'query' in request body.")

        # 1. Generate query embedding
        query_embedding = get_embedding(query)
        pg_vector_str = f"[{','.join(map(str, query_embedding))}]"

        # 2. Run Hybrid Search with RRF in PostgreSQL
        # We pass query arguments using standard psycopg2 placeholder lists
        rrf_query = """
          WITH semantic_search AS (
              SELECT id, ROW_NUMBER() OVER (ORDER BY min_distance) as rank
              FROM (
                  SELECT min(id) as id, min(embedding <=> %s) as min_distance
                  FROM analyzer_chunks
                  WHERE (%s = 'all' OR metadata->>'strategy' = %s)
                  GROUP BY content
              ) sub
              ORDER BY min_distance
              LIMIT 50
          ),
          keyword_search AS (
              SELECT id, ROW_NUMBER() OVER (ORDER BY max_rank DESC) as rank
              FROM (
                  SELECT min(id) as id, max(ts_rank(fts_tokens, websearch_to_tsquery('english', %s))) as max_rank
                  FROM analyzer_chunks
                  WHERE fts_tokens @@ websearch_to_tsquery('english', %s)
                    AND (%s = 'all' OR metadata->>'strategy' = %s)
                  GROUP BY content
              ) sub
              ORDER BY max_rank DESC
              LIMIT 50
          )
          SELECT 
              c.id,
              c.content,
              c.metadata,
              s.rank as semantic_rank,
              k.rank as keyword_rank,
              COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0) AS rrf_score
          FROM analyzer_chunks c
          LEFT JOIN semantic_search s ON c.id = s.id
          LEFT JOIN keyword_search k ON c.id = k.id
          WHERE s.id IS NOT NULL OR k.id IS NOT NULL
          ORDER BY rrf_score DESC
          LIMIT 5;
        """

        params = (
            pg_vector_str, strategy, strategy,
            query, query, strategy, strategy
        )

        results = []
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(rrf_query, params)
                rows = cur.fetchall()
                for row in rows:
                    results.append({
                        "id": row[0],
                        "content": row[1],
                        "metadata": row[2],
                        "semanticRank": int(row[3]) if row[3] else None,
                        "keywordRank": int(row[4]) if row[4] else None,
                        "rrfScore": float(row[5])
                    })
        finally:
            release_db_connection(conn)

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

        query_embedding = get_embedding(query)
        pg_vector_str = f"[{','.join(map(str, query_embedding))}]"

        strategies = ["fixed-size", "recursive", "semantic", "page-based"]
        comparisons = {}

        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                for strat in strategies:
                    # Run search specifically filtered by this strategy
                    compare_query = """
                      WITH semantic_search AS (
                          SELECT id, ROW_NUMBER() OVER (ORDER BY min_distance) as rank
                          FROM (
                              SELECT min(id) as id, min(embedding <=> %s) as min_distance
                              FROM analyzer_chunks
                              WHERE metadata->>'strategy' = %s
                              GROUP BY content
                          ) sub
                          ORDER BY min_distance
                          LIMIT 50
                      ),
                      keyword_search AS (
                          SELECT id, ROW_NUMBER() OVER (ORDER BY max_rank DESC) as rank
                          FROM (
                              SELECT min(id) as id, max(ts_rank(fts_tokens, websearch_to_tsquery('english', %s))) as max_rank
                              FROM analyzer_chunks
                              WHERE fts_tokens @@ websearch_to_tsquery('english', %s)
                                AND metadata->>'strategy' = %s
                              GROUP BY content
                          ) sub
                          ORDER BY max_rank DESC
                          LIMIT 50
                      )
                      SELECT 
                          c.id,
                          c.content,
                          c.metadata,
                          s.rank as semantic_rank,
                          k.rank as keyword_rank,
                          COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0) AS rrf_score,
                          (1.0 - (c.embedding <=> %s)) AS similarity
                      FROM analyzer_chunks c
                      LEFT JOIN semantic_search s ON c.id = s.id
                      LEFT JOIN keyword_search k ON c.id = k.id
                      WHERE s.id IS NOT NULL OR k.id IS NOT NULL
                      ORDER BY rrf_score DESC
                      LIMIT 3;
                    """
                    
                    params = (
                        pg_vector_str, strat,
                        query, query, strat,
                        pg_vector_str
                    )
                    
                    cur.execute(compare_query, params)
                    rows = cur.fetchall()
                    
                    strat_results = []
                    for row in rows:
                        strat_results.append({
                            "id": row[0],
                            "content": row[1],
                            "metadata": row[2],
                            "semanticRank": int(row[3]) if row[3] else None,
                            "keywordRank": int(row[4]) if row[4] else None,
                            "rrfScore": float(row[5]),
                            "similarity": float(row[6]) if row[6] is not None else None
                        })
                    comparisons[strat] = strat_results
        finally:
            release_db_connection(conn)

        # Format comparisons as a list of column objects for frontend comparisons.forEach
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

        # 1. Generate query embedding
        query_embedding = get_embedding(question)
        pg_vector_str = f"[{','.join(map(str, query_embedding))}]"

        # 2. Retrieve top 5 context chunks from database
        rrf_query = """
          WITH semantic_search AS (
              SELECT id, ROW_NUMBER() OVER (ORDER BY min_distance) as rank
              FROM (
                  SELECT min(id) as id, min(embedding <=> %s) as min_distance
                  FROM analyzer_chunks
                  WHERE (%s = 'all' OR metadata->>'strategy' = %s)
                  GROUP BY content
              ) sub
              ORDER BY min_distance
              LIMIT 50
          ),
          keyword_search AS (
              SELECT id, ROW_NUMBER() OVER (ORDER BY max_rank DESC) as rank
              FROM (
                  SELECT min(id) as id, max(ts_rank(fts_tokens, websearch_to_tsquery('english', %s))) as max_rank
                  FROM analyzer_chunks
                  WHERE fts_tokens @@ websearch_to_tsquery('english', %s)
                    AND (%s = 'all' OR metadata->>'strategy' = %s)
                  GROUP BY content
              ) sub
              ORDER BY max_rank DESC
              LIMIT 50
          )
          SELECT c.content
          FROM analyzer_chunks c
          LEFT JOIN semantic_search s ON c.id = s.id
          LEFT JOIN keyword_search k ON c.id = k.id
          WHERE s.id IS NOT NULL OR k.id IS NOT NULL
          ORDER BY COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0) DESC
          LIMIT 5;
        """

        params = (
            pg_vector_str, strategy, strategy,
            question, question, strategy, strategy
        )

        context_blocks = []
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(rrf_query, params)
                rows = cur.fetchall()
                for i, row in enumerate(rows):
                    context_blocks.append(f"[Document Block {i + 1}]:\n{row[0]}")
        finally:
            release_db_connection(conn)

        context = "\n\n".join(context_blocks)
        print(f"RRF Hybrid Search retrieved {len(context_blocks)} context chunks for chat.")

        # 3. Yield streaming content formatted as Server-Sent Events
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
