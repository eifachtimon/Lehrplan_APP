#!/usr/bin/env python3
"""
Benchmark für POST /search: misst Latenz und identifiziert Engpässe.

  cd backend && python3 benchmark_search.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:5001"

TEST_QUERIES = [
    "bruchrechnen",
    "argumentieren diskutieren",
    "schwimmen zyklus 2",
    "können Texte lesen und verstehen",
    "MI.2.3",
    "Die Schülerinnen und Schüler können einfache Problemstellungen analysieren",
    "gruppenarbeit mathe",
    "nachhaltigkeit umwelt konsum",
    "rhythmus klang musik",
    "geometrie strategie modellieren",
]


def post_search(query: str) -> tuple[float, int, dict]:
    """POST /search, gibt (Dauer in ms, Anzahl Treffer, meta) zurück."""
    url = f"{BASE_URL}/search"
    body = json.dumps({
        "query_texts": query,
        "querySchlagwort": "",
        "filters": {"fach": [], "zyklus": []},
    }).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")

    t0 = time.perf_counter()
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    ids = data.get("ids", [[]])
    count = len(ids[0]) if ids and isinstance(ids[0], list) else 0
    meta = data.get("meta", {})
    return elapsed_ms, count, meta


def main() -> int:
    print(f"Benchmark: {len(TEST_QUERIES)} Queries gegen {BASE_URL}/search\n")

    # Warm-up
    print("Warm-up …")
    for q in TEST_QUERIES[:2]:
        post_search(q)

    results = []
    for q in TEST_QUERIES:
        try:
            ms, n, meta = post_search(q)
            profile = meta.get("query_profile", "?")
            results.append((q, ms, n, profile))
            print(f"  {ms:7.1f} ms | {n:2} Treffer | {profile:18} | {q[:50]}")
        except Exception as e:
            print(f"  FEHLER: {q[:40]} → {e}")
            results.append((q, None, 0, "error"))

    times = [r[1] for r in results if r[1] is not None]
    if not times:
        print("\nKeine erfolgreichen Requests.")
        return 1

    print("\n--- Zusammenfassung ---")
    print(f"Requests:   {len(times)}")
    print(f"Min:        {min(times):.1f} ms")
    print(f"Max:        {max(times):.1f} ms")
    print(f"Median:     {statistics.median(times):.1f} ms")
    print(f"Mean:       {statistics.mean(times):.1f} ms")
    if len(times) >= 2:
        print(f"Stdev:      {statistics.stdev(times):.1f} ms")

    # Zweiter Durchlauf (Cache-Effekte)
    print("\n--- Zweiter Durchlauf (Cache warm) ---")
    times2 = []
    for q in TEST_QUERIES:
        try:
            ms, _, _ = post_search(q)
            times2.append(ms)
        except:
            pass
    if times2:
        print(f"Median:     {statistics.median(times2):.1f} ms")
        print(f"Mean:       {statistics.mean(times2):.1f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
