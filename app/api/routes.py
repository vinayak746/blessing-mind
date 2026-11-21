import logging
import os
import hmac

from dotenv import load_dotenv
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Header, Depends

from pydantic import BaseModel, Field

from app.services.retrieval import retrieve
from app.services.generation import analyze_image, generate_answer
from app.services.providers import (
    ProviderConfigurationError,
    ProviderRequestError,
    ProviderUnavailableError,
    resolve_model,
)

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


class ChatRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)
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





def get_provider_credentials(
    authorization: str | None = Header(default=None),
    provider_api_key: str | None = Header(
        default=None,
        alias="X-Provider-API-Key",
    ),
) -> str:
    """Authenticate Blessing and obtain the user's request-scoped API key."""
    expected_token = os.getenv("BLESSING_SERVICE_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail="Service authentication is not configured.",
        )

    if not authorization or authorization[:7].lower() != "bearer ":
        raise HTTPException(
            status_code=401,
            detail="Valid service authentication is required.",
        )

    supplied_token = authorization[7:].strip()

    if not hmac.compare_digest(
        supplied_token.encode("utf-8"),
        expected_token.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid service authentication.",
        )

    if not provider_api_key:
        raise HTTPException(
            status_code=400,
            detail="A provider API key is required.",
        )

    if (
        len(provider_api_key) > 4096
        or any(ord(char) < 32 or ord(char) == 127 for char in provider_api_key)
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid provider API key format.",
        )

    provider_api_key = provider_api_key.strip()

    if not provider_api_key:
        raise HTTPException(
            status_code=400,
            detail="A provider API key is required.",
        )

    return provider_api_key


def validate_provider(provider: str, model: str) -> None:
    """Reject unsupported provider/model selections before retrieval."""
    try:
        resolve_model(provider, model)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


def provider_http_error(exc: Exception) -> HTTPException:
    """Translate sanitized provider errors into safe HTTP responses."""
    if isinstance(exc, ProviderConfigurationError):
        return HTTPException(status_code=400, detail=str(exc))

    if isinstance(exc, ProviderUnavailableError):
        return HTTPException(
            status_code=503,
            detail="The AI provider is temporarily unavailable. Please retry shortly.",
        )

    if isinstance(exc, ProviderRequestError):
        return HTTPException(
            status_code=502,
            detail="The AI provider rejected or could not process the request. Check your provider key, model and account access.",
        )

    return HTTPException(
        status_code=502,
        detail="The AI request could not be completed.",
    )


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
                excerpts.append(chunk_text[:1200])

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
def make_evidence(matches: list[dict]) -> str:
    """Organize evidence by source and prioritize node-focused passages."""
    source_ids = build_source_ids(matches)
    grouped = {}
    source_order = []

    for match in matches:
        identity = source_identity(match)

        if identity not in grouped:
            grouped[identity] = []
            source_order.append(identity)

        grouped[identity].append(match)

    sections = []

    for identity in source_order:
        chunks = grouped[identity]
        chunks.sort(
            key=lambda item: bool(
                item.get("focused_for_nodes") or item.get("focused_for_node")
            ),
            reverse=True,
        )

        source_sections = []

        for match in chunks:
            focused_nodes = match.get("focused_for_nodes") or []
            if not focused_nodes and match.get("focused_for_node"):
                focused_nodes = [match["focused_for_node"]]

            focus_label = (
                " | Retrieved specifically for: " + ", ".join(focused_nodes)
                if focused_nodes else ""
            )

            source_sections.append(
                f"[{source_ids[identity]}] "
                f"Source: {match.get('source', 'unknown')} "
                f"(chunk {match.get('chunk_index', 'unknown')})"
                f"{focus_label}\n"
                f"{match.get('text', '')[:2500]}"
            )

        sections.append("\n\n".join(source_sections))

    return "\n\n".join(sections)


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
def chat(
    request: ChatRequest,
    api_key: str = Depends(get_provider_credentials),
):
    validate_provider(request.provider, request.model)

    try:
        matches = retrieve(request.message, top_k=10)
    except RuntimeError:
        logger.error("Knowledge database retrieval failed (%s)", "RuntimeError")
        raise HTTPException(
            status_code=503,
            detail="The knowledge database is temporarily unavailable. Please retry shortly.",
        ) from None

    if not matches:
        return no_evidence_response()

    try:
        answer = generate_answer(
            request.message,
            make_evidence(matches),
            provider=request.provider,
            model=request.model,
            api_key=api_key,
        )
    except (ProviderConfigurationError, ProviderRequestError, ProviderUnavailableError) as exc:
        logger.warning("AI provider request failed: %s", type(exc).__name__)
        raise provider_http_error(exc) from None
    except Exception as exc:
        logger.error("Answer generation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The AI answer could not be generated.",
        ) from None

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
    provider: str = Form(..., min_length=1, max_length=40),
    model: str = Form(..., min_length=1, max_length=120),
    image: UploadFile = File(...),
    api_key: str = Depends(get_provider_credentials),
):
    """Answer a question using an uploaded screenshot and RAG evidence."""
    validate_provider(provider, model)

    mime_type = (image.content_type or "").lower().split(";")[0].strip()

    if mime_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type. Upload a JPEG, PNG, or WebP image.",
        )

    try:
        image_bytes = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await image.close()

    if not image_bytes:
        raise HTTPException(status_code=400, detail="The uploaded image is empty.")

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
            provider=provider,
            model=model,
            api_key=api_key,
        )
    except (ProviderConfigurationError, ProviderRequestError, ProviderUnavailableError) as exc:
        logger.warning("Image provider request failed: %s", type(exc).__name__)
        raise provider_http_error(exc) from None
    except Exception as exc:
        logger.error("Image analysis failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The image could not be analyzed.",
        ) from None

    try:
        matches = retrieve_image_evidence(
            message=message,
            visual_context=visual_context,
            top_k=5,
        )
    except RuntimeError:
        logger.error("Image knowledge retrieval failed (%s)", "RuntimeError")
        raise HTTPException(
            status_code=503,
            detail="The knowledge database is temporarily unavailable. Please retry shortly.",
        ) from None

    if not matches:
        return no_evidence_response(visual_context)

    try:
        answer = generate_answer(
            message,
            make_evidence(matches),
            visual_context=visual_context,
            provider=provider,
            model=model,
            api_key=api_key,
        )
    except (ProviderConfigurationError, ProviderRequestError, ProviderUnavailableError) as exc:
        logger.warning("Image answer provider request failed: %s", type(exc).__name__)
        raise provider_http_error(exc) from None
    except Exception as exc:
        logger.error("Image-based answer generation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The AI answer could not be generated.",
        ) from None

    return ChatResponse(
        answer=answer,
        sources=build_sources(matches),
        next_steps=[],
        retrieval_configured=True,
    )
