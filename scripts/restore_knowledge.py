from pathlib import Path
import gzip
import json

import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_FILE = PROJECT_ROOT / "data" / "exports" / "blessing_knowledge.jsonl.gz"

COLLECTION_NAME = "blessing_knowledge"
BATCH_SIZE = 100
EXPECTED_DIMENSIONS = 384


def main():
    if not EXPORT_FILE.exists():
        raise FileNotFoundError(f"Export not found: {EXPORT_FILE}")

    client = chromadb.PersistentClient(
        path=str(PROJECT_ROOT / "data" / "restore_test")
    )

    try:
        collection = client.get_collection(COLLECTION_NAME)
        if collection.count() > 0:
            raise RuntimeError(
                "Refusing to overwrite a non-empty collection."
            )
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        collection = client.create_collection(
            name=COLLECTION_NAME,
            metadata={
                "description": "Blessing knowledge with source-trust metadata"
            },
        )

    batch = []
    restored = 0

    def insert_batch(records):
        collection.add(
            ids=[r["id"] for r in records],
            documents=[r["document"] for r in records],
            metadatas=[r["metadata"] for r in records],
            embeddings=[r["embedding"] for r in records],
        )

    with gzip.open(EXPORT_FILE, "rt", encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)

            if len(record["embedding"]) != EXPECTED_DIMENSIONS:
                raise ValueError(
                    f"Invalid embedding dimensions for {record['id']}"
                )

            batch.append(record)

            if len(batch) >= BATCH_SIZE:
                insert_batch(batch)
                restored += len(batch)
                print(f"Restored {restored} records")
                batch.clear()

    if batch:
        insert_batch(batch)
        restored += len(batch)

    actual = collection.count()

    if actual != restored:
        raise RuntimeError(
            f"Restore count mismatch: expected {restored}, got {actual}"
        )

    print("\nRestore complete.")
    print("Collection:", collection.name)
    print("Restored records:", actual)
    print("Database:", PROJECT_ROOT / "data" / "restore_test")


if __name__ == "__main__":
    main()
