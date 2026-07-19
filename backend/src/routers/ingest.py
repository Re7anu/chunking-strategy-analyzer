import uuid
import json

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Depends
from qdrant_client.http import models as qdrant_models

from src.config import settings
from src.auth.dependencies import get_current_user
from src.auth.models import UserContext
from src.db.qdrant_client import qdrant_manager
from src.clients.embedding_client import get_embeddings
from src.chunker_manager import chunk_document
from src.utils.financial_parser import parse_financial_pdf
from src.db.persistence_store import register_user_document, attach_document_to_thread

router = APIRouter(tags=["ingest"])


# ─── Raw Text Ingestion ────────────────────────────────────────────────────────

@router.post("/api/ingest")
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

                q_client.upsert(collection_name=settings.QDRANT_COLLECTION_NAME, points=points)
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


# ─── PDF Ingestion ─────────────────────────────────────────────────────────────

@router.post("/api/ingest-pdf")
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

                q_client.upsert(collection_name=settings.QDRANT_COLLECTION_NAME, points=points)
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
