
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from app.services.knowledge_store import ensure_knowledge_collection
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "blessing_knowledge"

VECTOR_CANDIDATES = 10
BM25_CANDIDATES = 10
RRF_K = 60

RERANKER_ENABLED = os.getenv(
    "RETRIEVAL_RERANKER_ENABLED",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}

RERANKER_MODEL = os.getenv(
    "RERANKER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)

MAX_DISTANCE = float(
    os.getenv("RETRIEVAL_MAX_DISTANCE", "1.12")
)

MIN_RERANK_SCORE = float(
    os.getenv("RETRIEVAL_MIN_RERANK_SCORE", "0.0")
)

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were",
    "what", "which", "who", "where", "when", "why",
    "how", "do", "does", "did", "i", "me", "my",
    "in", "on", "at", "to", "of", "for", "and",
    "or", "it", "this", "that", "with", "can",
    "could", "would", "should",
}

NODE_ALIASES = {
    "google-form": "google-form-trigger",
    "google-forms": "google-form-trigger",
    "gmail": "gmail-reader",
    "stripe": "stripe-trigger",
    "http": "http-request",
    "manual": "manual-trigger",
}


def tokenize(text: str) -> list[str]:
    """Match technical names as compounds and individual terms."""
    text = text.lower()

    words = re.findall(r"[a-z0-9]+", text)
    compounds = re.findall(
        r"[a-z0-9]+(?:[-_./][a-z0-9]+)+",
        text,
    )

    return words + compounds


def normalize_node_name(name: str) -> str:
    """Normalize a requested node name to a slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return NODE_ALIASES.get(slug, slug)


def extract_requested_node(query: str) -> str | None:
    """Extract a node name when the user explicitly asks about a node."""
    pattern = (
        r"\b(?:configure|set\s+up|setup|use|create|add|connect|trigger)"
        r"\s+(?:the\s+)?"
        r"(?P<name>[a-z0-9][a-z0-9\s_-]*?)\s+node\b"
    )

    match = re.search(pattern, query, flags=re.IGNORECASE)

    if not match:
        return None

    name = match.group("name").strip()
    name = re.sub(r"^(?:a|an|the)\s+", "", name, flags=re.IGNORECASE)

    if not name:
        return None

    # Do not interpret descriptive settings as part of a node name.
    # Example: "configure custom headers ... in the HTTP Request node".
    clause_words = {
        "in", "or", "with", "for", "on", "at",
        "about", "using", "from", "by", "the",
    }
    if clause_words.intersection(name.lower().split()):
        return None

    return normalize_node_name(name)


def get_known_nodes(metadatas: list[dict]) -> set[str]:
    """Build the known node inventory from indexed node documents."""
    nodes = set()

    for metadata in metadatas:
        source = (metadata or {}).get("source", "")
        match = re.search(
            r"(?:^|/)nodes-([^/]+)\.md$",
            source,
            flags=re.IGNORECASE,
        )

        if match:
            nodes.add(normalize_node_name(match.group(1)))

    return nodes


@lru_cache(maxsize=1)
def get_retrieval_store():
    """Cache Chroma data and the BM25 index for this process."""

    export_file = (
        PROJECT_ROOT
        / "data"
        / "exports"
        / "blessing_knowledge.jsonl.gz"
    )

    try:
        client, collection = ensure_knowledge_collection(
            chroma_dir=CHROMA_DIR,
            collection_name=COLLECTION_NAME,
            export_file=export_file,
        )

    except Exception as exc:
        logger.exception(
            "Could not initialize the knowledge database."
        )
        raise RuntimeError(
            "The Blessing knowledge database could not be initialized."
        ) from exc

    stored = collection.get(
        include=["documents", "metadatas"],
    )

    documents = stored["documents"] or []
    metadatas = stored["metadatas"] or []
    ids = stored["ids"]

    if not documents:
        raise RuntimeError(
            "The Blessing knowledge database contains no documents."
        )

    tokenized_documents = [
        tokenize(document)
        for document in documents
    ]

    bm25 = BM25Okapi(tokenized_documents)
    known_nodes = get_known_nodes(metadatas)

    logger.info(
        "Retrieval store initialized: %d documents",
        len(documents),
    )

    return (
        client,
        collection,
        documents,
        metadatas,
        ids,
        tokenized_documents,
        bm25,
        known_nodes,
    )

def clear_retrieval_cache():
    """Clear cached data after rebuilding the knowledge index."""
    get_retrieval_store.cache_clear()
    logger.info("Retrieval store cache cleared")


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]],
    k: int = RRF_K,
) -> list[dict]:
    """Merge rankings without comparing incompatible raw scores."""
    fused: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            key = item["id"]
            method = item.get("retrieval_method", "unknown")

            if key not in fused:
                fused[key] = {
                    **item,
                    "rrf_score": 0.0,
                    "retrieval_methods": [],
                }

            if method not in fused[key]["retrieval_methods"]:
                fused[key]["retrieval_methods"].append(method)

            fused[key]["rrf_score"] += 1.0 / (k + rank)

    return sorted(
        fused.values(),
        key=lambda item: item["rrf_score"],
        reverse=True,
    )


@lru_cache(maxsize=1)
def get_reranker():
    """Load the CPU reranker once and reuse it."""
    from sentence_transformers import CrossEncoder

    logger.info("Loading CrossEncoder model: %s", RERANKER_MODEL)

    model = CrossEncoder(RERANKER_MODEL, device="cpu")

    logger.info("CrossEncoder model loaded successfully")
    return model


def rerank(query: str, candidates: list[dict]) -> list[dict]:
    """Order candidates by question-passage relevance."""
    if not candidates:
        return []

    model = get_reranker()

    pairs = [
        (query, candidate["text"])
        for candidate in candidates
    ]

    scores = model.predict(
        pairs,
        batch_size=16,
        show_progress_bar=False,
    )

    reranked = []

    for candidate, score in zip(candidates, scores):
        result = dict(candidate)
        result["rerank_score"] = float(score)
        reranked.append(result)

    return sorted(
        reranked,
        key=lambda item: item["rerank_score"],
        reverse=True,
    )


def rerank_with_relevance_gate(
    query: str,
    candidates: list[dict],
    top_k: int,
) -> list[dict]:
    """Rerank evidence and reject it if scoring fails or relevance is weak."""
    if not candidates or top_k <= 0:
        return []

    if not RERANKER_ENABLED:
        logger.info(
            "CrossEncoder disabled; using fused retrieval ranking."
        )
        return candidates[:top_k]

    try:
        reranked = rerank(query, candidates)
    except Exception:
        logger.exception(
            "CrossEncoder failed; rejecting evidence rather than "
            "passing unverified candidates to answer generation"
        )
        return []

    if not reranked:
        return []

    best_score = reranked[0]["rerank_score"]

    if best_score < MIN_RERANK_SCORE:
        logger.info(
            "Rejected weak evidence: best rerank score %.3f "
            "is below threshold %.3f",
            best_score,
            MIN_RERANK_SCORE,
        )
        return []

    return reranked[:top_k]



def get_source_authority_bonus(query: str, candidate: dict) -> float:
    """Prefer sources based on whether the user needs Blessing or API help."""
    query_lower = query.lower()
    source = (candidate.get("source") or "").lower()
    source_type = candidate.get("source_type", "")

    is_readme = (
        source_type == "blessing_readme"
        or source.endswith("/readme.md.md")
    )
    is_node_doc = (
        source_type == "blessing_node_docs"
        or "/nodes-" in source
    )
    is_blessing_support = (
        source_type in {"blessing_supporting_docs", "blessing_source_code"}
        or "/raw/blessing/" in source
    )
    is_official = (
        source_type == "official_external"
        or "/raw/official/" in source
    )

    # Explicit external-service questions should prefer official documentation.
    external_help_terms = (
        "official",
        "api",
        "api key",
        "secret key",
        "access token",
        "credentials",
        "where do i find",
        "where can i find",
        "webhook secret",
        "signature verification",
        "rate limit",
        "http status",
        "api behavior",
    )
    asks_external_help = any(
        term in query_lower for term in external_help_terms
    )

    # Node-specific questions should prefer node docs, including when they
    # mention Blessing or ask how a particular node works.
    asks_about_node = (
        " node" in f" {query_lower}"
        or "trigger" in query_lower
        or "configure" in query_lower
        or "set up" in query_lower
        or "setup" in query_lower
    )

    # Workflow requests should prefer Blessing examples over unrelated
    # external integration pages, unless the question explicitly asks
    # about external-service behavior or official documentation.
    workflow_terms = (
        "workflow",
        "in blessing",
        "build",
        "automate",
        "automating",
        "send an email",
        "send email",
        "whenever",
        "when a payment",
        "payment succeeds",
        "connect these nodes",
    )
    is_workflow_request = any(
        term in query_lower for term in workflow_terms
    )

    if asks_external_help and is_official:
        return 1.5

    if asks_about_node:
        if is_node_doc:
            return 1.0
        if is_readme:
            return -1.0

    if is_workflow_request:
        if is_readme or is_node_doc or is_blessing_support:
            return 1.5
        if is_official:
            return -1.5

    return 0.0

def rank_by_source_authority(
    query: str,
    candidates: list[dict],
) -> list[dict]:
    """Adjust ordering by source category without overriding relevance."""
    ranked = []

    for candidate in candidates:
        result = dict(candidate)
        result["authority_bonus"] = get_source_authority_bonus(
            query,
            result,
        )

        if RERANKER_ENABLED:
            result["final_rank_score"] = (
                float(result.get("rerank_score", 0.0))
                + result["authority_bonus"]
            )
        else:
            result["final_rank_score"] = float(
                result.get("rrf_score", 0.0)
            )

        ranked.append(result)

    if RERANKER_ENABLED:
        return sorted(
            ranked,
            key=lambda item: item["final_rank_score"],
            reverse=True,
        )

    return sorted(
        ranked,
        key=lambda item: (
            item["final_rank_score"],
            item["authority_bonus"],
        ),
        reverse=True,
    )

def _retrieve_single_query(
    query: str,
    top_k: int = 5,
    apply_authority: bool = True,
) -> list[dict]:
    """Retrieve, validate, merge, rerank, and authority-rank evidence."""
    if not query.strip() or top_k <= 0:
        return []

    store = get_retrieval_store()

    if store is None:
        return []

    (
        _client,
        collection,
        documents,
        metadatas,
        ids,
        tokenized_documents,
        bm25,
        known_nodes,
    ) = store

    # Reject explicitly requested node names absent from the inventory.
    requested_node = extract_requested_node(query)

    if requested_node and requested_node not in known_nodes:
            logger.info(
                "Rejected unknown node request: %s",
                requested_node,
            )
            return []

    # 1. Semantic vector search.
    vector_results = collection.query(
        query_texts=[query],
        n_results=min(VECTOR_CANDIDATES, len(documents)),
        include=["documents", "metadatas", "distances"],
    )

    vector_ranked = []

    for doc_id, document, metadata, distance in zip(
        vector_results["ids"][0],
        vector_results["documents"][0],
        vector_results["metadatas"][0],
        vector_results["distances"][0],
    ):
        distance = float(distance)

        if distance > MAX_DISTANCE:
            continue

        metadata = metadata or {}

        vector_ranked.append({
            "id": doc_id,
            "text": document,
            "source": metadata.get("source", "unknown"),
            "chunk_index": metadata.get("chunk_index", 0),
            "source_type": metadata.get("source_type", "unverified"),
            "authority": metadata.get("authority", "unverified"),
            "canonical_url": metadata.get("canonical_url", ""),
            "document_title": metadata.get("document_title", ""),
            "service": metadata.get("service", ""),
            "distance": distance,
            "retrieval_method": "vector",
        })

    # 2. BM25 keyword search.
    query_tokens = [
        token
        for token in tokenize(query)
        if token not in STOP_WORDS
    ]

    if not query_tokens:
        candidates = vector_ranked
    else:
        scores = bm25.get_scores(query_tokens)
        unique_query_tokens = set(query_tokens)

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda index: float(scores[index]),
            reverse=True,
        )

        bm25_ranked = []

        for index in ranked_indices:
            if len(bm25_ranked) >= BM25_CANDIDATES:
                break

            if scores[index] <= 0:
                continue

            document_tokens = set(tokenized_documents[index])
            matched_terms = len(
                unique_query_tokens & document_tokens
            )
            overlap = matched_terms / len(unique_query_tokens)

            if overlap <= 0.5:
                continue

            metadata = metadatas[index] or {}

            bm25_ranked.append({
                "id": ids[index],
                "text": documents[index],
                "source": metadata.get("source", "unknown"),
                "chunk_index": metadata.get("chunk_index", 0),
                "source_type": metadata.get("source_type", "unverified"),
                "authority": metadata.get("authority", "unverified"),
                "canonical_url": metadata.get("canonical_url", ""),
                "document_title": metadata.get("document_title", ""),
                "service": metadata.get("service", ""),
                "distance": None,
                "retrieval_method": "bm25",
            })

        # 3. Reciprocal Rank Fusion.
        candidates = reciprocal_rank_fusion([
            vector_ranked,
            bm25_ranked,
        ])

    if not candidates:
        return []

    # 4. CrossEncoder reranking and relevance gate.
    # Score all merged candidates before applying the final top_k limit.
    reranked = rerank_with_relevance_gate(
        query,
        candidates,
        top_k=len(candidates),
    )

    if not reranked:
        return []

    # 5. Query-aware source-authority ranking.
    if not apply_authority:
        return reranked[:top_k]

    ranked = rank_by_source_authority(query, reranked)
    return ranked[:top_k]

def _mentioned_known_nodes(query: str) -> list[tuple[str, str]]:
    """Find known node names explicitly mentioned in a query."""
    store = get_retrieval_store()

    if store is None:
        return []

    known_nodes = sorted(store[7])
    query_lower = query.lower()
    found = []

    for slug in known_nodes:
        aliases = {slug.replace("-", " ")}

        if slug == "gmail-reader":
            aliases.update({"gmail", "gmail reader"})
        elif slug == "google-form-trigger":
            aliases.update({"google forms", "google form"})
        elif slug == "http-request":
            aliases.update({"http request"})
        elif slug == "manual-trigger":
            aliases.update({"manual trigger"})
        elif slug == "stripe-trigger":
            aliases.update({"stripe trigger"})

        if any(
            re.search(
                rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
                query_lower,
            )
            for alias in aliases
        ):
            found.append((slug, slug.replace("-", " ")))

    return found


def _focused_node_query(node_label: str) -> str:
    """Build a focused query for a node's documented behavior."""
    return (
        f"Explain the {node_label} node configuration, "
        "input fields, output fields, variable names, "
        "and expressions in Blessing workflows."
    )


def fuse_multi_query_rankings(
    ranked_lists: list[list[dict]],
    weights: list[float],
    focused_nodes: list[str | None],
    k: int = RRF_K,
) -> list[dict]:
    """Fuse independently ranked query results using weighted RRF."""
    fused = {}

    for ranked_list, weight, focused_node in zip(
        ranked_lists,
        weights,
        focused_nodes,
    ):
        for rank, item in enumerate(ranked_list, start=1):
            key = item["id"]

            if key not in fused:
                fused[key] = {
                    **item,
                    "rrf_score": 0.0,
                    "focused_for_nodes": [],
                }

            result = fused[key]
            result["rrf_score"] += float(weight) / (k + rank)

            if focused_node and focused_node not in result["focused_for_nodes"]:
                result["focused_for_nodes"].append(focused_node)

    results = list(fused.values())

    for item in results:
        nodes = item["focused_for_nodes"]
        item["focused_for_node"] = nodes[0] if nodes else ""

    return sorted(
        results,
        key=lambda item: item["rrf_score"],
        reverse=True,
    )


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve evidence for single-node and multi-node questions."""
    if not query.strip() or top_k <= 0:
        return []

    nodes = _mentioned_known_nodes(query)

    if len(nodes) < 2:
        return _retrieve_single_query(query, top_k)

    ranked_lists = []
    weights = []
    focused_nodes = []

    # The original question receives extra weight because it captures
    # the user's complete intent.
    original_results = _retrieve_single_query(
        query,
        top_k=max(top_k, 8),
        apply_authority=False,
    )

    if original_results:
        ranked_lists.append(original_results)
        weights.append(2.0)
        focused_nodes.append(None)

    # Retrieve each explicitly mentioned node independently.
    for slug, label in nodes:
        focused_query = _focused_node_query(label)
        focused_results = _retrieve_single_query(
            focused_query,
            top_k=5,
            apply_authority=False,
        )

        if focused_results:
            ranked_lists.append(focused_results)
            weights.append(1.0)
            focused_nodes.append(slug)

    if not ranked_lists:
        return []

    candidates = fuse_multi_query_rankings(
        ranked_lists,
        weights,
        focused_nodes,
    )

    if RERANKER_ENABLED:
        # Re-score the combined evidence against the complete user query.
        reranked = rerank(query, candidates)
    else:
        # Weighted rank fusion is used instead of comparing raw per-query
        # RRF scores, which are not comparable across different queries.
        reranked = candidates

    for item in reranked:
        item.setdefault("focused_for_node", "")
        item.setdefault("focused_for_nodes", [])

    return rank_by_source_authority(query, reranked)[:top_k]
