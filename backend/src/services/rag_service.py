from src.config import settings
from src.db.qdrant_client import qdrant_manager
from src.db.persistence_store import get_thread_documents
from src.clients.embedding_client import get_embedding
from qdrant_client.http import models as qdrant_models

# Alias frequently-used settings for readability
_COLLECTION = settings.QDRANT_COLLECTION_NAME
_RRF_K = settings.QDRANT_RRF_K
_CANDIDATES = settings.QDRANT_SEMANTIC_CANDIDATES


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
