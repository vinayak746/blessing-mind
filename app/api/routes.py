import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.retrieval import retrieve
from app.services.generation import analyze_image, generate_answer

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=12000)
    context: dict | None = None


class Source(BaseModel):
    id: str
    title: str
    type: str
    url: str | None = None
    excerpt: str | None = None
    chunk_index: int | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    retrieval_configured: bool = False




def source_identity(match: dict) -> str:
    """Identify a source by canonical URL, falling back to its file path."""
    url = (match.get("canonical_url") or "").strip()
    if url:
        return f"url:{url}"

    return f"path:{match.get('source', 'unknown')}"


def build_source_ids(matches: list[dict]) -> dict[str, str]:
    """Assign one stable citation ID to each unique source."""
    source_ids = {}

    for match in matches:
        identity = source_identity(match)
        if identity not in source_ids:
            source_ids[identity] = f"S{len(source_ids) + 1}"

    return source_ids


def build_sources(matches: list[dict]) -> list[Source]:
    """Return one source per document with excerpts from retrieved chunks."""
    source_ids = build_source_ids(matches)
    grouped = {}
    order = []

    for match in matches:
        identity = source_identity(match)
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append(match)

    sources = []

    for identity in order:
        chunks = grouped[identity]
        first = chunks[0]
        source_path = first.get("source", "unknown")
        is_external = first.get("source_type") == "official_external"

        title = (
            first.get("document_title")
            if is_external
            else source_path.rsplit("/", 1)[-1]
        )

        excerpts = []
        seen_text = set()

        for chunk in chunks[:3]:
            chunk_text = (chunk.get("text") or "").strip()
            if chunk_text and chunk_text not in seen_text:
                seen_text.add(chunk_text)
                excerpts.append(
                    f"[Chunk {chunk.get('chunk_index', 'unknown')}] "
                    f"{chunk_text[:1200]}"
                )

        sources.append(
            Source(
                id=source_ids[identity],
                title=title or source_path.rsplit("/", 1)[-1],
                type="official_external" if is_external else "blessing_document",
                url=first.get("canonical_url") or None,
                excerpt="\n\n".join(excerpts)[:3000] or None,
                chunk_index=first.get("chunk_index"),
            )
        )

    return sources
def retrieve_image_evidence(
    message: str,
    visual_context: str,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve screenshot evidence with separate, focused queries."""
    queries = [message.strip()]

    # Search the screenshot observations separately so that a long
    # description doesn't dilute the user's original question.
    if visual_context.strip():
        queries.append(visual_context.strip())

    # Add focused searches for relevant Blessing nodes.
    context_lower = visual_context.lower()

    node_queries = {
        "gmail-reader": "How do I configure the Gmail Reader node in Blessing?",
        "gemini": "How do I configure the Gemini node in Blessing?",
        "discord": "How do I configure the Discord node message content and template variables?",
        "slack": "How do I configure Slack message content and workflow variables?",
        "manual-trigger": "How do I start and execute a workflow using Manual Trigger in Blessing?",
        "google-form-trigger": "How do I configure the Google Form Trigger node in Blessing?",
        "stripe-trigger": "How do I configure the Stripe Trigger node in Blessing?",
        "http-request": "How do I configure the HTTP Request node in Blessing?",
    }

    for node, query in node_queries.items():
        if node in context_lower:
            queries.append(query)

    merged = {}
    for query in queries:
        if not query:
            continue

        for match in retrieve(query, top_k=top_k):
            # Chunk IDs are stable across retrieval queries.
            identity = match.get("id") or (
                match.get("source"),
                match.get("chunk_index"),
                match.get("text"),
            )

            existing = merged.get(identity)
            if existing is None:
                merged[identity] = match
            elif (
                match.get("final_rank_score", match.get("rerank_score", 0))
                > existing.get("final_rank_score", existing.get("rerank_score", 0))
            ):
                merged[identity] = match

    results = list(merged.values())
    results.sort(
        key=lambda item: item.get(
            "final_rank_score",
            item.get("rerank_score", float("-inf")),
        ),
        reverse=True,
    )

    return results[:top_k]

def make_evidence(matches: list[dict]) -> str:
    """Keep every evidence chunk while sharing IDs for the same source."""
    source_ids = build_source_ids(matches)

    return "\n\n".join(
        f"[{source_ids[source_identity(match)]}] "
        f"Source: {match.get('source', 'unknown')} "
        f"(chunk {match.get('chunk_index', 'unknown')})\n"
        f"{match.get('text', '')[:2500]}"
        for match in matches
    )


def no_evidence_response(
    visual_context: str | None = None,
) -> ChatResponse:
    """Return a safe fallback when the knowledge base has no matches."""
    if visual_context:
        answer = (
            "Here's what I could identify in your screenshot:\n\n"
            f"{visual_context}\n\n"
            "However, I couldn't find relevant information in the indexed "
            "Blessing knowledge base to verify a configuration fix."
        )
    else:
        answer = (
            "I couldn't find relevant information in the indexed "
            "Blessing knowledge base, so I can't give a reliable "
            "configuration answer yet."
        )

    return ChatResponse(
        answer=answer,
        next_steps=[
            "Try rephrasing your question or providing more context.",
            "Check whether the relevant documentation has been indexed.",
        ],
        retrieval_configured=True,
    )

def retrieve_image_evidence(
    message: str,
    visual_context: str,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve screenshot evidence using separate focused queries."""
    queries = [message.strip()]

    if visual_context.strip():
        queries.append(visual_context.strip())

    context_lower = visual_context.lower()

    node_queries = {
        "gmail-reader": "How do I configure the Gmail Reader node in Blessing?",
        "gemini": "How do I configure the Gemini node in Blessing?",
        "discord": "How do I configure Discord message content and template variables in Blessing?",
        "slack": "How do I configure Slack message content and workflow variables?",
        "manual-trigger": "How do I execute a workflow using Manual Trigger in Blessing?",
        "google-form-trigger": "How do I configure the Google Form Trigger node?",
        "stripe-trigger": "How do I configure the Stripe Trigger node?",
        "http-request": "How do I configure the HTTP Request node?",
    }

    for node, query in node_queries.items():
        if node in context_lower:
            queries.append(query)

    merged = {}

    for query in queries:
        for match in retrieve(query, top_k=top_k):
            identity = match.get("id") or (
                match.get("source"),
                match.get("chunk_index"),
                match.get("text"),
            )

            current = merged.get(identity)
            score = match.get(
                "final_rank_score",
                match.get("rerank_score", float("-inf")),
            )

            current_score = (
                current.get(
                    "final_rank_score",
                    current.get("rerank_score", float("-inf")),
                )
                if current
                else float("-inf")
            )

            if current is None or score > current_score:
                merged[identity] = match

    results = list(merged.values())
    results.sort(
        key=lambda item: item.get(
            "final_rank_score",
            item.get("rerank_score", float("-inf")),
        ),
        reverse=True,
    )

    return results[:top_k]


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "blessing-ai-service",
        "version": "0.1.0",
    }


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    matches = retrieve(request.message, top_k=8)

    if not matches:
        return no_evidence_response()

    try:
        answer = generate_answer(
            request.message,
            make_evidence(matches),
        )
    except Exception:
        logger.exception("Answer generation failed")
        raise HTTPException(
            status_code=502,
            detail="The AI answer could not be generated. Check service logs.",
        )

    return ChatResponse(
        answer=answer,
        sources=build_sources(matches),
        next_steps=[],
        retrieval_configured=True,
    )


def validate_image_bytes(data: bytes, mime_type: str) -> bool:
    """Check that the image signature matches its declared media type."""
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")

    if mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")

    if mime_type == "image/webp":
        return (
            len(data) >= 12
            and data[:4] == b"RIFF"
            and data[8:12] == b"WEBP"
        )

    return False


@router.post("/chat/image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(..., min_length=1, max_length=12000),
    image: UploadFile = File(...),
):
    """Answer a question using an uploaded screenshot and RAG evidence."""
    mime_type = (image.content_type or "").lower().split(";")[0].strip()

    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Upload a JPEG, PNG, or WebP image.",
        )

    image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
    await image.close()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="The uploaded image is empty.",
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image is too large. The maximum size is 8 MB.",
        )

    if not validate_image_bytes(image_bytes, mime_type):
        raise HTTPException(
            status_code=415,
            detail="The uploaded file does not match its declared image type.",
        )

    try:
        visual_context = analyze_image(
            message,
            image_bytes,
            mime_type,
        )
    except Exception:
        logger.exception("Image analysis failed")
        raise HTTPException(
            status_code=502,
            detail="The image could not be analyzed. Check service logs.",
        )

    # Use visual context to improve retrieval for vague questions such
    # as "What is wrong here?" or "How do I fix this error?"
    matches = retrieve_image_evidence(
    	message=message,
    	visual_context=visual_context,
    	top_k=5,
    )
    if not matches:
        return no_evidence_response(visual_context)

    try:
        answer = generate_answer(
            message,
            make_evidence(matches),
            visual_context=visual_context,
        )
    except Exception:
        logger.exception("Image-based answer generation failed")
        raise HTTPException(
            status_code=502,
            detail="The AI answer could not be generated. Check service logs.",
        )

    return ChatResponse(
        answer=answer,
        sources=build_sources(matches),
        next_steps=[],
        retrieval_configured=True,
    )
