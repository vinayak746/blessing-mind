# Blessing AI Service — starter

A standalone FastAPI service for Blessing's future RAG support assistant. It is intentionally independent of the main Blessing app.

## What it does now
- Provides `/v1/health` and a minimal `/v1/chat` endpoint.
- Generates text/Markdown knowledge documents from a local Blessing repository checkout.
- Maintains an external documentation source registry.
- Fetches allowed official documentation pages into Markdown-like text files.
- Keeps raw and processed knowledge files separate.

## What is not implemented yet
- Embedding generation and Chroma indexing
- LLM provider integration
- Persistent PostgreSQL conversation memory
- Authentication/authorization for production
- Scheduled refresh jobs and production crawler controls

The chat endpoint currently returns a clear "not configured" response rather than pretending RAG is working.

## Requirements
Python 3.11+

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs`.

## Generate internal knowledge from Blessing source

Pass the path to a separate local clone/check-out of Blessing:

```bash
python -m scripts.build_knowledge --repo /path/to/Blessing-main
```

The generated output is readable Markdown under `knowledge_base/raw/blessing/generated/`, plus a JSON manifest. Re-run after source changes. This first version uses deterministic extraction; review generated docs before treating them as definitive user instructions.

## Fetch official docs

Edit `knowledge_base/sources.json` to add or remove approved URLs, then run:

```bash
python -m scripts.fetch_docs
```

The fetcher is intentionally an allowlist-based documentation fetcher, not an unrestricted crawler. It only requests URLs in the registry and only follows links that remain on the same approved domain. Check each site's terms, robots policy, rate limits, and API before expanding crawling. Do not bypass logins, paywalls, CAPTCHAs, or access controls.

## Knowledge base format

Yes: the human-readable knowledge base is Markdown (`.md`) text. We keep:
- `raw/`: original or generated source material
- `processed/`: normalized chunks/metadata for indexing
- `sources.json`: official external source registry
- `manifest.json`: hashes and source metadata

Markdown is easy to inspect and edit. JSONL is useful later for chunks and ingestion pipelines. The vector database is an index, not the only copy of the knowledge.

## API examples

```bash
curl http://127.0.0.1:8000/v1/health
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"conversation_id":"demo-1","message":"How do I configure Discord?"}'
```

The current chat endpoint is a scaffold and will explain that retrieval is not configured yet.
