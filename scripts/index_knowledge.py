
from pathlib import Path
import hashlib
import re

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge_base" / "raw"
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "blessing_knowledge"

CHUNK_SIZE = 1800
CHUNK_OVERLAP = 250


def classify_source(relative_path: str) -> tuple[str, str]:
    """Classify a document by its location and intended authority."""
    normalized_path = relative_path.replace("\\", "/").lower()

    if "/raw/official/" in normalized_path:
        return "official_external", "official"
    if "/raw/external/" in normalized_path:
        return "official_external", "official"
	
    if "/raw/blessing/guides/node-reference/" in normalized_path:
        return "blessing_node_docs", "product_docs"

    if "/raw/blessing/generated/nodes-" in normalized_path:
        return "blessing_node_docs", "product_docs"

    if "/raw/blessing/generated/src-" in normalized_path:
        return "blessing_source_code", "implementation"

    if normalized_path.endswith("/readme.md.md"):
        return "blessing_readme", "supporting"

    if "/raw/blessing/" in normalized_path:
        return "blessing_supporting_docs", "supporting"

    return "unverified", "unverified"
def extract_frontmatter(text: str) -> dict[str, str]:
    """Extract simple key-value metadata from Markdown frontmatter."""
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        return {}

    metadata = {}

    for line in lines[1:]:
        if line.strip() == "---":
            break

        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip("\"'")

    return metadata

def split_long_block(text: str) -> list[str]:
    """Split oversized paragraphs or code blocks without losing all context."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))

        if end < len(text):
            boundary = max(
                text.rfind("\n", start + CHUNK_SIZE // 2, end),
                text.rfind(" ", start + CHUNK_SIZE // 2, end),
            )
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(start + 1, end - CHUNK_OVERLAP)

    return chunks


def split_section(body: str, heading_context: str) -> list[str]:
    """Pack paragraphs into chunks while retaining the section heading."""
    blocks = re.findall(
        r"```[\s\S]*?```|.+?(?=\n\s*\n|\Z)",
        body.strip(),
        flags=re.S,
    )
    blocks = [block.strip() for block in blocks if block.strip()]

    chunks = []
    current = []
    current_length = len(heading_context)

    def save_chunk(parts: list[str]) -> None:
        if not parts:
            return

        content = "\n\n".join(parts).strip()
        if content:
            chunks.append(f"{heading_context}\n\n{content}".strip())

    for block in blocks:
        if len(block) + len(heading_context) > CHUNK_SIZE:
            save_chunk(current)
            current = []
            current_length = len(heading_context)

            for piece in split_long_block(block):
                save_chunk([piece])
            continue

        additional_length = len(block) + (2 if current else 0)

        if current and current_length + additional_length > CHUNK_SIZE:
            previous_tail = current[-1]
            save_chunk(current)

            if len(previous_tail) <= CHUNK_OVERLAP:
                current = [previous_tail]
                current_length = len(heading_context) + len(previous_tail)
            else:
                current = []
                current_length = len(heading_context)

            additional_length = len(block) + (2 if current else 0)

        current.append(block)
        current_length += additional_length

    save_chunk(current)
    return chunks


def split_text(text: str) -> list[str]:
    """Split Markdown by heading sections, then by paragraphs."""
    text = text.strip()
    if not text:
        return []

    sections = []
    heading_stack = []
    body_lines = []

    def save_section() -> None:
        body = "\n".join(body_lines).strip()
        context = " > ".join(heading_stack) if heading_stack else "Document"
        if body:
            sections.append((context, body))

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)

        if match:
            save_section()
            body_lines = []

            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = heading_stack[:level - 1]
            heading_stack.append(title)
        else:
            body_lines.append(line)

    save_section()

    chunks = []
    for heading_context, body in sections:
        chunks.extend(split_section(body, heading_context))

    if not sections:
        chunks.extend(split_long_block(text))

    return chunks


def main() -> None:
    if not KNOWLEDGE_DIR.exists():
        raise SystemExit(f"Knowledge directory not found: {KNOWLEDGE_DIR}")

    files = sorted(KNOWLEDGE_DIR.rglob("*.md"))
    if not files:
        raise SystemExit(f"No Markdown files found under {KNOWLEDGE_DIR}")

    # Build the complete index before touching the current collection.
    ids = []
    documents = []
    metadatas = []

    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        frontmatter = extract_frontmatter(text)
        chunks = split_text(text)
        relative_path = str(file_path.relative_to(PROJECT_ROOT))
        source_type, authority = classify_source(relative_path)

        canonical_url = frontmatter.get("url", "")
        document_title = frontmatter.get("title", file_path.stem)
        service = frontmatter.get("service", "")

        for index, chunk in enumerate(chunks):
            chunk_hash = hashlib.sha256(
                f"{relative_path}:{index}:{chunk}".encode("utf-8")
            ).hexdigest()[:24]

            ids.append(chunk_hash)
            documents.append(chunk)
            metadatas.append({
                "source": relative_path,
                "chunk_index": index,
                "file_name": file_path.name,
                "source_type": source_type,
                "authority": authority,
                "canonical_url": canonical_url,
                "document_title": document_title,
                "service": service,
            })

    if not documents:
        raise SystemExit(
            f"No Markdown chunks found under {KNOWLEDGE_DIR}. "
            "Check the Markdown files before rebuilding the index."
        )

    # Display the planned classification before indexing.
    print("Source classification:")
    for source_type in sorted({m["source_type"] for m in metadatas}):
        count = sum(
            1 for metadata in metadatas
            if metadata["source_type"] == source_type
        )
        print(f"  {source_type}: {count} chunks")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Build a separate collection first so the existing collection survives
    # if indexing fails before the replacement is ready.
    staging_name = f"{COLLECTION_NAME}_staging"

    try:
        client.delete_collection(staging_name)
    except Exception:
        pass

    staging = client.create_collection(
        name=staging_name,
        metadata={
            "description": "Staging index with source-trust metadata"
        },
    )

    batch_size = 100

    try:
        for start in range(0, len(documents), batch_size):
            staging.add(
                ids=ids[start:start + batch_size],
                documents=documents[start:start + batch_size],
                metadatas=metadatas[start:start + batch_size],
            )

        if staging.count() != len(documents):
            raise RuntimeError(
                f"Staging count mismatch: expected {len(documents)}, "
                f"got {staging.count()}"
            )

    except Exception:
        client.delete_collection(staging_name)
        raise

    # Chroma doesn't provide an atomic collection rename. Keep the completed
    # staging collection until the new production collection is populated.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "Blessing knowledge with source-trust metadata"
        },
    )

    try:
        for start in range(0, len(documents), batch_size):
            collection.add(
                ids=ids[start:start + batch_size],
                documents=documents[start:start + batch_size],
                metadatas=metadatas[start:start + batch_size],
            )

        if collection.count() != len(documents):
            raise RuntimeError(
                f"Production count mismatch: expected {len(documents)}, "
                f"got {collection.count()}"
            )

    except Exception:
        # Leave the completed staging collection available for recovery.
        raise

    client.delete_collection(staging_name)

    print(
        f"\nIndexed {collection.count()} chunks from "
        f"{len(set(m['source'] for m in metadatas))} Markdown files."
    )
    print(f"Chroma database: {CHROMA_DIR}")
    print(f"Collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
