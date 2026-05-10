#!/usr/bin/env python3
"""
Wertet Suchanfragen aus eval_queries.json gegen die laufende /search-API aus.

  cd backend && python3 eval_search.py
  python3 eval_search.py --base-url http://127.0.0.1:5001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_queries(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("eval_queries.json muss eine JSON-Liste sein")
    return data


def post_search(base_url: str, query: str) -> dict:
    url = base_url.rstrip("/") + "/search"
    body = json.dumps(
        {
            "query_texts": query,
            "querySchlagwort": "",
            "filters": {"fach": [], "zyklus": []},
        }
    ).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Such-Evaluation gegen eval_queries.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--queries-file", type=Path, default=None)
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    queries_path = args.queries_file or (backend_dir / "eval_queries.json")
    if not queries_path.is_file():
        print(f"Datei nicht gefunden: {queries_path}", file=sys.stderr)
        return 2

    entries = load_queries(queries_path)
    base = args.base_url.rstrip("/")

    ok_top1 = 0
    ok_top3 = 0
    n = 0
    failures = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        query = (entry.get("query") or "").strip()
        expected = entry.get("expected_fach")
        if not query or not expected:
            continue
        n += 1
        try:
            data = post_search(base, query)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append((query, str(exc)))
            continue

        meta_rows = data.get("metadatas") or []
        row = meta_rows[0] if meta_rows and isinstance(meta_rows[0], list) else meta_rows
        if not isinstance(row, list):
            row = []

        fachs_ranked = []
        for i in range(min(10, len(row))):
            m = row[i] or {}
            f = m.get("fach")
            if f:
                fachs_ranked.append(f)

        hit1 = fachs_ranked[0] if fachs_ranked else None
        top3 = set(fachs_ranked[:3])

        if hit1 == expected:
            ok_top1 += 1
        if expected in top3:
            ok_top3 += 1

    print(f"Ausgewertet: {n} Anfragen (von {len(entries)} Einträgen)")
    if n == 0:
        print("Keine gültigen Testfälle.")
        return 1
    print(f"Top-1 Fach-Treffer (expected_fach): {ok_top1}/{n}  ({100 * ok_top1 / n:.1f}%)")
    print(f"Top-3 Fach-Treffer (expected_fach): {ok_top3}/{n}  ({100 * ok_top3 / n:.1f}%)")

    if failures:
        print(f"\nFehler bei {len(failures)} Anfragen (Backend unter {base}?):", file=sys.stderr)
        for q, err in failures[:5]:
            print(f"  … {q[:48]}… → {err}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
