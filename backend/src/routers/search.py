from fastapi import APIRouter, Request, HTTPException, Depends

from src.config import settings
from src.auth.dependencies import get_current_user
from src.auth.models import UserContext
from src.services.rag_service import run_hybrid_search

router = APIRouter(tags=["search"])


# ─── Hybrid RRF Search ────────────────────────────────────────────────────────

@router.post("/api/search")
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


# ─── Strategy Comparison ──────────────────────────────────────────────────────

@router.post("/api/compare")
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
