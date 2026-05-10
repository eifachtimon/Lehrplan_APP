import json
import os
from pathlib import Path

import chromadb

CHROMA_PERSIST_PATH = Path(__file__).resolve().parent / "chroma"


def get_chroma_client():
    return chromadb.PersistentClient(path=str(CHROMA_PERSIST_PATH))


def load_model_and_tokenizer():
    """Lädt Lehrplan21.json in Chroma; Embedding erfolgt über Chroma (Default-Embedding)."""
    print("Current Directory:", os.getcwd())
    print("Chroma persist:", CHROMA_PERSIST_PATH)

    current_directory = os.path.dirname(os.path.abspath(__file__))
    filename = "Lehrplan21.json"
    json_file_path = os.path.join(current_directory, filename)

    with open(json_file_path, encoding="utf-8") as json_file:
        json_data = json.load(json_file)

    # Pro JSON-Zeile stabile ID (lp21:<Index>): dieselbe offizielle uid kann mehrfach vorkommen.
    documents = []
    for idx, item in enumerate(json_data):
        meta = {
            k: (
                ",".join(v)
                if isinstance(v, list)
                else str(v)
                if not isinstance(v, (str, int, float, bool))
                else v
            )
            for k, v in item.items()
            if k != "text"
        }
        rid = f"lp21:{idx}"
        meta["doc_key"] = rid
        meta["lp21_row_index"] = str(idx)
        documents.append({"text": item["text"], "metadata": meta, "id": rid})

    collection = get_chroma_client().create_collection(name="Lehrplan_Basel_Stadt3")

    total = len(documents)
    for i, doc in enumerate(documents):
        collection.upsert(
            documents=[doc["text"]],
            metadatas=[doc["metadata"]],
            ids=[doc["id"]],
        )

        if (i + 1) % 500 == 0 or i + 1 == total:
            print(f"upsert {i + 1}/{total}")

    return collection
