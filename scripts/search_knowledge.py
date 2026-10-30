
from pathlib import Path
import chromadb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"
COLLECTION_NAME = "blessing_knowledge"


def main() -> None:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)

    print(f"Indexed chunks: {collection.count()}")
    query = input("\nAsk about Blessing: ").strip()

    if not query:
        print("Please enter a question.")
        return

    results = collection.query(
        query_texts=[query],
        n_results=5,
        include=["documents", "metadatas", "distances"],
    )

    for index, document in enumerate(results["documents"][0], start=1):
        metadata = results["metadatas"][0][index - 1]
        distance = results["distances"][0][index - 1]

        print(f"\n{'=' * 70}")
        print(f"Result {index}")
        print(f"Source: {metadata['source']}")
        print(f"Chunk: {metadata['chunk_index']}")
        print(f"Distance: {distance:.4f}")
        print("-" * 70)
        print(document[:1800])


if __name__ == "__main__":
    main()
