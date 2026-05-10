#!/usr/bin/env python3
"""
Smoke/Regression: POST /search mit Benchmark-Queries — gibt Top-3-IDs und meta aus.

  cd backend && python3 regression_search_aliases.py

Erfordert laufenden Flask-Server (Standard http://127.0.0.1:5001).
"""

from __future__ import annotations

import json
import sys
from urllib.request import Request, urlopen

from benchmark_search import BASE_URL, TEST_QUERIES


def main() -> int:
    print(f"Regression smoke: {len(TEST_QUERIES)} Queries → {BASE_URL}/search\n")
    any_fail = False
    warned_missing_alias_meta = False
    for query in TEST_QUERIES:
        body = json.dumps(
            {
                "query_texts": query,
                "querySchlagwort": "",
                "filters": {"fach": [], "zyklus": []},
            }
        ).encode("utf-8")
        req = Request(f"{BASE_URL}/search", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except OSError as ex:
            print(f"FAIL query={query!r}: {ex}")
            any_fail = True
            continue
        ids = data.get("ids", [[]])
        top3 = (ids[0] if ids else [])[:3]
        meta = data.get("meta") or {}
        if "query_aliases_version" in meta:
            ver = meta["query_aliases_version"]
        else:
            ver = "?"
            if not warned_missing_alias_meta:
                warned_missing_alias_meta = True
                print(
                    "  Hinweis: meta.query_aliases_version fehlt — Backend neu starten (aktueller server.py).\n",
                    file=sys.stderr,
                )
        print(f"  [{ver}] {query[:56]!r}")
        print(f"       top3: {top3}")
    if any_fail:
        print("\nHinweis: Server unter BASE_URL starten (python3 server.py).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
