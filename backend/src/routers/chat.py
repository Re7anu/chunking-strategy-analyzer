import json

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse

from src.config import settings
from src.auth.dependencies import get_current_user
from src.auth.models import UserContext
from src.clients.gemini_client import get_chat_stream, generate_conversation_title
from src.db.persistence_store import (
    get_user_threads,
    create_chat_thread,
    delete_chat_thread,
    rename_chat_thread,
    get_thread_messages,
    save_chat_message,
    get_user_documents,
    get_thread_documents,
    attach_document_to_thread,
    detach_document_from_thread,
)
from src.services.rag_service import run_hybrid_search

router = APIRouter(tags=["chat"])


# ─── Chat Threads ─────────────────────────────────────────────────────────────

@router.get("/api/threads")
async def api_get_threads(user_context: UserContext = Depends(get_current_user)):
    """
    Returns all chat threads for the current user.
    """
    try:
        threads = get_user_threads(user_context.user_id)
        return {"success": True, "threads": threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/threads")
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


@router.delete("/api/threads/{thread_id}")
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


@router.patch("/api/threads/{thread_id}")
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


@router.get("/api/threads/{thread_id}/messages")
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


# ─── Documents Library ────────────────────────────────────────────────────────

@router.get("/api/documents")
async def api_get_documents(user_context: UserContext = Depends(get_current_user)):
    """
    Returns all uploaded documents for the user.
    """
    try:
        documents = get_user_documents(user_context.user_id)
        return {"success": True, "documents": documents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/threads/{thread_id}/documents")
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


@router.post("/api/threads/{thread_id}/documents")
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


@router.delete("/api/threads/{thread_id}/documents/{document_id}")
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


# ─── Streaming Chat ───────────────────────────────────────────────────────────

@router.post("/api/chat")
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
        leak_keywords = [
            "system prompt", "system instruction", "system instructions",
            "repeat instructions", "reveal instructions", "ignore previous rules",
            "ignore rules", "output system prompt", "return your system prompt", "jailbreak"
        ]
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
