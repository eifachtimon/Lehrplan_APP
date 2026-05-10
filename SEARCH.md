# Suche (Backend)

Hybrid-Suche über **ChromaDB**: Embedding-Similarity, **Stichwort-/Contains-Suche**, optionale **Semantik-Varianten**, **Kompetenzcode-Erkennung** und gewichtetes **Ranking** (`score_candidates` in `backend/server.py`). Die Antwort enthält pro Treffer u. a. `_score`, `_match_sources`, `_primary_match_channel`, `_result_rank`, `_query_profile`.

### Ranking-Pipeline (nicht „reines Embedding“)

1. **Erste Stufe (`score_candidates`)** — Vektor-, Keyword-, Varianten- und RRF-Anteile; Metadaten (Fach, Intent, Kompetenzcode); **Themenbereich-Overlap** (Query-Tokens vs. `themenbereich`); **Phrase-Bonus**, wenn die normalisierte Nutzerzeile (oder ein langer Präfix) im Kompetenztext vorkommt.
2. **Zweite Stufe (`apply_second_stage_rerank`)** — Für die obersten Treffer zusätzlicher Score aus **lexikalischem Token-Overlap** Query↔Dokument, dann globales Neu-Sortieren.
3. **Auswahl (`mmr_diversify`)** — **MMR** auf einem Pool der besten Kandidaten: Balance aus Relevanz (`final_score`) und **Diversität** (Jaccard auf Dokument-Wortmengen), um sehr ähnliche Kompetenz-Doppelungen zu vermeiden.  
   Bei **reiner Kompetenzcode-Suche** (`exact_competency_code`): keine MMR-/Zweitstufe, nur gefilterte Liste nach Score.

## Aufbau-Kette: Titelzeile (`chain_heading`)

Die **Kompetenz-Langform** für die Chain-View stammt aus der lokalen Datei **`backend/chain_headings.json`** (kein Netzwerk bei `POST /search` / `lookup_competency_chain`).  
Neu erzeugen oder fehlende UIDs nachladen (nach Update von `Lehrplan21.json`):

```bash
cd backend && python3 build_chain_headings.py --resume
```

Optional: `CHAIN_HEADINGS_JSON=/pfad/zur.json`, **`CHAIN_HEADING_HTTP_FALLBACK=1`** lädt fehlende Einträge einmalig von BS-Lehrplan nach (langsam), **`DISABLE_BS_CHAIN_HEADING=1`** schaltet die Titelzeile ab.

## Bewertung / Skripte

| Skript | Zweck |
|--------|--------|
| `backend/eval_search.py` | `eval_queries.json` gegen `POST /search` — Metriken **Top-1 / Top-3** für erwartetes Fach |
| `backend/eval_search_corpus.py` | Stichproben aus `backend/Lehrplan21.json` — **Recall@k**, ob die **gleiche Kompetenz-UID** in den ersten *k* Treffern ist |
| `backend/build_chain_headings.py` | Erzeugt **`chain_headings.json`** aus öffentlichen BS-Lehrplan-HTML-Seiten (Batch; Zwischenstände alle 100 UIDs) |

Beispiele:

```bash
cd backend && python3 eval_search.py
python3 eval_search_corpus.py --samples 150 --top-k 12 --seed 42 --code-samples 50
```

## Corpus-Erkenntnisse (Referenz)

- **Reine Kompetenzcode-Eingabe** liefert sehr hohen Recall (Codes sind eindeutig).
- **Textauszüge** aus Kompetenzen (Standard: erste ~14 Wörter) zeigen **Recall@12** im Bereich **~two-thirds** — viele Formulierungen teilen sich denselben Einleitungstext („können …“); **reines Embedding** bringt Geschwister-Kompetenzen nah beieinander.

## Nächste Ausbaustufen

1. **Cross-Encoder / kleines Reranking-Modell** auf Top‑20 (feinere Übereinstimmung als Token-Jaccard).
2. **Längere / strukturierte Nutzerqueries** — weiterhin der grösste Hebel gegen Boilerplate („können …“).
3. **Optional KI** — siehe unten.

## Optional: KI für die Suche

KI kann **ergänzen**, ersetzt aber selten zuverlässig den gesamten Index:

| Ansatz | Nutzen | Aufwand / Risiko |
|--------|--------|-------------------|
| **Query-Rewriting / Expansion** | Synonyme, Didaktik-Begriffe, Zyklus/Fach aus Freitext | API-Kosten, Latenz, Qualitätskontrolle |
| **HyDE** (hypothetisches Dokument generieren, dann embedden) | bessere Treffer bei vagen Fragen | Genauigkeit des hypothetischen Texts |
| **Cross-Encoder / LLM-Reranking** auf Top-20 | feine Reihenfolge, „welcher Treffer passt zur Unterrichtssituation“ | Latenz, Kosten, Prompt-Pflege |
| **Klassifikation** | Fach/Zyklus/Thema vorfiltern | Training/Datenhaltung |

Empfehlung: **Retrieval bleibt lokal/regelbasiert + Vektor**; KI optional als **eine Rerank- oder Rewrite-Stufe** mit Timeout und Fallback auf die aktuelle Pipeline.
