#!/usr/bin/env python3
"""
Löscht die Collection Lehrplan_Basel_Stadt3 und baut sie neu ein (IDs lp21:<Zeilenindex>).

Ausführung aus dem backend-Verzeichnis:
  python3 rebuild_chroma.py
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from chroma_lehrplan import (  # noqa: E402
    CHROMA_PERSIST_PATH,
    get_chroma_client,
    load_model_and_tokenizer,
)

COLLECTION_NAME = "Lehrplan_Basel_Stadt3"


def main() -> int:
    print("Chroma-Persistenz:", CHROMA_PERSIST_PATH)
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION_NAME)
        print("Collection gelöscht:", COLLECTION_NAME)
    except Exception as exc:
        print("delete_collection (harmlos wenn noch keine Collection):", exc)

    print("Neuaufbau …")
    load_model_and_tokenizer()
    print("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
