#!/usr/bin/env python3
"""
Detailliertes Profiling des /search-Endpoints – misst Komponenten.
Läuft direkt im Backend-Prozess für genaue interne Zeiten.

  cd backend && python3 benchmark_search_profiled.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time

# Import direkt aus server.py
import server

TEST_QUERIES = [
    "bruchrechnen",
    "argumentieren diskutieren",
    "schwimmen zyklus 2",
    "können Texte lesen und verstehen",
    "Die Schülerinnen und Schüler können einfache Problemstellungen analysieren",
]


def profile_search(query: str) -> dict:
    """Misst einzelne Schritte in der Suche."""
    timings = {}
    
    # 1. init_collection
    t0 = time.perf_counter()
    collection = server.init_collection()
    timings["init_collection"] = (time.perf_counter() - t0) * 1000
    
    # 2. Query-Vorbereitung
    t0 = time.perf_counter()
    query_tokens = server.tokenize_query(query)
    fach_signals = server.detect_fach_signals(query)
    intent_signals = server.detect_intent_signals(query)
    query_profile = server.classify_query_profile(query, query_tokens, intent_signals)
    weights = server.get_score_weights(query_profile)
    n_results = server.resolve_n_results(None, query_profile)
    query_variants = server.build_query_variants(query, "")
    semantic_variants = server.build_semantic_variants(query, fach_signals, intent_signals)
    timings["query_prep"] = (time.perf_counter() - t0) * 1000
    
    # 3. Vector & Keyword Retrieval
    t0 = time.perf_counter()
    candidate_map = {}
    vector_limit = max(40, n_results * 4)
    keyword_limit = max(10, n_results * 2)
    chroma_query_count = 0
    
    for variant in query_variants:
        vector_results = server.vector_retrieve(collection, variant, None, limit=vector_limit)
        chroma_query_count += 1
        server.upsert_candidate(
            candidate_map,
            vector_results.get("ids", [[]])[0],
            vector_results.get("documents", [[]])[0],
            vector_results.get("metadatas", [[]])[0],
            vector_results.get("distances", [[]])[0],
            "vector",
            variant=variant,
            source_weight=1.0,
        )
        # keyword_retrieve_and_upsert macht mehrere queries
        vtokens = server.tokenize_query(variant)
        chroma_query_count += 1 + min(len(vtokens), 8)
        server.keyword_retrieve_and_upsert(
            collection,
            variant,
            vtokens,
            None,
            per_token_limit=keyword_limit,
            candidate_map=candidate_map,
            variant=variant,
        )
    
    for semantic_variant in semantic_variants:
        server.vector_retrieve(collection, semantic_variant, None, limit=max(25, n_results * 3))
        chroma_query_count += 1
    
    timings["retrieval"] = (time.perf_counter() - t0) * 1000
    timings["chroma_queries"] = chroma_query_count
    timings["candidates"] = len(candidate_map)
    
    # 4. Scoring
    t0 = time.perf_counter()
    combined_query = query
    scored_items = server.score_candidates(
        candidate_map, query_tokens, fach_signals, intent_signals, weights, combined_query=combined_query
    )
    timings["scoring"] = (time.perf_counter() - t0) * 1000
    
    # 5. Second-stage rerank + MMR
    t0 = time.perf_counter()
    scored_items = server.apply_second_stage_rerank(scored_items, combined_query)
    top_items = server.mmr_diversify(scored_items, n_results)
    timings["rerank_mmr"] = (time.perf_counter() - t0) * 1000
    
    # 6. format_response (inkl. lookup_competency_chain pro Treffer)
    t0 = time.perf_counter()
    response = server.format_response(top_items, query_profile)
    timings["format_response"] = (time.perf_counter() - t0) * 1000
    timings["result_count"] = len(response.get("ids", [[]])[0])
    
    return timings


def main() -> int:
    print("Detailliertes Profiling des /search Backends\n")
    print("=" * 80)
    
    # Warm-up
    print("Warm-up (einmaliger Chroma-Zugriff) ...")
    server.init_collection()
    server._load_lehrplan_rows()
    server._load_chain_headings_store()
    
    all_timings = []
    
    for q in TEST_QUERIES:
        print(f"\n>>> Query: {q[:60]}")
        t = profile_search(q)
        all_timings.append(t)
        
        print(f"  init_collection:   {t['init_collection']:7.1f} ms")
        print(f"  query_prep:        {t['query_prep']:7.1f} ms")
        print(f"  retrieval:         {t['retrieval']:7.1f} ms  ({t['chroma_queries']} Chroma-Queries)")
        print(f"  scoring:           {t['scoring']:7.1f} ms  ({t['candidates']} Kandidaten)")
        print(f"  rerank+MMR:        {t['rerank_mmr']:7.1f} ms")
        print(f"  format_response:   {t['format_response']:7.1f} ms  ({t['result_count']} Treffer)")
        
        total = t["init_collection"] + t["query_prep"] + t["retrieval"] + t["scoring"] + t["rerank_mmr"] + t["format_response"]
        print(f"  ─────────────────────────────")
        print(f"  TOTAL:             {total:7.1f} ms")
    
    print("\n" + "=" * 80)
    print("Zusammenfassung über alle Queries:")
    
    def avg(key):
        return statistics.mean(t[key] for t in all_timings)
    
    print(f"  Ø init_collection:   {avg('init_collection'):7.1f} ms")
    print(f"  Ø query_prep:        {avg('query_prep'):7.1f} ms")
    print(f"  Ø retrieval:         {avg('retrieval'):7.1f} ms")
    print(f"  Ø scoring:           {avg('scoring'):7.1f} ms")
    print(f"  Ø rerank+MMR:        {avg('rerank_mmr'):7.1f} ms")
    print(f"  Ø format_response:   {avg('format_response'):7.1f} ms")
    
    total_avg = sum(avg(k) for k in ["init_collection", "query_prep", "retrieval", "scoring", "rerank_mmr", "format_response"])
    print(f"  ─────────────────────────────────")
    print(f"  Ø TOTAL:             {total_avg:7.1f} ms")
    
    # Chroma-Query-Analyse
    avg_chroma = statistics.mean(t["chroma_queries"] for t in all_timings)
    print(f"\n  Ø Chroma-Queries/Suche: {avg_chroma:.1f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
