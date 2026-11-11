from pathlib import Path
import json
import gzip

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
EXPORT_DIR = PROJECT_ROOT / "data" / "exports"
EXPORT_FILE = EXPORT_DIR / "blessing_knowledge.jsonl.gz"

COLLECTION_NAME = "blessing_knowledge"
BATCH_SIZE = 100


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    total = collection.count()
    if total == 0:
        raise RuntimeError("Refusing to export an empty collection.")

    exported = 0

    with gzip.open(
        EXPORT_FILE,
        "wt",
        encoding="utf-8",
    ) as output:
        for offset in range(0, total, BATCH_SIZE):
            batch = collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=[
                    "documents",
                    "metadatas",
                    "embeddings",
                ],
            )

            for i, document_id in enumerate(batch["ids"]):
                record = {
                    "id": document_id,
                    "document": batch["documents"][i],
                    "metadata": batch["metadatas"][i],
                    "embedding": batch["embeddings"][i].tolist(),
                }

                output.write(json.dumps(record) + "\n")
                exported += 1

            print(f"Exported {exported}/{total} records")

    if exported != total:
        raise RuntimeError(
            f"Export count mismatch: expected {total}, got {exported}"
        )

    print("\nExport complete.")
    print(f"Records: {exported}")
    print(f"File: {EXPORT_FILE}")
    print(f"Size: {EXPORT_FILE.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
