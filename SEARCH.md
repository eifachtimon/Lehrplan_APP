# Suche (Backend)

Hybrid-Suche über **ChromaDB**: Embedding-Similarity, **Stichwort-/Contains-Suche**, optionale **Semantik-Varianten**, **Kompetenzcode-Erkennung** und gewichtetes **Ranking** (`score_candidates` in `backend/server.py`). Die Antwort enthält pro Treffer u. a. `_score`, `_match_sources`, `_primary_match_channel`, `_result_rank`, `_query_profile`.

## Bewertung / Skripte

| Skript | Zweck |
|--------|--------|
| `backend/eval_search.py` | `eval_queries.json` gegen `POST /search` — Metriken **Top-1 / Top-3** für erwartetes Fach |
| `backend/eval_search_corpus.py` | Stichproben aus `backend/Lehrplan21.json` — **Recall@k**, ob die **gleiche Kompetenz-UID** in den ersten *k* Treffern ist |

Beispiele:

```bash
cd backend && python3 eval_search.py
python3 eval_search_corpus.py --samples 150 --top-k 12 --seed 42 --code-samples 50
```

## Corpus-Erkenntnisse (Referenz)

- **Reine Kompetenzcode-Eingabe** liefert sehr hohen Recall (Codes sind eindeutig).
- **Textauszüge** aus Kompetenzen (Standard: erste ~14 Wörter) zeigen **Recall@12** im Bereich **~two-thirds** — viele Formulierungen teilen sich denselben Einleitungstext („können …“); **reines Embedding** bringt Geschwister-Kompetenzen nah beieinander.

## Nächste Ausbaustufen (ohne nur Synonyme zu stapeln)

1. **Themenbereich / Metadaten** — Query oder erkannte Signale stärker mit `themenbereich`, Zyklus, Code-Kontext verknüpfen.
2. **MMR** (Maximal Marginal Relevance) — ähnliche Treffer diversifizieren, zu ähnliche Embeddings abwerten.
3. **Längere / strukturierte Nutzerqueries** — mehr Kontext reduziert Mehrdeutigkeit gegenüber Boilerplate.
4. **Optional KI** — siehe unten.

## Optional: KI für die Suche

KI kann **ergänzen**, ersetzt aber selten zuverlässig den gesamten Index:

| Ansatz | Nutzen | Aufwand / Risiko |
|--------|--------|-------------------|
| **Query-Rewriting / Expansion** | Synonyme, Didaktik-Begriffe, Zyklus/Fach aus Freitext | API-Kosten, Latenz, Qualitätskontrolle |
| **HyDE** (hypothetisches Dokument generieren, dann embedden) | bessere Treffer bei vagen Fragen | Genauigkeit des hypothetischen Texts |
| **Cross-Encoder / LLM-Reranking** auf Top-20 | feine Reihenfolge, „welcher Treffer passt zur Unterrichtssituation“ | Latenz, Kosten, Prompt-Pflege |
| **Klassifikation** | Fach/Zyklus/Thema vorfiltern | Training/Datenhaltung |

Empfehlung: **Retrieval bleibt lokal/regelbasiert + Vektor**; KI optional als **eine Rerank- oder Rewrite-Stufe** mit Timeout und Fallback auf die aktuelle Pipeline.
