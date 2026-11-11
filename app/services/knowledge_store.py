import gzip
import json
import logging
import threading
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_METADATA = {
    "description": "Blessing knowledge with source-trust metadata"
}

BATCH_SIZE = 100
EXPECTED_DIMENSIONS = 384

_restore_lock = threading.Lock()


def ensure_knowledge_collection(
    chroma_dir: Path,
    collection_name: str,
    export_file: Path,
):
    """
    Open the existing Chroma collection or restore it from
    the compressed export if the collection is missing or empty.
    """
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))

    with _restore_lock:
        try:
            collection = client.get_collection(collection_name)

            if collection.count() > 0:
                return client, collection

            logger.warning(
                "Chroma collection exists but is empty."
            )

        except Exception:
            logger.info(
                "Chroma collection not found. Restoration required."
            )

        if not export_file.exists():
            raise FileNotFoundError(
                f"Knowledge export not found: {export_file}"
            )

        # Remove an empty or incomplete collection before restoring.
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        collection = client.create_collection(
            name=collection_name,
            metadata=COLLECTION_METADATA,
        )

        restored = 0
        batch = []

        def insert_batch(records):
            collection.add(
                ids=[record["id"] for record in records],
                documents=[
                    record["document"] for record in records
                ],
                metadatas=[
                    record["metadata"] for record in records
                ],
                embeddings=[
                    record["embedding"] for record in records
                ],
            )

        try:
            with gzip.open(
                export_file,
                "rt",
                encoding="utf-8",
            ) as source:
                for line in source:
                    record = json.loads(line)

                    embedding = record["embedding"]

                    if len(embedding) != EXPECTED_DIMENSIONS:
                        raise ValueError(
                            "Invalid embedding dimensions for "
                            f"{record['id']}"
                        )

                    batch.append(record)

                    if len(batch) >= BATCH_SIZE:
                        insert_batch(batch)
                        restored += len(batch)
                        batch.clear()

            if batch:
                insert_batch(batch)
                restored += len(batch)

            actual = collection.count()

            if actual != restored or actual == 0:
                raise RuntimeError(
                    f"Restoration count mismatch: "
                    f"expected {restored}, got {actual}"
                )

        except Exception:
            logger.exception(
                "Knowledge database restoration failed."
            )

            try:
                client.delete_collection(collection_name)
            except Exception:
                pass

            raise

        logger.info(
            "Knowledge database restored successfully: %d records",
            restored,
        )

        return client, collection
