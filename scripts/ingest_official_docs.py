from datetime import datetime, timezone
from pathlib import Path
import re
import time

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = (
    PROJECT_ROOT / "knowledge_base" / "raw" / "official" / "discord"
)

SOURCES = [
    {
        "title": "Discord Incoming Webhooks",
        "slug": "discord-incoming-webhooks",
        "raw_url": (
            "https://raw.githubusercontent.com/discord/"
            "discord-api-docs/main/developers/platform/webhooks.mdx"
        ),
        "canonical_url": (
            "https://docs.discord.com/developers/platform/webhooks"
        ),
        "description": (
            "Creating and executing incoming webhooks to post messages "
            "into Discord channels."
        ),
    },
    {
        "title": "Discord Webhook Events",
        "slug": "discord-webhook-events",
        "raw_url": (
            "https://raw.githubusercontent.com/discord/"
            "discord-api-docs/main/developers/events/webhook-events.mdx"
        ),
        "canonical_url": (
            "https://docs.discord.com/developers/events/webhook-events"
        ),
        "description": (
            "Receiving outgoing webhook events from Discord in an "
            "application endpoint."
        ),
    },
]

HEADERS = {
    "User-Agent": "BlessingKnowledgeIndexer/1.0"
}


def clean_mdx(text: str) -> str:
    """Remove imports and frontmatter that aren't useful for retrieval."""
    text = re.sub(
        r"\A---\s*\n.*?\n---\s*\n",
        "",
        text,
        count=1,
        flags=re.S,
    )

    # Remove MDX import statements.
    text = re.sub(r"(?m)^\s*import\s+.*?;\s*$", "", text)
    text = re.sub(r"(?m)^\s*import\s+.*$", "", text)

    # Remove JSX tags while retaining text between paired tags.
    text = re.sub(r"</?[A-Za-z][A-Za-z0-9.]*(?:\s[^<>]*?)?\s*/?>", "", text)

    # Remove excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    successful = 0

    for source in SOURCES:
        print(f"\nFetching {source['title']}")

        try:
            response = session.get(source["raw_url"], timeout=30)
            response.raise_for_status()

            body = clean_mdx(response.text)

            if len(body) < 1000:
                raise ValueError(
                    f"Extracted content is too short: {len(body)} characters"
                )

            document = (
                f"# {source['title']}\n\n"
                f"Document type: Official Discord developer documentation\n\n"
                f"Purpose: {source['description']}\n\n"
                f"Source URL: {source['canonical_url']}\n\n"
                f"Fetched at: {datetime.now(timezone.utc).isoformat()}\n\n"
                f"---\n\n"
                f"{body}\n"
            )

            output_path = OUTPUT_DIR / f"{source['slug']}.md"
            output_path.write_text(document, encoding="utf-8")

            print(f"Saved: {output_path}")
            print(f"Extracted characters: {len(body)}")
            successful += 1

        except Exception as exc:
            print(f"FAILED: {source['canonical_url']}")
            print(f"Reason: {exc}")

        time.sleep(1)

    print(f"\nFinished: {successful}/{len(SOURCES)} sources saved.")

    if successful != len(SOURCES):
        raise SystemExit(
            "Not all sources were ingested. Review the errors before "
            "rebuilding the Chroma index."
        )


if __name__ == "__main__":
    main()
