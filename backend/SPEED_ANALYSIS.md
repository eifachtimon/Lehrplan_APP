# Speed-Analyse: POST /search

Stand: 2026-05-10

## Aktuelle Performance

| Metrik | Wert |
|--------|------|
| Median | ~460 ms |
| Mean | ~530 ms |
| Min | ~220 ms |
| Max | ~1.000 ms |

## Optimierungen umgesetzt

1. **Collection-Caching** (`_CACHED_COLLECTION`)
   - ChromaDB-Collection wird beim ersten Request geladen und wiederverwendet

2. **Parallele Chroma-Queries** (`parallel_retrieve_all`)
   - ThreadPoolExecutor mit 6 Workern
   - Alle Vector- und Keyword-Queries parallel statt sequentiell

3. **Reduzierte Query-Varianten**
   - `build_query_variants`: 10 → 4
   - `build_semantic_variants`: 8 → 3
   - Keyword-Token-Limit: 8 → 4

## Verbleibende Engpässe

| Komponente | Zeit | Anteil |
|------------|------|--------|
| Retrieval (Chroma) | ~350-500 ms | 70-80% |
| format_response | ~18 ms | 3% |
| Scoring/Rerank/MMR | ~3 ms | <1% |

Die ChromaDB-Queries dominieren weiterhin. Jeder einzelne Chroma-Query dauert ~40-80ms.

## Weitere Optimierungsmöglichkeiten

### A. LRU-Cache für häufige Queries
```python
from functools import lru_cache

@lru_cache(maxsize=256)
def cached_search(query_hash):
    ...
```
Aufwand: mittel | Speedup: ++ für wiederholte Queries

### B. Leichtere Chain-Daten
`_competency_chain` erst bei Bedarf laden (lazy) statt bei jedem Treffer.

Aufwand: mittel | Speedup: ~15ms pro Request

### C. Weniger Queries bei kurzen Anfragen
Bei `lookup_short` nur 1 Variante + 2 Keyword-Queries statt alle.

Aufwand: gering | Speedup: + bei 60% der Queries

### D. Produktions-Server (Gunicorn/uWSGI)
Flask-Debug vs. Gunicorn mit mehreren Workern.

Aufwand: gering | Speedup: + (Parallelität über Requests)

### E. Pre-computed Embeddings
Top-100 Query-Patterns vorberechnen.

Aufwand: hoch | Speedup: +++ für bekannte Queries

## Benchmark-Scripts

```bash
# Einfacher Latenz-Test
python3 benchmark_search.py

# Detailliertes Profiling (per-Komponente)
python3 benchmark_search_profiled.py
```
