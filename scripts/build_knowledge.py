
"""Generate knowledge documents from a local Blessing repository checkout.

Also sync human-written Markdown guides from the Blessing repository's
documentation/ directory into the AI service knowledge base.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


NODE_ROOTS = [
    "src/features/executions/components",
    "src/features/triggers/components",
]

SOURCE_FILES = [
    "README.md",
    "CONTRIBUTION.md",
    "prisma/schema.prisma",
    "src/config/node-components.ts",
    "src/features/executions/lib/executor-registry.ts",
]

STRING_RE = re.compile(
    r"""(?:"([^"\\]*(?:\\.[^"\\]*)*)"|'([^'\\]*(?:\\.[^'\\]*)*)'|`([^`\\]*(?:\\.[^`\\]*)*)`)"""
)

JSX_TEXT_RE = re.compile(r">([^<>]{2,240})<")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\\n", " ").replace("\\t", " ")).strip()


def extract_strings(source: str) -> list[str]:
    values = []

    for match in STRING_RE.finditer(source):
        value = clean(next((g for g in match.groups() if g is not None), ""))

        if len(value) >= 3 and not value.startswith(
            ("http://", "https://", "@/"),
        ):
            values.append(value)

    values += [
        clean(match.group(1))
        for match in JSX_TEXT_RE.finditer(source)
    ]

    output = []
    seen = set()

    for value in values:
        if len(value) >= 3 and len(value) <= 220 and value not in seen:
            if not value.startswith(
                ("className=", "text-", "bg-", "border-", "rounded", "flex "),
            ):
                seen.add(value)
                output.append(value)

    return output


def write_doc(
    out_dir: Path,
    relative: str,
    title: str,
    body: str,
    metadata: dict,
) -> Path:
    slug = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "-",
        relative,
    ).strip("-").lower()

    target = out_dir / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(
        f"---\n"
        f"source: blessing-repository\n"
        f"source_path: {relative}\n"
        f"generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"content_sha256: {hashlib.sha256(body.encode()).hexdigest()}\n"
        f"metadata: {json.dumps(metadata, ensure_ascii=False)}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body}\n",
        encoding="utf-8",
    )

    return target


def sync_human_guides(
    repo: Path,
    project_root: Path,
    manifest: dict,
) -> int:
    """Sync human-written guides without touching other knowledge documents."""

    docs_source = repo / "documentation"

    guides_output = (
        project_root
        / "knowledge_base"
        / "raw"
        / "blessing"
        / "guides"
        / "node-reference"
    )

    if not docs_source.is_dir():
        print(
            f"No documentation directory found at {docs_source}; "
            "skipping human-guide sync."
        )
        return 0

    guides_output.mkdir(parents=True, exist_ok=True)

    # Remove only Markdown files previously synced into this dedicated folder.
    # Other knowledge-base guides are left untouched.
    for existing in guides_output.rglob("*.md"):
        existing.unlink()

    synced_count = 0

    for guide in sorted(docs_source.rglob("*.md")):
        # These are authoring aids, not product knowledge documents.
        if guide.name.lower() in {"readme.md", "template.md"}:
            continue

        relative = guide.relative_to(docs_source)
        target = guides_output / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(guide, target)

        content = target.read_text(encoding="utf-8")
        relative_output = target.relative_to(project_root).as_posix()

        manifest["documents"].append(
            {
                "path": f"human-guides/{relative.as_posix()}",
                "output": relative_output,
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
                "kind": "human_authored_guide",
            }
        )

        synced_count += 1

    print(f"Synced {synced_count} human-written guides from {docs_source}")
    return synced_count


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo",
        required=True,
        help="Path to a local Blessing repository checkout",
    )

    parser.add_argument(
        "--output",
        default="knowledge_base/raw/blessing/generated",
        help="Directory for generated source-code documentation",
    )

    parser.add_argument(
        "--docs-source",
        default=None,
        help=(
            "Directory containing human-written Markdown guides. "
            "Defaults to <repo>/documentation."
        ),
    )

    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()

    if not repo.is_dir():
        raise SystemExit(f"Repository directory not found: {repo}")

    project_root = Path(__file__).resolve().parents[1]

    output = Path(args.output).expanduser()

    if not output.is_absolute():
        output = project_root / output

    output.mkdir(parents=True, exist_ok=True)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo),
        "documents": [],
    }

    # Generate reference documents for important repository files.
    for relative in SOURCE_FILES:
        source_path = repo / relative

        if not source_path.is_file():
            continue

        body = source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        target = write_doc(
            output,
            relative,
            source_path.name,
            f"Source path: `{relative}`\n\n```text\n{body}\n```",
            {},
        )

        manifest["documents"].append(
            {
                "path": relative,
                "output": str(target.relative_to(output)),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
                "kind": "repository_document",
            }
        )

    # Generate implementation documents for node folders.
    discovered = set()

    for node_root_relative in NODE_ROOTS:
        node_root = repo / node_root_relative

        if not node_root.is_dir():
            continue

        for folder in sorted(
            path for path in node_root.iterdir() if path.is_dir()
        ):
            source_files = []

            for filename in (
                "node.tsx",
                "dialog.tsx",
                "actions.ts",
                "executor.ts",
            ):
                source_path = folder / filename

                if source_path.is_file():
                    source_files.append(
                        (
                            filename,
                            source_path.read_text(
                                encoding="utf-8",
                                errors="replace",
                            ),
                        )
                    )

            if not source_files:
                continue

            slug = folder.name
            discovered.add(slug)

            sections = [
                f"Node folder: `{folder.relative_to(repo).as_posix()}`",
                "",
                "## Extracted UI strings and labels",
                "",
            ]

            ui_strings = []

            for filename, content in source_files:
                if filename in ("node.tsx", "dialog.tsx", "actions.ts"):
                    ui_strings.extend(extract_strings(content))

            sections.extend(
                f"- {value}"
                for value in dict.fromkeys(ui_strings[:180])
            )

            sections.extend(
                [
                    "",
                    "## Source implementation",
                    "",
                ]
            )

            for filename, content in source_files:
                sections.extend(
                    [
                        f"### {filename}",
                        "",
                        "```tsx",
                        content,
                        "```",
                        "",
                    ]
                )

            body = "\n".join(sections)
            relative = f"nodes/{slug}"

            target = write_doc(
                output,
                relative,
                f"Blessing node: {slug}",
                body,
                {
                    "node_slug": slug,
                    "files": [name for name, _ in source_files],
                    "has_dialog": any(
                        name == "dialog.tsx"
                        for name, _ in source_files
                    ),
                    "has_executor": any(
                        name == "executor.ts"
                        for name, _ in source_files
                    ),
                },
            )

            manifest["documents"].append(
                {
                    "path": relative,
                    "output": str(target.relative_to(output)),
                    "sha256": hashlib.sha256(body.encode()).hexdigest(),
                    "kind": "node_implementation",
                }
            )

    manifest["node_folders_discovered"] = sorted(discovered)

    # Sync human-authored guides into the RAG knowledge directory.
    docs_source = (
        Path(args.docs_source).expanduser().resolve()
        if args.docs_source
        else repo / "documentation"
    )

    # sync_human_guides defaults to repo/documentation. Support an explicit
    # alternate source directory without changing the repository generator.
    if docs_source == repo / "documentation":
        sync_human_guides(repo, project_root, manifest)
    elif docs_source.is_dir():
        # Reuse the same safe sync behavior for a user-specified source path.
        original_docs = repo / "documentation"
        try:
            if docs_source != original_docs:
                # Perform a direct sync from the requested source.
                guides_output = (
                    project_root
                    / "knowledge_base"
                    / "raw"
                    / "blessing"
                    / "guides"
                    / "node-reference"
                )
                guides_output.mkdir(parents=True, exist_ok=True)

                for existing in guides_output.rglob("*.md"):
                    existing.unlink()

                count = 0

                for guide in sorted(docs_source.rglob("*.md")):
                    if guide.name.lower() in {"readme.md", "template.md"}:
                        continue

                    relative = guide.relative_to(docs_source)
                    target = guides_output / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(guide, target)

                    content = target.read_text(encoding="utf-8")
                    manifest["documents"].append(
                        {
                            "path": f"human-guides/{relative.as_posix()}",
                            "output": target.relative_to(project_root).as_posix(),
                            "sha256": hashlib.sha256(content.encode()).hexdigest(),
                            "kind": "human_authored_guide",
                        }
                    )
                    count += 1

                print(f"Synced {count} human-written guides from {docs_source}")
        except OSError as exc:
            raise SystemExit(f"Failed to sync human-written guides: {exc}") from exc
    else:
        print(
            f"No documentation directory found at {docs_source}; "
            "skipping human-guide sync."
        )

    manifest["document_count"] = len(manifest["documents"])

    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {manifest['document_count']} Markdown documents to {output}")
    print(
        f"Discovered {len(discovered)} node folders: "
        f"{', '.join(sorted(discovered))}"
    )


if __name__ == "__main__":
    main()
